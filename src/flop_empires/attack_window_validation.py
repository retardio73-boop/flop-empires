from __future__ import annotations

import argparse,json
from pathlib import Path

RAID_WINDOWS=(300,900,1800,3600)
SIEGE_WINDOWS=(3600,10800,21600,43200)
CHECK_INTERVALS={"AUTONOMOUS":60,"ALLIANCE_COORDINATED":900,
    "ACTIVE_HUMAN":1800,"CASUAL_HUMAN":7200}
EPOCH_SECONDS=21_600


def evaluate_window(seconds: int)->dict:
    # Opportunity model, not a behavioral forecast: attack arrival phase is uniform
    # relative to each fixed check interval and every check is assumed successful.
    visibility={name:min(1.0,seconds/interval) for name,interval in CHECK_INTERVALS.items()}
    return {"seconds":seconds,"defender_sees_attack_opportunity":visibility,
        "model_note":"uniform phase against explicit check intervals; not a human-behavior estimate",
        "alliance_participation_profiles_at_or_above_50_percent":sum(x>=.5 for x in visibility.values()),
        "concurrent_open_attacks_at_one_arrival_per_hour":seconds/3600,
        "lock_exposure_hours":seconds/3600,
        "epoch_overlap_opportunity":min(1.0,seconds/EPOCH_SECONDS),
        "maximum_resolution_cycles_per_day":86_400/seconds,
        "stale_lock_pressure":"LOW" if seconds<=EPOCH_SECONDS//2 else
            "MODERATE" if seconds<=EPOCH_SECONDS else "HIGH"}


def validate()->dict:
    return {"schema":"season-0-attack-window-validation-v1","protocol_minimum_seconds":30,
        "epoch_seconds":EPOCH_SECONDS,"reaction_model":CHECK_INTERVALS,
        "raid":{str(x):evaluate_window(x) for x in RAID_WINDOWS},
        "siege":{str(x):evaluate_window(x) for x in SIEGE_WINDOWS},
        "selected":{"raid_defense_window_seconds":1800,
            "siege_defense_window_seconds":21600,"recon_ttl_seconds":1800},
        "conclusion":"30-minute Raid and six-hour Siege avoid instant wars while bounding locks; Recon expires after 30 minutes"}


def write(report: dict,json_path: Path,markdown_path: Path)->None:
    json_path.parent.mkdir(parents=True,exist_ok=True)
    json_path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    lines=["# Season 0 attack-window validation","",
        "This is an operational opportunity model, not a precise prediction of human response.",
        "It assumes uniformly phased attack arrival relative to four explicit check intervals.","",
        "## Raid candidates","",
        "| Window | Active-human opportunity | Alliance profiles >=50% | Concurrent at 1/hour | Epoch overlap |",
        "|---:|---:|---:|---:|---:|",
        *[f"| {x//60} min | {report['raid'][str(x)]['defender_sees_attack_opportunity']['ACTIVE_HUMAN']:.0%} | {report['raid'][str(x)]['alliance_participation_profiles_at_or_above_50_percent']} | {report['raid'][str(x)]['concurrent_open_attacks_at_one_arrival_per_hour']:.2f} | {report['raid'][str(x)]['epoch_overlap_opportunity']:.1%} |" for x in RAID_WINDOWS],"",
        "## Siege candidates","",
        "| Window | Casual-human opportunity | Alliance profiles >=50% | Concurrent at 1/hour | Epoch overlap |",
        "|---:|---:|---:|---:|---:|",
        *[f"| {x//3600} h | {report['siege'][str(x)]['defender_sees_attack_opportunity']['CASUAL_HUMAN']:.0%} | {report['siege'][str(x)]['alliance_participation_profiles_at_or_above_50_percent']} | {report['siege'][str(x)]['concurrent_open_attacks_at_one_arrival_per_hour']:.1f} | {report['siege'][str(x)]['epoch_overlap_opportunity']:.0%} |" for x in SIEGE_WINDOWS],"",
        "Selected: Raid 30 minutes, Siege 6 hours, Recon TTL 30 minutes. Raid gives an active human one full check interval and keeps lock exposure to half an hour. Siege spans one economic epoch and gives every modeled profile a response opportunity without the 12-hour stale-lock pressure.","",
        "The 30-second protocol minimum remains only a lower bound; it is not a normal Season 0 defense window."]
    markdown_path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def main(argv=None)->int:
    parser=argparse.ArgumentParser();parser.add_argument("--json-output",type=Path,required=True)
    parser.add_argument("--markdown-output",type=Path,required=True);args=parser.parse_args(argv)
    report=validate();write(report,args.json_output,args.markdown_output)
    print(json.dumps(report["selected"],sort_keys=True));return 0


if __name__=="__main__": raise SystemExit(main())
