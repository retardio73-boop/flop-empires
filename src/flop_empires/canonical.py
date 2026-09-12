"""Strict deterministic JSON used for commands, hashes, and signatures."""
from __future__ import annotations

import hashlib
import json
from typing import Any


class CanonicalError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CanonicalError(f"duplicate key: {key}")
        out[key] = value
    return out


def _validate(value: Any) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 9_007_199_254_740_991:
            raise CanonicalError("integer exceeds interoperable JSON range")
        return
    if isinstance(value, list):
        for item in value:
            _validate(item)
        return
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise CanonicalError("object keys must be strings")
        for item in value.values():
            _validate(item)
        return
    raise CanonicalError(f"unsupported JSON value: {type(value).__name__}")


def dumps(value: Any) -> str:
    _validate(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def bytes_(value: Any) -> bytes:
    return dumps(value).encode("utf-8")


def loads(raw: str | bytes) -> Any:
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_float=lambda _: (_ for _ in ()).throw(CanonicalError("floats forbidden")), parse_constant=lambda _: (_ for _ in ()).throw(CanonicalError("non-finite number forbidden")))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CanonicalError(str(exc)) from exc
    _validate(value)
    return value


def sha256(value: Any) -> str:
    return hashlib.sha256(bytes_(value)).hexdigest()
