from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, asdict
import json, random, statistics
from pathlib import Path

from .gate_a import RESOURCES, derive_power


@dataclass(frozen=True)
class GateBParams:
    empires: int = 16
    territories: int = 64
    epochs: int = 56
    base_territory_production: int = 6
    strategic_territory_bonus: int = 5
    fortify_cost: int = 12
    raid_cost: int = 14
    siege_cost: int = 24
    recon_cost: int = 8
    upkeep_per_noncapital: int = 3
    overextension_free_territories: int = 5
    overextension_cost_per_territory: int = 2
    trade_max_stockpile_bp: int = 2500
    trade_cooldown_epochs: int = 1
    recon_fresh_epochs: int = 1
    recon_aging_epochs: int = 2
    nap_min_epochs: int = 4
    nap_exit_cooldown_epochs: int = 2
    endgame_epochs: int = 8
    hegemon_min_share_bp: int = 1800
    hegemon_lead_over_second_bp: int = 3000
    hegemon_sustain_epochs: int = 4
    momentum_deadband_bp: int = 500
    late_join_boost_bp: int = 18750
    late_join_protection_epochs: int = 4


DEFAULT_PARAMS = GateBParams()
STANDING_ORDER = ("Domain", "Regional", "Major", "Great", "Dominant", "Hegemon")
SCENARIOS = ("BALANCED", "WHALE", "CARTEL", "TRADER_RING", "LATE_JOIN", "AGGRESSIVE")
VICTORY_WEIGHTS_BP = {"territory_value":3000,"power":2500,"production":1500,"objective_points":2000,"hegemon_epochs":1000}
SEEDS = (7, 11, 19, 29, 41, 53, 67, 79, 97, 107)


def _ring_edges(n: int) -> set[tuple[int, int]]:
    edges=set()
    for i in range(n):
        edges.add(tuple(sorted((i,(i+1)%n))))
        edges.add(tuple(sorted((i,(i+2)%n))))
    return edges


def _initial_world(p: GateBParams):
    owners=[i % p.empires for i in range(p.territories)]
    capitals=set(range(p.empires))
    strategic={t for t in range(p.empires, p.territories) if t % 7 == 0}
    edges=_ring_edges(p.territories)
    return owners, capitals, strategic, edges


def _territories_of(owners, empire):
    return [i for i,o in enumerate(owners) if o==empire]


def _noncap_count(owners, capitals, empire):
    return sum(1 for t,o in enumerate(owners) if o==empire and t not in capitals)


def _production_for(owners, strategic, empire, p):
    total=0
    for t,o in enumerate(owners):
        if o!=empire: continue
        total += p.base_territory_production + (p.strategic_territory_bonus if t in strategic else 0)
    return total


def _standing_from_rank(rank: int, total: int) -> str:
    q=rank/max(1,total)
    if q <= .06: return "Dominant"
    if q <= .18: return "Great"
    if q <= .38: return "Major"
    if q <= .70: return "Regional"
    return "Domain"


def _shares(values):
    total=sum(values)
    return [v/max(1,total) for v in values]


def _gini(values):
    vals=sorted(values)
    n=len(vals); total=sum(vals)
    if not total: return 0.0
    weighted=sum((i+1)*v for i,v in enumerate(vals))
    return (2*weighted)/(n*total) - (n+1)/n


def simulate(seed: int, scenario: str, p: GateBParams = DEFAULT_PARAMS) -> dict:
    rng=random.Random(seed)
    owners,capitals,strategic,edges=_initial_world(p)
    balances=[{r:100 for r in RESOURCES} for _ in range(p.empires)]
    if scenario=="WHALE":
        for r in RESOURCES: balances[0][r]=500
    if scenario=="LATE_JOIN":
        for r in RESOURCES: balances[-1][r]=0
    fort=[0]*p.territories
    recon_until={}
    napsed=set(); alliances=set(); last_trade={}
    breach_count=0; attacks=Counter(); trades=0; rejected_trades=0
    trade_volume=0; trade_created=0; nap_blocks=0; alliance_support_events=0
    hegemon_streak=[0]*p.empires; hegemon_epochs=[0]*p.empires
    standing_history=[[] for _ in range(p.empires)]
    power_history=[[] for _ in range(p.empires)]
    score_history=[[] for _ in range(p.empires)]
    objective_points=[0]*p.empires
    late_join_epoch=p.epochs//2

    for epoch in range(p.epochs):
        active_empires=range(p.empires-1) if scenario=="LATE_JOIN" and epoch<late_join_epoch else range(p.empires)
        for e in active_empires:
            prod=_production_for(owners,strategic,e,p)
            if scenario=="LATE_JOIN" and e==p.empires-1 and epoch>=late_join_epoch:
                prod=prod*p.late_join_boost_bp//10000
            for r in RESOURCES:
                balances[e][r]+=prod//3
            noncap=_noncap_count(owners,capitals,e)
            upkeep=noncap*p.upkeep_per_noncapital + max(0,noncap-p.overextension_free_territories)*p.overextension_cost_per_territory
            balances[e]["ENGINEERING"]=max(0,balances[e]["ENGINEERING"]-upkeep)

        # diplomacy: deterministic NAP/alliance opportunities; cartel coordinates more often.
        for e in active_empires:
            other=(e+1)%p.empires
            if scenario=="CARTEL" and e<4 and other<4:
                alliances.add(tuple(sorted((e,other))))
            elif epoch%8==0 and rng.random()<.22:
                napsed.add((tuple(sorted((e,other))),epoch+p.nap_min_epochs))

        # basic trade, including adversarial ring scenario.
        for e in active_empires:
            other=(e+1)%p.empires
            wants_trade=(scenario=="TRADER_RING" or rng.random()<.12)
            if not wants_trade: continue
            pair=(e,other)
            if epoch-last_trade.get(pair,-99)<p.trade_cooldown_epochs:
                rejected_trades+=1; continue
            offered=min(balances[e]["ENGINEERING"]*p.trade_max_stockpile_bp//10000,20)
            requested=min(balances[other]["KNOWLEDGE"]*p.trade_max_stockpile_bp//10000,20)
            if offered<=0 or requested<=0:
                rejected_trades+=1; continue
            before=sum(sum(b.values()) for b in balances)
            balances[e]["ENGINEERING"]-=offered; balances[other]["ENGINEERING"]+=offered
            balances[other]["KNOWLEDGE"]-=requested; balances[e]["KNOWLEDGE"]+=requested
            after=sum(sum(b.values()) for b in balances)
            trade_created+=max(0,after-before); trade_volume+=offered+requested; trades+=1; last_trade[pair]=epoch

        # recon creates temporary information availability, not resources.
        for e in active_empires:
            if balances[e]["KNOWLEDGE"]>=p.recon_cost and rng.random()<.10:
                target=(e+3)%p.empires
                balances[e]["KNOWLEDGE"]-=p.recon_cost
                recon_until[(e,target)]=epoch+p.recon_fresh_epochs+p.recon_aging_epochs

        # one attack opportunity per empire per epoch.
        for e in active_empires:
            own={t for t,o in enumerate(owners) if o==e}
            frontier={b if a in own else a for a,b in edges if (a in own) ^ (b in own)}
            targets=[t for t in sorted(frontier) if owners[t]!=e and t not in capitals]
            if not targets: continue
            target=targets[(epoch+e+seed)%len(targets)]
            defender=owners[target]
            pair=tuple(sorted((e,defender)))
            active_nap=any(pp==pair and epoch<until for pp,until in napsed)
            if active_nap:
                nap_blocks+=1
                if scenario!="AGGRESSIVE" or rng.random()>=.08:
                    continue
                # explicit early breach; attack may proceed and breach is factual.
                breach_count+=1
                napsed={x for x in napsed if x[0]!=pair}
            kind="RAID" if rng.random()<(.55 if scenario=="AGGRESSIVE" else .35) else "SIEGE"
            minimum=p.raid_cost if kind=="RAID" else p.siege_cost
            attack_power=max(minimum,8+((epoch*7+e*11+seed)%33))
            defender_commit=min(8+((epoch*5+defender*13+target)%33),balances[defender]["ENGINEERING"])
            if balances[e]["ENGINEERING"]<attack_power: continue
            balances[e]["ENGINEERING"]-=attack_power
            allied=0
            if scenario=="CARTEL" and defender<4:
                ally=(defender+1)%4
                if ally==e: ally=(defender+2)%4
                if ally!=e and balances[ally]["ENGINEERING"]>=5:
                    allied+=5; alliance_support_events+=1
            elif pair in alliances:
                ally=(defender+1)%p.empires
                if ally!=e and balances[ally]["ENGINEERING"]>=5:
                    allied+=5; alliance_support_events+=1
            defense=defender_commit*11000//10000 + fort[target] + allied
            success=attack_power>defense
            attacks[(kind,"success" if success else "failure")]+=1
            if not success: continue
            if kind=="RAID":
                reward=min(attack_power//2,balances[defender]["ENGINEERING"])
                balances[defender]["ENGINEERING"]-=reward; balances[e]["ENGINEERING"]+=reward
            elif target not in capitals:
                owners[target]=e

        # fortification competes with offense.
        for e in active_empires:
            own=[t for t in _territories_of(owners,e) if t not in capitals]
            if own and balances[e]["ENGINEERING"]>=p.fortify_cost and rng.random()<.18:
                t=own[(epoch+e)%len(own)]
                balances[e]["ENGINEERING"]-=p.fortify_cost
                fort[t]+=p.fortify_cost

        powers=[derive_power(b) for b in balances]
        territory_values=[]; productions=[]; strategic_capacity=[]
        for e in range(p.empires):
            territory_values.append(sum(1+(2 if t in strategic else 0) for t,o in enumerate(owners) if o==e))
            productions.append(_production_for(owners,strategic,e,p))
            strategic_capacity.append(sum(fort[t] for t,o in enumerate(owners) if o==e)+powers[e]//10)
        composite=[powers[e]+20*territory_values[e]+productions[e]+strategic_capacity[e] for e in range(p.empires)]
        ranked=sorted(range(p.empires),key=lambda e:(-composite[e],e))
        shares=_shares(composite)
        leader=ranked[0]; second=ranked[1]
        lead_ratio=(composite[leader]-composite[second])*10000//max(1,composite[second])
        qualifies=shares[leader]*10000>=p.hegemon_min_share_bp and lead_ratio>=p.hegemon_lead_over_second_bp
        for e in range(p.empires):
            hegemon_streak[e]=hegemon_streak[e]+1 if e==leader and qualifies else 0
            if hegemon_streak[e]>=p.hegemon_sustain_epochs: hegemon_epochs[e]+=1
        active_hegemon=leader if hegemon_streak[leader]>=p.hegemon_sustain_epochs else None
        if epoch>=p.epochs-p.endgame_epochs:
            objective_points[leader]+=5
        component_totals={"territory_value":sum(territory_values),"power":sum(powers),"production":sum(productions),"objective_points":sum(objective_points),"hegemon_epochs":sum(hegemon_epochs)}
        for rank,e in enumerate(ranked,1):
            standing="Hegemon" if e==active_hegemon else _standing_from_rank(rank,p.empires)
            standing_history[e].append(standing); power_history[e].append(powers[e])
            values={"territory_value":territory_values[e],"power":powers[e],"production":productions[e],"objective_points":objective_points[e],"hegemon_epochs":hegemon_epochs[e]}
            score=0
            for name,weight in VICTORY_WEIGHTS_BP.items():
                total=component_totals[name]
                score += (values[name]*10000//total if total else 0)*weight//10000
            score_history[e].append(score)

    final_power=[derive_power(b) for b in balances]
    territory_counts=Counter(owners)
    final_scores=[history[-1] for history in score_history]
    standings=[history[-1] for history in standing_history]
    leader=max(range(p.empires),key=lambda e:(final_scores[e],-e))
    late=p.empires-1
    return {
        "scenario":scenario,"seed":seed,"params":asdict(p),
        "final_power":final_power,"power_gini":_gini(final_power),
        "territory_counts":[territory_counts[e] for e in range(p.empires)],
        "largest_territory_share":max(territory_counts.values())/p.territories,
        "standings":standings,"hegemon_count":sum(s=="Hegemon" for s in standings),
        "hegemon_epochs":hegemon_epochs,"winner":leader,
        "final_scores":final_scores,
        "final_victory_inputs":[{"territory_value":sum(1+(2 if t in strategic else 0) for t,o in enumerate(owners) if o==e),"power":final_power[e],"production":_production_for(owners,strategic,e,p),"objective_points":objective_points[e],"hegemon_epochs":hegemon_epochs[e]} for e in range(p.empires)],
        "attack_count":sum(attacks.values()),
        "raid_success_rate":attacks[("RAID","success")]/max(1,attacks[("RAID","success")]+attacks[("RAID","failure")]),
        "siege_success_rate":attacks[("SIEGE","success")]/max(1,attacks[("SIEGE","success")]+attacks[("SIEGE","failure")]),
        "nap_blocks":nap_blocks,"breaches":breach_count,"alliance_support_events":alliance_support_events,
        "trades":trades,"rejected_trades":rejected_trades,"trade_volume":trade_volume,"trade_created":trade_created,
        "recon_snapshots":len(recon_until),
        "late_join_power_ratio":final_power[late]/max(1,statistics.median(final_power[:-1])),
        "late_join_territories":territory_counts[late],
        "pre_endgame_leader":max(range(p.empires),key=lambda e:(score_history[e][max(0,p.epochs-p.endgame_epochs-1)],-e)),
        "endgame_flip":max(range(p.empires),key=lambda e:(score_history[e][max(0,p.epochs-p.endgame_epochs-1)],-e))!=leader,
        "winner_hegemon_epochs":hegemon_epochs[leader],
        "final_standing_counts":dict(Counter(standings)),
        "resource_nonnegative":all(v>=0 for b in balances for v in b.values()),
        "capitals_intact":all(owners[c]==c for c in capitals),
        "final_resource_total":sum(sum(b.values()) for b in balances),
    }


def summarize(rows: list[dict]) -> dict:
    def mean(key): return statistics.mean(r[key] for r in rows)
    return {
        "runs":len(rows),
        "power_gini":mean("power_gini"),
        "largest_territory_share":mean("largest_territory_share"),
        "raid_success_rate":mean("raid_success_rate"),
        "siege_success_rate":mean("siege_success_rate"),
        "attack_count":mean("attack_count"),
        "nap_blocks":mean("nap_blocks"),"breaches":mean("breaches"),
        "alliance_support_events":mean("alliance_support_events"),
        "trades":mean("trades"),"trade_volume":mean("trade_volume"),
        "trade_created":sum(r["trade_created"] for r in rows),
        "hegemon_frequency":sum(r["hegemon_count"]==1 for r in rows)/len(rows),
        "multi_hegemon_failures":sum(r["hegemon_count"]>1 for r in rows),
        "capital_failures":sum(not r["capitals_intact"] for r in rows),
        "negative_balance_failures":sum(not r["resource_nonnegative"] for r in rows),
        "late_join_power_ratio":mean("late_join_power_ratio"),
        "late_join_territories":mean("late_join_territories"),
        "endgame_flip_rate":sum(r["endgame_flip"] for r in rows)/len(rows),
        "winner_hegemon_epochs":mean("winner_hegemon_epochs"),
    }


def run_matrix(p: GateBParams = DEFAULT_PARAMS) -> dict:
    by={}
    all_rows=[]
    for scenario in SCENARIOS:
        rows=[simulate(seed,scenario,p) for seed in SEEDS]
        by[scenario]=summarize(rows); all_rows.extend(rows)
    invariants={
        "trade_resource_creation":sum(r["trade_created"] for r in all_rows),
        "capital_failures":sum(not r["capitals_intact"] for r in all_rows),
        "negative_balance_failures":sum(not r["resource_nonnegative"] for r in all_rows),
        "multi_hegemon_failures":sum(r["hegemon_count"]>1 for r in all_rows),
    }
    return {"schema":"gate-b-simulation-v0.1","params":asdict(p),"seeds":list(SEEDS),"scenarios":list(SCENARIOS),"by_scenario":by,"invariants":invariants,"rows":all_rows}


def write_report(report: dict, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True,exist_ok=True)
    json_path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    b=report["by_scenario"]
    inv=report["invariants"]
    lines=["# Gate B strategic simulation","",f"Runs: {len(report['rows'])} ({len(report['scenarios'])} scenarios x {len(report['seeds'])} seeds).","",
        f"Invariant failures: capital={inv['capital_failures']}, negative_balance={inv['negative_balance_failures']}, trade_mint={inv['trade_resource_creation']}, multi_hegemon={inv['multi_hegemon_failures']}.","",
        "## Scenario summary","",
    ]
    for name in report["scenarios"]:
        x=b[name]
        lines.append(f"- {name}: territory leader {x['largest_territory_share']:.1%}, power Gini {x['power_gini']:.3f}, raid {x['raid_success_rate']:.1%}, siege {x['siege_success_rate']:.1%}, hegemon runs {x['hegemon_frequency']:.0%}, trades {x['trades']:.1f}.")
    lines += ["","## Late join","",f"- Final power vs median established empire: {b['LATE_JOIN']['late_join_power_ratio']:.1%}.",f"- Final territories: {b['LATE_JOIN']['late_join_territories']:.2f} average.","",
        "## Interpretation","","This is a Gate B tuning model, not authoritative gameplay execution. Parameters that fail balance targets must move before Season 0 freeze; Gate A invariants remain unchanged."]
    md_path.write_text("\n".join(lines)+"\n",encoding="utf-8")


if __name__=="__main__":
    r=run_matrix(); write_report(r,Path("reports/gate-b-simulation.json"),Path("reports/gate-b-simulation.md")); print(json.dumps({"invariants":r["invariants"],"scenarios":r["by_scenario"]},sort_keys=True))


def candidate_params() -> list[GateBParams]:
    base=DEFAULT_PARAMS
    return [
        GateBParams(**{**asdict(base),"siege_cost":20}),
        GateBParams(**{**asdict(base),"siege_cost":22}),
        base,
        GateBParams(**{**asdict(base),"siege_cost":26}),
    ]

def tuning_score(report: dict) -> tuple[float, dict]:
    b=report["by_scenario"]; inv=report["invariants"]
    balanced=b["BALANCED"]; whale=b["WHALE"]; late=b["LATE_JOIN"]; trader=b["TRADER_RING"]
    penalties=0.0
    # Target meaningful but non-automatic combat.
    penalties += abs(balanced["raid_success_rate"]-.55)*5
    penalties += abs(balanced["siege_success_rate"]-.50)*7
    # Late join should become viable, not equivalent to day-one immediately.
    if late["late_join_power_ratio"]<.65: penalties+=(.65-late["late_join_power_ratio"])*8
    if late["late_join_power_ratio"]>1.05: penalties+=(late["late_join_power_ratio"]-1.05)*4
    # Whale may become hegemon, but not deterministically.
    penalties += abs(whale["hegemon_frequency"]-.50)*2
    if whale["largest_territory_share"]>.30: penalties+=(whale["largest_territory_share"]-.30)*10
    if trader["power_gini"]>.20: penalties+=(trader["power_gini"]-.20)*5
    penalties += 1000*sum(inv.values())
    metrics={"balanced_raid":balanced["raid_success_rate"],"balanced_siege":balanced["siege_success_rate"],
        "late_join_power_ratio":late["late_join_power_ratio"],"whale_hegemon_frequency":whale["hegemon_frequency"],
        "whale_territory_share":whale["largest_territory_share"],"trader_power_gini":trader["power_gini"]}
    return penalties,metrics


def run_tuning() -> dict:
    candidates=[]
    for idx,p in enumerate(candidate_params()):
        report=run_matrix(p); score,metrics=tuning_score(report)
        candidates.append({"candidate":idx,"params":asdict(p),"score":score,"metrics":metrics,"invariants":report["invariants"]})
    selected=min(candidates,key=lambda x:(x["score"],x["candidate"]))
    return {"schema":"gate-b-tuning-v0.1","candidates":candidates,"selected_candidate":selected["candidate"]}
