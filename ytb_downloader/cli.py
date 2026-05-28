"""CLI entry point for ytb-downloader.

Usage:
    python -m ytb_downloader start          # Start batch download
    python -m ytb_downloader monitor        # Start web monitor
    python -m ytb_downloader status         # Show current state
    python -m ytb_downloader list           # List categories
    python -m ytb_downloader check          # Validate config
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .config import load_config, validate_config
from .state import load_state


def _setup_stdio() -> None:
    """Configure stdout for UTF-8 on Windows."""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass


class TeeOutput:
    """Duplicate stdout to a log file."""
    def __init__(self, log_path: str):
        self.file = open(log_path, "a", encoding="utf-8")
        self.stdout = sys.stdout

    def write(self, data: str):
        self.stdout.write(data)
        self.file.write(data)
        self.file.flush()

    def flush(self):
        self.stdout.flush()
        self.file.flush()


def cmd_start(args: argparse.Namespace) -> None:
    """Start the batch download."""
    _setup_stdio()

    config = load_config(args.config)

    # Env overrides
    if args.workers:
        config["workers"] = args.workers
    if args.proxy:
        config["proxy"] = args.proxy
    if args.limit:
        for cat in config.get("categories", []):
            cat["target"] = args.limit

    # Validate
    errors = validate_config(config)
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    # Tee output to log
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "download_log.txt")
    log_path = os.path.abspath(log_path)
    sys.stdout = TeeOutput(log_path)

    from .engine import start as engine_start
    engine_start(config)


def cmd_monitor(args: argparse.Namespace) -> None:
    """Start the web monitor."""
    from .monitor import serve
    serve(port=args.port)


def cmd_status(args: argparse.Namespace) -> None:
    """Show current download status."""
    state = load_state()
    if state is None:
        print("No download state found (not started yet or state file deleted).")
        return

    o = state.get("overall", {})
    cats = state.get("categories", {})
    cur = state.get("current", {})
    total_dl = sum(c.get("downloaded", 0) for c in cats.values())
    completed = sum(1 for c in cats.values() if c.get("status") == "completed")
    running = sum(1 for c in cats.values() if c.get("status") == "running")
    failed = sum(c.get("failed", 0) for c in cats.values())

    print(f"ytb-downloader 状态")
    print(f"  Status   : {'Running' if o.get('is_running') else 'Stopped'}")
    print(f"  Progress : {total_dl}/{o.get('total_target', 0)} ({completed}/{len(cats)} categories)")
    print(f"  Failed   : {failed}")
    print(f"  Active   : {running} workers")
    print()
    if cur.get("category"):
        print(f"  Current  : {cur['category']} — {cur.get('status', '?')}")
        if cur.get("message"):
            print(f"             {cur['message']}")
    print()
    for name, cat in sorted(cats.items()):
        pct = (cat["downloaded"] / cat["target"] * 100) if cat["target"] > 0 else 0
        bar = "#" * int(pct / 5) + "." * (20 - int(pct / 5))
        print(f"  {name:30s} [{bar}] {cat['downloaded']:3d}/{cat['target']:<3d}  {cat['status']}")


def cmd_list(args: argparse.Namespace) -> None:
    """List configured categories and their status."""
    config = load_config(args.config)
    state = load_state()

    cats_config = config.get("categories", [])
    print(f"Categories: {len(cats_config)} configured\n")
    print(f"{'Name':30s} {'Target':>6s} {'Disk':>6s} {'Status':>12s}")
    print("-" * 58)
    for cat in cats_config:
        name = cat.get("name", "?")
        target = cat.get("target", 40)
        disk = 0
        status = "configured"
        if state:
            sc = state.get("categories", {}).get(name)
            if sc:
                disk = sc.get("downloaded", 0)
                status = sc.get("status", "configured")
        print(f"{name:30s} {target:>6d} {disk:>6d} {status:>12s}")


def cmd_check(args: argparse.Namespace) -> None:
    """Validate the configuration file."""
    config = load_config(args.config)
    errors = validate_config(config)
    if errors:
        print("Configuration ERRORS:")
        for e in errors:
            print(f"  [FAIL] {e}")
        sys.exit(1)
    else:
        cats = config.get("categories", [])
        total_target = sum(c.get("target", 0) for c in cats)
        print("Configuration OK")
        print(f"  Categories: {len(cats)}")
        print(f"  Total target: ~{total_target} videos")
        print(f"  Workers: {config.get('workers', 3)}")
        print(f"  Proxy: {config.get('proxy', 'none')}")
        print(f"  Output: {config.get('output_dir', 'downloads')}")
        print(f"  Cookies: {config.get('cookies', 'cookies.txt')}")
        # Check cookies
        cookies_path = config.get("cookies", "cookies.txt")
        if os.path.exists(cookies_path):
            print(f"  Cookies file: exists ({os.path.getsize(cookies_path)} bytes)")
        else:
            print(f"  Cookies file: NOT FOUND — YouTube will block downloads")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ytb-downloader",
        description="Configurable YouTube batch video downloader",
    )
    parser.add_argument("--version", action="version", version=__version__)

    sub = parser.add_subparsers(dest="command", required=True)

    # start
    p_start = sub.add_parser("start", help="Start batch download")
    p_start.add_argument("-c", "--config", default=None, help="Config file path")
    p_start.add_argument("-w", "--workers", type=int, default=None, help="Parallel workers")
    p_start.add_argument("-p", "--proxy", default=None, help="Proxy URL")
    p_start.add_argument("-l", "--limit", type=int, default=None, help="Override target per category")

    # monitor
    p_mon = sub.add_parser("monitor", help="Start web monitor")
    p_mon.add_argument("--port", type=int, default=8080, help="Port (default 8080)")

    # status
    sub.add_parser("status", help="Show download status")

    # list
    p_list = sub.add_parser("list", help="List categories")
    p_list.add_argument("-c", "--config", default=None, help="Config file path")

    # check
    p_check = sub.add_parser("check", help="Validate config")
    p_check.add_argument("-c", "--config", default=None, help="Config file path")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    commands = {
        "start": cmd_start,
        "monitor": cmd_monitor,
        "status": cmd_status,
        "list": cmd_list,
        "check": cmd_check,
    }

    fn = commands.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
