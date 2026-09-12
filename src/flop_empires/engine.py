from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from typing import Any, Callable

from .alliances import active_allies
from .canonical import dumps, sha256
from .combat import attack_succeeds, raid_reward
from .events import append_event
from .github_evidence import validate_evidence_url
from .identity import Signer, require_signer
from .models import Command, Receipt, SeasonStatus
from .protocol import parse_command
from .receipts import issue_receipt
from .store import Store
from .technical_yield import BASE_UNITS, LIFETIME_SECONDS, empire_yield
from .world import add_edge, adjacent


class RuleViolation(ValueError):
    pass


class Engine:
    def __init__(self, store: Store, configured_referee_did: str, signer: Signer | None,
                 clock: Callable[[], int] | None = None):
        self.store = store
        self.signer = require_signer(configured_referee_did, signer)
        self.clock = clock or (lambda: int(time.time()))
        existing = store.one("SELECT value FROM config WHERE key='referee_did'")
        if existing and existing[0] != configured_referee_did:
            raise RuntimeError("database belongs to a different referee DID")
        store.conn.execute("INSERT OR IGNORE INTO config(key,value) VALUES('referee_did',?)", (configured_referee_did,))
        store.conn.execute("INSERT OR IGNORE INTO config(key,value) VALUES('season_status',?)", (SeasonStatus.REGISTRATION,))

    def execute(self, raw: str | bytes | dict[str, Any] | Command) -> Receipt:
        command = raw if isinstance(raw, Command) else parse_command(raw)
        obj = asdict(command)
        command_hash = sha256(obj)
        with self.store.transaction():
            prior = self.store.one("SELECT command_hash,receipt_json FROM requests WHERE actor_did=? AND request_id=?", (command.actor_did, command.request_id))
            if prior:
                if prior["command_hash"] != command_hash:
                    raise RuleViolation("request_id reused with different command")
                return Receipt(**json.loads(prior["receipt_json"]))
            accepted_at = int(self.clock())
            before = self.store.state_hash()
            self.store.conn.execute("SAVEPOINT command_effect")
            accepted = True
            try:
                details = self._dispatch(command, accepted_at)
                self.store.conn.execute("RELEASE command_effect")
            except (RuleViolation, sqlite3.IntegrityError, ValueError) as exc:
                self.store.conn.execute("ROLLBACK TO command_effect")
                self.store.conn.execute("RELEASE command_effect")
                accepted = False
                details = {"error": str(exc)}
            after = self.store.state_hash()
            seq, event_hash = append_event(self.store, event_type=command.action, actor_did=command.actor_did,
                request_id=command.request_id, accepted_at=accepted_at, accepted=accepted,
                command_hash=command_hash, before=before, after=after, details=details)
            unsigned = {"referee_did": self.signer.did, "request_id": command.request_id,
                "actor_did": command.actor_did, "accepted": accepted, "accepted_at": accepted_at,
                "event_seq": seq, "state_before_hash": before, "state_after_hash": after,
                "details": {**details, "event_hash": event_hash}}
            receipt = issue_receipt(self.signer, unsigned)
            self.store.conn.execute("INSERT INTO requests VALUES(?,?,?,?)", (command.actor_did, command.request_id, command_hash, dumps(asdict(receipt))))
            return receipt

    def _status(self) -> str:
        return self.store.one("SELECT value FROM config WHERE key='season_status'")[0]

    def _referee(self, did: str) -> None:
        if did != self.signer.did:
            raise RuleViolation("referee authorization required")

    def _empire(self, did: str) -> str:
        row = self.store.one("SELECT empire_id FROM memberships WHERE actor_did=?", (did,))
        if not row:
            raise RuleViolation("actor is not an empire member")
        return row[0]

    @staticmethod
    def _text(p: dict[str, Any], key: str) -> str:
        value = p.get(key)
        if not isinstance(value, str) or not value or len(value) > 200:
            raise RuleViolation(f"invalid {key}")
        return value

    @staticmethod
    def _amount(p: dict[str, Any], key: str, *, zero: bool = False) -> int:
        value = p.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < (0 if zero else 1):
            raise RuleViolation(f"invalid {key}")
        return value

    def _dispatch(self, c: Command, now: int) -> dict[str, Any]:
        p = c.payload
        fn = getattr(self, f"_do_{c.action}", None)
        if fn is None:
            raise RuleViolation("unsupported action")
        return fn(c.actor_did, p, now)

    def _do_register_actor(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        if p:
            raise RuleViolation("register_actor payload must be empty")
        self.store.conn.execute("INSERT INTO actors VALUES(?,?)", (did, now))
        return {"actor_did": did}

    def _do_create_empire(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        if self._status() != SeasonStatus.REGISTRATION:
            raise RuleViolation("membership is frozen")
        if not self.store.one("SELECT 1 FROM actors WHERE did=?", (did,)):
            raise RuleViolation("actor not registered")
        empire_id, name, capital = self._text(p, "empire_id"), self._text(p, "name"), self._text(p, "capital_id")
        self.store.conn.execute("INSERT INTO empires VALUES(?,?,?,?)", (empire_id, name, capital, now))
        self.store.conn.execute("INSERT INTO memberships VALUES(?,?,?)", (did, empire_id, now))
        self.store.conn.execute("INSERT INTO balances VALUES(?,0,0)", (empire_id,))
        self.store.conn.execute("INSERT INTO territories VALUES(?,?,1,0)", (capital, empire_id))
        return {"empire_id": empire_id, "capital_id": capital}

    def _do_join_empire(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        if self._status() != SeasonStatus.REGISTRATION:
            raise RuleViolation("membership is frozen")
        if not self.store.one("SELECT 1 FROM actors WHERE did=?", (did,)):
            raise RuleViolation("actor not registered")
        empire = self._text(p, "empire_id")
        self.store.conn.execute("INSERT INTO memberships VALUES(?,?,?)", (did, empire, now))
        return {"empire_id": empire}

    def _do_activate_season(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        self._referee(did)
        if self._status() != SeasonStatus.REGISTRATION:
            raise RuleViolation("season cannot be activated")
        self.store.conn.execute("UPDATE config SET value=? WHERE key='season_status'", (SeasonStatus.ACTIVE,))
        return {"status": SeasonStatus.ACTIVE}

    def _do_bind_github(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        if not self.store.one("SELECT 1 FROM actors WHERE did=?", (did,)):
            raise RuleViolation("actor not registered")
        login = self._text(p, "login")
        if p.get("verified") is not True:
            raise RuleViolation("GitHub binding verification failed")
        self.store.conn.execute("INSERT INTO github_bindings VALUES(?,?,?)", (did, login, now))
        return {"login": login}

    def _do_add_contribution(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        self._referee(did)
        actor = self._text(p, "contributor_did")
        cluster = self._text(p, "cluster_id")
        cls = self._text(p, "evidence_class")
        url = self._text(p, "url")
        repo = validate_evidence_url(url, cls)
        if p.get("verified") is not True:
            raise RuleViolation("GitHub verification failed")
        binding = self.store.one("SELECT 1 FROM github_bindings WHERE actor_did=?", (actor,))
        if not binding:
            raise RuleViolation("contributor lacks verified GitHub binding")
        empire = self._empire(actor)
        self_owned = bool(p.get("self_owned", False))
        existing = self.store.one("SELECT empire_id,evidence_class,repository FROM contribution_clusters WHERE id=?", (cluster,))
        if existing:
            if (existing[0], existing[1], existing[2]) != (empire, cls, repo):
                raise RuleViolation("cluster identity conflict")
        else:
            base = 0 if self_owned else BASE_UNITS[cls]
            self.store.conn.execute("INSERT INTO contribution_clusters VALUES(?,?,?,?,?,?,?,?,?)", (cluster, empire, actor, cls, repo, base, now, now + LIFETIME_SECONDS, int(self_owned)))
        self.store.conn.execute("INSERT INTO contribution_evidence VALUES(?,?,1)", (url, cluster))
        return {"cluster_id": cluster, "base_units": 0 if self_owned else BASE_UNITS[cls]}

    def _do_mint_resources(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        self._referee(did)
        empire, amount = self._text(p, "empire_id"), self._amount(p, "amount")
        cur = self.store.conn.execute("UPDATE balances SET available=available+? WHERE empire_id=?", (amount, empire))
        if cur.rowcount != 1:
            raise RuleViolation("unknown empire")
        return {"empire_id": empire, "amount": amount, "source": "season_allocation"}

    def _do_claim_yield(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        empire = self._empire(did)
        amount = empire_yield(self.store, empire, now)
        # Claims are deliberately snapshots for alpha; each cluster can be claimed once.
        key = f"yield_claimed:{empire}"
        if self.store.one("SELECT 1 FROM config WHERE key=?", (key,)):
            raise RuleViolation("yield already claimed")
        self.store.conn.execute("INSERT INTO config VALUES(?,?)", (key, str(now)))
        self.store.conn.execute("UPDATE balances SET available=available+? WHERE empire_id=?", (amount, empire))
        return {"empire_id": empire, "amount": amount}

    def _do_add_territory(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        self._referee(did)
        tid, owner = self._text(p, "territory_id"), self._text(p, "owner_empire_id")
        if p.get("capital", False):
            raise RuleViolation("additional capitals forbidden")
        self.store.conn.execute("INSERT INTO territories VALUES(?,?,0,0)", (tid, owner))
        return {"territory_id": tid}

    def _do_add_edge(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        self._referee(did)
        a, b = self._text(p, "a"), self._text(p, "b")
        add_edge(self.store, a, b)
        return {"a": a, "b": b}

    def _do_fortify(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        empire, tid, amount = self._empire(did), self._text(p, "territory_id"), self._amount(p, "amount")
        row = self.store.one("SELECT owner_empire_id FROM territories WHERE id=?", (tid,))
        if not row or row[0] != empire:
            raise RuleViolation("territory not owned")
        bal = self.store.one("SELECT available FROM balances WHERE empire_id=?", (empire,))[0]
        if bal < amount:
            raise RuleViolation("insufficient resources")
        self.store.conn.execute("UPDATE balances SET available=available-? WHERE empire_id=?", (amount, empire))
        self.store.conn.execute("UPDATE territories SET fortification=fortification+? WHERE id=?", (amount, tid))
        return {"territory_id": tid, "fortification_added": amount}

    def _do_create_alliance(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        creator = self._empire(did)
        aid = self._text(p, "alliance_id")
        members = p.get("members")
        if not isinstance(members, list) or creator not in members or len(set(members)) < 2 or not all(isinstance(x, str) for x in members):
            raise RuleViolation("invalid alliance members")
        seq = self.store.one("SELECT COALESCE(MAX(seq),0) FROM events")[0] + 1
        self.store.conn.execute("INSERT INTO alliances VALUES(?,0,?)", (aid, seq))
        for member in sorted(set(members)):
            self.store.conn.execute("INSERT INTO alliance_members VALUES(?,?)", (aid, member))
        return {"alliance_id": aid, "active": False}

    def _do_set_alliance_active(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        empire, aid = self._empire(did), self._text(p, "alliance_id")
        if not self.store.one("SELECT 1 FROM alliance_members WHERE alliance_id=? AND empire_id=?", (aid, empire)):
            raise RuleViolation("not an alliance member")
        active = p.get("active")
        if not isinstance(active, bool):
            raise RuleViolation("active must be boolean")
        self.store.conn.execute("UPDATE alliances SET active=? WHERE id=?", (int(active), aid))
        return {"alliance_id": aid, "active": active}

    def _do_recon(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        self._empire(did)
        tid = self._text(p, "territory_id")
        row = self.store.one("SELECT owner_empire_id,is_capital,fortification FROM territories WHERE id=?", (tid,))
        if not row:
            raise RuleViolation("unknown territory")
        return {"territory_id": tid, "owner_empire_id": row[0], "is_capital": bool(row[1]), "fortification": row[2]}

    def _combat(self, did: str, p: dict[str, Any], now: int, kind: str) -> dict[str, Any]:
        attacker = self._empire(did)
        attack_id, origin, target = self._text(p, "attack_id"), self._text(p, "origin_id"), self._text(p, "target_id")
        power = self._amount(p, "power")
        o = self.store.one("SELECT owner_empire_id FROM territories WHERE id=?", (origin,))
        t = self.store.one("SELECT owner_empire_id,is_capital,fortification FROM territories WHERE id=?", (target,))
        if not o or not t or o[0] != attacker or t[0] == attacker or not adjacent(self.store, origin, target):
            raise RuleViolation("invalid combat territories")
        if kind == "SIEGE" and t[1]:
            raise RuleViolation("Capital conquest forbidden")
        bal = self.store.one("SELECT available FROM balances WHERE empire_id=?", (attacker,))[0]
        if bal < power:
            raise RuleViolation("insufficient attack resources")
        defender = t[0]
        alliance_id = p.get("alliance_id")
        contributions = p.get("allied_defense", {})
        if not isinstance(contributions, dict):
            raise RuleViolation("allied_defense must be object")
        allied_total = 0
        allowed = active_allies(self.store, defender, alliance_id) if isinstance(alliance_id, str) else []
        for empire, amount in sorted(contributions.items()):
            if empire not in allowed or not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
                raise RuleViolation("inactive or invalid allied defense")
            available = self.store.one("SELECT available FROM balances WHERE empire_id=?", (empire,))[0]
            if available < amount:
                raise RuleViolation("ally has insufficient unlocked resources")
            self.store.conn.execute("UPDATE balances SET available=available-?,locked=locked+? WHERE empire_id=?", (amount, amount, empire))
            allied_total += amount
        self.store.conn.execute("UPDATE balances SET available=available-? WHERE empire_id=?", (power, attacker))
        defense = t[2] + allied_total
        success = attack_succeeds(power, defense)
        self.store.conn.execute("INSERT INTO attacks VALUES(?,?,?,?,?,?,?,?,?,?,1,?)", (attack_id, kind, attacker, defender, origin, target, power, allied_total, alliance_id, now, int(success)))
        reward = 0
        if kind == "RAID" and success:
            defender_available = self.store.one("SELECT available FROM balances WHERE empire_id=?", (defender,))[0]
            reward = raid_reward(power, defender_available)
            self.store.conn.execute("UPDATE balances SET available=available-? WHERE empire_id=?", (reward, defender))
            self.store.conn.execute("UPDATE balances SET available=available+? WHERE empire_id=?", (reward, attacker))
        elif kind == "SIEGE" and success:
            self.store.conn.execute("UPDATE territories SET owner_empire_id=? WHERE id=?", (attacker, target))
        for empire, amount in sorted(contributions.items()):
            self.store.conn.execute("UPDATE balances SET available=available+?,locked=locked-? WHERE empire_id=?", (amount, amount, empire))
        return {"attack_id": attack_id, "kind": kind, "success": success, "attack": power,
                "defense": defense, "raid_reward": reward, "alliance_id_at_creation": alliance_id}

    def _do_raid(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        return self._combat(did, p, now, "RAID")

    def _do_siege(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        return self._combat(did, p, now, "SIEGE")
