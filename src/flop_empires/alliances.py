from __future__ import annotations

from .store import Store


def active_allies(store: Store, empire_id: str, alliance_id: str) -> list[str]:
    row = store.one("SELECT active FROM alliances WHERE id=?", (alliance_id,))
    if not row or not row["active"]:
        return []
    members = [r[0] for r in store.conn.execute("SELECT empire_id FROM alliance_members WHERE alliance_id=? ORDER BY empire_id", (alliance_id,))]
    return [x for x in members if x != empire_id] if empire_id in members else []
