from __future__ import annotations

import argparse
import json
import random
from collections import Counter, deque
from dataclasses import asdict, replace
from pathlib import Path

from .canonical import sha256
from .combat import raid_reward
from .economics_v02 import EconomicRulesV02

SCENARIOS = ("BALANCED","WHALE_2X","WHALE_5X","WHALE_10X","CARTEL",
             "RAIDER","TURTLE","CONTRIBUTOR","OPPORTUNIST","COMEBACK")
SEEDS = (7, 19, 41, 73, 101)


def _manifest_candidates(base: EconomicRulesV02) -> list[EconomicRulesV02]:
    return [base,
        replace(base, overextension_penalty_bp=800, fatigue_step_bp=1000,
                stockpile_carry_cost_bp=300),
        replace(base, overextension_penalty_bp=1600, fatigue_step_bp=2000,
                stockpile_carry_cost_bp=700)]


def simulate_scenario(rules: EconomicRulesV02, scenario: str, seed: int,
                      actions: int = 50_000) -> dict:
    rng, n = random.Random(seed), 8
    multiplier = {"WHALE_2X":2,"WHALE_5X":5,"WHALE_10X":10}.get(scenario, 1)
    prestige = [1000] * n; prestige[0] *= multiplier
    if scenario == "CONTRIBUTOR": prestige[0] *= 5
    resources = [rules.allocate(p)["ENGINEERING"] * 3 for p in prestige]
    owners = [i % n for i in range(n * 4)]
    capitals = set(range(n)); fort = [0] * len(owners)
    lost = {n, 2*n} if scenario == "COMEBACK" else set()
    if lost:
        prestige[0] = 5000
        for t in lost: owners[t] = 1
    fatigue = [deque() for _ in range(n)]
    wins = Counter(); tries = Counter(); raid_cost = raid_income = 0
    combat_created = 0; dominance_at = None; invariant_failures = []
    created_yield = 0
    for step in range(actions):
        if step % 500 == 0:
            for empire in range(n):
                noncap = sum(1 for t,o in enumerate(owners) if t not in capitals and o == empire)
                produced = rules.allocate(prestige[empire])["ENGINEERING"] // 20
                produced += rules.territory_benefit(noncap)
                resources[empire] += produced; created_yield += produced
                resources[empire] -= rules.upkeep(resources[empire], noncap,
                    sum(fort[t] for t,o in enumerate(owners) if o == empire))
        actor = step % n
        while fatigue[actor] and fatigue[actor][0] <= step-rules.fatigue_window_actions:
            fatigue[actor].popleft()
        if scenario == "TURTLE" or (scenario == "CARTEL" and actor < 3 and step % 3):
            own = [t for t,o in enumerate(owners) if o == actor and t not in capitals]
            if own and resources[actor] >= 5:
                resources[actor] -= 5; fort[own[step % len(own)]] += 5
            continue
        if scenario == "COMEBACK" and actor == 0:
            targets = [t for t in lost if owners[t] != 0]
            target = targets[0] if targets else n + rng.randrange(3*n)
        else:
            target = n + rng.randrange(3*n)
        defender = owners[target]
        if defender == actor:
            continue
        kind = "raid" if scenario == "RAIDER" or rng.randrange(3) == 0 else "siege"
        base_cost = 10 + rng.randrange(31)
        cost = rules.offensive_cost(base_cost, len(fatigue[actor]))
        if resources[actor] < cost:
            continue
        total_before = sum(resources)
        engineering_defense = min(resources[defender], 10 + fort[target] // 5)
        alliance = 0
        if scenario == "CARTEL" and defender < 3:
            alliance = sum(min(5, resources[x]) for x in range(3) if x != defender)
        defense = rules.defense_power(engineering_defense, fort[target], alliance)
        resources[actor] -= cost; tries[kind] += 1
        if base_cost > defense:
            wins[kind] += 1
            if kind == "raid":
                reward = raid_reward(cost, resources[defender])
                resources[defender] -= reward; resources[actor] += reward
                raid_cost += cost; raid_income += reward
            else:
                owners[target] = actor; fatigue[actor].append(step)
        if sum(resources) > total_before:
            combat_created += sum(resources)-total_before
        if any(x < 0 for x in resources) or any(owners[c] != c for c in capitals):
            invariant_failures.append("economic invariant")
        shares = Counter(owners)
        if dominance_at is None and max(shares.values()) > len(owners)//2:
            dominance_at = step
    territory = Counter(owners); total = sum(resources)
    recovered = len([t for t in lost if owners[t] == 0]) / max(1,len(lost))
    return {"scenario":scenario,"seed":seed,"actions":actions,
        "manifest_hash":rules.manifest_hash,"resource_shares":[x/max(1,total) for x in resources],
        "largest_resource_share":max(resources)/max(1,total),
        "largest_territory_share":max(territory.values())/len(owners),
        "whale_resource_rank":sorted(resources,reverse=True).index(resources[0])+1,
        "combat_resource_creation":combat_created,"circular_raid_profit":raid_income-raid_cost,
        "win_rates":{k:wins[k]/max(1,tries[k]) for k in ("raid","siege")},
        "time_to_dominance":dominance_at,"comeback_recovery":recovered,
        "invariant_failures":sorted(set(invariant_failures)),"technical_creation":created_yield}


def run_sweep(base: EconomicRulesV02, actions: int = 50_000) -> dict:
    candidates = []
    for rules in _manifest_candidates(base):
        runs = [simulate_scenario(rules, scenario, seed, actions)
                for scenario in SCENARIOS for seed in SEEDS]
        comeback = [r["comeback_recovery"] for r in runs if r["scenario"] == "COMEBACK"]
        whale10 = [r["largest_territory_share"] for r in runs if r["scenario"] == "WHALE_10X"]
        violations = sum(len(r["invariant_failures"]) + (r["combat_resource_creation"] != 0)
                         + (r["circular_raid_profit"] >= 0 and r["circular_raid_profit"] != 0)
                         for r in runs)
        score = violations * 1000 + sum(whale10) / len(whale10) - sum(comeback) / len(comeback)
        candidates.append({"manifest":asdict(rules),"manifest_hash":rules.manifest_hash,
                           "score":score,"runs":runs})
    selected = min(candidates, key=lambda x:(x["score"],x["manifest_hash"]))
    return {"search_version":"balance-search-v0.2","seeds":list(SEEDS),
            "scenarios":list(SCENARIOS),"actions_per_run":actions,
            "candidates":candidates,"selected_manifest_hash":selected["manifest_hash"],
            "previous":{"whale_resource_share":0.6986,"comeback_recovery":0.0}}


def main(argv=None) -> int:
    p=argparse.ArgumentParser(); p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--actions",type=int,default=50_000); p.add_argument("--json-output",type=Path,required=True)
    p.add_argument("--markdown-output",type=Path,required=True); a=p.parse_args(argv)
    sweep=run_sweep(EconomicRulesV02.from_manifest(json.loads(a.manifest.read_text())),a.actions)
    a.json_output.parent.mkdir(parents=True,exist_ok=True)
    a.json_output.write_text(json.dumps(sweep,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    selected=next(x for x in sweep["candidates"] if x["manifest_hash"]==sweep["selected_manifest_hash"])
    runs=selected["runs"]; comeback=[r["comeback_recovery"] for r in runs if r["scenario"]=="COMEBACK"]
    whale=[r["largest_resource_share"] for r in runs if r["scenario"]=="WHALE_10X"]
    md=("# Balance v0.2 deterministic sweep\n\n"
        f"- Seeds: `{sweep['seeds']}`\n- Scenarios: `{sweep['scenarios']}`\n"
        f"- Actions per run: `{a.actions}`\n- Candidate manifests: `{len(sweep['candidates'])}`\n"
        f"- Selected manifest hash: `{sweep['selected_manifest_hash']}`\n"
        f"- Previous WHALE share: `69.86%`; selected mean WHALE_10X resource share: `{sum(whale)/len(whale):.2%}`\n"
        f"- Previous comeback: `0%`; selected mean productive comeback recovery: `{sum(comeback)/len(comeback):.2%}`\n"
        f"- Invariant failures: `{sum(len(r['invariant_failures']) for r in runs)}`\n"
        f"- Combat-created resources: `{sum(r['combat_resource_creation'] for r in runs)}`\n")
    a.markdown_output.write_text(md,encoding="utf-8"); print(md); return 0


if __name__ == "__main__": raise SystemExit(main())
