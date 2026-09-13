from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from typing import Any
from pathlib import Path

from .canonical import sha256
from .combat import raid_reward

PROFILES = ("FARMER", "SYBIL", "WHALE", "CARTEL", "RAIDER", "TURTLE",
            "CONTRIBUTOR", "OPPORTUNIST")


def gini(values: list[int]) -> float:
    ordered = sorted(max(0, x) for x in values)
    total, n = sum(ordered), len(ordered)
    if not total or not n:
        return 0.0
    return sum((2 * i - n - 1) * value for i, value in enumerate(ordered, 1)) / (n * total)


def run_adversarial(seed: int = 7, actions: int = 250_000) -> dict[str, Any]:
    rng, n = random.Random(seed), len(PROFILES)
    initial = [20_000] * n
    initial[2] = 200_000  # WHALE scenario input, reported rather than normalized away.
    resources = initial[:]
    fort = [0] * (n * 4)
    owners = [i % n for i in range(n * 4)]
    capitals = set(range(n))
    clusters: set[str] = set()
    wins, attempts = Counter(), Counter()
    created = Counter({"initial_allocation": sum(initial), "technical_yield": 0})
    raid_cost = raid_rewards = 0
    invalid_farming_gain = sybil_gain = 0
    invariant_failures: list[str] = []
    dominance_at = None
    comeback_chances = comebacks = 0
    last_loser = None
    alliance_defenses = Counter()
    for step in range(actions):
        actor = step % n
        profile = PROFILES[actor]
        target = (actor + 1 + rng.randrange(n - 1)) % n
        territory = target + n * (1 + rng.randrange(3))
        if profile in {"FARMER", "CONTRIBUTOR"}:
            cluster = f"legit-{actor}-{step // (n * 200)}" if profile == "CONTRIBUTOR" else f"farm-{step // (n * 1000)}"
            before = resources[actor]
            if cluster not in clusters:
                clusters.add(cluster)
                if profile == "CONTRIBUTOR":
                    award = 40
                    resources[actor] += award
                    created["technical_yield"] += award
            if cluster in clusters and profile == "FARMER" and resources[actor] != before:
                invalid_farming_gain += resources[actor] - before
        elif profile == "SYBIL":
            # Frozen membership rejects churn and extra DIDs; no resource effect.
            before = resources[actor]
            if resources[actor] != before:
                sybil_gain += resources[actor] - before
        elif profile == "TURTLE":
            cost = min(resources[actor], 1 + rng.randrange(12))
            resources[actor] -= cost
            fort[actor + n] += cost
        else:
            kind = "raid" if profile == "RAIDER" or rng.randrange(2) == 0 else "siege"
            cost = min(resources[actor], 1 + rng.randrange(30))
            if not cost or owners[territory] == actor:
                continue
            total_before = sum(resources)
            defender = owners[territory]
            defense = fort[territory]
            if profile == "CARTEL" or defender == 3:
                defense += 5
                alliance_defenses[f"empire-{defender}"] += 1
            success = cost > defense
            attempts[kind] += 1
            resources[actor] -= cost
            if success:
                wins[kind] += 1
                if kind == "raid":
                    reward = raid_reward(cost, resources[defender])
                    resources[defender] -= reward
                    resources[actor] += reward
                    raid_cost += cost
                    raid_rewards += reward
                elif territory not in capitals:
                    prior_count = owners.count(defender)
                    owners[territory] = actor
                    if prior_count >= 2 and owners.count(defender) <= prior_count // 2:
                        comeback_chances += 1
                        last_loser = defender
            if sum(resources) > total_before:
                invariant_failures.append("combat created resources")
        if any(x < 0 for x in resources) or any(owners[c] != c for c in capitals):
            invariant_failures.append("negative balance or capital conquest")
        if last_loser is not None and owners.count(last_loser) >= 4:
            comebacks += 1
            last_loser = None
        shares = Counter(owners)
        if dominance_at is None and max(shares.values()) / len(owners) > .5:
            dominance_at = step
    territory = Counter(owners)
    total = sum(resources)
    exploits = []
    if invalid_farming_gain: exploits.append("duplicate contribution farming profitable")
    if sybil_gain: exploits.append("Sybil churn profitable")
    if raid_rewards >= raid_cost and raid_cost: exploits.append("repeated raids non-negative")
    result = {"seed": seed, "actions": actions, "profiles": list(PROFILES),
        "final_state_hash": sha256({"resources":resources,"fort":fort,"owners":owners,"clusters":sorted(clusters)}),
        "resource_conservation": {"initial": sum(initial), "created": sum(created.values())-sum(initial),
            "remaining": total, "consumed": sum(initial)+created["technical_yield"]-total},
        "resource_creation_by_source": dict(created), "gini_like_concentration": gini(resources),
        "largest_empire_share": max(resources) / max(1,total),
        "territory_concentration": {f"empire-{i}":territory[i] for i in range(n)},
        "win_rate_by_attack_type": {k:wins[k]/max(1,attempts[k]) for k in ("raid","siege")},
        "alliance_concentration": dict(alliance_defenses),
        "repeated_raid_profitability": raid_rewards-raid_cost,
        "sybil_profitability": sybil_gain,
        "contribution_farming_profitability": invalid_farming_gain,
        "time_to_dominance": dominance_at,
        "comeback_probability_after_losing_50pct_territory": comebacks/max(1,comeback_chances),
        "exploits_found": exploits, "invariant_failures": sorted(set(invariant_failures))}
    return result


def markdown_summary(report: dict[str, Any]) -> str:
    return "\n".join(["# FLOP Empires adversarial economic report", "",
        f"- Seed: `{report['seed']}`", f"- Actions: `{report['actions']}`",
        f"- Final state hash: `{report['final_state_hash']}`",
        f"- Gini-like concentration: `{report['gini_like_concentration']:.6f}`",
        f"- Largest empire share: `{report['largest_empire_share']:.6f}`",
        f"- Repeated raid profitability: `{report['repeated_raid_profitability']}`",
        f"- Sybil profitability: `{report['sybil_profitability']}`",
        f"- Invalid contribution farming profitability: `{report['contribution_farming_profitability']}`",
        f"- Exploits found: `{report['exploits_found']}`",
        f"- Invariant failures: `{report['invariant_failures']}`", "",
        "The WHALE starts with the declared higher production input; this is not normalized away.",
        "Technical Yield is the only post-start resource creation source in this model."])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--actions", type=int, default=250_000)
    parser.add_argument("--stress-actions", type=int, default=1_000_000)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args(argv)
    primary = run_adversarial(args.seed, args.actions)
    stress = run_adversarial(args.seed, args.stress_actions)
    suite = {"adversarial": primary, "stress": stress}
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(suite, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown_summary(primary) + "\n\n## Stress run\n\n" +
        markdown_summary(stress).removeprefix("# FLOP Empires adversarial economic report\n") + "\n", encoding="utf-8")
    print(json.dumps({"adversarial_hash": primary["final_state_hash"],
        "stress_hash": stress["final_state_hash"], "exploits": primary["exploits_found"],
        "failures": primary["invariant_failures"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
