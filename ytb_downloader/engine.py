"""Core download engine for ytb-downloader.

Orchestrates parallel category downloads with search, download, retry, and state tracking.
"""

import concurrent.futures
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import state as st
from .config import get_search_queries

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
YTDLP_BIN = "yt-dlp"
MAX_SEARCH_ROUNDS = 6
SEARCH_RESULTS_PER_ROUND = 50
SEARCH_SLEEP = 1.0
DOWNLOAD_SLEEP = 1.5
SEARCH_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 600
SEARCH_RETRY_WAIT = 3
DOWNLOAD_RETRY_WAIT = 5
STDERR_TRUNCATE = 200
PROGRESS_INTERVAL = 10


def _sanitize(name: str) -> str:
    """Sanitize a string for use as a folder name."""
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s]+", "_", s)
    return s


def _sanitize_search_query(query: str) -> str:
    """Remove characters that could interfere with yt-dlp search syntax."""
    sanitized = query.strip()
    # ytsearch uses colon as separator, strip to avoid param injection
    sanitized = sanitized.replace(":", " ")
    sanitized = sanitized.replace("\n", " ").replace("\r", " ")
    # YouTube search ignores leading/trailing special chars, just trim them
    sanitized = sanitized.strip("\"'")
    return sanitized


def _extract_video_id(filename: str) -> str:
    """Extract video ID from a filename following {index:04d}_{video_id}.mp4."""
    stem = Path(filename).stem
    vid_part = stem.split("_", 1)[-1] if "_" in stem else stem
    return vid_part.split(".")[0] if "." in vid_part else vid_part


class DownloadEngine:
    """Configurable download engine for batch YouTube video collection.

    Manages search, download, retry, deduplication, and state tracking
    across multiple categories running in parallel.
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self.cookies_path: str = config.get("cookies", "cookies.txt")
        self.output_dir: str = config.get("output_dir", "downloads")
        self.proxy: str = config.get("proxy", "")
        self.max_duration: int = config.get("max_duration", 600)
        self.max_filesize: str = config.get("max_filesize", "300M")
        self.video_format: str = config.get(
            "video_format", "bestvideo[height<=720]+bestaudio/best[height<=720]"
        )
        self.search_retries: int = config.get("search_retries", 3)
        self.download_retries: int = config.get("download_retries", 5)
        self.max_workers: int = config.get("workers", 3)

        self.state: dict | None = None

    # -- Public API -----------------------------------------------------------

    def start(self) -> None:
        """Start the batch download with the configured parameters."""
        categories = self.config.get("categories", [])

        self.state = st.init_state(self.config)
        st.add_log(self.state, f"下载启动: {len(categories)} 个类别, {self.max_workers} 个 worker")

        if not os.path.exists(self.cookies_path):
            st.add_log(self.state, f"[WARN] Cookie 文件不存在: {self.cookies_path}")
            logger.warning("Cookie file not found: %s", self.cookies_path)

        os.makedirs(self.output_dir, exist_ok=True)

        logger.info(
            "ytb-downloader — Batch YouTube Downloader\n"
            "  Categories : %d\n"
            "  Workers    : %d\n"
            "  Proxy      : %s\n"
            "  Output     : %s",
            len(categories),
            self.max_workers,
            self.proxy or "none",
            self.output_dir,
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            fut_map = {pool.submit(self._process_category, cat): cat for cat in categories}
            done, _ = concurrent.futures.wait(fut_map.keys())
            for fut in done:
                cat = fut_map[fut]
                try:
                    fut.result()
                except KeyboardInterrupt:
                    logger.info("Interrupted. Exiting.")
                    sys.exit(1)
                except Exception as e:
                    logger.error("Failed processing '%s': %s", cat["name"], e)
                    st.add_log(self.state, f"[ERROR] {cat['name']}: {e}")

        st.finalize(self.state)
        st.add_log(self.state, "全部类别处理完成")
        logger.info("ALL DONE!")

    # -- Search ---------------------------------------------------------------

    def _build_base_cmd(self) -> list[str]:
        cmd = [YTDLP_BIN]
        if self.proxy:
            cmd.extend(["--proxy", self.proxy])
        cmd.extend(["--cookies", self.cookies_path])
        return cmd

    def _search_videos(self, query: str, max_results: int = 50) -> list[dict]:
        """Search YouTube and return list of video metadata."""
        query = _sanitize_search_query(query)
        search_query = f"ytsearch{max_results}:{query}"
        cmd = [
            *self._build_base_cmd(),
            "--flat-playlist",
            "--dump-json",
            "--no-warnings",
            "--retries",
            "10",
            search_query,
        ]
        for attempt in range(self.search_retries):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=SEARCH_TIMEOUT)
                videos = []
                if result.returncode != 0 and not result.stdout.strip():
                    raise ConnectionError(result.stderr.strip()[:STDERR_TRUNCATE])
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        vid_id = data.get("id", "")
                        duration = data.get("duration", 0) or 0
                        title = data.get("title", "")
                        if self.max_duration > 0 and duration > self.max_duration:
                            continue
                        videos.append(
                            {
                                "id": vid_id,
                                "title": title,
                                "url": f"https://www.youtube.com/watch?v={vid_id}",
                                "duration": duration,
                            }
                        )
                    except json.JSONDecodeError:
                        continue
                return videos
            except subprocess.TimeoutExpired:
                logger.warning("Search timed out for: %s", query)
                return []
            except Exception as e:
                msg = str(e)[:100]
                if attempt < self.search_retries - 1:
                    logger.info("[RETRY search] %s: %s", query, msg)
                    time.sleep(SEARCH_RETRY_WAIT)
                    continue
                logger.warning("Search failed: '%s': %s", query, msg)
                return []
        return []

    # -- Download -------------------------------------------------------------

    def _download_video(self, category_dir: Path, video: dict, index: int) -> bool:
        """Download a single video. Returns True on success."""
        filename = f"{index:04d}_{video['id']}.mp4"
        filepath = category_dir / filename
        if filepath.exists():
            return True
        cmd = [
            *self._build_base_cmd(),
            "-f",
            self.video_format,
            "--output",
            str(filepath),
            "--max-filesize",
            self.max_filesize,
            "--merge-output-format",
            "mp4",
            "--retries",
            "10",
            "--fragment-retries",
            "10",
            "--no-playlist",
            video["url"],
        ]
        for attempt in range(self.download_retries):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT
                )
                if result.returncode == 0:
                    return True
                err = result.stderr.strip()[:STDERR_TRUNCATE]
                if "Private video" in err or "Video unavailable" in err:
                    return False
                if attempt < self.download_retries - 1:
                    logger.info("[RETRY %d] %s: %s", attempt + 1, video["id"], err)
                    time.sleep(DOWNLOAD_RETRY_WAIT)
                    continue
                logger.info("[FAIL] %s: %s", video["id"], err)
                return False
            except subprocess.TimeoutExpired:
                if attempt < self.download_retries - 1:
                    logger.info("[RETRY %d] %s: timeout", attempt + 1, video["id"])
                    time.sleep(DOWNLOAD_RETRY_WAIT)
                    continue
                logger.info("[TIMEOUT] %s", video["id"])
                return False
            except Exception as e:
                if attempt < self.download_retries - 1:
                    logger.info("[RETRY %d] %s: %s", attempt + 1, video["id"], e)
                    time.sleep(DOWNLOAD_RETRY_WAIT)
                    continue
                logger.info("[ERROR] %s: %s", video["id"], e)
                return False
        return False

    # -- Category processing --------------------------------------------------

    def _scan_existing(self, category_dir: Path) -> tuple[set[str], int]:
        """Scan for existing mp4 files and return (downloaded_ids, count)."""
        ids: set[str] = set()
        track_file = category_dir / "_downloaded.json"
        if track_file.exists():
            try:
                data = json.loads(track_file.read_text())
                ids.update(data.get("ids", []))
            except Exception:
                pass
        for f in category_dir.glob("*.mp4"):
            vid_id = _extract_video_id(f.name)
            if vid_id and len(vid_id) == 11:
                ids.add(vid_id)
        return ids, len(ids)

    def _save_downloaded(self, category_dir: Path, ids: set[str]) -> None:
        """Save downloaded IDs to tracking file."""
        track_file = category_dir / "_downloaded.json"
        track_file.write_text(json.dumps({"ids": sorted(ids)}, ensure_ascii=False))

    def _process_category(self, cat: dict) -> None:
        """Process a single category: search + download."""
        name = cat["name"]
        target = cat.get("target", 40)
        folder_name = _sanitize(name)
        category_dir = Path(self.output_dir) / folder_name
        category_dir.mkdir(exist_ok=True)

        downloaded_ids, current_count = self._scan_existing(category_dir)

        st.set_category_state(self.state, name, status="running", downloaded=current_count)
        st.set_overall(self.state, current_category=name)
        st.set_current(
            self.state, category=name, status="scanning", message=f"已有 {current_count} 个视频"
        )
        st.add_log(self.state, f"[{name}] 开始处理 ({current_count}/{target})")

        logger.info("")
        logger.info("=" * 60)
        logger.info("[%s] → %s/  (target: %d)", name, folder_name, target)
        logger.info("  Already on disk: %d", current_count)
        logger.info("=" * 60)

        if current_count >= target:
            logger.info("  [OK] Already meets target, skipping.")
            st.set_category_state(self.state, name, status="completed", downloaded=current_count)
            st.set_current(
                self.state,
                category=name,
                status="completed",
                message=f"已有 {current_count} 个视频",
            )
            st.add_log(self.state, f"[{name}] 已有 {current_count} 个视频，跳过")
            return

        queries = get_search_queries(cat)
        all_new_videos: list[dict] = []
        seen_ids = set(downloaded_ids)

        round_num = 0
        while len(all_new_videos) + current_count < target and round_num < MAX_SEARCH_ROUNDS:
            round_num += 1
            found_this_round = 0
            for query in queries:
                needed = target - len(all_new_videos) - current_count
                if needed <= 0:
                    break
                search_count = min(SEARCH_RESULTS_PER_ROUND, needed * 3)
                logger.info('  [Round %d] Searching: "%s" (need %d)...', round_num, query, needed)

                st.set_current(
                    self.state, category=name, status="searching", message=f"搜索: {query[:40]}"
                )

                results = self._search_videos(query, max_results=search_count)
                new_count = 0
                for v in results:
                    if v["id"] not in seen_ids and v["id"]:
                        seen_ids.add(v["id"])
                        all_new_videos.append(v)
                        new_count += 1
                        found_this_round += 1
                logger.info("    Found %d new videos", new_count)
                time.sleep(SEARCH_SLEEP)

            if found_this_round == 0:
                logger.info("  [INFO] No new videos in round %d, stopping.", round_num)
                break

            logger.info(
                "  [Round %d] Total: %d/%d", round_num, current_count + len(all_new_videos), target
            )

        all_new_videos = all_new_videos[: target - current_count]

        if not all_new_videos:
            logger.info("  No new videos found.")
            return

        logger.info("  To download: %d", len(all_new_videos))

        successful = 0
        failed = 0
        base_index = current_count

        for i, video in enumerate(all_new_videos):
            idx = base_index + i + 1
            title_short = video["title"][:50]
            logger.info("  [%d/%d] Downloading %s - %s...", idx, target, video["id"], title_short)

            st.set_current(
                self.state,
                category=name,
                video_id=video["id"],
                title=title_short,
                status="downloading",
                message=f"{idx}/{target}",
            )

            ok = self._download_video(category_dir, video, idx)
            if ok:
                downloaded_ids.add(video["id"])
                self._save_downloaded(category_dir, downloaded_ids)
                successful += 1
            else:
                failed += 1

            st.set_category_state(
                self.state, name, downloaded=current_count + successful, failed=failed
            )

            if (i + 1) % PROGRESS_INTERVAL == 0:
                total = current_count + successful
                logger.info("  --- Progress: %d/%d ---", total, target)
                self._save_downloaded(category_dir, downloaded_ids)

            time.sleep(DOWNLOAD_SLEEP)

        total = current_count + successful
        logger.info("  [OK] Done: %d/%d (failed: %d)", total, target, failed)
        status = "completed" if total >= target else "partial"
        st.set_category_state(self.state, name, downloaded=total, failed=failed, status=status)
        st.set_current(self.state, category=name, status="completed", message=f"{total}/{target}")
        st.add_log(self.state, f"[{name}] 完成 ({total}/{target}, fail={failed})")


# ---------------------------------------------------------------------------
# Standalone single-video download (for `dl` command)
# ---------------------------------------------------------------------------


def download_single(
    url: str,
    output_dir: str = "downloads",
    proxy: str = "",
    cookies: str = "cookies.txt",
    video_format: str = "bestvideo[height<=720]+bestaudio/best[height<=720]",
    max_filesize: str = "300M",
) -> bool:
    """Download a single video by URL. Returns True on success."""
    cmd = [YTDLP_BIN]
    if proxy:
        cmd.extend(["--proxy", proxy])
    cmd.extend(
        [
            "--cookies",
            cookies,
            "-f",
            video_format,
            "--max-filesize",
            max_filesize,
            "--merge-output-format",
            "mp4",
            "--retries",
            "10",
            "--fragment-retries",
            "10",
            "--no-playlist",
            "-o",
            os.path.join(output_dir, "%(title).50s_%(id)s.%(ext)s"),
            url,
        ]
    )
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT)
        if result.returncode == 0:
            logger.info("Downloaded: %s", url)
            return True
        logger.warning("Download failed: %s - %s", url, result.stderr.strip()[:STDERR_TRUNCATE])
        return False
    except subprocess.TimeoutExpired:
        logger.warning("Download timed out: %s", url)
        return False
    except Exception as e:
        logger.error("Download error for %s: %s", url, e)
        return False


# ---------------------------------------------------------------------------
# Legacy wrapper (keeps backward compat with existing code)
# ---------------------------------------------------------------------------


def start(config: dict) -> None:
    """Legacy wrapper — creates an engine and starts it."""
    engine = DownloadEngine(config)
    engine.start()
