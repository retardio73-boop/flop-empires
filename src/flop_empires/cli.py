from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from .observability import health_summary
from .simulator import simulate
from .staging import ReadOnlyObserver
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
        print(json.dumps({"state": store.state(), "state_hash": store.state_hash()}, indent=2, sort_keys=True))
        return 0
    if args.command == "status":
        store = Store(args.database)
        print(json.dumps(health_summary(store, mode=args.mode), indent=2, sort_keys=True))
        return 0
    if args.command == "staging":
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
