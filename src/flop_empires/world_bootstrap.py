from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import loads, sha256
from .store import Store


def bootstrap_frozen_world(store: Store, world_path: str | Path, *,
                           expected_hash: str, initial_balances: dict[str, int],
                           now: int) -> dict[str, Any]:
    world = loads(Path(world_path).read_text(encoding="utf-8"))
    if sha256(world) != expected_hash:
        raise RuntimeError("WORLD_HASH_MISMATCH")
    if store.one("SELECT 1 FROM events LIMIT 1"):
        raise RuntimeError("WORLD_BOOTSTRAP_REQUIRES_EMPTY_EVENT_LOG")
    counts = {t: store.one(f"SELECT COUNT(*) FROM {t}")[0] for t in
              ("empires", "territories", "territory_edges", "memberships")}
    if any(counts.values()):
        raise RuntimeError("WORLD_BOOTSTRAP_REQUIRES_EMPTY_WORLD_STATE")
    if world.get("schema") != "flop-empires-world-v1" or world.get("empires") != 16:
        raise RuntimeError("INVALID_FROZEN_WORLD")
    capital_by_empire = {}
    for t in world["territories"]:
        if t["capital"]:
            capital_by_empire[t["owner"]] = t["id"]
    empire_ids = sorted({t["owner"] for t in world["territories"]})
    if len(empire_ids) != 16 or set(capital_by_empire) != set(empire_ids):
        raise RuntimeError("INVALID_FROZEN_WORLD_CAPITALS")

    with store.transaction():
        for i, empire_id in enumerate(empire_ids, 1):
            store.conn.execute(
                "INSERT INTO empires(id,name,capital_id,created_at) VALUES(?,?,?,?)",
                (empire_id, f"Empire {i:02d}", capital_by_empire[empire_id], now),
            )
            store.conn.execute("INSERT INTO balances(empire_id,available,locked) VALUES(?,?,0)",
                               (empire_id, initial_balances["ENGINEERING"]))
            store.conn.execute(
                "INSERT INTO empire_economy(empire_id,prestige,engineering,knowledge,influence,last_settled_epoch) VALUES(?,?,?,?,?,-1)",
                (empire_id, 0, initial_balances["ENGINEERING"], initial_balances["KNOWLEDGE"], initial_balances["INFLUENCE"]),
            )
        for t in world["territories"]:
            store.conn.execute(
                "INSERT INTO territories(id,owner_empire_id,is_capital,fortification) VALUES(?,?,?,?)",
                (t["id"], t["owner"], int(bool(t["capital"])), int(t.get("fortification", 0))),
            )
        for a, b in world["edges"]:
            x, y = sorted((a, b))
            store.conn.execute("INSERT INTO territory_edges(a,b) VALUES(?,?)", (x, y))
        store.conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('world_graph_hash',?)", (expected_hash,))
        store.conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('world_materialized','1')")
    return {"empires": len(empire_ids), "territories": len(world["territories"]), "edges": len(world["edges"]), "world_hash": expected_hash}
