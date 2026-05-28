"""Tests for the download engine.

Uses unittest.mock to avoid real subprocess calls to yt-dlp and ytb API.
"""
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ytb_downloader.engine import DownloadEngine, download_single, _sanitize, _extract_video_id


# ---------------------------------------------------------------------------
# Unit: _sanitize
# ---------------------------------------------------------------------------

class TestSanitize:
    def test_basic(self):
        assert _sanitize("Hello World") == "hello_world"

    def test_whitespace(self):
        assert _sanitize("  Test  Name  ") == "test_name"

    def test_special_chars(self):
        assert _sanitize("Special@#$Chars") == "specialchars"

    def test_empty(self):
        assert _sanitize("") == ""


# ---------------------------------------------------------------------------
# Unit: _extract_video_id
# ---------------------------------------------------------------------------

class TestExtractVideoId:
    def test_standard_format(self):
        assert _extract_video_id("0001_aaaaaaaaaaa.mp4") == "aaaaaaaaaaa"

    def test_no_underscore(self):
        assert _extract_video_id("aaaaaaaaaaa.mp4") == "aaaaaaaaaaa"

    def test_no_extension(self):
        assert _extract_video_id("0001_aaaaaaaaaaa") == "aaaaaaaaaaa"

    def test_extra_underscores(self):
        assert _extract_video_id("0001_aaa_bbb_ccc.mp4") == "aaa_bbb_ccc"


# ---------------------------------------------------------------------------
# DownloadEngine: _build_base_cmd
# ---------------------------------------------------------------------------

class TestBuildBaseCmd:
    def test_no_proxy(self):
        engine = DownloadEngine({"categories": []})
        cmd = engine._build_base_cmd()
        assert cmd == ["yt-dlp", "--cookies", "cookies.txt"]

    def test_with_proxy(self):
        engine = DownloadEngine({"categories": [], "proxy": "http://proxy:7890"})
        cmd = engine._build_base_cmd()
        assert "--proxy" in cmd
        assert "http://proxy:7890" in cmd

    def test_custom_cookies(self):
        engine = DownloadEngine({"categories": [], "cookies": "/custom/path/cookies.txt"})
        cmd = engine._build_base_cmd()
        assert "/custom/path/cookies.txt" in cmd


# ---------------------------------------------------------------------------
# DownloadEngine: _scan_existing
# ---------------------------------------------------------------------------

class TestScanExisting:
    def test_empty_dir(self, tmp_path):
        engine = DownloadEngine({"categories": []})
        ids, count = engine._scan_existing(tmp_path)
        assert count == 0
        assert ids == set()

    def test_with_mp4_files(self, tmp_path):
        (tmp_path / "0001_aaaaaaaaaaa.mp4").write_text("fake")
        (tmp_path / "0002_bbbbbbbbbbb.mp4").write_text("fake")
        engine = DownloadEngine({"categories": []})
        ids, count = engine._scan_existing(tmp_path)
        assert count == 2
        assert "aaaaaaaaaaa" in ids

    def test_with_json_tracker(self, tmp_path):
        (tmp_path / "_downloaded.json").write_text(
            json.dumps({"ids": ["abc123defgh", "ijk456lmnop"]})
        )
        engine = DownloadEngine({"categories": []})
        ids, count = engine._scan_existing(tmp_path)
        assert count == 2

    def test_dedup(self, tmp_path):
        (tmp_path / "0001_aaaaaaaaaaa.mp4").write_text("fake")
        (tmp_path / "_downloaded.json").write_text(
            json.dumps({"ids": ["aaaaaaaaaaa", "bbbbbbbbbbb"]})
        )
        engine = DownloadEngine({"categories": []})
        ids, count = engine._scan_existing(tmp_path)
        assert count == 2
        assert len(ids) == 2

    def test_short_video_id_ignored(self, tmp_path):
        """Video IDs that are not 11 chars should not be counted."""
        (tmp_path / "0001_short.mp4").write_text("fake")
        engine = DownloadEngine({"categories": []})
        ids, count = engine._scan_existing(tmp_path)
        assert count == 0


# ---------------------------------------------------------------------------
# DownloadEngine: _search_videos (mocked)
# ---------------------------------------------------------------------------

class TestSearchVideos:
    def _make_result(self, returncode: float = 0, stdout: str = "", stderr: str = ""):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode,
            stdout=stdout, stderr=stderr,
        )

    @patch("ytb_downloader.engine.subprocess.run")
    def test_search_success(self, mock_run):
        mock_run.return_value = self._make_result(stdout=json.dumps({
            "id": "aaaaaaaaaaa", "title": "Test Video",
            "duration": 120, "webpage_url": "https://youtube.com/watch?v=aaaaaaaaaaa",
        }))
        engine = DownloadEngine({"categories": [], "max_duration": 600})
        results = engine._search_videos("test query")
        assert len(results) == 1
        assert results[0]["id"] == "aaaaaaaaaaa"
        assert results[0]["title"] == "Test Video"

    @patch("ytb_downloader.engine.subprocess.run")
    def test_search_duration_filter(self, mock_run):
        mock_run.return_value = self._make_result(stdout=json.dumps({
            "id": "bbbbbbbbbbb", "title": "Long Video", "duration": 900,
        }))
        engine = DownloadEngine({"categories": [], "max_duration": 600})
        results = engine._search_videos("long video")
        # Duration exceeds max_duration, should be filtered out
        assert len(results) == 0

    @patch("ytb_downloader.engine.subprocess.run")
    def test_search_duration_zero_disables_filter(self, mock_run):
        mock_run.return_value = self._make_result(stdout=json.dumps({
            "id": "ccccccccccc", "title": "Long Video", "duration": 900,
        }))
        engine = DownloadEngine({"categories": [], "max_duration": 0})
        results = engine._search_videos("long video")
        assert len(results) == 1

    @patch("ytb_downloader.engine.subprocess.run")
    def test_search_retry_on_failure(self, mock_run):
        mock_run.side_effect = [
            self._make_result(returncode=1, stderr="Server error"),
            self._make_result(returncode=1, stderr="Server error"),
            self._make_result(stdout=json.dumps({
                "id": "ddddddddddd", "title": "Retry Video", "duration": 60,
            })),
        ]
        engine = DownloadEngine({"categories": [], "search_retries": 3})
        results = engine._search_videos("retry query")
        assert len(results) == 1
        assert mock_run.call_count == 3

    @patch("ytb_downloader.engine.subprocess.run")
    def test_search_all_retries_exhausted(self, mock_run):
        mock_run.return_value = self._make_result(returncode=1, stderr="Server error")
        engine = DownloadEngine({"categories": [], "search_retries": 3})
        results = engine._search_videos("fail query")
        assert results == []
        assert mock_run.call_count == 3

    @patch("ytb_downloader.engine.subprocess.run")
    def test_search_multiple_results(self, mock_run):
        lines = "\n".join([
            json.dumps({"id": v, "title": f"Video {v}", "duration": 60})
            for v in ["v1id1111111", "v2id2222222", "v3id3333333"]
        ])
        mock_run.return_value = self._make_result(stdout=lines)
        engine = DownloadEngine({"categories": [], "max_duration": 600})
        results = engine._search_videos("multi query")
        assert len(results) == 3

    @patch("ytb_downloader.engine.subprocess.run")
    def test_search_timeout_returns_empty(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=60)
        engine = DownloadEngine({"categories": []})
        results = engine._search_videos("timeout query")
        assert results == []


# ---------------------------------------------------------------------------
# DownloadEngine: _download_video (mocked)
# ---------------------------------------------------------------------------

class TestDownloadVideo:
    def _make_result(self, returncode: float = 0, stderr: str = ""):
        return subprocess.CompletedProcess(
            args=[], returncode=returncode, stdout="", stderr=stderr,
        )

    VIDEO = {"id": "testvid12345", "url": "https://youtube.com/watch?v=testvid12345"}

    @patch("ytb_downloader.engine.subprocess.run")
    def test_download_success(self, mock_run):
        mock_run.return_value = self._make_result(returncode=0)
        engine = DownloadEngine({"categories": []})
        result = engine._download_video(Path("/tmp"), self.VIDEO, 1)
        assert result is True

    @patch("ytb_downloader.engine.subprocess.run")
    def test_download_already_exists(self, mock_run, tmp_path):
        (tmp_path / "0001_testvid12345.mp4").write_text("fake")
        engine = DownloadEngine({"categories": []})
        result = engine._download_video(tmp_path, self.VIDEO, 1)
        assert result is True
        mock_run.assert_not_called()

    @patch("ytb_downloader.engine.subprocess.run")
    def test_download_retry_then_success(self, mock_run):
        mock_run.side_effect = [
            self._make_result(returncode=1, stderr="Network error"),
            self._make_result(returncode=0),
        ]
        engine = DownloadEngine({"categories": [], "download_retries": 3})
        result = engine._download_video(Path("/tmp"), self.VIDEO, 1)
        assert result is True
        assert mock_run.call_count == 2

    @patch("ytb_downloader.engine.subprocess.run")
    def test_download_all_retries_fail(self, mock_run):
        mock_run.return_value = self._make_result(returncode=1, stderr="Error")
        engine = DownloadEngine({"categories": [], "download_retries": 3})
        result = engine._download_video(Path("/tmp"), self.VIDEO, 1)
        assert result is False
        assert mock_run.call_count == 3

    @patch("ytb_downloader.engine.subprocess.run")
    def test_download_private_video(self, mock_run):
        mock_run.return_value = self._make_result(
            returncode=1, stderr="Private video"
        )
        engine = DownloadEngine({"categories": [], "download_retries": 3})
        result = engine._download_video(Path("/tmp"), self.VIDEO, 1)
        assert result is False
        assert mock_run.call_count == 1  # no retry for private videos

    @patch("ytb_downloader.engine.subprocess.run")
    def test_download_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=600)
        engine = DownloadEngine({"categories": [], "download_retries": 2})
        result = engine._download_video(Path("/tmp"), self.VIDEO, 1)
        assert result is False

    @patch("ytb_downloader.engine.subprocess.run")
    def test_download_uses_proxy(self, mock_run):
        mock_run.return_value = self._make_result(returncode=0)
        engine = DownloadEngine({"categories": [], "proxy": "http://proxy:7890"})
        engine._download_video(Path("/tmp"), self.VIDEO, 1)
        cmd = mock_run.call_args[0][0]
        assert "--proxy" in cmd
        assert "http://proxy:7890" in cmd


# ---------------------------------------------------------------------------
# download_single (standalone function)
# ---------------------------------------------------------------------------

class TestDownloadSingle:
    @patch("ytb_downloader.engine.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="",
        )
        result = download_single("https://youtube.com/watch?v=test123")
        assert result is True

    @patch("ytb_downloader.engine.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="Error",
        )
        result = download_single("https://youtube.com/watch?v=test123")
        assert result is False

    @patch("ytb_downloader.engine.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=[], timeout=600)
        result = download_single("https://youtube.com/watch?v=test123")
        assert result is False

    @patch("ytb_downloader.engine.subprocess.run")
    def test_uses_proxy(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="",
        )
        download_single("https://youtube.com/watch?v=test123", proxy="http://p:7890")
        cmd = mock_run.call_args[0][0]
        assert "--proxy" in cmd
