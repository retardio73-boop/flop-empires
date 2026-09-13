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
                      actions: int = 50_000, comeback_profile: str = "continued", *,
                      historical_weight_bp: int | None = None,
                      alliance_support_bp: int = 10_000) -> dict:
    rng, n = random.Random(seed), 8
    multiplier = {"WHALE_2X":2,"WHALE_5X":5,"WHALE_10X":10}.get(scenario, 1)
    prestige = [1000] * n; prestige[0] *= multiplier
    if scenario == "CONTRIBUTOR": prestige[0] *= 5
    owners = [i % n for i in range(n * 4)]
    capitals = set(range(n)); fort = [0] * len(owners)
    lost = {n, 2*n} if scenario == "COMEBACK" else set()
    if lost:
        prestige[0] = 5000
        for t in lost: owners[t] = 1
    effective_prestige=list(prestige)
    if historical_weight_bp is not None:
        effective_prestige=[p*historical_weight_bp//10_000 for p in prestige]
    resources = [rules.allocate(p)["ENGINEERING"] * 3 for p in effective_prestige]
    fatigue = [deque() for _ in range(n)]
    wins = Counter(); tries = Counter(); raid_cost = raid_income = 0
    combat_created = 0; dominance_at = None; invariant_failures = []
    created_yield = 0
    attribution=[Counter() for _ in range(n)]
    for empire,p in enumerate(prestige):
        attribution[empire]["raw_technical_contribution"]=p
        attribution[empire]["prestige"]=p
        attribution[empire]["gross_spendable_yield"]=rules.spendable_total(effective_prestige[empire])
        attribution[empire]["diminishing_return_loss"]=p-rules.spendable_total(effective_prestige[empire])
    peak_resource=(0.0,0); peak_territory=(0.0,0); above={40:0,50:0,60:0}
    first_above_50=None; first_territory_dominance=None; reversal_time=None; recovery_streak=0; recovery_at=None
    recovery_resource_cost=0; recovery_attacks=0; recovery_defense=0; new_contribution=0
    alliance_support_events=0
    cartel_defenses=cartel_breaches=0
    def observe(step):
        nonlocal peak_resource,peak_territory,first_above_50,first_territory_dominance,reversal_time
        shares=Counter(owners); resource_share=resources[0]/max(1,sum(resources)); territory_share=shares[0]/len(owners)
        if resource_share>peak_resource[0]: peak_resource=(resource_share,step)
        if territory_share>peak_territory[0]: peak_territory=(territory_share,step)
        for threshold in above:
            if resource_share>threshold/100: above[threshold]+=1
        if first_above_50 is None and resource_share>.5: first_above_50=step
        if first_territory_dominance is None and territory_share>.5: first_territory_dominance=step
        if first_territory_dominance is not None and reversal_time is None and step>first_territory_dominance and territory_share<.4:
            reversal_time=step-first_territory_dominance
    for step in range(actions):
        if step % 500 == 0:
            if scenario=="COMEBACK":
                added={"none":0,"low":10,"continued":50,"high":100}.get(comeback_profile,50)
                prestige[0]+=added
                effective_prestige[0]+=added
                if recovery_at is None: new_contribution+=added
                attribution[0]["new_technical_contribution"]+=added
            for empire in range(n):
                noncap = sum(1 for t,o in enumerate(owners) if t not in capitals and o == empire)
                epoch=rules.epoch_attribution(prestige[empire],resources[empire],noncap,
                    sum(fort[t] for t,o in enumerate(owners) if o==empire),
                    effective_prestige=effective_prestige[empire])
                gross=epoch["allocation"]["ENGINEERING"]
                territory_effective=epoch["territory_production"]
                produced=gross+territory_effective
                resources[empire] += produced; created_yield += produced
                resources[empire]-=epoch["total_cost"]
                attribution[empire].update({"gross_yield":gross,"territory_production":territory_effective,
                    "overextension_penalty":epoch["overextension_penalty"],
                    "upkeep":epoch["upkeep"],"stockpile_cost":epoch["stockpile_cost"]})
            if scenario=="COMEBACK":
                recovered_now=sum(owners[t]==0 for t in lost)
                leader=max(resources); positive_net=attribution[0]["gross_yield"]>attribution[0]["upkeep"]+attribution[0]["stockpile_cost"]
                competitive=(recovered_now>=1 and resources[0]>=leader*35//100 and positive_net and
                    resources[0]>=rules.offensive_cost(30,len(fatigue[0])))
                recovery_streak=recovery_streak+1 if competitive else 0
                if recovery_streak>=3 and recovery_at is None: recovery_at=step
        observe(step)
        actor = step % n
        while fatigue[actor] and fatigue[actor][0] <= step-rules.fatigue_window_actions:
            fatigue[actor].popleft()
        if scenario=="COMEBACK" and actor==0 and comeback_profile=="none":
            continue
        if scenario == "TURTLE" or (scenario == "CARTEL" and actor < 3 and step % 3):
            own = [t for t,o in enumerate(owners) if o == actor and t not in capitals]
            if own and resources[actor] >= 5:
                resources[actor] -= 5; fort[own[step % len(own)]] += 5
                if actor==0: recovery_defense+=1; recovery_resource_cost+=5
            continue
        if scenario == "COMEBACK" and actor == 0 and comeback_profile!="none":
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
        sustainable=rules.epoch_allocation(effective_prestige[actor])["ENGINEERING"]
        if scenario not in {"RAIDER","COMEBACK"} and resources[actor] < cost+2*sustainable:
            continue
        if resources[actor] < cost:
            continue
        attribution[actor]["combat_spend"]+=cost
        attribution[actor]["offensive_fatigue_cost"]+=cost-base_cost
        if scenario=="COMEBACK" and actor==0 and recovery_at is None:
            recovery_attacks+=1; recovery_resource_cost+=cost
        total_before = sum(resources)
        engineering_defense = min(resources[defender], 10 + fort[target] // 5)
        alliance = 0
        if scenario == "CARTEL" and defender < 3:
            alliance = sum(min(5, resources[x]) for x in range(3) if x != defender)*alliance_support_bp//10_000
            if alliance: alliance_support_events+=1
            cartel_defenses+=1
        defense = rules.defense_power(engineering_defense, fort[target], alliance)
        resources[actor] -= cost; tries[kind] += 1
        if base_cost > defense:
            if scenario=="CARTEL" and defender<3: cartel_breaches+=1
            wins[kind] += 1
            if kind == "raid":
                reward = raid_reward(cost, resources[defender])
                resources[defender] -= reward; resources[actor] += reward
                raid_cost += cost; raid_income += reward
                attribution[actor]["raid_gains"]+=reward; attribution[defender]["raid_losses"]+=reward
            else:
                old_owner=owners[target]
                owners[target] = actor; fatigue[actor].append(step)
                attribution[actor]["territory_gains"]+=1; attribution[old_owner]["territory_losses"]+=1
        if sum(resources) > total_before:
            combat_created += sum(resources)-total_before
        if any(x < 0 for x in resources) or any(owners[c] != c for c in capitals):
            invariant_failures.append("economic invariant")
        shares = Counter(owners)
        if dominance_at is None and max(shares.values()) > len(owners)//2:
            dominance_at = step
    territory = Counter(owners); total = sum(resources)
    recovered = len([t for t in lost if owners[t] == 0]) / max(1,len(lost))
    for empire,p in enumerate(prestige):
        attribution[empire]["raw_technical_contribution"]=p
        attribution[empire]["prestige"]=p
        attribution[empire]["gross_spendable_yield"]=rules.spendable_total(effective_prestige[empire])
        attribution[empire]["diminishing_return_loss"]=p-rules.spendable_total(effective_prestige[empire])
    viable=sum(1 for empire in range(1,n) if territory[empire]>0 and rules.epoch_allocation(effective_prestige[empire])["ENGINEERING"]>0)
    return {"scenario":scenario,"seed":seed,"actions":actions,
        "manifest_hash":rules.manifest_hash,"resource_shares":[x/max(1,total) for x in resources],
        "largest_resource_share":max(resources)/max(1,total),
        "largest_territory_share":max(territory.values())/len(owners),
        "whale_resource_rank":sorted(resources,reverse=True).index(resources[0])+1,
        "combat_resource_creation":combat_created,"circular_raid_profit":raid_income-raid_cost,
        "win_rates":{k:wins[k]/max(1,tries[k]) for k in ("raid","siege")},
        "attack_count":sum(tries.values()),"successful_raids":wins["raid"],
        "successful_sieges":wins["siege"],"alliance_support_events":alliance_support_events,
        "yield_produced":sum(x["gross_yield"]+x["territory_production"] for x in attribution),
        "upkeep_total":sum(x["upkeep"] for x in attribution),
        "carrying_cost_total":sum(x["stockpile_cost"] for x in attribution),
        "overextension_total":sum(x["overextension_penalty"] for x in attribution),
        "fatigue_cost_total":sum(x["offensive_fatigue_cost"] for x in attribution),
        "focus_resource_share":resources[0]/max(1,total),
        "focus_territory_share":territory[0]/len(owners),
        "cartel_territory_share":sum(v for owner,v in territory.items() if owner<3)/len(owners),
        "cartel_defense_rate":1-cartel_breaches/max(1,cartel_defenses),
        "time_to_dominance":dominance_at,"comeback_recovery":recovered,
        "invariant_failures":sorted(set(invariant_failures)),"technical_creation":created_yield,
        "attribution":[dict(x) for x in attribution],"time_to_peak_share":peak_resource[1],
        "peak_resource_share":peak_resource[0],"peak_territory_share":peak_territory[0],
        "duration_above_40_percent":above[40],"duration_above_50_percent":above[50],
        "duration_above_60_percent":above[60],"reversal_time":reversal_time,
        "number_of_other_empires_still_viable":viable,
        "dominance_reversibility":reversal_time is not None and viable>=3,
        "comeback_profile":comeback_profile,"recovery_definition":"one of two lost territories plus >=35% leader resources, positive net production, viable 30-power siege for 3 epochs",
        "recovery_probability":float(recovery_at is not None),"actions_to_recovery":recovery_at,
        "epochs_to_recovery":None if recovery_at is None else recovery_at//500,
        "resource_cost_to_recovery":recovery_resource_cost,"territory_recovered":int(recovered*len(lost)),
        "prestige_delta":new_contribution,"new_technical_contribution_required":new_contribution,
        "attacks_required":recovery_attacks,"defensive_actions_required":recovery_defense}


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
