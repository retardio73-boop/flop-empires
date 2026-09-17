from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from .readiness import readiness_report
from .recovery import RecoveryRecord
from .season0_runner import ACTIVATION_PATH, DB_PATH, MANIFEST_PATH, RECOVERY_PATH, RUNTIME_DIR, STATUS_PATH, ROOT
from .manifest import SeasonZeroFreezeV2CandidateManifest
from .store import Store
from .windows_signer import season0_referee_backend

WATCHDOG_STATUS = RUNTIME_DIR / "watchdog-status.json"
WORLD_PATH = ROOT / "season" / "world-season-0-v1.json"
UI_URL = "http://127.0.0.1:8876/api/state"
TECHNOCORE_ORIGIN = "https://technocore.chat"


def _priority() -> None:
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass


def _recovery_checks(store: Store, client: httpx.Client) -> tuple[dict, dict]:
    manifest = SeasonZeroFreezeV2CandidateManifest.load(MANIFEST_PATH)
    recovery = RecoveryRecord.load(RECOVERY_PATH, manifest)
    values = {r["key"]: r["value"] for r in store.conn.execute(
        "SELECT key,value FROM config WHERE key LIKE 'production_%'")}
    expected = {
        "production_manifest_hash": manifest.manifest_hash,
        "production_activation_id": recovery.value["recovery_id"],
        "production_referee_did": recovery.value["referee_did"],
        "production_actions_namespace": recovery.value["duplex_namespace"],
        "production_events_namespace": recovery.value["duplex_namespace"],
    }
    signer = season0_referee_backend().status()
    room = client.get(f"{TECHNOCORE_ORIGIN}/r/{recovery.value['duplex_namespace']}")
    ui = client.get(UI_URL)
    ui_body = ui.json() if ui.status_code == 200 else {}
    ui_season = ui_body.get("season", {}) if isinstance(ui_body, dict) else {}
    high_retry_pending = store.one(
        "SELECT COUNT(*) FROM receipt_outbox WHERE status='PENDING' AND attempts>=3")[0]
    checks = {
        "recovery_signature_and_manifest": True,
        "recovery_binding_exact": values == expected,
        "referee_signer_ready": bool(signer.get("ready") and signer.get("did") == recovery.value["referee_did"]),
        "technocore_duplex_room_readable": room.status_code == 200,
        "ui_healthy": ui.status_code == 200,
        "ui_recovery_binding": ui_season.get("activation_id") == recovery.value["recovery_id"],
        "ui_duplex_binding": ui_season.get("actions_namespace") == recovery.value["duplex_namespace"] == ui_season.get("events_namespace"),
        "no_stuck_receipts": high_retry_pending == 0,
    }
    detail = {
        "recovery_id": recovery.value["recovery_id"],
        "duplex_namespace": recovery.value["duplex_namespace"],
        "signer": signer,
        "technocore_status": room.status_code,
        "ui_status": ui.status_code,
        "high_retry_pending": high_retry_pending,
    }
    return checks, detail


def main() -> int:
    _priority(); RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        store = Store(DB_PATH, readonly=True)
        try:
            report = readiness_report(store, MANIFEST_PATH, ACTIVATION_PATH, WORLD_PATH, STATUS_PATH)
            with httpx.Client(timeout=5.0) as client:
                recovery_checks, recovery_detail = _recovery_checks(store, client)
        finally:
            store.close()
        checks = {**report["checks"], **recovery_checks}
        payload = {
            "watchdog": "OK" if all(checks.values()) else "ALERT",
            "checked_at": int(time.time()),
            **report,
            "checks": checks,
            "recovery": recovery_detail,
        }
        payload["ok"] = all(checks.values())
    except Exception as exc:
        payload = {
            "watchdog": "ERROR",
            "checked_at": int(time.time()),
            "error_type": type(exc).__name__,
            "safe_error": str(exc)[:160],
        }
    temporary = WATCHDOG_STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(',', ':')), encoding='utf-8')
    os.replace(temporary, WATCHDOG_STATUS)
    return 0 if payload.get('watchdog') == 'OK' else 2


if __name__ == '__main__':
    raise SystemExit(main())
