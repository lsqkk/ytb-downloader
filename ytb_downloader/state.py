"""Shared state for download progress monitoring.

Writes/reads a JSON file that the web monitor reads in real-time.
Write throttling batches disk writes to reduce I/O.
"""

import datetime
import glob
import json
import os
import threading
import time
from pathlib import Path

from .config import _sanitize

STATE_FILE = "download_state.json"
_WRITE_INTERVAL = 2.0  # seconds between disk writes
_MAX_LOG = 200

_lock = threading.Lock()


def init_state(config: dict) -> dict:
    """Initialize state from config, scanning existing files on disk."""
    output_dir = config.get("output_dir", "downloads")
    categories = config.get("categories", [])

    state: dict = {
        "overall": {
            "total_categories": len(categories),
            "completed_categories": 0,
            "total_target": 0,
            "total_downloaded": 0,
            "total_failed": 0,
            "is_running": True,
            "start_time": datetime.datetime.now().isoformat(),
            "current_category": "",
        },
        "categories": {},
        "current": {
            "category": "",
            "video_id": "",
            "title": "",
            "status": "initializing",
            "message": "",
        },
        "config": _summarize_config(config),
        "log": [],
        "_meta": {"last_write": 0.0, "dirty": False},
    }

    total_target = 0
    total_downloaded = 0
    completed_cats = 0

    for cat in categories:
        name = cat["name"]
        target = cat.get("target", 40)
        total_target += target
        folder = os.path.join(output_dir, _sanitize(name))

        existing = len(glob.glob(os.path.join(folder, "*.mp4")))
        status = "pending"
        if existing >= target:
            status = "completed"
            completed_cats += 1
        total_downloaded += existing

        state["categories"][name] = {
            "name": name,
            "target": target,
            "downloaded": existing,
            "status": status,
            "failed": 0,
        }

    state["overall"]["total_target"] = total_target
    state["overall"]["total_downloaded"] = total_downloaded
    state["overall"]["completed_categories"] = completed_cats

    _write(state)
    return state


def _summarize_config(config: dict) -> dict:
    return {
        "workers": config.get("workers", 3),
        "proxy": _mask_proxy(config.get("proxy", "")),
        "max_duration": config.get("max_duration", 600),
        "video_format": config.get("video_format", ""),
    }


def _mask_proxy(proxy: str) -> str:
    if not proxy:
        return "none"
    # Mask password in http://user:pass@host:port format
    if "@" in proxy:
        scheme, _, rest = proxy.partition("://")
        userinfo, _, hostpart = rest.partition("@")
        if ":" in userinfo:
            user = userinfo.split(":", 1)[0]
            return f"{scheme}://{user}:***@{hostpart}"
    return proxy


def load_state() -> dict | None:
    """Load state from file (used by web monitor)."""
    if os.path.exists(STATE_FILE):
        try:
            return json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _write(state: dict) -> None:
    """Atomically write state to JSON file (with throttling)."""
    with _lock:
        meta = state.get("_meta", {})
        now = time.time()
        last_write = meta.get("last_write", 0.0)

        if now - last_write < _WRITE_INTERVAL:
            meta["dirty"] = True
            return

        meta["last_write"] = now
        meta["dirty"] = False

        clean = {k: v for k, v in state.items() if k != "_meta"}
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)


def _flush(state: dict | None) -> None:
    """Force an immediate write, bypassing throttle."""
    if state is None:
        return
    with _lock:
        meta = state.get("_meta", {})
        meta["last_write"] = 0.0
        meta["dirty"] = False
        clean = {k: v for k, v in state.items() if k != "_meta"}
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)


def set_current(state: dict | None, **kwargs) -> None:
    """Update the 'current download' field."""
    if state is None:
        return
    with _lock:
        state["current"] = {
            "category": kwargs.get("category", ""),
            "video_id": kwargs.get("video_id", ""),
            "title": kwargs.get("title", ""),
            "status": kwargs.get("status", ""),
            "message": kwargs.get("message", ""),
        }
    _write(state)


def set_category_state(state: dict | None, name: str, **kwargs) -> None:
    """Update fields for a specific category."""
    if state is None:
        return
    with _lock:
        if name in state.get("categories", {}):
            state["categories"][name].update(kwargs)
    _write(state)


def add_log(state: dict | None, message: str) -> None:
    """Append a log entry."""
    if state is None:
        return
    with _lock:
        state["log"].append(
            {
                "time": datetime.datetime.now().isoformat(),
                "message": message,
            }
        )
        if len(state["log"]) > _MAX_LOG:
            state["log"] = state["log"][-_MAX_LOG:]
    _write(state)


def set_overall(state: dict | None, **kwargs) -> None:
    """Update overall stats."""
    if state is None:
        return
    with _lock:
        state["overall"].update(kwargs)
    _write(state)


def finalize(state: dict | None) -> None:
    """Mark download as complete and flush immediately."""
    if state is None:
        return
    with _lock:
        state["overall"]["is_running"] = False
        state["current"]["status"] = "completed"
        state["current"]["message"] = "全部完成"
    _flush(state)
