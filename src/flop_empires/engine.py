from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from typing import Any, Callable

from .alliances import active_allies
from .canonical import dumps, sha256
from .combat import attack_succeeds, raid_reward
from .events import append_event, require_valid_chain
from .github_evidence import validate_evidence_url
from .github_evidence import VerifiedEvidence
from .identity import Signer, require_signer
from .models import Command, Receipt, RuntimeMode, SeasonStatus
from .protocol import parse_command
from .receipts import issue_receipt
from .store import Store
from .technical_yield import (BASE_UNITS, EPOCH_SECONDS, LIFETIME_SECONDS,
    empire_yield, epoch_yield)
from .world import add_edge, adjacent
from .economics_v02 import EconomicRulesV02


class RuleViolation(ValueError):
    pass


class LifecycleViolation(RuntimeError):
    """A lifecycle refusal happens before a command transaction or receipt exists."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_ENGINE_FACTORY_TOKEN = object()

REGISTRATION_ACTIONS = frozenset({"register_actor", "create_empire", "join_empire", "bind_github"})
ACTIVE_ACTIONS = frozenset({"add_contribution", "claim_yield", "settle_epoch", "create_alliance",
    "set_alliance_active", "fortify", "recon", "create_attack", "submit_defense",
    "resolve_attack", "raid", "siege", "pause_season"})
LOCAL_OPERATOR_ACTIONS = frozenset({"add_territory", "add_edge", "mint_resources"})
STAGING_ACTIONS = frozenset({"add_synthetic_contribution","add_contribution"})


class Engine:
    @classmethod
    def for_test(cls, store: Store, configured_referee_did: str, signer: Signer,
                 clock=None, **kwargs) -> "Engine":
        return cls(store, configured_referee_did, signer, clock=clock,
            runtime_mode=RuntimeMode.LOCAL_TEST, _factory_token=_ENGINE_FACTORY_TOKEN, **kwargs)

    @classmethod
    def for_staging(cls, store: Store, configured_referee_did: str, signer: Signer,
                    clock=None, **kwargs) -> "Engine":
        return cls(store, configured_referee_did, signer, clock=clock,
            runtime_mode=RuntimeMode.STAGING, _factory_token=_ENGINE_FACTORY_TOKEN, **kwargs)

    @classmethod
    def from_manifest(cls,store: Store,manifest,signer: Signer,clock=None)->"Engine":
        manifest_value=getattr(manifest,"value",{})
        activation=manifest_value.get("activation") if isinstance(manifest_value,dict) else None
        environment=manifest.environment
        if activation=="LOCAL_DRY_RUN": mode=RuntimeMode.LOCAL_TEST
        elif environment=="staging": mode=RuntimeMode.STAGING
        elif activation=="FROZEN_NOT_ACTIVE": mode=RuntimeMode.PRODUCTION_FROZEN
        else: mode=RuntimeMode.LOCAL_TEST
        return cls(store,manifest.referee_did,signer,clock=clock,economic_rules=manifest.rules,
            manifest_hash=manifest.manifest_hash,initial_balances=manifest.initial_balances,
            epoch_duration=manifest.epoch_duration,environment=environment,
            combat_parameters=manifest.combat_parameters,
            alliance_parameters=manifest.alliance_parameters,
            bootstrap_policy=manifest_value.get("bootstrap_policy") if isinstance(manifest_value,dict) else None,
            pause_policy=manifest_value.get("pause_policy_version") if isinstance(manifest_value,dict) else None,
            activation_guard=activation,runtime_mode=mode,_factory_token=_ENGINE_FACTORY_TOKEN)

    @classmethod
    def _for_verified_production(cls,store: Store,manifest,signer: Signer,activation_context,
                                 clock=None,launch_context=None)->"Engine":
        from .activation import is_verified_activation_context
        if not is_verified_activation_context(activation_context):
            raise RuntimeError("VERIFIED_ACTIVATION_REQUIRED")
        if activation_context.frozen_manifest_hash != manifest.manifest_hash:
            raise RuntimeError("ACTIVATION_MANIFEST_MISMATCH")
        if launch_context is not None:
            from .launch import is_verified_launch_context
            if not is_verified_launch_context(launch_context) or launch_context.binding_id!=activation_context.activation_id:
                raise RuntimeError("VERIFIED_LAUNCH_AUTHORIZATION_REQUIRED")
        return cls(store,manifest.referee_did,signer,clock=clock,economic_rules=manifest.rules,
            manifest_hash=manifest.manifest_hash,initial_balances=manifest.initial_balances,
            epoch_duration=manifest.epoch_duration,environment="production",
            combat_parameters=manifest.combat_parameters,alliance_parameters=manifest.alliance_parameters,
            bootstrap_policy=manifest.bootstrap_policy,pause_policy=manifest.pause_policy_version,
            activation_guard="VERIFIED_ACTIVATION",runtime_mode=RuntimeMode.PRODUCTION,
            activation_context=activation_context,launch_context=launch_context,_factory_token=_ENGINE_FACTORY_TOKEN)

    def __init__(self, store: Store, configured_referee_did: str, signer: Signer | None,
                 clock: Callable[[], int] | None = None, *,
                 economic_rules: EconomicRulesV02 | None = None,
                 manifest_hash: str | None = None,
                 initial_balances: dict[str,int] | None = None,
                 epoch_duration: int = EPOCH_SECONDS,
                 environment: str = "local",combat_parameters: dict[str,Any] | None = None,
                 alliance_parameters: dict[str,Any] | None = None,
                 bootstrap_policy: dict[str,Any] | None = None,
                 pause_policy: str | None = None,
                 activation_guard: str | None = None,
                 runtime_mode: RuntimeMode | None = None,
                 activation_context=None,
                 launch_context=None,
                 _factory_token=None):
        if _factory_token is not _ENGINE_FACTORY_TOKEN or runtime_mode is None:
            raise RuntimeError("direct Engine construction is disabled; use an explicit runtime factory")
        self.store = store
        if store.one("SELECT 1 FROM events LIMIT 1"): require_valid_chain(store)
        self.signer = require_signer(configured_referee_did, signer)
        self.clock = clock or (lambda: int(time.time()))
        self.economic_rules=economic_rules
        self.initial_balances=initial_balances or {"ENGINEERING":0,"KNOWLEDGE":0,"INFLUENCE":0}
        self.epoch_duration=epoch_duration; self.environment=environment
        self.combat_parameters=combat_parameters or {"capital_conquest":False,
            "max_deadline_seconds":86_400,"min_deadline_seconds":1,
            "raid_reward_divisor":2,"tie_goes_to_defender":True}
        self.alliance_parameters=alliance_parameters or {"eligibility_snapshotted":True,
            "max_defensive_alliances":2,"support_coefficient_bp":10_000}
        self.bootstrap_policy=bootstrap_policy
        self.pause_policy=pause_policy
        self.activation_guard=activation_guard
        self.runtime_mode=RuntimeMode(runtime_mode)
        self.activation_context=activation_context
        self.launch_context=launch_context
        existing = store.one("SELECT value FROM config WHERE key='referee_did'")
        if existing and existing[0] != configured_referee_did:
            raise RuntimeError("database belongs to a different referee DID")
        store.conn.execute("INSERT OR IGNORE INTO config(key,value) VALUES('referee_did',?)", (configured_referee_did,))
        initial_status=(SeasonStatus.FROZEN_NOT_ACTIVE if self.runtime_mode==RuntimeMode.PRODUCTION_FROZEN
            else SeasonStatus.REGISTRATION)
        store.conn.execute("INSERT OR IGNORE INTO config(key,value) VALUES('season_status',?)", (initial_status,))
        actual_status=store.one("SELECT value FROM config WHERE key='season_status'")[0]
        if self.runtime_mode==RuntimeMode.PRODUCTION_FROZEN and actual_status!=SeasonStatus.FROZEN_NOT_ACTIVE:
            raise RuntimeError("frozen manifest cannot open a non-frozen database")
        version=economic_rules.version if economic_rules else "technical-yield-v0.1"
        prior=store.one("SELECT value FROM config WHERE key='economic_rules_version'")
        if prior and prior[0]!=version: raise RuntimeError("database economic rules mismatch")
        if economic_rules:
            store.conn.execute("INSERT OR IGNORE INTO config VALUES('economic_rules_version',?)",(version,))
            store.conn.execute("INSERT OR IGNORE INTO config VALUES('environment',?)",(environment,))
            if manifest_hash: store.conn.execute("INSERT OR IGNORE INTO config VALUES('manifest_hash',?)",(manifest_hash,))
            last=store.one("SELECT state_after_hash FROM events ORDER BY seq DESC LIMIT 1")
            if last and last[0]!=store.state_hash():
                raise RuntimeError("impossible replay divergence")
        if self.runtime_mode==RuntimeMode.PRODUCTION:
            if activation_context is None: raise RuntimeError("VERIFIED_ACTIVATION_REQUIRED")
            bindings={"activation_id":activation_context.activation_id,
                "activation_manifest_hash":activation_context.frozen_manifest_hash,
                "actions_namespace":activation_context.actions_namespace,
                "events_namespace":activation_context.events_namespace}
            for key,value in bindings.items():
                prior=store.one("SELECT value FROM config WHERE key=?",(key,))
                if prior and prior[0]!=value: raise RuntimeError("persisted activation binding mismatch")
                store.conn.execute("INSERT OR IGNORE INTO config(key,value) VALUES(?,?)",(key,value))

    def execute(self, raw: str | bytes | dict[str, Any] | Command) -> Receipt:
        command = raw if isinstance(raw, Command) else parse_command(raw)
        self._require_lifecycle(command,hard_only=True)
        obj = asdict(command)
        command_hash = sha256(obj)
        with self.store.transaction():
            prior = self.store.one("SELECT command_hash,receipt_json FROM requests WHERE actor_did=? AND request_id=?", (command.actor_did, command.request_id))
            if prior:
                if prior["command_hash"] != command_hash:
                    conflict = self.store.one("SELECT receipt_json FROM request_conflicts WHERE actor_did=? AND request_id=? AND command_hash=?",
                        (command.actor_did, command.request_id, command_hash))
                    if conflict:
                        return Receipt(**json.loads(conflict[0]))
                    accepted_at = int(self.clock()); before = self.store.state_hash()
                    details = {"error":"REQUEST_ID_CONFLICT","original_command_hash":prior["command_hash"],
                               "conflicting_command_hash":command_hash}
                    if self.economic_rules: details["command"]=obj
                    seq,event_hash = append_event(self.store,event_type="REQUEST_ID_CONFLICT",
                        actor_did=command.actor_did,request_id=command.request_id,
                        accepted_at=accepted_at,accepted=False,command_hash=command_hash,
                        before=before,after=before,details=details)
                    receipt=issue_receipt(self.signer,{"referee_did":self.signer.did,
                        "request_id":command.request_id,"actor_did":command.actor_did,
                        "accepted":False,"accepted_at":accepted_at,"event_seq":seq,
                        "state_before_hash":before,"state_after_hash":before,
                        "details":{**details,"event_hash":event_hash}})
                    self.store.conn.execute("INSERT INTO request_conflicts VALUES(?,?,?,?)",
                        (command.actor_did,command.request_id,command_hash,dumps(asdict(receipt))))
                    return receipt
                return Receipt(**json.loads(prior["receipt_json"]))
            accepted_at = int(self.clock())
            before = self.store.state_hash()
            self.store.conn.execute("SAVEPOINT command_effect")
            accepted = True
            try:
                self._require_lifecycle(command)
                details = self._dispatch(command, accepted_at)
                self.store.conn.execute("RELEASE command_effect")
            except (RuleViolation, sqlite3.IntegrityError, ValueError) as exc:
                self.store.conn.execute("ROLLBACK TO command_effect")
                self.store.conn.execute("RELEASE command_effect")
                accepted = False
                details = {"error": str(exc)}
            if self.economic_rules:
                details={**details,"command":obj,"economic_rules_version":self.economic_rules.version}
            after = self.store.state_hash()
            event_type=details.get("event_type",command.action) if self.economic_rules else command.action
            seq, event_hash = append_event(self.store, event_type=event_type, actor_did=command.actor_did,
                request_id=command.request_id, accepted_at=accepted_at, accepted=accepted,
                command_hash=command_hash, before=before, after=after, details=details)
            unsigned = {"referee_did": self.signer.did, "request_id": command.request_id,
                "actor_did": command.actor_did, "accepted": accepted, "accepted_at": accepted_at,
                "event_seq": seq, "state_before_hash": before, "state_after_hash": after,
                "details": {**details, "event_hash": event_hash}}
            receipt = issue_receipt(self.signer, unsigned)
            self.store.conn.execute("INSERT INTO requests VALUES(?,?,?,?)", (command.actor_did, command.request_id, command_hash, dumps(asdict(receipt))))
            return receipt

    def _require_lifecycle(self, command: Command,*,hard_only: bool=False) -> None:
        status=self._status()
        if status==SeasonStatus.FROZEN_NOT_ACTIVE:
            raise LifecycleViolation("SEASON_NOT_ACTIVATED")
        if status in {SeasonStatus.FINALIZED,SeasonStatus.CLOSED}:
            raise LifecycleViolation("SEASON_FINALIZED")
        if hard_only:return
        action=command.action
        if status==SeasonStatus.PAUSED:
            if action!="resume_season": raise RuleViolation("SEASON_PAUSED")
            return
        if status==SeasonStatus.REGISTRATION:
            allowed=set(REGISTRATION_ACTIONS)
            if self.runtime_mode in {RuntimeMode.LOCAL_TEST,RuntimeMode.STAGING}:
                allowed.update(LOCAL_OPERATOR_ACTIONS);allowed.add("activate_season")
                if self.runtime_mode==RuntimeMode.STAGING: allowed.update(STAGING_ACTIONS)
            if action not in allowed: raise RuleViolation("ACTION_NOT_ALLOWED_DURING_REGISTRATION")
            if self.runtime_mode==RuntimeMode.PRODUCTION and self.activation_context is not None:
                now=int(self.clock())
                closes_at=self.launch_context.effective_start if self.launch_context is not None else None
                if now<self.activation_context.registration_open or (closes_at is not None and now>=closes_at):
                    raise RuleViolation("REGISTRATION_CLOSED")
            return
        if status==SeasonStatus.ACTIVE:
            allowed=set(ACTIVE_ACTIONS)
            if self.runtime_mode in {RuntimeMode.LOCAL_TEST,RuntimeMode.STAGING}:
                allowed.update(LOCAL_OPERATOR_ACTIONS)
                if self.runtime_mode==RuntimeMode.STAGING: allowed.update(STAGING_ACTIONS)
            if action not in allowed: raise RuleViolation("ACTION_NOT_ALLOWED_DURING_ACTIVE")
            return
        raise RuntimeError("unknown persisted lifecycle state")

    def advance_production_lifecycle(self, now: int | None=None) -> str:
        if self.runtime_mode!=RuntimeMode.PRODUCTION or self.activation_context is None:
            raise RuntimeError("VERIFIED_PRODUCTION_RUNTIME_REQUIRED")
        wall=int(self.clock()) if now is None else int(now);ctx=self.activation_context
        status=self._status(); launch=self.launch_context
        if launch is None:
            if status in {SeasonStatus.ACTIVE,SeasonStatus.PAUSED,SeasonStatus.FINALIZED}:
                raise RuntimeError("LAUNCH_AUTHORIZATION_REQUIRED_FOR_LIVE_STATE")
            if wall<ctx.registration_open:
                raise LifecycleViolation("ACTIVATION_NOT_YET_EFFECTIVE")
            target=SeasonStatus.REGISTRATION
        elif wall>=launch.effective_end:
            target=SeasonStatus.FINALIZED
        elif wall>=launch.effective_start:
            target=SeasonStatus.ACTIVE
        elif wall>=ctx.registration_open:
            target=SeasonStatus.REGISTRATION
        else:
            raise LifecycleViolation("ACTIVATION_NOT_YET_EFFECTIVE")
        if status==SeasonStatus.PAUSED and target==SeasonStatus.ACTIVE: return status
        allowed={(SeasonStatus.FROZEN_NOT_ACTIVE,SeasonStatus.REGISTRATION),
            (SeasonStatus.REGISTRATION,SeasonStatus.ACTIVE),(SeasonStatus.ACTIVE,SeasonStatus.FINALIZED),
            (SeasonStatus.REGISTRATION,SeasonStatus.FINALIZED)}
        if status!=target and (status,target) not in allowed:
            raise RuntimeError("invalid production lifecycle transition")
        if status!=target:
            self.store.conn.execute("UPDATE config SET value=? WHERE key='season_status'",(target,))
            if target==SeasonStatus.ACTIVE:
                self.store.conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('season_started_at',?)",
                    (str(launch.effective_start),))
                self.store.conn.execute("INSERT OR IGNORE INTO config(key,value) VALUES('total_paused_seconds','0')")
        return target

    def record_verified_contribution(self, evidence: VerifiedEvidence, contributor_did: str,
                                     request_id: str) -> Receipt:
        """Trusted adapter boundary: only a verifier-created typed result enters scoring."""
        if not isinstance(evidence, VerifiedEvidence):
            raise TypeError("evidence must be VerifiedEvidence")
        return self.execute({"action": "add_contribution", "actor_did": self.signer.did,
            "request_id": request_id, "payload": {"contributor_did": contributor_did,
            "cluster_id": evidence.cluster_id, "evidence_class": evidence.evidence_class,
            "url": evidence.url, "verified": True, "self_owned": evidence.self_owned}})

    def _status(self) -> str:
        return self.store.one("SELECT value FROM config WHERE key='season_status'")[0]

    def _game_now(self,wall_now: int)->int:
        if self.pause_policy is None: return wall_now
        accumulated=self.store.one("SELECT value FROM config WHERE key='total_paused_seconds'")
        paused=int(accumulated[0]) if accumulated else 0
        if self._status()==SeasonStatus.PAUSED:
            started=self.store.one("SELECT value FROM config WHERE key='pause_started_wall_at'")
            if not started: raise RuntimeError("paused Season lacks persisted clock anchor")
            paused+=max(0,wall_now-int(started[0]))
        return wall_now-paused

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
        if self._status()==SeasonStatus.PAUSED and c.action!="resume_season":
            raise RuleViolation("season is paused")
        if c.action in {"pause_season","resume_season"}:
            return fn(c.actor_did,p,now)
        return fn(c.actor_did, p, self._game_now(now))

    def _do_register_actor(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        if p:
            raise RuleViolation("register_actor payload must be empty")
        self.store.conn.execute("INSERT INTO actors VALUES(?,?)", (did, now))
        return {"actor_did": did}

    def _do_create_empire(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        if self._status() != SeasonStatus.REGISTRATION:
            raise RuleViolation("membership is frozen")
        if self.runtime_mode==RuntimeMode.PRODUCTION:
            raise RuleViolation("Season 0 empire slots are pre-provisioned; use join_empire")
        if not self.store.one("SELECT 1 FROM actors WHERE did=?", (did,)):
            raise RuleViolation("actor not registered")
        empire_id, name, capital = self._text(p, "empire_id"), self._text(p, "name"), self._text(p, "capital_id")
        self.store.conn.execute("INSERT INTO empires VALUES(?,?,?,?)", (empire_id, name, capital, now))
        self.store.conn.execute("INSERT INTO memberships VALUES(?,?,?)", (did, empire_id, now))
        self.store.conn.execute("INSERT INTO balances VALUES(?,0,0)", (empire_id,))
        if self.economic_rules:
            initial=self.initial_balances
            self.store.conn.execute("INSERT INTO empire_economy VALUES(?,?,?,?,?,?)",
                (empire_id,0,initial["ENGINEERING"],initial["KNOWLEDGE"],initial["INFLUENCE"],-1))
            self.store.conn.execute("UPDATE balances SET available=? WHERE empire_id=?",
                (initial["ENGINEERING"],empire_id))
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
        if self.runtime_mode not in {RuntimeMode.LOCAL_TEST,RuntimeMode.STAGING}:
            raise RuleViolation("activation is external to production game commands")
        self._referee(did)
        if self.activation_guard in {"FROZEN_NOT_ACTIVE","DISABLED_PENDING_FINAL_REVIEW"}:
            raise RuleViolation("manifest activation is disabled")
        if self._status() != SeasonStatus.REGISTRATION:
            raise RuleViolation("season cannot be activated")
        self.store.conn.execute("UPDATE config SET value=? WHERE key='season_status'", (SeasonStatus.ACTIVE,))
        self.store.conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('season_started_at',?)",
            (str(now),))
        if self.pause_policy is not None:
            self.store.conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('total_paused_seconds','0')")
        return {"status": SeasonStatus.ACTIVE}

    def _do_pause_season(self,did: str,p: dict[str,Any],wall_now: int)->dict[str,Any]:
        self._referee(did)
        if self.pause_policy!="authoritative-clock-freeze-v1": raise RuleViolation("pause policy is not configured")
        if p: raise RuleViolation("pause_season payload must be empty")
        if self._status()!=SeasonStatus.ACTIVE: raise RuleViolation("only an active Season can pause")
        game_now=self._game_now(wall_now)
        self.store.conn.execute("UPDATE config SET value=? WHERE key='season_status'",(SeasonStatus.PAUSED,))
        self.store.conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('pause_started_wall_at',?)",(str(wall_now),))
        return {"event_type":"SEASON_PAUSED","status":SeasonStatus.PAUSED,
            "authoritative_game_time":game_now,"policy":"authoritative-clock-freeze-v1"}

    def _do_resume_season(self,did: str,p: dict[str,Any],wall_now: int)->dict[str,Any]:
        self._referee(did)
        if self.pause_policy!="authoritative-clock-freeze-v1": raise RuleViolation("pause policy is not configured")
        if p: raise RuleViolation("resume_season payload must be empty")
        if self._status()!=SeasonStatus.PAUSED: raise RuleViolation("Season is not paused")
        started=self.store.one("SELECT value FROM config WHERE key='pause_started_wall_at'")
        if not started or wall_now<int(started[0]): raise RuntimeError("invalid persisted pause clock")
        prior=self.store.one("SELECT value FROM config WHERE key='total_paused_seconds'")
        total=(int(prior[0]) if prior else 0)+(wall_now-int(started[0]))
        self.store.conn.execute("INSERT OR REPLACE INTO config(key,value) VALUES('total_paused_seconds',?)",(str(total),))
        self.store.conn.execute("DELETE FROM config WHERE key='pause_started_wall_at'")
        self.store.conn.execute("UPDATE config SET value=? WHERE key='season_status'",(SeasonStatus.ACTIVE,))
        return {"event_type":"SEASON_RESUMED","status":SeasonStatus.ACTIVE,
            "authoritative_game_time":wall_now-total,"total_paused_seconds":total,
            "policy":"authoritative-clock-freeze-v1"}

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
            if self.economic_rules and base:
                self.store.conn.execute("UPDATE empire_economy SET prestige=prestige+? WHERE empire_id=?",(base,empire))
        self.store.conn.execute("INSERT INTO contribution_evidence VALUES(?,?,1)", (url, cluster))
        return {"cluster_id": cluster, "base_units": 0 if self_owned else BASE_UNITS[cls]}

    def _do_mint_resources(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        self._referee(did)
        empire, amount = self._text(p, "empire_id"), self._amount(p, "amount")
        cur = self.store.conn.execute("UPDATE balances SET available=available+? WHERE empire_id=?", (amount, empire))
        if cur.rowcount != 1:
            raise RuleViolation("unknown empire")
        if self.economic_rules:
            self.store.conn.execute("UPDATE empire_economy SET engineering=engineering+? WHERE empire_id=?",(amount,empire))
        return {"empire_id": empire, "amount": amount, "source": "season_allocation"}

    def _do_add_synthetic_contribution(self,did: str,p: dict[str,Any],now: int)->dict[str,Any]:
        self._referee(did)
        if self.environment!="staging" or not self.economic_rules:
            raise RuleViolation("synthetic contribution is staging only")
        empire=self._text(p,"empire_id"); profile=self._text(p,"profile")
        points=self._amount(p,"verified_points")
        if p.get("marker")!="SIMULATION_STAGING_ONLY":
            raise RuleViolation("synthetic contribution marker required")
        cur=self.store.conn.execute("UPDATE empire_economy SET prestige=prestige+? WHERE empire_id=?",(points,empire))
        if cur.rowcount!=1: raise RuleViolation("unknown empire")
        return {"empire_id":empire,"profile":profile,"prestige_added":points,
            "marker":"SIMULATION_STAGING_ONLY","real_github_evidence":False}

    def _do_settle_epoch(self,did: str,p: dict[str,Any],now: int)->dict[str,Any]:
        self._referee(did)
        if not self.economic_rules: raise RuleViolation("settle_epoch requires technical-yield-v0.2")
        epoch=self._amount(p,"epoch",zero=True)
        started=self.store.one("SELECT value FROM config WHERE key='season_started_at'")
        if not started or now < int(started[0])+epoch*self.epoch_duration:
            raise RuleViolation("epoch boundary not reached")
        rows=list(self.store.conn.execute("SELECT * FROM empire_economy ORDER BY empire_id"))
        if any(row["last_settled_epoch"]>=epoch for row in rows): raise RuleViolation("epoch already settled")
        if any(row["last_settled_epoch"]!=epoch-1 for row in rows): raise RuleViolation("epoch settlement must be sequential")
        results=[]
        for row in rows:
            empire=row["empire_id"]
            noncap=self.store.one("SELECT COUNT(*) FROM territories WHERE owner_empire_id=? AND is_capital=0",(empire,))[0]
            fort=self.store.one("SELECT COALESCE(SUM(fortification),0) FROM territories WHERE owner_empire_id=?",(empire,))[0]
            effective_prestige=row["prestige"]
            if self.bootstrap_policy is not None:
                policy=self.bootstrap_policy
                weight=policy.get("historical_spendable_weight_bp")
                lookback_days=policy.get("lookback_days")
                if (not isinstance(weight,int) or isinstance(weight,bool) or not 0<=weight<=10_000 or
                        not isinstance(lookback_days,int) or isinstance(lookback_days,bool) or lookback_days<0):
                    raise RuleViolation("invalid bootstrap policy")
                season_start=int(started[0])
                historical=self.store.one(
                    "SELECT COALESCE(SUM(base_units),0) FROM contribution_clusters "
                    "WHERE empire_id=? AND self_owned=0 AND verified_at<?",(empire,season_start))[0]
                cutoff=season_start-lookback_days*86_400
                eligible=self.store.one(
                    "SELECT COALESCE(SUM(base_units),0) FROM contribution_clusters "
                    "WHERE empire_id=? AND self_owned=0 AND verified_at>=? AND verified_at<?",
                    (empire,cutoff,season_start))[0] if lookback_days else 0
                effective_prestige=row["prestige"]-historical+(eligible*weight//10_000)
            attr=self.economic_rules.epoch_attribution(row["prestige"],row["engineering"],noncap,fort,
                effective_prestige=effective_prestige)
            allocation=attr["allocation"]
            eng_delta=allocation["ENGINEERING"]+attr["territory_production"]-attr["total_cost"]
            self.store.conn.execute("UPDATE empire_economy SET engineering=engineering+?,knowledge=knowledge+?,influence=influence+?,last_settled_epoch=? WHERE empire_id=?",
                (eng_delta,allocation["KNOWLEDGE"],allocation["INFLUENCE"],epoch,empire))
            self.store.conn.execute("UPDATE balances SET available=available+? WHERE empire_id=?",(eng_delta,empire))
            self.store.conn.execute("INSERT INTO economic_epochs VALUES(?,?,?)",(empire,epoch,dumps(attr)))
            results.append({"empire_id":empire,**attr,"engineering_net":eng_delta})
        return {"event_type":"ECONOMIC_EPOCH_SETTLED","epoch":epoch,"empires":results}

    def _do_claim_yield(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        if self.economic_rules:
            raise RuleViolation("v0.2 yield is settled by the referee at epoch boundary")
        empire = self._empire(did)
        started = self.store.one("SELECT value FROM config WHERE key='season_started_at'")
        if not started or now < int(started[0]) or (now - int(started[0])) % EPOCH_SECONDS:
            raise RuleViolation("yield can be claimed only at a valid epoch boundary")
        rows = [dict(r) for r in self.store.conn.execute(
            "SELECT id,actor_did,base_units,verified_at,self_owned FROM contribution_clusters WHERE empire_id=?",
            (empire,))]
        amount = epoch_yield(rows, now, int(started[0]))
        epoch = (now - int(started[0])) // EPOCH_SECONDS
        key = f"yield_claimed:{empire}:{epoch}"
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
        if self.economic_rules:
            self.store.conn.execute("UPDATE empire_economy SET engineering=engineering-? WHERE empire_id=?",(amount,empire))
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
        if active:
            members=[r[0] for r in self.store.conn.execute("SELECT empire_id FROM alliance_members WHERE alliance_id=?",(aid,))]
            maximum=self.alliance_parameters["max_defensive_alliances"]
            for member in members:
                count=self.store.one("SELECT COUNT(*) FROM alliances a JOIN alliance_members m ON m.alliance_id=a.id WHERE m.empire_id=? AND a.active=1",(member,))[0]
                if count>=maximum: raise RuleViolation("maximum defensive alliances reached")
        self.store.conn.execute("UPDATE alliances SET active=? WHERE id=?", (int(active), aid))
        return {"alliance_id": aid, "active": active}

    def _do_recon(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        self._empire(did)
        tid = self._text(p, "territory_id")
        row = self.store.one("SELECT owner_empire_id,is_capital,fortification FROM territories WHERE id=?", (tid,))
        if not row:
            raise RuleViolation("unknown territory")
        result={"territory_id": tid, "owner_empire_id": row[0], "is_capital": bool(row[1]), "fortification": row[2]}
        ttl=self.combat_parameters.get("recon_ttl_seconds")
        if ttl is not None: result["expires_at"]=now+ttl
        return result

    def _do_create_attack(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        attacker = self._empire(did)
        attack_id, origin, target = self._text(p, "attack_id"), self._text(p, "origin_id"), self._text(p, "target_id")
        kind, power = self._text(p, "kind").upper(), self._amount(p, "power")
        minimum_power=self.combat_parameters.get("raid_min_power" if kind=="RAID" else "siege_min_power")
        if minimum_power is not None and power < minimum_power:
            raise RuleViolation("attack power below frozen minimum")
        configured=self.combat_parameters.get(
            "raid_defense_window_seconds" if kind=="RAID" else "siege_defense_window_seconds")
        if configured is None:
            deadline_seconds=self._amount(p,"deadline_seconds")
        else:
            supplied=p.get("deadline_seconds",configured)
            if supplied!=configured: raise RuleViolation("attack deadline differs from frozen manifest")
            deadline_seconds=configured
        if (kind not in {"RAID", "SIEGE"} or
                not self.combat_parameters.get("min_deadline_seconds",1)<=deadline_seconds<=self.combat_parameters["max_deadline_seconds"]):
            raise RuleViolation("invalid attack kind or deadline")
        o = self.store.one("SELECT owner_empire_id FROM territories WHERE id=?", (origin,))
        t = self.store.one("SELECT owner_empire_id,is_capital FROM territories WHERE id=?", (target,))
        if not o or not t or o[0] != attacker or t[0] == attacker or not adjacent(self.store, origin, target):
            raise RuleViolation("invalid combat territories")
        if kind == "SIEGE" and t[1]:
            raise RuleViolation("Capital conquest forbidden")
        cost=self._offensive_cost(attacker,power)
        if self.store.one("SELECT available FROM balances WHERE empire_id=?", (attacker,))[0] < cost:
            raise RuleViolation("insufficient attack resources")
        alliance_id = p.get("alliance_id")
        eligible = active_allies(self.store, t[0], alliance_id) if isinstance(alliance_id, str) else []
        self.store.conn.execute("UPDATE balances SET available=available-?,locked=locked+? WHERE empire_id=?",
            (cost, cost, attacker))
        if self.economic_rules:
            self.store.conn.execute("UPDATE empire_economy SET engineering=engineering-? WHERE empire_id=?",(cost,attacker))
        self.store.conn.execute("INSERT INTO attacks(id,kind,attacker_empire_id,defender_empire_id,origin_id,target_id,attack_power,allied_defense,alliance_id,created_at,resolved,success,deadline_at,attacker_cost_locked) VALUES(?,?,?,?,?,?,?,?,?,?,0,NULL,?,?)",
            (attack_id, kind, attacker, t[0], origin, target, power, 0, alliance_id, now,
             now + deadline_seconds, cost))
        for ally in eligible:
            self.store.conn.execute("INSERT INTO attack_eligible_allies VALUES(?,?)", (attack_id, ally))
        return {"attack_id": attack_id, "deadline_at": now + deadline_seconds,
            "eligible_allies": eligible, "resources_locked": cost,
            "base_power":power,"fatigue_cost":cost-power}

    def _do_submit_defense(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        empire, attack_id = self._empire(did), self._text(p, "attack_id")
        amount = self._amount(p, "amount")
        attack = self.store.one("SELECT resolved,deadline_at FROM attacks WHERE id=?", (attack_id,))
        if not attack or attack["resolved"] or now > attack["deadline_at"]:
            raise RuleViolation("defense deadline expired or attack unavailable")
        defender=self.store.one("SELECT defender_empire_id FROM attacks WHERE id=?",(attack_id,))[0]
        if empire != defender and not self.store.one("SELECT 1 FROM attack_eligible_allies WHERE attack_id=? AND empire_id=?",
                              (attack_id, empire)):
            raise RuleViolation("alliance was not eligible at attack creation")
        if self.store.one("SELECT available FROM balances WHERE empire_id=?", (empire,))[0] < amount:
            raise RuleViolation("ally has insufficient unlocked resources")
        self.store.conn.execute("UPDATE balances SET available=available-?,locked=locked+? WHERE empire_id=?",
            (amount, amount, empire))
        if self.economic_rules:
            self.store.conn.execute("UPDATE empire_economy SET engineering=engineering-? WHERE empire_id=?",(amount,empire))
        self.store.conn.execute("INSERT INTO attack_defenses VALUES(?,?,?,?)",
            (attack_id, empire, amount, now))
        self.store.conn.execute("UPDATE attacks SET allied_defense=allied_defense+? WHERE id=?",
            (amount, attack_id))
        return {"attack_id": attack_id, "empire_id": empire, "resources_locked": amount}

    def _do_resolve_attack(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        self._referee(did)
        attack_id = self._text(p, "attack_id")
        attack = self.store.one("SELECT * FROM attacks WHERE id=?", (attack_id,))
        if not attack or attack["resolved"]:
            raise RuleViolation("attack unavailable or already resolved")
        if now < attack["deadline_at"]:
            raise RuleViolation("defense deadline has not elapsed")
        target = self.store.one("SELECT is_capital,fortification FROM territories WHERE id=?",
                                (attack["target_id"],))
        if not target:
            raise RuleViolation("target no longer exists")
        defense_rows=list(self.store.conn.execute("SELECT empire_id,amount FROM attack_defenses WHERE attack_id=?",(attack_id,)))
        defender_engineering=sum(r["amount"] for r in defense_rows if r["empire_id"]==attack["defender_empire_id"])
        allied=sum(r["amount"] for r in defense_rows if r["empire_id"]!=attack["defender_empire_id"])
        allied_effective=allied*self.alliance_parameters["support_coefficient_bp"]//10_000
        defense = (self.economic_rules.defense_power(defender_engineering,target["fortification"],allied_effective)
            if self.economic_rules else target["fortification"]+attack["allied_defense"])
        success = attack_succeeds(attack["attack_power"], defense)
        attacker, defender = attack["attacker_empire_id"], attack["defender_empire_id"]
        self.store.conn.execute("UPDATE balances SET locked=locked-? WHERE empire_id=?",
            (attack["attacker_cost_locked"], attacker))
        reward = 0
        if attack["kind"] == "RAID" and success:
            defender_available = self.store.one("SELECT available FROM balances WHERE empire_id=?", (defender,))[0]
            reward = (raid_reward(attack["attack_power"],defender_available) if not self.economic_rules else
                min(attack["attack_power"]//self.combat_parameters["raid_reward_divisor"],defender_available))
            self.store.conn.execute("UPDATE balances SET available=available-? WHERE empire_id=?", (reward, defender))
            self.store.conn.execute("UPDATE balances SET available=available+? WHERE empire_id=?", (reward, attacker))
            if self.economic_rules:
                self.store.conn.execute("UPDATE empire_economy SET engineering=engineering-? WHERE empire_id=?",(reward,defender))
                self.store.conn.execute("UPDATE empire_economy SET engineering=engineering+? WHERE empire_id=?",(reward,attacker))
        elif attack["kind"] == "SIEGE" and success:
            if target["is_capital"]:
                raise RuleViolation("Capital conquest forbidden")
            self.store.conn.execute("UPDATE territories SET owner_empire_id=? WHERE id=?",
                (attacker, attack["target_id"]))
            self._record_fatigue(attack_id,attacker)
        for row in self.store.conn.execute("SELECT empire_id,amount FROM attack_defenses WHERE attack_id=?", (attack_id,)):
            self.store.conn.execute("UPDATE balances SET available=available+?,locked=locked-? WHERE empire_id=?",
                (row["amount"], row["amount"], row["empire_id"]))
            if self.economic_rules:
                self.store.conn.execute("UPDATE empire_economy SET engineering=engineering+? WHERE empire_id=?",(row["amount"],row["empire_id"]))
        self.store.conn.execute("UPDATE attacks SET resolved=1,success=?,attacker_cost_locked=0 WHERE id=?",
            (int(success), attack_id))
        return {"attack_id": attack_id, "success": success, "attack": attack["attack_power"],
            "defense": defense, "raid_reward": reward}

    def _combat(self, did: str, p: dict[str, Any], now: int, kind: str) -> dict[str, Any]:
        attacker = self._empire(did)
        attack_id, origin, target = self._text(p, "attack_id"), self._text(p, "origin_id"), self._text(p, "target_id")
        power = self._amount(p, "power")
        minimum_power=self.combat_parameters.get("raid_min_power" if kind=="RAID" else "siege_min_power")
        if minimum_power is not None and power < minimum_power:
            raise RuleViolation("attack power below frozen minimum")
        o = self.store.one("SELECT owner_empire_id FROM territories WHERE id=?", (origin,))
        t = self.store.one("SELECT owner_empire_id,is_capital,fortification FROM territories WHERE id=?", (target,))
        if not o or not t or o[0] != attacker or t[0] == attacker or not adjacent(self.store, origin, target):
            raise RuleViolation("invalid combat territories")
        if kind == "SIEGE" and t[1]:
            raise RuleViolation("Capital conquest forbidden")
        cost=self._offensive_cost(attacker,power)
        bal = self.store.one("SELECT available FROM balances WHERE empire_id=?", (attacker,))[0]
        if bal < cost:
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
            if self.economic_rules:
                self.store.conn.execute("UPDATE empire_economy SET engineering=engineering-? WHERE empire_id=?",(amount,empire))
            allied_total += amount
        self.store.conn.execute("UPDATE balances SET available=available-? WHERE empire_id=?", (cost, attacker))
        if self.economic_rules:
            self.store.conn.execute("UPDATE empire_economy SET engineering=engineering-? WHERE empire_id=?",(cost,attacker))
        allied_effective=allied_total*self.alliance_parameters["support_coefficient_bp"]//10_000
        defense = self.economic_rules.defense_power(0,t[2],allied_effective) if self.economic_rules else t[2]+allied_total
        success = attack_succeeds(power, defense)
        self.store.conn.execute("INSERT INTO attacks(id,kind,attacker_empire_id,defender_empire_id,origin_id,target_id,attack_power,allied_defense,alliance_id,created_at,resolved,success,deadline_at,attacker_cost_locked) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,NULL,0)",
            (attack_id, kind, attacker, defender, origin, target, power, allied_total,
             alliance_id, now, int(success)))
        reward = 0
        if kind == "RAID" and success:
            defender_available = self.store.one("SELECT available FROM balances WHERE empire_id=?", (defender,))[0]
            reward = (raid_reward(power,defender_available) if not self.economic_rules else
                min(power//self.combat_parameters["raid_reward_divisor"],defender_available))
            self.store.conn.execute("UPDATE balances SET available=available-? WHERE empire_id=?", (reward, defender))
            self.store.conn.execute("UPDATE balances SET available=available+? WHERE empire_id=?", (reward, attacker))
            if self.economic_rules:
                self.store.conn.execute("UPDATE empire_economy SET engineering=engineering-? WHERE empire_id=?",(reward,defender))
                self.store.conn.execute("UPDATE empire_economy SET engineering=engineering+? WHERE empire_id=?",(reward,attacker))
        elif kind == "SIEGE" and success:
            self.store.conn.execute("UPDATE territories SET owner_empire_id=? WHERE id=?", (attacker, target))
            self._record_fatigue(attack_id,attacker)
        for empire, amount in sorted(contributions.items()):
            self.store.conn.execute("UPDATE balances SET available=available+?,locked=locked-? WHERE empire_id=?", (amount, amount, empire))
            if self.economic_rules:
                self.store.conn.execute("UPDATE empire_economy SET engineering=engineering+? WHERE empire_id=?",(amount,empire))
        return {"attack_id": attack_id, "kind": kind, "success": success, "attack": power,
                "offensive_cost":cost,"fatigue_cost":cost-power,"defense": defense,
                "raid_reward": reward, "alliance_id_at_creation": alliance_id}

    def _offensive_cost(self,empire: str,base: int)->int:
        if not self.economic_rules: return base
        next_seq=self.store.one("SELECT COALESCE(MAX(seq),0)+1 FROM events")[0]
        count=self.store.one("SELECT COUNT(*) FROM offensive_fatigue WHERE empire_id=? AND event_seq>?",
            (empire,next_seq-self.economic_rules.fatigue_window_actions))[0]
        return self.economic_rules.offensive_cost(base,count)

    def _record_fatigue(self,attack_id: str,empire: str)->None:
        if self.economic_rules:
            next_seq=self.store.one("SELECT COALESCE(MAX(seq),0)+1 FROM events")[0]
            self.store.conn.execute("INSERT INTO offensive_fatigue VALUES(?,?,?)",(attack_id,empire,next_seq))

    def _do_raid(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        if "raid_defense_window_seconds" in self.combat_parameters:
            raise RuleViolation("frozen Season attacks require create_attack")
        return self._combat(did, p, now, "RAID")

    def _do_siege(self, did: str, p: dict[str, Any], now: int) -> dict[str, Any]:
        if "siege_defense_window_seconds" in self.combat_parameters:
            raise RuleViolation("frozen Season attacks require create_attack")
        return self._combat(did, p, now, "SIEGE")
