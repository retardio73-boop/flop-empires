import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from flop_empires.store import Store
from flop_empires.identity import EphemeralSigner
from flop_empires.canonical import dumps
from flop_empires.ui_auth import AuthManager
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


def _post_json(url, body, cookie=None):
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.status, dict(response.headers), json.load(response)


def test_auth_endpoints_create_http_only_session(tmp_path, monkeypatch):
    db = tmp_path / "auth-http.db"
    Store(db).close()
    monkeypatch.setattr(ui_server, "DEFAULT_DB", db)
    monkeypatch.setattr(ui_server, "AUTH", AuthManager(clock=lambda: 1000))
    signer = EphemeralSigner(b"e" * 32)
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        _, _, challenge = _post_json(base + "/api/auth/challenge", {"did": signer.did})
        sig = signer.sign(challenge["message"].encode())
        status, headers, verified = _post_json(base + "/api/auth/verify", {"challenge_id": challenge["challenge_id"], "did": signer.did, "signature": sig})
        assert status == 200 and verified["did"] == signer.did
        cookie = headers["Set-Cookie"]
        assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    finally:
        server.shutdown(); server.server_close()


def test_action_proxy_requires_session_did_and_valid_signature(tmp_path, monkeypatch):
    db = tmp_path / "action-http.db"
    Store(db).close()
    monkeypatch.setattr(ui_server, "DEFAULT_DB", db)
    auth = AuthManager(clock=lambda: 1000); monkeypatch.setattr(ui_server, "AUTH", auth)
    signer = EphemeralSigner(b"f" * 32)
    ch = auth.issue(signer.did); token, _ = auth.verify_challenge(ch["challenge_id"], signer.did, signer.sign(ch["message"].encode()))
    activation = json.loads(ui_server.ACTIVATION.read_text(encoding="utf-8"))
    text = dumps({"season_id": activation["season_id"], "command": {"action": "register_actor", "actor_did": signer.did, "payload": {}, "request_id": "r1"}})
    nonce = "1000-1"; sig = signer.sign(f"{activation['actions_namespace']}|{nonce}|{text}".encode())
    calls = []
    class FakeResponse:
        status_code = 200
        text = ""
        def json(self): return {"ok": True}
    def fake_post(*args, **kwargs): calls.append((args, kwargs)); return FakeResponse()
    monkeypatch.setattr(ui_server.httpx, "post", fake_post)
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        status, _, payload = _post_json(base + "/api/action", {"did": signer.did, "sig": sig, "nonce": nonce, "text": text}, f"{ui_server.COOKIE_NAME}={token}")
        assert status == 200 and payload["ok"] is True and len(calls) == 1
        assert calls[0][1]["json"]["did"] == signer.did
    finally:
        server.shutdown(); server.server_close()
