from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .ui_projection import build_public_state

ROOT = Path(__file__).resolve().parents[2]
UI_DIR = ROOT / "ui"
DEFAULT_DB = Path(os.environ.get(
    "FLOP_EMPIRES_DB",
    Path(os.environ.get("LOCALAPPDATA", ROOT)) / "FLOPEmpires" / "season0-runtime-v1" / "season0.sqlite3",
))
WORLD = ROOT / "season" / "world-season-0-v1.json"
ACTIVATION = ROOT / "season" / "SEASON-0-ACTIVATION-v1.json"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def do_GET(self):
        if urlparse(self.path).path == "/api/state":
            payload = build_public_state(DEFAULT_DB, WORLD, ACTIVATION)
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def main() -> None:
    host = os.environ.get("FLOP_EMPIRES_UI_HOST", "127.0.0.1")
    port = int(os.environ.get("FLOP_EMPIRES_UI_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"FLOP Empires UI: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
