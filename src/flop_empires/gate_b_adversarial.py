from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
import json, random, statistics
from pathlib import Path

from .gate_a import RESOURCES, derive_power
from .gate_b import GateBParams, DEFAULT_PARAMS, VICTORY_WEIGHTS_BP

STRATEGIES = (
    "BALANCED", "TERRITORIAL", "ECONOMIC", "DIPLOMATIC",
    "TURTLE", "RAIDER", "COALITION", "TRADER",
)


@dataclass(frozen=True)
class Policy:
    siege: int
    raid: int
    fortify: int
    trade: int
    nap: int
    alliance: int
    recon: int
POLICIES = {
    "BALANCED": Policy(40,35,25,20,20,20,15),
    "TERRITORIAL": Policy(75,10,20,5,5,10,10),
    "ECONOMIC": Policy(10,10,10,45,25,10,15),
    "DIPLOMATIC": Policy(15,10,15,20,70,65,20),
    "TURTLE": Policy(10,5,80,10,35,35,20),
    "RAIDER": Policy(10,80,10,5,5,5,25),
    "COALITION": Policy(35,15,25,15,40,80,20),
    "TRADER": Policy(5,5,10,90,30,15,15),
}


def _ring_edges(n: int) -> set[tuple[int,int]]:
    edges=set()
    for i in range(n):
        edges.add(tuple(sorted((i,(i+1)%n))))
        edges.add(tuple(sorted((i,(i+2)%n))))
    return edges


def _world(p: GateBParams):
    owners=[i % p.empires for i in range(p.territories)]
    capitals=set(range(p.empires))
    strategic={t for t in range(p.empires,p.territories) if t%7==0}
    return owners,capitals,strategic,_ring_edges(p.territories)
def _prod(owners, strategic, empire, p):
    return sum(p.base_territory_production + (p.strategic_territory_bonus if t in strategic else 0)
               for t,o in enumerate(owners) if o==empire)


def _noncap(owners, capitals, empire):
    return sum(1 for t,o in enumerate(owners) if o==empire and t not in capitals)


def _territory_value(owners, strategic, empire):
    return sum(1 + (2 if t in strategic else 0) for t,o in enumerate(owners) if o==empire)


def _chance(rng, pct):
    return rng.randrange(100) < pct


def _score_components(values_by_empire):
    names=("territory_value","power","production","objective_points","hegemon_epochs")
    totals={n:sum(v[n] for v in values_by_empire) for n in names}
    out=[]
    for values in values_by_empire:
        score=0
        for name,weight in VICTORY_WEIGHTS_BP.items():
            share=values[name]*10000//totals[name] if totals[name] else 0
            score += share*weight//10000
        out.append(score)
    return out
def simulate_mixed(seed: int, p: GateBParams = DEFAULT_PARAMS) -> dict:
    rng=random.Random(seed)
    owners,capitals,strategic,edges=_world(p)
    strategies=[STRATEGIES[i % len(STRATEGIES)] for i in range(p.empires)]
    rng.shuffle(strategies)
    balances=[{r:100 for r in RESOURCES} for _ in range(p.empires)]
    fort=[0]*p.territories
    napsed={}; alliances=set(); coalition=frozenset({5,6,13,14})
    last_trade={}; attacks=Counter(); trades=Counter(); support=Counter(); trade_partners=[set() for _ in range(p.empires)]
    hegemon_streak=[0]*p.empires; hegemon_epochs=[0]*p.empires
    objective_points=[0]*p.empires; score_history=[[] for _ in range(p.empires)]

    for epoch in range(p.epochs):
        for e in range(p.empires):
            prod=_prod(owners,strategic,e,p)
            for r in RESOURCES: balances[e][r]+=prod//3
            noncap=_noncap(owners,capitals,e)
            upkeep=noncap*p.upkeep_per_noncapital + max(0,noncap-p.overextension_free_territories)*p.overextension_cost_per_territory
            balances[e]["ENGINEERING"]=max(0,balances[e]["ENGINEERING"]-upkeep)

        for e,strategy in enumerate(strategies):
            pol=POLICIES[strategy]; other=(e+1)%p.empires; pair=tuple(sorted((e,other)))
            if _chance(rng,pol.nap) and pair not in napsed:
                napsed[pair]=epoch+p.nap_min_epochs
            if _chance(rng,pol.alliance): alliances.add(pair)
            if strategy=="COALITION" and e in coalition:
                for x in coalition:
                    if x!=e: alliances.add(tuple(sorted((e,x))))
        for e,strategy in enumerate(strategies):
            pol=POLICIES[strategy]; other=(e+1)%p.empires
            if _chance(rng,pol.trade):
                pair=(e,other)
                if epoch-last_trade.get(pair,-99)>=p.trade_cooldown_epochs:
                    offer_cap=min(20,balances[e]["ENGINEERING"]*p.trade_max_stockpile_bp//10000)
                    request_cap=min(20,balances[other]["KNOWLEDGE"]*p.trade_max_stockpile_bp//10000)
                    amount=min(offer_cap,request_cap)
                    if amount>0:
                        balances[e]["ENGINEERING"]-=amount; balances[other]["ENGINEERING"]+=amount
                        balances[other]["KNOWLEDGE"]-=amount; balances[e]["KNOWLEDGE"]+=amount
                        trades[strategy]+=2*amount; last_trade[pair]=epoch
                        trade_partners[e].add(other); trade_partners[other].add(e)
            if _chance(rng,pol.fortify):
                own=[t for t,o in enumerate(owners) if o==e and t not in capitals]
                if own and balances[e]["ENGINEERING"]>=p.fortify_cost:
                    t=own[(epoch+e)%len(own)]
                    balances[e]["ENGINEERING"]-=p.fortify_cost; fort[t]+=p.fortify_cost

        for e,strategy in enumerate(strategies):
            pol=POLICIES[strategy]
            want_raid=_chance(rng,pol.raid); want_siege=_chance(rng,pol.siege)
            if not (want_raid or want_siege): continue
            kind="RAID" if want_raid and not want_siege else "SIEGE" if want_siege and not want_raid else ("RAID" if rng.randrange(2)==0 else "SIEGE")
            own={t for t,o in enumerate(owners) if o==e}
            frontier={b if a in own else a for a,b in edges if (a in own) ^ (b in own)}
            targets=[t for t in sorted(frontier) if owners[t]!=e and t not in capitals]
            if not targets: continue
            if strategy=="TERRITORIAL":
                targets.sort(key=lambda t:(-(2 if t in strategic else 0), fort[t], t))
            elif strategy=="RAIDER":
                targets.sort(key=lambda t:(fort[t], t))
            target=targets[(seed+epoch+e)%min(len(targets),8)]
            defender=owners[target]; pair=tuple(sorted((e,defender)))
            if epoch<napsed.get(pair,-1): continue
            minimum=p.raid_cost if kind=="RAID" else p.siege_cost
            attack_power=max(minimum,8+((epoch*7+e*11+seed)%33))
            if balances[e]["ENGINEERING"]<attack_power: continue
            dcommit=min(8+((epoch*5+defender*13+target)%33),balances[defender]["ENGINEERING"])
            balances[e]["ENGINEERING"]-=attack_power
            allied=0
            allies=[x for x in range(p.empires) if x not in {e,defender} and tuple(sorted((defender,x))) in alliances]
            for ally in allies[:2]:
                if balances[ally]["ENGINEERING"]>=5:
                    allied+=5; support[strategies[defender]]+=1
            defense=dcommit*11000//10000 + fort[target] + allied
            success=attack_power>defense
            attacks[(strategy,kind,"success" if success else "failure")]+=1
            if not success: continue
            if kind=="RAID":
                reward=min(attack_power//2,balances[defender]["ENGINEERING"])
                balances[defender]["ENGINEERING"]-=reward; balances[e]["ENGINEERING"]+=reward
            else:
                owners[target]=e

        powers=[derive_power(b) for b in balances]
        territory=[_territory_value(owners,strategic,e) for e in range(p.empires)]
        productions=[_prod(owners,strategic,e,p) for e in range(p.empires)]
        composite=[powers[e]+20*territory[e]+productions[e]+sum(fort[t] for t,o in enumerate(owners) if o==e)+powers[e]//10 for e in range(p.empires)]
        ranked=sorted(range(p.empires),key=lambda e:(-composite[e],e)); leader,second=ranked[:2]
        share=composite[leader]*10000//max(1,sum(composite)); lead=(composite[leader]-composite[second])*10000//max(1,composite[second])
        qualifies=share>=p.hegemon_min_share_bp and lead>=p.hegemon_lead_over_second_bp
        for e in range(p.empires):
            hegemon_streak[e]=hegemon_streak[e]+1 if e==leader and qualifies else 0
            if hegemon_streak[e]>=p.hegemon_sustain_epochs: hegemon_epochs[e]+=1
        if epoch>=p.epochs-p.endgame_epochs:
            median_power=statistics.median(derive_power(b) for b in balances)
            median_production=statistics.median(_prod(owners,strategic,x,p) for x in range(p.empires))
            median_reserve=statistics.median(min(b.values()) for b in balances)
            for e,strategy in enumerate(strategies):
                own_strategic=sum(o==e and t in strategic for t,o in enumerate(owners))
                own_fort=sum(fort[t] for t,o in enumerate(owners) if o==e)
                ally_count=sum(e in pair for pair in alliances)
                active_naps=sum(e in pair and epoch<until for pair,until in napsed.items())
                raid_wins=attacks[(strategy,"RAID","success")]
                gains=[]
                if own_strategic>=2: gains.append(2)
                if derive_power(balances[e])>=median_power: gains.append(1)
                if _prod(owners,strategic,e,p)>=median_production: gains.append(2)
                if min(balances[e].values())>=median_reserve: gains.append(2)
                if ally_count>=2 and active_naps>=1: gains.append(2)
                if own_fort>=48: gains.append(2)
                if raid_wins>=4: gains.append(2)
                if support[strategy]>=4: gains.append(2)
                if len(trade_partners[e])>=3: gains.append(2)
                objective_points[e]+=min(4,sum(gains))
        values=[]
        for e in range(p.empires):
            values.append({"territory_value":territory[e],"power":powers[e],"production":productions[e],
                "objective_points":objective_points[e],"hegemon_epochs":hegemon_epochs[e]})
        scores=_score_components(values)
        for e in range(p.empires): score_history[e].append(scores[e])

    final_scores=[h[-1] for h in score_history]
    winner=max(range(p.empires),key=lambda e:(final_scores[e],-e))
    positions=sorted(range(p.empires),key=lambda e:(-final_scores[e],e))
    by_strategy={}
    for strategy in STRATEGIES:
        ids=[e for e,s in enumerate(strategies) if s==strategy]
        ranks=[positions.index(e)+1 for e in ids]
        by_strategy[strategy]={
            "mean_rank":statistics.mean(ranks),
            "wins":sum(e==winner for e in ids),
            "mean_power":statistics.mean(derive_power(balances[e]) for e in ids),
            "mean_territories":statistics.mean(sum(o==e for o in owners) for e in ids),
            "trade_volume":trades[strategy],
            "alliance_support":support[strategy],
            "mean_score":statistics.mean(final_scores[e] for e in ids),
            "mean_objectives":statistics.mean(objective_points[e] for e in ids),
            "mean_hegemon_epochs":statistics.mean(hegemon_epochs[e] for e in ids),
        }
    return {"seed":seed,"winner":winner,"winner_strategy":strategies[winner],"by_strategy":by_strategy,
        "capitals_intact":all(owners[c]==c for c in capitals),
        "nonnegative":all(v>=0 for b in balances for v in b.values()),
        "hegemon_count":sum(1 for x in hegemon_streak if x>=p.hegemon_sustain_epochs),
        "final_scores":final_scores}
def run_adversarial(seeds=range(1,201), p: GateBParams = DEFAULT_PARAMS) -> dict:
    rows=[simulate_mixed(seed,p) for seed in seeds]
    wins=Counter(r["winner_strategy"] for r in rows)
    summary={}
    for strategy in STRATEGIES:
        strategy_rows=[r["by_strategy"][strategy] for r in rows]
        summary[strategy]={
            "win_rate":wins[strategy]/len(rows),
            "mean_rank":statistics.mean(x["mean_rank"] for x in strategy_rows),
            "mean_power":statistics.mean(x["mean_power"] for x in strategy_rows),
            "mean_territories":statistics.mean(x["mean_territories"] for x in strategy_rows),
            "mean_trade_volume":statistics.mean(x["trade_volume"] for x in strategy_rows),
            "mean_alliance_support":statistics.mean(x["alliance_support"] for x in strategy_rows),
        }
    return {"schema":"gate-b-adversarial-v0.1","runs":len(rows),"params":asdict(p),"summary":summary,
        "max_strategy_win_rate":max(wins.values())/len(rows),"unique_winning_strategies":sum(v>0 for v in wins.values()),
        "capital_failures":sum(not r["capitals_intact"] for r in rows),
        "negative_balance_failures":sum(not r["nonnegative"] for r in rows),
        "multi_hegemon_failures":sum(r["hegemon_count"]>1 for r in rows),"winner_counts":dict(wins)}


def main():
    report=run_adversarial()
    out=Path("reports/gate-b-adversarial.json"); out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
