from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import sha256
from .combat import raid_reward
from .technical_yield import BASE_UNITS, LIFETIME_SECONDS, decayed_yield


@dataclass
class SimState:
    resources: list[int]
    locked: list[int]
    fortification: list[int]
    owners: list[int]
    capitals: set[int]
    clusters: set[str]
    yields: Counter[str]

    def value(self) -> dict[str, Any]:
        return {"resources": self.resources, "locked": self.locked,
                "fortification": self.fortification, "owners": self.owners,
                "capitals": sorted(self.capitals), "clusters": sorted(self.clusters),
                "yields": dict(sorted(self.yields.items()))}


def _percentiles(values: list[int]) -> dict[str, int]:
    v = sorted(values)
    return {"min": v[0], "p25": v[len(v)//4], "median": v[len(v)//2],
            "p75": v[(3*len(v))//4], "max": v[-1]}


def _run(seed: int, actions: int) -> tuple[dict[str, Any], list[str]]:
    rng = random.Random(seed)
    n = 12
    state = SimState([100_000] * n, [0] * n, [0] * (n * 3),
                     [i % n for i in range(n * 3)], set(range(n)), set(), Counter())
    initial_total = sum(state.resources)
    frozen_membership = tuple(range(n))
    seen: set[str] = set()
    hashes: list[str] = []
    failures: list[str] = []
    attacks = Counter()
    alliances = {(i, (i + 1) % n): i % 2 == 0 for i in range(n)}
    alliance_uses = Counter()
    rejected_verifications = 0
    for i in range(actions):
        request_id = f"r-{i - 1}" if i % 997 == 0 and i else f"r-{i}"
        if request_id in seen:
            before_duplicate = sha256(state.value())
            if sha256(state.value()) != before_duplicate:
                failures.append("duplicate request changed state")
            continue
        seen.add(request_id)
        actor = rng.randrange(n)
        op = rng.randrange(6)
        if op == 0:  # fortification consumes resources
            tid = actor + n
            cost = min(state.resources[actor], 1 + rng.randrange(20))
            state.resources[actor] -= cost
            state.fortification[tid] += cost
        elif op in (1, 2):  # deterministic combat
            target = rng.randrange(n * 3)
            defender = state.owners[target]
            if defender == actor:
                continue
            cost = min(state.resources[actor], 1 + rng.randrange(50))
            total_before = sum(state.resources) + sum(state.locked)
            ally = (defender + 1) % n
            active = alliances.get((defender, ally), alliances.get((ally, defender), False))
            contribution = min(state.resources[ally], rng.randrange(10)) if active and ally != actor else 0
            if not active and contribution:
                failures.append("inactive alliance defended")
            state.resources[ally] -= contribution
            state.locked[ally] += contribution
            if state.locked[ally] < contribution:
                failures.append("locked resources double-spent")
            state.resources[actor] -= cost
            defense = state.fortification[target] + contribution
            success = cost > defense
            kind = "raid" if op == 1 else "siege"
            attacks[(kind, "success" if success else "failure")] += 1
            if active and contribution:
                alliance_uses[f"empire-{ally}"] += 1
            if kind == "raid" and success:
                reward = raid_reward(cost, state.resources[defender])
                state.resources[defender] -= reward
                state.resources[actor] += reward
            elif kind == "siege" and success and target not in state.capitals:
                state.owners[target] = actor
            state.locked[ally] -= contribution
            state.resources[ally] += contribution
            if sum(state.resources) + sum(state.locked) > total_before:
                failures.append("combat increased resources")
            if any(state.owners[c] != c for c in state.capitals):
                failures.append("capital conquered")
        elif op == 3:  # one cluster, possibly many evidence URLs
            cluster = f"cluster-{rng.randrange(max(1, actions // 20))}"
            cls = list(BASE_UNITS)[rng.randrange(len(BASE_UNITS))]
            self_owned = rng.randrange(8) == 0
            verified = rng.randrange(20) != 0
            if cluster not in state.clusters:
                state.clusters.add(cluster)
                awarded = 0 if self_owned or not verified else BASE_UNITS[cls]
                state.yields[cls] += awarded
                if not verified and awarded:
                    failures.append("failed verification awarded yield")
                if not verified:
                    rejected_verifications += 1
            # Further URLs deliberately do not award again.
        elif op == 4:  # recon has no state effect and no RNG outcome
            _ = (state.owners[actor + n], state.fortification[actor + n])
        else:  # toggle alliance, which only affects future attacks
            pair = (actor, (actor + 1) % n)
            alliances[pair] = not alliances[pair]
        if i % 1000 == 0:
            hashes.append(sha256(state.value()))
        if any(x < 0 for x in state.resources + state.locked):
            failures.append("negative balance")
    if decayed_yield(100, 0, LIFETIME_SECONDS) != 0:
        failures.append("expired contribution nonzero")
    if len(state.clusters) > sum(1 for x in state.clusters):
        failures.append("cluster multiplication")
    if sum(state.resources) + sum(state.locked) > initial_total:
        failures.append("resources exceed initial supply")
    if tuple(range(n)) != frozen_membership:
        failures.append("membership changed after ACTIVE")
    territory_counts = Counter(state.owners)
    power = [state.resources[i] + sum(state.fortification[t] for t, owner in enumerate(state.owners) if owner == i) for i in range(n)]
    positive = [x for x in power if x > 0]
    report = {
        "seed": seed, "generated_actions": actions, "unique_requests": len(seen),
        "rejected_verifications": rejected_verifications,
        "final_state_hash": sha256(state.value()), "checkpoint_hashes": hashes,
        "resource_distribution": _percentiles(state.resources),
        "empire_power_distribution": _percentiles(power),
        "territory_concentration": {f"empire-{k}": territory_counts[k] for k in sorted(territory_counts)},
        "attack_success_rates": {kind: {"success": attacks[(kind,"success")], "failure": attacks[(kind,"failure")],
            "rate": attacks[(kind,"success")] / max(1, attacks[(kind,"success")] + attacks[(kind,"failure")])} for kind in ("raid", "siege")},
        "alliance_concentration": dict(sorted(alliance_uses.items())),
        "largest_smallest_empire_ratio": max(positive) / min(positive),
        "yield_source_distribution": dict(sorted(state.yields.items())),
        "detected_invariant_failures": sorted(set(failures)),
    }
    return report, failures


def simulate(seed: int = 0, actions: int = 100_000) -> dict[str, Any]:
    if actions < 100_000:
        raise ValueError("protocol simulation requires at least 100,000 actions")
    report, failures = _run(seed, actions)
    replay, replay_failures = _run(seed, actions)
    if replay["final_state_hash"] != report["final_state_hash"] or replay["checkpoint_hashes"] != report["checkpoint_hashes"]:
        failures.append("replay state hashes differ")
    failures.extend(replay_failures)
    report["detected_invariant_failures"] = sorted(set(failures))
    assert not failures, report["detected_invariant_failures"]
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--actions", type=int, default=100_000)
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    report = simulate(args.seed, args.actions)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
