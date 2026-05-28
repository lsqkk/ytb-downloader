"""Web-based real-time monitor for ytb-downloader.

Serves a dashboard at http://localhost:PORT that shows download progress
for all categories with progress bars, logs, and stall detection.
"""
import http.server
import json
import os
import sys
from pathlib import Path

PORT = int(os.environ.get("MONITOR_PORT", "8080"))
HOST = os.environ.get("MONITOR_HOST", "0.0.0.0")
STATE_FILE = "download_state.json"

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_HTML_PAGE: str | None = None


def _load_html() -> str:
    global _HTML_PAGE
    if _HTML_PAGE is None:
        template_path = _TEMPLATE_DIR / "monitor.html"
        _HTML_PAGE = template_path.read_text(encoding="utf-8")
    return _HTML_PAGE


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            self._json_response()
        elif path == "/":
            self._html_response()
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            state = json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
            self.wfile.write(json.dumps(state, ensure_ascii=False).encode("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.wfile.write(b'{"error":"state_file_not_found"}')

    def _html_response(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(_load_html().encode("utf-8"))


def serve(port: int | None = None, host: str | None = None) -> None:
    """Start the web monitor server (blocking)."""
    bind_host = host or HOST
    bind_port = port or PORT
    server = http.server.HTTPServer((bind_host, bind_port), Handler)
    url = f"http://localhost:{bind_port}"
    print(f"\n{'='*50}")
    print(f"  ytb-downloader 监控面板")
    print(f"  {url}")
    print(f"{'='*50}")
    print(f"  Ctrl+C 退出\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down monitor...")
        server.shutdown()
