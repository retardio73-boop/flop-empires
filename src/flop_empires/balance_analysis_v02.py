from __future__ import annotations

import json
import statistics
import argparse
from pathlib import Path

from .balance_search import simulate_scenario
from .economics_v02 import EconomicRulesV02

WHALE_SEEDS=(7,19,41,73,101)
COMEBACK_SEEDS=(7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,73,79,83,89,97,101,103,107)


def _mean(rows,key): return sum(r[key] for r in rows)/len(rows)
def _median_present(rows,key):
    values=[r[key] for r in rows if r[key] is not None]
    return statistics.median(values) if values else None


def analyze(rules: EconomicRulesV02,actions: int=50_000)->dict:
    whale={}
    for scenario in ("WHALE_2X","WHALE_5X","WHALE_10X"):
        rows=[simulate_scenario(rules,scenario,seed,actions) for seed in WHALE_SEEDS]
        attr=[r["attribution"][0] for r in rows]
        whale[scenario]={"resource_share":_mean(rows,"largest_resource_share"),
            "peak_resource_share":_mean(rows,"peak_resource_share"),
            "peak_territory_share":_mean(rows,"peak_territory_share"),
            "time_to_peak_share":_mean(rows,"time_to_peak_share"),
            "duration_above_40_percent":_mean(rows,"duration_above_40_percent"),
            "duration_above_50_percent":_mean(rows,"duration_above_50_percent"),
            "duration_above_60_percent":_mean(rows,"duration_above_60_percent"),
            "reversal_probability":sum(r["dominance_reversibility"] for r in rows)/len(rows),
            "other_empires_viable":_mean(rows,"number_of_other_empires_still_viable"),
            "attribution":{key:sum(x.get(key,0) for x in attr)/len(attr) for key in sorted(set().union(*(x.keys() for x in attr)))}}
    five,ten=whale["WHALE_5X"],whale["WHALE_10X"]
    a5,a10=five["attribution"],ten["attribution"]
    causes={key:a10.get(key,0)-a5.get(key,0) for key in
        ("combat_spend","offensive_fatigue_cost","overextension_penalty","upkeep","stockpile_cost","territory_gains","territory_losses","raid_gains","raid_losses")}
    coherent=(ten["resource_share"]<five["resource_share"] and
        sum(causes[x] for x in ("combat_spend","offensive_fatigue_cost","overextension_penalty","upkeep","stockpile_cost"))>0)
    explanation=("COHERENT_STRATEGIC_COST_INTERACTION" if coherent else
        "SIMULATION_BIAS_FIXED" if ten["resource_share"]>=five["resource_share"] else "UNEXPLAINED_REVIEW")
    comeback={}
    for profile in ("none","low","continued","high"):
        rows=[simulate_scenario(rules,"COMEBACK",seed,actions,profile) for seed in COMEBACK_SEEDS]
        recovered=[r for r in rows if r["recovery_probability"]]
        comeback[profile]={"seeds":list(COMEBACK_SEEDS),"recovery_probability":len(recovered)/len(rows),
            "median_epochs_to_recovery":_median_present(rows,"epochs_to_recovery"),
            "median_actions_to_recovery":_median_present(rows,"actions_to_recovery"),
            "median_resource_cost_to_recovery":_median_present(recovered,"resource_cost_to_recovery"),
            "median_territory_recovered":_median_present(rows,"territory_recovered"),
            "median_prestige_delta":_median_present(rows,"prestige_delta"),
            "median_new_technical_contribution":_median_present(rows,"new_technical_contribution_required"),
            "median_attacks_required":_median_present(recovered,"attacks_required"),
            "median_defensive_actions_required":_median_present(recovered,"defensive_actions_required")}
    return {"version":"balance-attribution-v0.2","actions_per_run":actions,
        "manifest_hash":rules.manifest_hash,"whale":whale,"whale_10x_vs_5x_cost_deltas":causes,
        "whale_nonmonotonic_explanation":explanation,
        "comeback_definition":"recover >=1/2 lost non-capitals, >=35% leader resources, positive net production and viable 30-power siege for 3 epochs",
        "comeback":comeback}


def write_analysis(result: dict,directory: Path)->None:
    directory.mkdir(parents=True,exist_ok=True)
    (directory/"balance-analysis-v02.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    w=result["whale"]; causes=result["whale_10x_vs_5x_cost_deltas"]
    (directory/"whale-attribution-v02.md").write_text("\n".join(["# WHALE attribution v0.2","",
        *[f"- {name}: final resource share {data['resource_share']:.2%}, peak {data['peak_resource_share']:.2%}, territory peak {data['peak_territory_share']:.2%}, reversible {data['reversal_probability']:.0%}" for name,data in w.items()],
        "",f"Conclusion: `{result['whale_nonmonotonic_explanation']}`.",
        "WHALE_10X minus WHALE_5X attribution deltas: `"+json.dumps(causes,sort_keys=True)+"`.",
        "The conclusion is attribution-based; no parameter was changed to force monotonic final liquid share."])+"\n",encoding="utf-8")
    c=result["comeback"]
    (directory/"comeback-v02.md").write_text("\n".join(["# Productive comeback v0.2","",
        f"Definition: {result['comeback_definition']}","",
        *[f"- {name}: recovery {data['recovery_probability']:.0%}; median actions {data['median_actions_to_recovery']}; new contribution {data['median_new_technical_contribution']}" for name,data in c.items()]])+"\n",encoding="utf-8")


def main(argv=None)->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",type=Path,default=Path("season/economic-v02.example.json"))
    parser.add_argument("--actions",type=int,default=50_000)
    parser.add_argument("--output-directory",type=Path,default=Path("reports"))
    args=parser.parse_args(argv)
    rules=EconomicRulesV02.from_manifest(json.loads(args.manifest.read_text(encoding="utf-8")))
    result=analyze(rules,args.actions); write_analysis(result,args.output_directory)
    print(json.dumps({"manifest_hash":result["manifest_hash"],"actions_per_run":args.actions},sort_keys=True))
    return 0


if __name__=="__main__": raise SystemExit(main())
