"""Tests for utility functions in engine.py."""
import os
import tempfile
from pathlib import Path

import pytest

from ytb_downloader.engine import _sanitize, _scan_existing


def test_sanitize():
    assert _sanitize("Hello World") == "hello_world"
    assert _sanitize("  Test  Name  ") == "test_name"
    assert _sanitize("Special@#$Chars") == "specialchars"
    assert _sanitize("UPPER lower") == "upper_lower"
    assert _sanitize("already_snake") == "already_snake"
    assert _sanitize("") == ""


def test_scan_existing_empty(tmp_path):
    """Scanning an empty dir should return empty set and 0 count."""
    ids, count = _scan_existing(tmp_path, "test")
    assert count == 0
    assert len(ids) == 0


def test_scan_existing_with_files(tmp_path):
    """Scanning a dir with mp4 files should find them."""
    (tmp_path / "0001_aaaaaaaaaaa.mp4").write_text("fake")
    (tmp_path / "0002_bbbbbbbbbbb.mp4").write_text("fake")
    ids, count = _scan_existing(tmp_path, "test")
    assert count == 2
    assert "aaaaaaaaaaa" in ids
    assert "bbbbbbbbbbb" in ids


def test_scan_existing_tracked_json(tmp_path):
    """_downloaded.json should be read properly."""
    import json
    (tmp_path / "_downloaded.json").write_text(
        json.dumps({"ids": ["abc123defgh", "ijk456lmnop"]})
    )
    ids, count = _scan_existing(tmp_path, "test")
    assert count == 2
    assert "abc123defgh" in ids
    assert "ijk456lmnop" in ids


def test_scan_existing_dedup(tmp_path):
    """Files that are both on disk and in json should be counted once."""
    import json
    (tmp_path / "0001_aaaaaaaaaaa.mp4").write_text("fake")
    (tmp_path / "_downloaded.json").write_text(
        json.dumps({"ids": ["aaaaaaaaaaa", "bbbbbbbbbbb"]})
    )
    ids, count = _scan_existing(tmp_path, "test")
    # 1 file on disk + 1 file only in json = 2 unique IDs
    assert count == 2
    assert len(ids) == 2
