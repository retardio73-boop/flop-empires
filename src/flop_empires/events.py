from __future__ import annotations

import hashlib
from typing import Any

from .canonical import bytes_, dumps
from .store import Store


def append_event(store: Store, *, event_type: str, actor_did: str, request_id: str,
                 accepted_at: int, accepted: bool, command_hash: str,
                 before: str, after: str, details: dict[str, Any]) -> tuple[int, str]:
    prev = store.one("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1")
    prev_hash = prev[0] if prev else "0" * 64
    body = {"event_type": event_type, "actor_did": actor_did, "request_id": request_id,
            "accepted_at": accepted_at, "accepted": accepted, "command_hash": command_hash,
            "state_before_hash": before, "state_after_hash": after,
            "details": details, "prev_event_hash": prev_hash}
    event_hash = hashlib.sha256(bytes_(body)).hexdigest()
    cur = store.conn.execute("INSERT INTO events(event_type,actor_did,request_id,accepted_at,accepted,command_hash,state_before_hash,state_after_hash,details_json,prev_event_hash,event_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (event_type, actor_did, request_id, accepted_at, int(accepted), command_hash, before, after, dumps(details), prev_hash, event_hash))
    return int(cur.lastrowid), event_hash


def verify_chain(store: Store) -> bool:
    prev = "0" * 64
    for row in store.conn.execute("SELECT * FROM events ORDER BY seq"):
        details = __import__("json").loads(row["details_json"])
        body = {"event_type": row["event_type"], "actor_did": row["actor_did"], "request_id": row["request_id"],
                "accepted_at": row["accepted_at"], "accepted": bool(row["accepted"]), "command_hash": row["command_hash"],
                "state_before_hash": row["state_before_hash"], "state_after_hash": row["state_after_hash"],
                "details": details, "prev_event_hash": prev}
        if row["prev_event_hash"] != prev or hashlib.sha256(bytes_(body)).hexdigest() != row["event_hash"]:
            return False
        prev = row["event_hash"]
    return True


def require_valid_chain(store: Store) -> None:
    if not verify_chain(store):
        raise RuntimeError("invalid historical event chain")
