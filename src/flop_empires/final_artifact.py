from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .season_insights import descriptive_scoreboard
from .season_verifier import verify_season_artifacts
from .store import Store


def build_final_artifact(store: Store, manifest_path: str | Path,
                         activation_path: str | Path, world_path: str | Path,
                         recovery_path: str | Path | None = None, launch_path: str | Path | None = None) -> dict:
    status = store.one("SELECT value FROM config WHERE key='season_status'")
    verification = verify_season_artifacts(store, manifest_path, activation_path, world_path, recovery_path, launch_path)
    scoreboard = descriptive_scoreboard(store, world_path)
    return {
        "schema": "flop-empires-final-state-v1",
        "generated_at": int(time.time()),
        "season_status": status[0] if status else "UNKNOWN",
        "state_hash": store.state_hash(),
        "verification": verification,
        "lineage": verification.get("lineage"),
        "effective_binding_id": verification.get("effective_binding_id"),
        "launch_authorized": verification.get("launch_authorized",False),
        "authoritative_winner": None,
        "authoritative_winner_reason": "Gate B victory is SIMULATION_CANDIDATE_NOT_FROZEN",
        "descriptive_scoreboard": scoreboard,
    }


def write_final_artifact(value: dict, path: str | Path) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
