from __future__ import annotations

from .store import Store

BASE_UNITS = {"merged_pull_request": 100, "accepted_security_fix": 160,
              "accepted_documentation": 40, "released_package": 120}
LIFETIME_SECONDS = 90 * 24 * 60 * 60


def decayed_yield(base: int, verified_at: int, at: int, lifetime: int = LIFETIME_SECONDS) -> int:
    if base < 0 or lifetime <= 0:
        raise ValueError("invalid yield inputs")
    age = max(0, at - verified_at)
    return base * max(0, lifetime - age) // lifetime


def empire_yield(store: Store, empire_id: str, at: int) -> int:
    rows = store.conn.execute("SELECT id,base_units,verified_at,expires_at,self_owned FROM contribution_clusters WHERE empire_id=?", (empire_id,))
    return sum(0 if r["self_owned"] or at >= r["expires_at"] else decayed_yield(r["base_units"], r["verified_at"], at) for r in rows)
