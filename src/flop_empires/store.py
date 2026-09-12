from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .canonical import sha256

MIGRATIONS = [
"""
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS actors(did TEXT PRIMARY KEY, registered_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS empires(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, capital_id TEXT, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS memberships(actor_did TEXT PRIMARY KEY REFERENCES actors(did), empire_id TEXT NOT NULL REFERENCES empires(id), joined_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS github_bindings(actor_did TEXT PRIMARY KEY REFERENCES actors(did), login TEXT NOT NULL UNIQUE, verified_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS contribution_clusters(id TEXT PRIMARY KEY, empire_id TEXT NOT NULL REFERENCES empires(id), actor_did TEXT NOT NULL REFERENCES actors(did), evidence_class TEXT NOT NULL, repository TEXT NOT NULL, base_units INTEGER NOT NULL CHECK(base_units>=0), verified_at INTEGER NOT NULL, expires_at INTEGER NOT NULL, self_owned INTEGER NOT NULL CHECK(self_owned IN(0,1)));
CREATE TABLE IF NOT EXISTS contribution_evidence(url TEXT PRIMARY KEY, cluster_id TEXT NOT NULL REFERENCES contribution_clusters(id), verified INTEGER NOT NULL CHECK(verified IN(0,1)));
CREATE TABLE IF NOT EXISTS balances(empire_id TEXT PRIMARY KEY REFERENCES empires(id), available INTEGER NOT NULL DEFAULT 0 CHECK(available>=0), locked INTEGER NOT NULL DEFAULT 0 CHECK(locked>=0));
CREATE TABLE IF NOT EXISTS territories(id TEXT PRIMARY KEY, owner_empire_id TEXT NOT NULL REFERENCES empires(id), is_capital INTEGER NOT NULL DEFAULT 0 CHECK(is_capital IN(0,1)), fortification INTEGER NOT NULL DEFAULT 0 CHECK(fortification>=0));
CREATE TABLE IF NOT EXISTS territory_edges(a TEXT NOT NULL REFERENCES territories(id), b TEXT NOT NULL REFERENCES territories(id), PRIMARY KEY(a,b), CHECK(a<b));
CREATE TABLE IF NOT EXISTS alliances(id TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 0 CHECK(active IN(0,1)), created_event_seq INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS alliance_members(alliance_id TEXT NOT NULL REFERENCES alliances(id), empire_id TEXT NOT NULL REFERENCES empires(id), PRIMARY KEY(alliance_id,empire_id));
CREATE TABLE IF NOT EXISTS attacks(id TEXT PRIMARY KEY, kind TEXT NOT NULL, attacker_empire_id TEXT NOT NULL, defender_empire_id TEXT NOT NULL, origin_id TEXT NOT NULL, target_id TEXT NOT NULL, attack_power INTEGER NOT NULL CHECK(attack_power>=0), allied_defense INTEGER NOT NULL DEFAULT 0 CHECK(allied_defense>=0), alliance_id TEXT, created_at INTEGER NOT NULL, resolved INTEGER NOT NULL DEFAULT 0, success INTEGER);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, actor_did TEXT NOT NULL, request_id TEXT NOT NULL, accepted_at INTEGER NOT NULL, accepted INTEGER NOT NULL, command_hash TEXT NOT NULL, state_before_hash TEXT NOT NULL, state_after_hash TEXT NOT NULL, details_json TEXT NOT NULL, prev_event_hash TEXT NOT NULL, event_hash TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS requests(actor_did TEXT NOT NULL, request_id TEXT NOT NULL, command_hash TEXT NOT NULL, receipt_json TEXT NOT NULL, PRIMARY KEY(actor_did,request_id));
CREATE TABLE IF NOT EXISTS technocore_state(mailbox TEXT PRIMARY KEY, cursor TEXT NOT NULL, bootstrapped INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS technocore_records(record_id TEXT PRIMARY KEY, mailbox TEXT NOT NULL, seq INTEGER, ts INTEGER, accepted_at INTEGER NOT NULL, receipt_json TEXT NOT NULL);
"""
]


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.migrate()

    def migrate(self) -> None:
        self.conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY)")
        done = {r[0] for r in self.conn.execute("SELECT version FROM schema_migrations")}
        for version, sql in enumerate(MIGRATIONS, 1):
            if version not in done:
                # executescript owns its transaction boundary in sqlite3.
                self.conn.executescript("BEGIN IMMEDIATE;\n" + sql +
                    f"\nINSERT INTO schema_migrations VALUES({version});\nCOMMIT;")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        nested = self.conn.in_transaction
        if not nested:
            self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
            if not nested:
                self.conn.execute("COMMIT")
        except Exception:
            if not nested and self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            raise

    def one(self, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, args).fetchone()

    def state(self) -> dict[str, Any]:
        tables = ["config", "actors", "empires", "memberships", "github_bindings", "contribution_clusters", "contribution_evidence", "balances", "territories", "territory_edges", "alliances", "alliance_members", "attacks"]
        result: dict[str, Any] = {}
        for table in tables:
            rows = [dict(r) for r in self.conn.execute(f"SELECT * FROM {table} ORDER BY 1,2")]
            result[table] = rows
        return result

    def state_hash(self) -> str:
        return sha256(self.state())

    def close(self) -> None:
        self.conn.close()
