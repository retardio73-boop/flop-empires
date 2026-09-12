from __future__ import annotations

import argparse
import json
from pathlib import Path

from .simulator import simulate
from .store import Store


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
    report = simulate(args.seed, args.actions)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0
