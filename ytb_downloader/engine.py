"""Core download engine for ytb-downloader.

Orchestrates parallel category downloads with search, download, retry, and state tracking.
"""
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import state as st
from .config import get_search_queries

# ---------------------------------------------------------------------------
# Globals (set by start())
# ---------------------------------------------------------------------------
_config: dict = {}
_state: dict | None = None
_cookies_path: str = ""
_output_dir: str = ""
_proxy: str = ""
_max_duration: int = 600
_max_filesize: str = "300M"
_video_format: str = "bestvideo[height<=720]+bestaudio/best[height<=720]"
_search_retries: int = 3
_download_retries: int = 5
_max_workers: int = 3

_YTDLP_BIN = "yt-dlp"
_JS_RUNTIME = "node:C:\\nvm4w\\nodejs\\node.exe"


def start(config: dict) -> None:
    """Start the batch download with the given config."""
    global _config, _state, _cookies_path, _output_dir, _proxy
    global _max_duration, _max_filesize, _video_format
    global _search_retries, _download_retries, _max_workers

    _config = config
    _cookies_path = config.get("cookies", "cookies.txt")
    _output_dir = config.get("output_dir", "downloads")
    _proxy = config.get("proxy", "")
    _max_duration = config.get("max_duration", 600)
    _max_filesize = config.get("max_filesize", "300M")
    _video_format = config.get(
        "video_format", "bestvideo[height<=720]+bestaudio/best[height<=720]"
    )
    _search_retries = config.get("search_retries", 3)
    _download_retries = config.get("download_retries", 5)
    _max_workers = config.get("workers", 3)

    categories = config.get("categories", [])

    # Init state
    _state = st.init_state(config)
    st.add_log(_state, f"下载启动: {len(categories)} 个类别, {_max_workers} 个 worker")

    # Check cookies
    if not os.path.exists(_cookies_path):
        st.add_log(_state, f"[WARN] Cookie 文件不存在: {_cookies_path}")
        print(f"[WARN] Cookie file not found: {_cookies_path}")

    # Create output dir
    os.makedirs(_output_dir, exist_ok=True)

    print(f"\nytb-downloader — Batch YouTube Downloader")
    print(f"  Categories : {len(categories)}")
    print(f"  Workers    : {_max_workers}")
    print(f"  Proxy      : {_proxy or 'none'}")
    print(f"  Output     : {_output_dir}")
    print()

    with concurrent.futures.ThreadPoolExecutor(max_workers=_max_workers) as pool:
        fut_map = {
            pool.submit(_process_category, cat): cat
            for cat in categories
        }
        done, _ = concurrent.futures.wait(fut_map.keys())
        for fut in done:
            cat = fut_map[fut]
            try:
                fut.result()
            except KeyboardInterrupt:
                print("\nInterrupted. Exiting.")
                sys.exit(1)
            except Exception as e:
                print(f"[ERROR] Failed processing '{cat['name']}': {e}")
                st.add_log(_state, f"[ERROR] {cat['name']}: {e}")

    st.finalize(_state)
    st.add_log(_state, "全部类别处理完成")
    print("\nALL DONE!")


def _sanitize(name: str) -> str:
    """Sanitize a string for use as a folder name."""
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s]+", "_", s)
    return s


def _scan_existing(category_dir: Path, cat_name: str) -> tuple[set[str], int]:
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
        vid_part = f.stem.split("_", 1)[-1] if "_" in f.stem else f.stem
        vid_id = vid_part.split(".")[0]
        if vid_id and len(vid_id) == 11:
            ids.add(vid_id)
    return ids, len(ids)


def _save_downloaded(category_dir: Path, ids: set[str]) -> None:
    """Save downloaded IDs to tracking file."""
    track_file = category_dir / "_downloaded.json"
    track_file.write_text(
        json.dumps({"ids": sorted(ids)}, ensure_ascii=False)
    )


def _search_videos(query: str, max_results: int = 50) -> list[dict]:
    """Search YouTube and return list of video metadata."""
    search_query = f"ytsearch{max_results}:{query}"
    cmd = [
        _YTDLP_BIN,
        *(["--proxy", _proxy] if _proxy else []),
        "--cookies", _cookies_path,
        "--js-runtimes", _JS_RUNTIME,
        "--flat-playlist", "--dump-json", "--no-warnings",
        "--retries", "10",
        search_query,
    ]
    for attempt in range(_search_retries):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )
            videos = []
            if result.returncode != 0 and not result.stdout.strip():
                raise ConnectionError(result.stderr.strip()[:200])
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    vid_id = data.get("id", "")
                    duration = data.get("duration", 0) or 0
                    title = data.get("title", "")
                    if _max_duration > 0 and duration > _max_duration:
                        continue
                    videos.append({
                        "id": vid_id,
                        "title": title,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "duration": duration,
                    })
                except json.JSONDecodeError:
                    continue
            return videos
        except subprocess.TimeoutExpired:
            print(f"  [WARN] Search timed out for: {query}")
            return []
        except Exception as e:
            msg = str(e)[:100]
            if attempt < _search_retries - 1:
                print(f"    [RETRY search] {query}: {msg}")
                time.sleep(3)
                continue
            print(f"  [WARN] Search failed: '{query}': {msg}")
            return []
    return []


def _download_video(category_dir: Path, video: dict, index: int) -> bool:
    """Download a single video. Returns True on success."""
    filename = f"{index:04d}_{video['id']}.mp4"
    filepath = category_dir / filename
    if filepath.exists():
        return True
    cmd = [
        _YTDLP_BIN,
        *(["--proxy", _proxy] if _proxy else []),
        "--cookies", _cookies_path,
        "--js-runtimes", _JS_RUNTIME,
        "-f", _video_format,
        "--output", str(filepath),
        "--max-filesize", _max_filesize,
        "--merge-output-format", "mp4",
        "--retries", "10",
        "--fragment-retries", "10",
        "--no-playlist",
        video["url"],
    ]
    for attempt in range(_download_retries):
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            if result.returncode == 0:
                return True
            err = result.stderr.strip()[:200]
            if "Private video" in err or "Video unavailable" in err:
                return False
            if attempt < _download_retries - 1:
                print(f"    [RETRY {attempt+1}] {video['id']}: {err}")
                time.sleep(5)
                continue
            print(f"    [FAIL] {video['id']}: {err}")
            return False
        except subprocess.TimeoutExpired:
            if attempt < _download_retries - 1:
                print(f"    [RETRY {attempt+1}] {video['id']}: timeout")
                time.sleep(5)
                continue
            print(f"    [TIMEOUT] {video['id']}")
            return False
        except Exception as e:
            if attempt < _download_retries - 1:
                print(f"    [RETRY {attempt+1}] {video['id']}: {e}")
                time.sleep(5)
                continue
            print(f"    [ERROR] {video['id']}: {e}")
            return False
    return False


def _process_category(cat: dict) -> None:
    """Process a single category: search + download."""
    global _state

    name = cat["name"]
    target = cat.get("target", 40)
    folder_name = _sanitize(name)
    category_dir = Path(_output_dir) / folder_name
    category_dir.mkdir(exist_ok=True)

    downloaded_ids, current_count = _scan_existing(category_dir, name)

    # Update state
    if _state is not None:
        st.set_category_state(_state, name, status="running", downloaded=current_count)
        st.set_overall(_state, current_category=name)
        st.set_current(_state, category=name, status="scanning",
                       message=f"已有 {current_count} 个视频")
        st.add_log(_state, f"[{name}] 开始处理 ({current_count}/{target})")

    print(f"\n{'='*60}")
    print(f"[{name}] → {folder_name}/  (target: {target})")
    print(f"  Already on disk: {current_count}")
    print(f"{'='*60}")

    if current_count >= target:
        print(f"  [OK] Already meets target, skipping.")
        if _state is not None:
            st.set_category_state(_state, name, status="completed",
                                  downloaded=current_count)
            st.set_current(_state, category=name, status="completed",
                           message=f"已有 {current_count} 个视频")
            st.add_log(_state, f"[{name}] 已有 {current_count} 个视频，跳过")
        return

    queries = get_search_queries(cat)
    all_new_videos: list[dict] = []
    seen_ids = set(downloaded_ids)

    # Multi-round search
    round_num = 0
    while len(all_new_videos) + current_count < target and round_num < 6:
        round_num += 1
        found_this_round = 0
        for query in queries:
            needed = target - len(all_new_videos) - current_count
            if needed <= 0:
                break
            search_count = min(50, needed * 3)
            print(f"  [Round {round_num}] Searching: \"{query}\" (need {needed})...")

            if _state is not None:
                st.set_current(_state, category=name, status="searching",
                               message=f"搜索: {query[:40]}")

            results = _search_videos(query, max_results=search_count)
            new_count = 0
            for v in results:
                if v["id"] not in seen_ids and v["id"]:
                    seen_ids.add(v["id"])
                    all_new_videos.append(v)
                    new_count += 1
                    found_this_round += 1
            print(f"    Found {new_count} new videos")
            time.sleep(1.0)

        if found_this_round == 0:
            print(f"  [INFO] No new videos in round {round_num}, stopping.")
            break

        print(f"  [Round {round_num}] Total: "
              f"{current_count + len(all_new_videos)}/{target}")

    all_new_videos = all_new_videos[:target - current_count]

    if not all_new_videos:
        print(f"  No new videos found.")
        return

    print(f"  To download: {len(all_new_videos)}")

    successful = 0
    failed = 0
    base_index = current_count

    for i, video in enumerate(all_new_videos):
        idx = base_index + i + 1
        title_short = video["title"][:50]
        print(f"  [{idx}/{target}] Downloading {video['id']} - {title_short}...")

        if _state is not None:
            st.set_current(_state, category=name, video_id=video["id"],
                           title=title_short, status="downloading",
                           message=f"{idx}/{target}")

        ok = _download_video(category_dir, video, idx)
        if ok:
            downloaded_ids.add(video["id"])
            _save_downloaded(category_dir, downloaded_ids)
            successful += 1
        else:
            failed += 1

        if _state is not None:
            st.set_category_state(_state, name,
                                  downloaded=current_count + successful,
                                  failed=failed)

        if (i + 1) % 10 == 0:
            total = current_count + successful
            print(f"  --- Progress: {total}/{target} ---")
            _save_downloaded(category_dir, downloaded_ids)

        time.sleep(1.5)

    total = current_count + successful
    print(f"  [OK] Done: {total}/{target} (failed: {failed})")
    if _state is not None:
        status = "completed" if total >= target else "partial"
        st.set_category_state(_state, name, downloaded=total,
                              failed=failed, status=status)
        st.set_current(_state, category=name, status="completed",
                       message=f"{total}/{target}")
        st.add_log(_state, f"[{name}] 完成 ({total}/{target}, fail={failed})")
