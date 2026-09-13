from __future__ import annotations

from .store import Store

BASE_UNITS = {"merged_pull_request": 100, "accepted_security_fix": 160,
              "accepted_documentation": 40, "released_package": 120}
LIFETIME_SECONDS = 90 * 24 * 60 * 60
EPOCH_SECONDS = 7 * 24 * 60 * 60
CONTRIBUTOR_EPOCH_CAP = 320
CLUSTER_BASE_CAP = max(BASE_UNITS.values())
BOOTSTRAP_SECONDS = 30 * 24 * 60 * 60
BOOTSTRAP_MULTIPLIER = 2


def decayed_yield(base: int, verified_at: int, at: int, lifetime: int = LIFETIME_SECONDS) -> int:
    if base < 0 or lifetime <= 0:
        raise ValueError("invalid yield inputs")
    if at < verified_at:
        return 0
    age = at - verified_at
    return base * max(0, lifetime - age) // lifetime


def epoch_yield(clusters: list[dict], at: int, season_started_at: int) -> int:
    """Capped deterministic epoch evaluation; future evidence is never backdated."""
    if at < season_started_at or (at - season_started_at) % EPOCH_SECONDS:
        return 0
    per_actor: dict[str, int] = {}
    seen: set[str] = set()
    multiplier = BOOTSTRAP_MULTIPLIER if at - season_started_at < BOOTSTRAP_SECONDS else 1
    for row in sorted(clusters, key=lambda x: str(x["id"])):
        cluster_id = str(row["id"])
        if cluster_id in seen or row.get("self_owned"):
            continue
        seen.add(cluster_id)
        value = decayed_yield(min(int(row["base_units"]), CLUSTER_BASE_CAP),
                              int(row["verified_at"]), at) * multiplier
        actor = str(row["actor_did"])
        per_actor[actor] = min(CONTRIBUTOR_EPOCH_CAP, per_actor.get(actor, 0) + value)
    return sum(per_actor.values())


def empire_yield(store: Store, empire_id: str, at: int) -> int:
    rows = store.conn.execute("SELECT id,base_units,verified_at,expires_at,self_owned FROM contribution_clusters WHERE empire_id=?", (empire_id,))
    return sum(0 if r["self_owned"] or at >= r["expires_at"] else decayed_yield(r["base_units"], r["verified_at"], at) for r in rows)
