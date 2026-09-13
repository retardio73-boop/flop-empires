from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from .observability import health_summary
from .economics_v02 import EconomicRulesV02, economic_leaderboard
from .simulator import simulate
from .staging import ReadOnlyObserver
from .live_staging import run_live_crash_a, run_live_write_smoke, write_report
from .season_minus_one import run_season_minus_one, write_season_report
from .store import Store
from .technocore import TechnocoreHttpMailbox


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flop-empires")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create a local alpha database")
    init.add_argument("database", type=Path)
    init.add_argument("--referee-did", required=True)
    state = sub.add_parser("state", help="print complete materialized state as JSON")
    state.add_argument("database", type=Path)
    state.add_argument("--economic-manifest", type=Path)
    sim = sub.add_parser("simulate", help="run deterministic invariant simulation")
    sim.add_argument("--seed", type=int, default=0)
    sim.add_argument("--actions", type=int, default=100_000)
    sim.add_argument("--output", type=Path)
    status = sub.add_parser("status", help="print local health summary")
    status.add_argument("database", type=Path)
    status.add_argument("--mode", default="LOCAL_SIMULATION",
                        choices=["LOCAL_SIMULATION","STAGING_READ_ONLY","STAGING_WRITE"])
    staging = sub.add_parser("staging", help="safe staging operations")
    staging_sub = staging.add_subparsers(dest="staging_command", required=True)
    observe = staging_sub.add_parser("observe", help="read and classify without game-state writes")
    observe.add_argument("database", type=Path)
    observe.add_argument("--mailbox", required=True)
    write_smoke = staging_sub.add_parser("write-smoke", help="explicit low-volume signed live staging E2E")
    write_smoke.add_argument("database", type=Path)
    write_smoke.add_argument("--manifest", type=Path, required=True)
    write_smoke.add_argument("--confirm-live-write", action="store_true")
    write_smoke.add_argument("--report-prefix", type=Path, default=Path("reports/technocore-write-e2e"))
    crash_a = staging_sub.add_parser("crash-a-smoke", help="exercise DB-commit-before-publish recovery")
    crash_a.add_argument("database", type=Path)
    crash_a.add_argument("--manifest", type=Path, required=True)
    crash_a.add_argument("--confirm-live-write", action="store_true")
    rehearsal = staging_sub.add_parser("season-minus-one", help="run deterministic private Season -1")
    rehearsal.add_argument("database",type=Path)
    rehearsal.add_argument("--manifest",type=Path,required=True)
    rehearsal.add_argument("--confirm-live-write",action="store_true")
    rehearsal.add_argument("--report-prefix",type=Path,default=Path("reports/season-minus-one"))
    args = parser.parse_args(argv)
    if args.command == "init":
        if not args.referee_did.startswith("did:key:"):
            parser.error("--referee-did must be a did:key identifier")
        store = Store(args.database)
        store.conn.execute("INSERT OR IGNORE INTO config VALUES('referee_did',?)", (args.referee_did,))
        store.conn.execute("INSERT OR IGNORE INTO config VALUES('season_status','REGISTRATION')")
        print(json.dumps({"database": str(args.database), "referee_did": args.referee_did,
                          "signing_key_stored": False}, sort_keys=True))
        return 0
    if args.command == "state":
        store = Store(args.database)
        value = {"state": store.state(), "state_hash": store.state_hash()}
        if args.economic_manifest:
            rules = EconomicRulesV02.from_manifest(json.loads(args.economic_manifest.read_text(encoding="utf-8")))
            value["economic_rules_version"] = rules.version
            value["leaderboard"] = economic_leaderboard(store, rules)
        print(json.dumps(value, indent=2, sort_keys=True))
        return 0
    if args.command == "status":
        store = Store(args.database)
        print(json.dumps(health_summary(store, mode=args.mode), indent=2, sort_keys=True))
        return 0
    if args.command == "staging":
        if args.staging_command == "season-minus-one":
            result=run_season_minus_one(args.manifest,args.database,
                confirm_live_write=args.confirm_live_write)
            write_season_report(result,args.report_prefix.with_suffix(".json"),
                args.report_prefix.with_suffix(".md"))
            print(json.dumps(result,indent=2,sort_keys=True)); return 0
        if args.staging_command == "crash-a-smoke":
            print(json.dumps(run_live_crash_a(args.manifest,args.database,
                confirm_live_write=args.confirm_live_write),indent=2,sort_keys=True))
            return 0
        if args.staging_command == "write-smoke":
            result = run_live_write_smoke(args.manifest, args.database,
                confirm_live_write=args.confirm_live_write)
            write_report(result, args.report_prefix.with_suffix(".json"),
                         args.report_prefix.with_suffix(".md"))
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        store = Store(args.database)
        with httpx.Client(headers={"User-Agent": "flop-empires/0.1 staging-read-only"}) as client:
            source = TechnocoreHttpMailbox(client, args.mailbox)
            result = ReadOnlyObserver(store, args.mailbox).observe(source)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    report = simulate(args.seed, args.actions)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0
