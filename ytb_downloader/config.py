"""Configuration loader for ytb-downloader."""

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"

# Default config if no file is found
DEFAULTS: dict[str, Any] = {
    "proxy": "",
    "cookies": "cookies.txt",
    "workers": 3,
    "output_dir": "downloads",
    "max_duration": 600,
    "max_filesize": "300M",
    "video_format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "search_retries": 3,
    "download_retries": 5,
    "categories": [],
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load config from YAML file, merging with defaults."""
    config = dict(DEFAULTS)

    if path is None:
        path = DEFAULT_CONFIG_PATH

    path = Path(path)
    if not path.exists():
        return config

    if yaml is None:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")

    raw = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw) or {}
    config.update(parsed)

    # Resolve relative paths to absolute
    base = path.parent
    for key in ("cookies", "output_dir"):
        val = config.get(key)
        if val and not os.path.isabs(val):
            config[key] = str((base / val).resolve())

    return config


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate config and return list of error messages (empty = valid)."""
    errors: list[str] = []

    if not config.get("categories"):
        errors.append("配置中没有定义任何类别（categories）")

    for i, cat in enumerate(config.get("categories", [])):
        prefix = f"categories[{i}]"
        if not cat.get("name"):
            errors.append(f"{prefix}: 缺少 name")
        if not cat.get("queries"):
            errors.append(f"{prefix} '{cat.get('name', '?')}': 缺少 queries（搜索关键词）")
        target = cat.get("target", 0)
        if not isinstance(target, int) or target < 1:
            errors.append(f"{prefix} '{cat.get('name', '?')}': target 必须 >= 1")

    workers = config.get("workers", 3)
    if not isinstance(workers, int) or workers < 1:
        errors.append("workers 必须 >= 1")

    return errors


def get_search_queries(category: dict[str, Any]) -> list[str]:
    """Build search query list from a category config."""
    raw_queries = category.get("queries", [])
    if not raw_queries:
        return [category.get("name", "")]
    return list(raw_queries)
