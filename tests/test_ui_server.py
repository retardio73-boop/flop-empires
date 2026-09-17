import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from flop_empires.store import Store
from flop_empires import ui_server


def test_public_ui_state_endpoint_serves_fog_safe_projection(tmp_path, monkeypatch):
    db = tmp_path / "ui-http.db"
    store = Store(db)
    store.conn.execute("INSERT INTO config(key,value) VALUES('season_status','FROZEN_NOT_ACTIVE')")
    store.close()
    monkeypatch.setattr(ui_server, "DEFAULT_DB", db)

    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/api/state"
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.load(response)
            assert response.status == 200
        assert payload["evidence"]["projection_schema"] == "flop-empires-public-state-v1"
        assert payload["capabilities"]["fog_safe_public_projection"] is True
        assert len(payload["world"]["territories"]) == 64
    finally:
        server.shutdown()
        server.server_close()
