from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .gate_b import STANDING_ORDER, VICTORY_WEIGHTS_BP
from .store import Store


def _rank_label(rank: int, total: int) -> str:
    q = rank / max(1, total)
    if q <= .06: return "Dominant"
    if q <= .18: return "Great"
    if q <= .38: return "Major"
    if q <= .70: return "Regional"
    return "Domain"


def descriptive_scoreboard(store: Store, world_path: str | Path) -> dict[str, Any]:
    world = json.loads(Path(world_path).read_text(encoding="utf-8"))
    strategic = {t["id"]: int(t.get("strategic_value", 1)) for t in world["territories"]}
    economy = {r["empire_id"]: dict(r) for r in store.conn.execute("SELECT * FROM empire_economy")}
    owners = Counter(r["owner_empire_id"] for r in store.conn.execute("SELECT owner_empire_id FROM territories"))
    rows = []
    for empire in store.conn.execute("SELECT id,name FROM empires ORDER BY id"):
        eid = empire["id"]; econ = economy.get(eid, {})
        power = int(econ.get("engineering", 0)) + int(econ.get("knowledge", 0)) + int(econ.get("influence", 0))
        territory_value = sum(strategic.get(r["id"], 1) for r in store.conn.execute(
            "SELECT id FROM territories WHERE owner_empire_id=?", (eid,)))
        rows.append({"empire_id": eid, "name": empire["name"], "power": power,
                     "territories": owners[eid], "territory_value": territory_value,
                     "production_proxy": owners[eid] * 20,
                     "objective_points": 0, "hegemon_epochs": 0})
    component_names = ("territory_value", "power", "production_proxy", "objective_points", "hegemon_epochs")
    totals = {name: sum(r[name] for r in rows) for name in component_names}
    weight_name = {"production_proxy": "production"}
    for r in rows:
        score = 0
        for name in component_names:
            manifest_name = weight_name.get(name, name); total = totals[name]
            share_bp = r[name] * 10_000 // total if total else 0
            score += share_bp * VICTORY_WEIGHTS_BP[manifest_name] // 10_000
        r["candidate_score"] = score
    ranked = sorted(rows, key=lambda r: (-r["candidate_score"], r["empire_id"]))
    for idx, r in enumerate(ranked, 1): r["descriptive_standing"] = _rank_label(idx, len(ranked))
    return {"schema": "flop-empires-descriptive-scoreboard-v1", "authoritative": False,
            "reason": "Gate B standing/victory remains SIMULATION_CANDIDATE_NOT_FROZEN",
            "weights_bp": VICTORY_WEIGHTS_BP, "rows": ranked}


def replay_timeline(store: Store, *, limit: int = 500) -> dict[str, Any]:
    events = []
    for row in store.conn.execute("SELECT seq,event_type,request_id,accepted_at,accepted,state_before_hash,state_after_hash,event_hash,details_json FROM events ORDER BY seq LIMIT ?", (limit,)):
        details = json.loads(row["details_json"])
        item = {"seq": row["seq"], "event_type": row["event_type"], "request_id": row["request_id"],
                "accepted_at": row["accepted_at"], "accepted": bool(row["accepted"]),
                "state_before_hash": row["state_before_hash"], "state_after_hash": row["state_after_hash"],
                "event_hash": row["event_hash"]}
        command = details.get("command") if isinstance(details, dict) else None
        if isinstance(command, dict):
            item["action"] = command.get("action")
            payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
            for key in ("territory_id", "origin_id", "target_id", "attack_id", "alliance_id"):
                if key in payload: item[key] = payload[key]
        events.append(item)
    return {"schema": "flop-empires-replay-timeline-v1", "events": events,
            "truncated": store.one("SELECT COUNT(*) FROM events")[0] > limit}
