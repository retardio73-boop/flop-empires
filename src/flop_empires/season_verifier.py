from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .activation import ActivationRecord
from .canonical import bytes_, loads, sha256
from .events import verify_chain
from .identity import verify
from .launch import LaunchAuthorization
from .manifest import SeasonZeroFreezeV2CandidateManifest
from .recovery import RecoveryRecord
from .store import Store


def verify_season_artifacts(store: Store, manifest_path: str | Path,
                            activation_path: str | Path, world_path: str | Path,
                            recovery_path: str | Path | None = None,
                            launch_path: str | Path | None = None) -> dict[str, Any]:
    manifest_raw=loads(Path(manifest_path).read_text(encoding="utf-8"))
    activation_raw=loads(Path(activation_path).read_text(encoding="utf-8"))
    world=loads(Path(world_path).read_text(encoding="utf-8"))
    manifest_unsigned=dict(manifest_raw); manifest_hash=manifest_unsigned.pop("manifest_hash")
    activation_unsigned=dict(activation_raw); activation_sig=activation_unsigned.pop("signature")
    checks={
        "manifest_hash":sha256(manifest_unsigned)==manifest_hash,
        "activation_manifest_binding":activation_raw.get("frozen_manifest_hash")==manifest_hash,
        "world_hash":sha256(world)==manifest_raw.get("world_graph_hash"),
        "activation_signature":verify(activation_raw["referee_did"],bytes_(activation_unsigned),activation_sig),
        "event_chain":verify_chain(store),
        "database_integrity":store.one("PRAGMA integrity_check")[0]=="ok",
    }
    persisted_world=store.one("SELECT value FROM config WHERE key='world_graph_hash'")
    persisted_manifest=store.one("SELECT value FROM config WHERE key='activation_manifest_hash'")
    checks["persisted_world_binding"]=bool(persisted_world and persisted_world[0]==manifest_raw["world_graph_hash"])
    checks["persisted_manifest_binding"]=bool(persisted_manifest and persisted_manifest[0]==manifest_hash)

    manifest=SeasonZeroFreezeV2CandidateManifest.load(manifest_path)
    activation=ActivationRecord.load(activation_path,manifest)
    effective_context=activation.context()
    lineage={"activation_id":activation.value["activation_id"],"recovery_id":None,"launch_id":None}
    recovery_used=False
    if recovery_path and Path(recovery_path).is_file():
        recovery=RecoveryRecord.load(recovery_path,manifest)
        effective_context=recovery.context(); recovery_used=True
        lineage["recovery_id"]=recovery.value["recovery_id"]
        checks["recovery_original_activation_binding"]=recovery.value["original_activation_id"]==activation.value["activation_id"]
        checks["recovery_failed_state_hash_present"]=len(recovery.value["failed_state_hash"])==64

    launch_authorized=False
    launch=None
    if launch_path and Path(launch_path).is_file():
        launch=LaunchAuthorization.load(launch_path,manifest,effective_context)
        launch_authorized=True; lineage["launch_id"]=launch.value["launch_id"]
        checks["launch_binding_verified"]=True

    persisted={r["key"]:r["value"] for r in store.conn.execute(
        "SELECT key,value FROM config WHERE key LIKE 'production_%'")}
    if persisted:
        expected={
            "production_manifest_hash":manifest.manifest_hash,
            "production_activation_id":effective_context.activation_id,
            "production_referee_did":effective_context.referee_did,
            "production_actions_namespace":effective_context.actions_namespace,
            "production_events_namespace":effective_context.events_namespace,
        }
        checks["production_binding_exact"]=persisted==expected

    event_head=store.one("SELECT seq,event_hash,state_after_hash FROM events ORDER BY seq DESC LIMIT 1")
    return {
        "schema":"flop-empires-season-verification-v1",
        "ok":all(checks.values()),
        "checks":checks,
        "manifest_hash":manifest_hash,
        "world_hash":manifest_raw["world_graph_hash"],
        "activation_id":activation.value["activation_id"],
        "effective_binding_id":effective_context.activation_id,
        "recovery_active":recovery_used,
        "launch_authorized":launch_authorized,
        "launch_effective_start":launch.value["effective_start"] if launch else None,
        "launch_effective_end":launch.value["effective_end"] if launch else None,
        "lineage":lineage,
        "event_count":store.one("SELECT COUNT(*) FROM events")[0],
        "event_head":dict(event_head) if event_head else None,
        "current_state_hash":store.state_hash(),
    }


def write_verification_report(result: dict[str, Any], output: str | Path) -> None:
    Path(output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
