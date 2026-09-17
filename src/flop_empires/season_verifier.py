from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import bytes_, loads, sha256
from .events import verify_chain
from .identity import verify
from .store import Store


def verify_season_artifacts(store: Store, manifest_path: str | Path,
                            activation_path: str | Path, world_path: str | Path) -> dict[str, Any]:
    manifest = loads(Path(manifest_path).read_text(encoding="utf-8"))
    activation = loads(Path(activation_path).read_text(encoding="utf-8"))
    world = loads(Path(world_path).read_text(encoding="utf-8"))
    manifest_unsigned = dict(manifest); manifest_hash = manifest_unsigned.pop("manifest_hash")
    activation_unsigned = dict(activation); activation_sig = activation_unsigned.pop("signature")
    checks = {
        "manifest_hash": sha256(manifest_unsigned) == manifest_hash,
        "activation_manifest_binding": activation.get("frozen_manifest_hash") == manifest_hash,
        "world_hash": sha256(world) == manifest.get("world_graph_hash"),
        "activation_signature": verify(activation["referee_did"], bytes_(activation_unsigned), activation_sig),
        "event_chain": verify_chain(store),
        "database_integrity": store.one("PRAGMA integrity_check")[0] == "ok",
    }
    persisted_world = store.one("SELECT value FROM config WHERE key='world_graph_hash'")
    persisted_manifest = store.one("SELECT value FROM config WHERE key='activation_manifest_hash'")
    checks["persisted_world_binding"] = bool(persisted_world and persisted_world[0] == manifest["world_graph_hash"])
    checks["persisted_manifest_binding"] = bool(persisted_manifest and persisted_manifest[0] == manifest_hash)
    event_head = store.one("SELECT seq,event_hash,state_after_hash FROM events ORDER BY seq DESC LIMIT 1")
    return {
        "schema": "flop-empires-season-verification-v1",
        "ok": all(checks.values()),
        "checks": checks,
        "manifest_hash": manifest_hash,
        "world_hash": manifest["world_graph_hash"],
        "activation_id": activation["activation_id"],
        "event_count": store.one("SELECT COUNT(*) FROM events")[0],
        "event_head": dict(event_head) if event_head else None,
        "current_state_hash": store.state_hash(),
    }


def write_verification_report(result: dict[str, Any], output: str | Path) -> None:
    Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
