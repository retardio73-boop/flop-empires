from __future__ import annotations

from typing import Any

from .canonical import CanonicalError, loads
from .models import Command

MAX_ID = 200
MAX_COMMAND_BYTES = 64_000


def parse_command(raw: str | bytes | dict[str, Any]) -> Command:
    if isinstance(raw, (str, bytes)):
        if len(raw) > MAX_COMMAND_BYTES:
            raise CanonicalError("command too large")
        obj = loads(raw)
    else:
        obj = raw
    if not isinstance(obj, dict) or set(obj) != {"action", "actor_did", "request_id", "payload"}:
        raise CanonicalError("command fields must be action, actor_did, request_id, payload")
    for key in ("action", "actor_did", "request_id"):
        if not isinstance(obj[key], str) or not obj[key] or len(obj[key]) > MAX_ID:
            raise CanonicalError(f"invalid {key}")
    if not obj["actor_did"].startswith("did:key:"):
        raise CanonicalError("actor_did must be did:key")
    if not isinstance(obj["payload"], dict):
        raise CanonicalError("payload must be an object")
    return Command(**obj)
