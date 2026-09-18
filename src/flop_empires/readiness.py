from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .season_verifier import verify_season_artifacts
from .store import Store


def readiness_report(store: Store, manifest_path: str | Path, activation_path: str | Path,
                     world_path: str | Path, runner_status_path: str | Path | None = None,
                     recovery_path: str | Path | None = None, launch_path: str | Path | None = None,
                     *, now: int | None = None) -> dict[str, Any]:
    wall = int(time.time()) if now is None else int(now)
    verification = verify_season_artifacts(store, manifest_path, activation_path, world_path, recovery_path, launch_path)
    status = store.one("SELECT value FROM config WHERE key='season_status'")
    pending = store.one("SELECT COUNT(*) FROM receipt_outbox WHERE status='PENDING'")[0]
    unverified = store.one("SELECT COUNT(*) FROM receipt_outbox WHERE status='PUBLISHED' AND readback_verified=0")[0]
    runner = None
    if runner_status_path and Path(runner_status_path).is_file():
        try: runner = json.loads(Path(runner_status_path).read_text(encoding="utf-8"))
        except Exception: runner = {"runner": "INVALID_STATUS_FILE"}
    runner_heartbeat = int(runner.get("heartbeat", 0)) if isinstance(runner, dict) else 0
    runner_fresh = bool(runner and runner.get("runner") == "RUNNING" and wall - runner_heartbeat <= 90)
    checks = {
        "artifacts_verified": verification["ok"],
        "runner_fresh": runner_fresh,
        "pending_receipts_below_threshold": pending < 10,
        "unverified_publications_below_threshold": unverified < 3,
    }
    return {
        "schema": "flop-empires-readiness-v1",
        "ok": all(checks.values()),
        "checks": checks,
        "season_status": status[0] if status else "UNKNOWN",
        "runner": runner,
        "pending_receipts": pending,
        "published_unverified": unverified,
        "verification": verification,
    }
