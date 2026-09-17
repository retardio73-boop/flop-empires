from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

EMPIRE_PALETTE = [
    "#7c3aed", "#2563eb", "#0891b2", "#059669",
    "#65a30d", "#ca8a04", "#ea580c", "#dc2626",
    "#db2777", "#9333ea", "#4f46e5", "#0284c7",
    "#0d9488", "#16a34a", "#84cc16", "#d97706",
]


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _rows(conn: sqlite3.Connection, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, args)]


def _layout(index: int, total: int = 64) -> tuple[float, float]:
    angle = -math.pi / 2 + (2 * math.pi * index / total)
    radius = 322 + ((index % 4) - 1.5) * 24
    return round(450 + math.cos(angle) * radius, 2), round(450 + math.sin(angle) * radius, 2)


def build_public_state(db_path: str | Path, world_path: str | Path, activation_path: str | Path) -> dict[str, Any]:
    world = _read_json(world_path)
    activation = _read_json(activation_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        config = dict(conn.execute("SELECT key,value FROM config"))
        live_territories = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM territories")}
        empires = _rows(conn, "SELECT * FROM empires ORDER BY id")
        economy = {r["empire_id"]: dict(r) for r in conn.execute("SELECT empire_id,prestige FROM empire_economy")}
        attacks = _rows(conn, "SELECT * FROM attacks ORDER BY created_at DESC")
        events = _rows(conn, "SELECT seq,event_type,actor_did,request_id,accepted_at,accepted,details_json FROM events ORDER BY seq DESC LIMIT 40")
        memberships = _rows(conn, "SELECT * FROM memberships ORDER BY empire_id,actor_did")
        actor_count = conn.execute("SELECT COUNT(*) FROM actors").fetchone()[0]
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        event_head = conn.execute("SELECT seq,event_hash,state_after_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        alliances = _rows(conn, "SELECT * FROM alliances WHERE active=1 ORDER BY id")
        alliance_members = _rows(conn, "SELECT * FROM alliance_members ORDER BY alliance_id,empire_id")
    finally:
        conn.close()

    empire_ids = [f"season0-e{i:02d}" for i in range(1, 17)]
    live_by_id = {e["id"]: e for e in empires}
    member_count: dict[str, int] = {}
    for row in memberships:
        member_count[row["empire_id"]] = member_count.get(row["empire_id"], 0) + 1

    empire_view = []
    for i, empire_id in enumerate(empire_ids):
        live = live_by_id.get(empire_id, {})
        econ = economy.get(empire_id, {})
        empire_view.append({
            "id": empire_id,
            "name": live.get("name") or f"Empire {i + 1:02d}",
            "color": EMPIRE_PALETTE[i],
            "claimed": member_count.get(empire_id, 0) > 0,
            "members": member_count.get(empire_id, 0),
            "standing": None,
            "standing_state": "PENDING_RUNTIME_MATERIALIZATION",
            "prestige_public": int(econ.get("prestige", 0) or 0),
        })

    empire_lookup = {e["id"]: e for e in empire_view}
    territories = []
    for index, frozen in enumerate(world["territories"]):
        live = live_territories.get(frozen["id"])
        owner = live["owner_empire_id"] if live else frozen["owner"]
        x, y = _layout(index, len(world["territories"]))
        territories.append({
            "id": frozen["id"],
            "index": index,
            "region": frozen["region"],
            "owner": owner,
            "owner_name": empire_lookup.get(owner, {}).get("name", owner),
            "color": empire_lookup.get(owner, {}).get("color", "#64748b"),
            "capital": bool(live["is_capital"] if live else frozen["capital"]),
            "strategic_value": int(frozen.get("strategic_value", 1)),
            "fog": {"fortification": "HIDDEN", "production": "HIDDEN"},
            "x": x,
            "y": y,
            "live": live is not None,
        })

    public_events = [{
        "seq": e["seq"], "event_type": e["event_type"], "request_id": e["request_id"],
        "accepted_at": e["accepted_at"], "accepted": bool(e["accepted"]),
    } for e in events]
    active_attacks = [{k: a.get(k) for k in (
        "id", "kind", "attacker_empire_id", "defender_empire_id", "origin_id",
        "target_id", "alliance_id", "created_at", "deadline_at", "resolved", "success"
    )} for a in attacks if not a["resolved"]]
    return {
        "season": {
            "id": activation["season_id"],
            "status": config.get("season_status", "UNKNOWN"),
            "registration_open": activation["registration_open"],
            "registration_close": activation["registration_close"],
            "season_start": activation["season_start"],
            "season_end": activation["season_end"],
            "activation_id": activation["activation_id"],
            "manifest_hash": activation["frozen_manifest_hash"],
        },
        "world": {
            "schema": world["schema"],
            "seed": world["seed"],
            "empires": empire_view,
            "territories": territories,
            "edges": world["edges"],
            "live_materialized": len(live_territories) == len(world["territories"]),
        },
        "activity": {
            "active_attacks": active_attacks,
            "recent_events": public_events,
            "active_alliances": alliances,
            "alliance_members": alliance_members,
        },
        "registration": {
            "actors": actor_count,
            "memberships_by_empire": member_count,
        },
        "capabilities": {
            "fog_safe_public_projection": True,
            "raid_siege": True,
            "recon": True,
            "alliances_runtime": True,
            "treaties_rule_contract": True,
            "treaties_runtime_materialized": False,
            "trade_rule_contract": True,
            "trade_runtime_materialized": False,
            "standing_mode": "relative_rank",
            "standing_runtime_materialized": False,
            "victory_scoring": "world-share-normalized",
        },
        "evidence": {
            "projection_schema": "flop-empires-public-state-v1",
            "manifest_hash": activation["frozen_manifest_hash"],
            "world_hash": config.get("world_graph_hash"),
            "event_count": event_count,
            "event_head_seq": int(event_head["seq"]) if event_head else None,
            "event_head_hash": event_head["event_hash"] if event_head else None,
            "state_after_hash": event_head["state_after_hash"] if event_head else None,
            "claim": "Public view is fog-safe and derived read-only from the frozen world plus canonical SQLite state.",
        },
    }
