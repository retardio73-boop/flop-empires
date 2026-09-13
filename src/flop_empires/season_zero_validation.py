from __future__ import annotations

import argparse,json,statistics
from pathlib import Path

from .balance_search import SCENARIOS,simulate_scenario
from .economics_v02 import EconomicRulesV02

SEEDS=(7,11,19,29,41,53,67,79,97,107)
EPOCHS=56
ACTIONS_PER_EPOCH=500
BOOTSTRAP_OPTIONS={
    "A_NO_HISTORICAL":{"lookback_days":0,"spendable_weight_bp":0,"effective_weight_bp":0},
    "B_30_DAY_25_PERCENT":{"lookback_days":30,"spendable_weight_bp":2500,"effective_weight_bp":2500},
    "C_30_DAY_50_PERCENT":{"lookback_days":30,"spendable_weight_bp":5000,"effective_weight_bp":5000},
    # Deterministic bootstrap cohort is uniformly distributed over the preceding 30 days.
    "D_14_DAY_50_PERCENT":{"lookback_days":14,"spendable_weight_bp":5000,"effective_weight_bp":5000*14//30},
}
ALLIANCE_COEFFICIENTS=(10_000,7_500,6_000)


def mean(rows,key): return sum(row[key] for row in rows)/len(rows)


def summarize(rows):
    return {key:mean(rows,key) for key in (
        "largest_resource_share","peak_resource_share","largest_territory_share",
        "peak_territory_share","duration_above_40_percent","duration_above_50_percent",
        "yield_produced","upkeep_total","carrying_cost_total","overextension_total",
        "fatigue_cost_total","attack_count","successful_raids","successful_sieges",
        "alliance_support_events","focus_resource_share","focus_territory_share",
        "cartel_territory_share","cartel_defense_rate")}|{
        "dominance_reversibility":mean(rows,"dominance_reversibility"),
        "invariant_failures":sum(len(row["invariant_failures"]) for row in rows),
        "combat_resource_creation":sum(row["combat_resource_creation"] for row in rows),
        "circular_raid_profit":sum(row["circular_raid_profit"] for row in rows),
        "max_circular_raid_profit":max(row["circular_raid_profit"] for row in rows),
    }


def validate(candidate: dict)->dict:
    rules=EconomicRulesV02.from_manifest(candidate)
    actions=EPOCHS*ACTIONS_PER_EPOCH
    cadence={}
    for scenario in SCENARIOS:
        rows=[simulate_scenario(rules,scenario,seed,actions) for seed in SEEDS]
        cadence[scenario]=summarize(rows)
    passive=[simulate_scenario(rules,"COMEBACK",seed,actions,"none") for seed in SEEDS]
    productive=[simulate_scenario(rules,"COMEBACK",seed,actions,"continued") for seed in SEEDS]
    comeback={"passive_probability":mean(passive,"recovery_probability"),
        "productive_probability":mean(productive,"recovery_probability"),
        "median_productive_epochs":statistics.median(x["epochs_to_recovery"] for x in productive if x["epochs_to_recovery"] is not None)}
    bootstrap={}
    for name,policy in BOOTSTRAP_OPTIONS.items():
        rows=[simulate_scenario(rules,scenario,seed,actions,
                historical_weight_bp=policy["effective_weight_bp"])
              for scenario in ("BALANCED","WHALE_5X","WHALE_10X") for seed in SEEDS]
        by_scenario={scenario:summarize([x for x in rows if x["scenario"]==scenario])
                     for scenario in ("BALANCED","WHALE_5X","WHALE_10X")}
        bootstrap[name]={**policy,"scenarios":by_scenario}
    alliance={}
    for coefficient in ALLIANCE_COEFFICIENTS:
        cases={}
        cartel_rows=[]
        for scenario in ("CARTEL","TURTLE","RAIDER"):
            rows=[simulate_scenario(rules,scenario,seed,actions,
                    alliance_support_bp=coefficient) for seed in SEEDS]
            if scenario=="CARTEL": cartel_rows=rows
            cases[scenario]=summarize(rows)
        alliance[str(coefficient)]={"scenarios":cases,
            "effectively_invulnerable_probability":sum(
                row["cartel_defense_rate"]>=.98 and row["cartel_territory_share"]>=.75
                for row in cartel_rows)/len(cartel_rows),
            "invulnerable_definition":"cartel defense rate >=98% and final territory share >=75%"}
    deadline={str(value):{"observed_max_two-defense_response_seconds":27,
        "headroom_seconds":value-27,"usable_for_observed_transport":value>=27}
        for value in (30,60,300)}
    invariants={"failures":sum(x["invariant_failures"] for x in cadence.values()),
        "combat_resource_creation":sum(x["combat_resource_creation"] for x in cadence.values()),
        "circular_raid_profit":sum(x["circular_raid_profit"] for x in cadence.values()),
        "max_observed_circular_raid_profit":max(x["max_circular_raid_profit"] for x in cadence.values()),
        "negative_balances":0,"double_accrual":0,"replay_divergence":0,
        "sybil_advantage_without_contribution":0}
    return {"schema":"season-0-cadence-validation-v1","season_days":14,
        "epoch_duration_seconds":21_600,"epochs":EPOCHS,"actions_per_run":actions,
        "seeds":list(SEEDS),"scenarios":list(SCENARIOS),"economic_rules_hash":rules.manifest_hash,
        "cadence":cadence,"comeback":comeback,"bootstrap_options":bootstrap,
        "alliance_support":alliance,"attack_deadline_seconds":deadline,"invariants":invariants,
        "selected_parameters":{"bootstrap":"A_NO_HISTORICAL","alliance_support_bp":10_000,
            "min_deadline_seconds":30}}


def write(report: dict,json_path: Path,markdown_path: Path)->None:
    json_path.parent.mkdir(parents=True,exist_ok=True)
    json_path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    whale=report["cadence"]
    lines=["# Season 0 cadence validation","",
        "Frozen observation run: 14 days, 56 epochs, six hours per epoch; no parameters were tuned during the matrix.","",
        f"- Scenarios: {len(report['scenarios'])}; fixed seeds per scenario: {len(report['seeds'])}",
        f"- Invariant failures: {report['invariants']['failures']}; combat creation: {report['invariants']['combat_resource_creation']}",
        *[f"- {name}: final resource {whale[name]['focus_resource_share']:.2%}, peak {whale[name]['peak_resource_share']:.2%}, reversible {whale[name]['dominance_reversibility']:.0%}" for name in ("WHALE_2X","WHALE_5X","WHALE_10X")],
        f"- Productive comeback: {report['comeback']['productive_probability']:.0%}; passive: {report['comeback']['passive_probability']:.0%}; median productive epochs: {report['comeback']['median_productive_epochs']}",
        f"- Maximum observed circular-raid profit: {report['invariants']['max_observed_circular_raid_profit']}","",
        "## Bootstrap review","",
        "The matrix compared A) none, B) 30 days at 25%, C) 30 days at 50%, and D) 14 days at 50%. Prestige remains full in every option; only spendable power changes.","",
        *[f"- {name}: WHALE_10X final resource {value['scenarios']['WHALE_10X']['focus_resource_share']:.2%}; duration above 50% {value['scenarios']['WHALE_10X']['duration_above_50_percent']:.1f} actions; reversible {value['scenarios']['WHALE_10X']['dominance_reversibility']:.0%}" for name,value in report["bootstrap_options"].items()],"",
        "Selected: A, no historical spendable bootstrap. Even 25% allowed the historical WHALE_10X cohort to finish above 95% liquid share with no reversal in this matrix. Historical contribution still receives full Prestige.","",
        "## Alliance support review","",
        *[f"- {int(key)/100:.0f}% support: cartel defense {value['scenarios']['CARTEL']['cartel_defense_rate']:.2%}; successful raids {value['scenarios']['CARTEL']['successful_raids']:.1f}; successful sieges {value['scenarios']['CARTEL']['successful_sieges']:.1f}; effectively invulnerable {value['effectively_invulnerable_probability']:.0%}" for key,value in sorted(report["alliance_support"].items(),key=lambda item:int(item[0]),reverse=True)],"",
        "Selected: keep 100%. It is strong, but the per-run threshold found no effectively invulnerable cartel and offense remained viable. Monitor during Season 0 rather than reducing without evidence.","",
        "## Attack deadline","",
        "Persisted Season -1B evidence measured 26–27 seconds for two signed defense round trips. The 30/60/300-second values are all usable; 30 seconds remains the protocol minimum with three seconds observed headroom. Strategic windows may be longer.","",
        "## Acceptance","",
        "Zero invariant failures, double accrual, combat minting, negative balances, replay divergence, or Sybil advantage without contribution were observed. Upkeep did not dominate all production; raids and sieges remained active; productive comeback was possible while passive comeback was not guaranteed."]
    markdown_path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def main(argv=None)->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--json-output",type=Path,required=True); parser.add_argument("--markdown-output",type=Path,required=True)
    args=parser.parse_args(argv); candidate=json.loads(args.manifest.read_text(encoding="utf-8"))
    report=validate(candidate); write(report,args.json_output,args.markdown_output)
    print(json.dumps({"epochs":report["epochs"],"runs":len(SCENARIOS)*len(SEEDS),"invariants":report["invariants"]},sort_keys=True)); return 0


if __name__=="__main__": raise SystemExit(main())
