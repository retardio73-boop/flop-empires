from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re

from .canonical import loads, sha256
from .economics_v02 import EconomicRulesV02
from .identity import verify_key_from_did

ROOM_NAME=re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
PRODUCTION_NAMESPACE_TOKEN=re.compile(r"^[0-9a-f]{16}$")


@dataclass(frozen=True)
class SeasonManifestV02:
    value: dict[str, Any]

    @classmethod
    def load(cls,path: str|Path) -> "SeasonManifestV02":
        value=loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value,dict): raise ValueError("invalid Season manifest")
        required={"season_id","environment","protocol_version","economic_rules_version",
            "technical_yield_version","referee_did","actions_namespace","events_namespace",
            "actor_allowlist","world_graph_hash","world_fixture","epoch_duration",
            "registration_boundary","initial_balances","economic_parameters","combat_parameters",
            "alliance_parameters","github_allowlist","manifest_hash"}
        if set(value)!=required: raise ValueError("Season manifest fields mismatch")
        unsigned=dict(value); supplied=unsigned.pop("manifest_hash")
        if sha256(unsigned)!=supplied: raise ValueError("Season manifest hash mismatch")
        result=cls(value); result.validate()
        world_path=Path(path).resolve().parent.parent/value["world_fixture"]
        if not world_path.is_file() or sha256(loads(world_path.read_text(encoding="utf-8")))!=value["world_graph_hash"]:
            raise ValueError("world graph hash mismatch")
        return result

    def validate(self) -> None:
        v=self.value
        if v["environment"]!="staging" or not v["season_id"].startswith("staging-season-minus-one-b-"):
            raise ValueError("Season -1B requires explicit staging namespace")
        prefix="mb-p-staging-flop-empires-s1b-"
        if not v["actions_namespace"].startswith(prefix) or not v["events_namespace"].startswith(prefix):
            raise ValueError("Season -1B rooms require signed unlisted namespace")
        if v["actions_namespace"]==v["events_namespace"]: raise ValueError("rooms must differ")
        if v["economic_rules_version"]!="technical-yield-v0.2" or v["technical_yield_version"]!="technical-yield-v0.2":
            raise ValueError("Season -1B must select v0.2")
        if not isinstance(v["epoch_duration"],int) or v["epoch_duration"]<1: raise ValueError("invalid epoch")
        if len(v["actor_allowlist"])<4 or len(set(v["actor_allowlist"]))!=len(v["actor_allowlist"]):
            raise ValueError("invalid actor allowlist")
        if set(v["initial_balances"])!={"ENGINEERING","KNOWLEDGE","INFLUENCE"}: raise ValueError("invalid initial balances")
        if any(not isinstance(x,int) or x<0 for x in v["initial_balances"].values()): raise ValueError("invalid initial balances")
        combat=v["combat_parameters"]
        if (combat.get("capital_conquest") is not False or combat.get("tie_goes_to_defender") is not True or
                not isinstance(combat.get("max_deadline_seconds"),int) or combat["max_deadline_seconds"]<1 or
                not isinstance(combat.get("raid_reward_divisor"),int) or combat["raid_reward_divisor"]<2):
            raise ValueError("invalid combat parameters")
        alliance=v["alliance_parameters"]
        if (alliance.get("eligibility_snapshotted") is not True or
                not isinstance(alliance.get("max_defensive_alliances"),int) or alliance["max_defensive_alliances"]<1 or
                not isinstance(alliance.get("support_coefficient_bp"),int) or not 0<=alliance["support_coefficient_bp"]<=10_000):
            raise ValueError("invalid alliance parameters")
        EconomicRulesV02.from_manifest(v)

    @property
    def manifest_hash(self): return self.value["manifest_hash"]
    @property
    def rules(self): return EconomicRulesV02.from_manifest(self.value)
    def __getattr__(self,name):
        try: return self.value[name]
        except KeyError as exc: raise AttributeError(name) from exc


@dataclass(frozen=True)
class SeasonZeroCandidateManifest:
    """Strict, deliberately non-activatable production candidate."""
    value: dict[str,Any]

    @classmethod
    def load(cls,path: str|Path)->"SeasonZeroCandidateManifest":
        value=loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value,dict): raise ValueError("invalid Season 0 candidate")
        required={"activation","candidate_hash","environment","season_id","intended_duration_days",
            "epoch_count","protocol_version","economic_rules_version","technical_yield_version",
            "referee_did","actions_namespace","events_namespace","registration_boundary",
            "world_graph_hash","world_fixture","epoch_duration","initial_balances","bootstrap_policy",
            "economic_parameters","combat_parameters","alliance_parameters","github_allowlist"}
        if set(value)!=required: raise ValueError("Season 0 candidate fields mismatch")
        unsigned=dict(value); supplied=unsigned.pop("candidate_hash")
        if sha256(unsigned)!=supplied: raise ValueError("Season 0 candidate hash mismatch")
        result=cls(value); result.validate()
        world_path=Path(path).resolve().parent.parent/value["world_fixture"]
        if not world_path.is_file() or sha256(loads(world_path.read_text(encoding="utf-8")))!=value["world_graph_hash"]:
            raise ValueError("world graph hash mismatch")
        return result

    def validate(self)->None:
        v=self.value
        if v["activation"]!="DISABLED_PENDING_FINAL_REVIEW" or v["environment"]!="production-candidate-not-active":
            raise ValueError("candidate must remain disabled")
        if v["registration_boundary"] is not None: raise ValueError("registration must remain unopened")
        if v["intended_duration_days"]!=14 or v["epoch_duration"]!=21_600 or v["epoch_count"]!=56:
            raise ValueError("invalid Season 0 cadence")
        verify_key_from_did(v["referee_did"])
        for room in (v["actions_namespace"],v["events_namespace"]):
            if not ROOM_NAME.fullmatch(room) or "staging" in room:
                raise ValueError("invalid production candidate namespace")
        if v["actions_namespace"]==v["events_namespace"]: raise ValueError("rooms must differ")
        if v["economic_rules_version"]!="technical-yield-v0.2" or v["technical_yield_version"]!="technical-yield-v0.2":
            raise ValueError("Season 0 candidate must select v0.2")
        policy=v["bootstrap_policy"]
        if policy!={"lookback_days":0,"historical_spendable_weight_bp":0,
                "prestige_retains_full_verified_value":True}:
            raise ValueError("unvalidated bootstrap policy")
        if set(v["initial_balances"])!={"ENGINEERING","KNOWLEDGE","INFLUENCE"} or any(
                not isinstance(x,int) or isinstance(x,bool) or x<0 for x in v["initial_balances"].values()):
            raise ValueError("invalid initial balances")
        if v["combat_parameters"].get("min_deadline_seconds")!=30:
            raise ValueError("unvalidated minimum deadline")
        if v["alliance_parameters"].get("support_coefficient_bp")!=10_000:
            raise ValueError("unvalidated alliance support")
        EconomicRulesV02.from_manifest(v)

    @property
    def candidate_hash(self): return self.value["candidate_hash"]

    @property
    def rules(self): return EconomicRulesV02.from_manifest(self.value)

    def __getattr__(self,name):
        try: return self.value[name]
        except KeyError as exc: raise AttributeError(name) from exc


@dataclass(frozen=True)
class FrozenSeasonManifest:
    """Immutable rule snapshot. Loading it never activates or contacts transport."""
    value: dict[str,Any]

    @classmethod
    def load(cls,path: str|Path)->"FrozenSeasonManifest":
        value=loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value,dict): raise ValueError("invalid frozen Season manifest")
        required={"manifest_schema_version","manifest_hash","previous_candidate_hash","activation",
            "environment","season_id","protocol_version","economic_rules_version",
            "technical_yield_version","referee_did","actions_namespace","events_namespace",
            "registration_boundary","season_start","season_end","epoch_duration",
            "intended_duration_epochs","intended_duration_seconds","world_graph_hash","world_fixture",
            "initial_balances","bootstrap_policy","economic_parameters","combat_parameters",
            "alliance_parameters","github_allowlist","monitoring_policy_version",
            "monitoring_thresholds","pause_policy_version"}
        if set(value)!=required: raise ValueError("frozen Season manifest fields mismatch")
        unsigned=dict(value); supplied=unsigned.pop("manifest_hash")
        if sha256(unsigned)!=supplied: raise ValueError("frozen Season manifest hash mismatch")
        result=cls(value); result.validate()
        world_path=Path(path).resolve().parent.parent/value["world_fixture"]
        if not world_path.is_file() or sha256(loads(world_path.read_text(encoding="utf-8")))!=value["world_graph_hash"]:
            raise ValueError("world graph hash mismatch")
        return result

    def validate(self)->None:
        v=self.value
        if v["manifest_schema_version"]!="flop-empires-season-manifest-v1": raise ValueError("unsupported manifest schema")
        if v["activation"]!="FROZEN_NOT_ACTIVE" or v["environment"]!="production-frozen" or v["season_id"]!="season-0":
            raise ValueError("frozen manifest must remain inactive")
        if any(v[key] is not None for key in ("registration_boundary","season_start","season_end")):
            raise ValueError("frozen manifest cannot contain launch timestamps")
        if (v["epoch_duration"]!=21_600 or v["intended_duration_epochs"]!=56 or
                v["intended_duration_seconds"]!=1_209_600):
            raise ValueError("invalid frozen cadence")
        verify_key_from_did(v["referee_did"])
        for room in (v["actions_namespace"],v["events_namespace"]):
            if not ROOM_NAME.fullmatch(room) or "staging" in room: raise ValueError("invalid production namespace")
        if v["actions_namespace"]==v["events_namespace"]: raise ValueError("rooms must differ")
        combat=v["combat_parameters"]
        expected={"min_deadline_seconds":30,"raid_defense_window_seconds":1800,
            "siege_defense_window_seconds":21600,"recon_ttl_seconds":1800}
        if any(combat.get(key)!=value for key,value in expected.items()): raise ValueError("unvalidated combat windows")
        if (combat.get("capital_conquest") is not False or combat.get("tie_goes_to_defender") is not True or
                combat.get("raid_reward_divisor")!=2): raise ValueError("invalid frozen combat rules")
        if v["monitoring_policy_version"]!="season-0-monitoring-v1": raise ValueError("invalid monitoring policy")
        if v["pause_policy_version"]!="authoritative-clock-freeze-v1": raise ValueError("invalid pause policy")
        policy=v["bootstrap_policy"]
        if policy!={"historical_spendable_yield":0,"historical_prestige":"full_verified_value",
                "lookback_days":0,"historical_spendable_weight_bp":0,
                "prestige_retains_full_verified_value":True}:
            raise ValueError("invalid frozen bootstrap policy")
        EconomicRulesV02.from_manifest(v)

    @property
    def manifest_hash(self): return self.value["manifest_hash"]
    @property
    def rules(self): return EconomicRulesV02.from_manifest(self.value)
    def __getattr__(self,name):
        try: return self.value[name]
        except KeyError as exc: raise AttributeError(name) from exc


@dataclass(frozen=True)
class SeasonZeroFreezeV2CandidateManifest:
    """Rules-only candidate. Operational rooms and times belong to Activation Record v1."""
    value: dict[str,Any]

    @classmethod
    def load(cls,path: str|Path)->"SeasonZeroFreezeV2CandidateManifest":
        value=loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value,dict): raise ValueError("invalid freeze v2 candidate")
        required={"manifest_schema_version","manifest_hash","previous_failed_freeze_manifest_hash",
            "activation","environment","season_id","protocol_version","economic_rules_version",
            "technical_yield_version","referee_did","namespace_policy","registration_open",
            "registration_close","season_start","season_end","epoch_duration",
            "intended_duration_epochs","intended_duration_seconds","world_graph_hash","world_fixture",
            "initial_balances","bootstrap_policy","economic_parameters","combat_parameters",
            "alliance_parameters","github_allowlist","monitoring_policy_version",
            "monitoring_thresholds","pause_policy_version","gate_b_parameters"}
        if set(value)!=required: raise ValueError("freeze v2 candidate fields mismatch")
        unsigned=dict(value);supplied=unsigned.pop("manifest_hash")
        if sha256(unsigned)!=supplied: raise ValueError("freeze v2 candidate hash mismatch")
        result=cls(value);result.validate()
        world_path=Path(path).resolve().parent.parent/value["world_fixture"]
        if not world_path.is_file() or sha256(loads(world_path.read_text(encoding="utf-8")))!=value["world_graph_hash"]:
            raise ValueError("world graph hash mismatch")
        return result

    def validate(self)->None:
        v=self.value
        if v["manifest_schema_version"]!="flop-empires-season-freeze-v2-candidate-v2":
            raise ValueError("unsupported freeze v2 schema")
        if (v["activation"]!="FROZEN_NOT_ACTIVE" or v["environment"]!="production-freeze-v2-candidate"
                or v["season_id"]!="season-0"):
            raise ValueError("freeze v2 candidate must remain inactive")
        if any(v[key] is not None for key in ("registration_open","registration_close","season_start","season_end")):
            raise ValueError("freeze v2 candidate cannot contain launch timestamps")
        if v["economic_rules_version"]!="technical-yield-v0.2" or v["technical_yield_version"]!="technical-yield-v0.2":
            raise ValueError("freeze v2 must select technical-yield-v0.2")
        verify_key_from_did(v["referee_did"])
        policy=v["namespace_policy"]
        if policy!={"transport":"technocore-room-json-signed-v1","namespace_environment":"production",
                "namespace_prefix":"mb-p-flop-empires-s0-","namespace_token_hex_length":16,
                "require_empty_namespace":True}:
            raise ValueError("invalid production namespace policy")
        if (v["epoch_duration"]!=21600 or v["intended_duration_epochs"]!=56 or
                v["intended_duration_seconds"]!=1209600): raise ValueError("invalid frozen cadence")
        combat=v["combat_parameters"]
        expected={"min_deadline_seconds":30,"raid_defense_window_seconds":1800,
            "siege_defense_window_seconds":21600,"recon_ttl_seconds":1800,
            "raid_min_power":14,"siege_min_power":24}
        if any(combat.get(key)!=value for key,value in expected.items()): raise ValueError("unvalidated combat parameters")
        if combat.get("capital_conquest") is not False or combat.get("tie_goes_to_defender") is not True:
            raise ValueError("invalid frozen combat rules")
        if v["pause_policy_version"]!="authoritative-clock-freeze-v1": raise ValueError("invalid pause policy")
        gate=v["gate_b_parameters"]
        if gate.get("version")!="gate-b-v0.2-engine-aligned-candidate" or gate.get("status")!="SIMULATION_CANDIDATE_NOT_FROZEN":
            raise ValueError("invalid Gate B candidate")
        if gate.get("world",{}).get("empires")!=16 or gate.get("world",{}).get("territories")!=64:
            raise ValueError("invalid Gate B world")
        if gate.get("combat",{}).get("raid_min_power")!=14 or gate.get("combat",{}).get("siege_min_power")!=24:
            raise ValueError("invalid Gate B combat")
        if gate.get("late_join",{})!={"production_boost_bp":18750,"protection_epochs":4}:
            raise ValueError("invalid Gate B catch-up")
        EconomicRulesV02.from_manifest(v)

    @property
    def manifest_hash(self): return self.value["manifest_hash"]
    @property
    def rules(self): return EconomicRulesV02.from_manifest(self.value)
    def __getattr__(self,name):
        try:return self.value[name]
        except KeyError as exc:raise AttributeError(name) from exc


def validate_production_namespace(policy: dict[str,Any],room: str,kind: str)->None:
    if kind not in {"actions","events"}: raise ValueError("invalid namespace kind")
    prefix=policy.get("namespace_prefix")
    token_length=policy.get("namespace_token_hex_length")
    if not isinstance(prefix,str) or token_length!=16 or not isinstance(room,str):
        raise ValueError("NAMESPACE_BINDING_MISMATCH")
    expected_prefix=prefix
    suffix=f"-{kind}"
    if not room.startswith(expected_prefix) or not room.endswith(suffix) or not ROOM_NAME.fullmatch(room):
        raise ValueError("NAMESPACE_BINDING_MISMATCH")
    token=room[len(expected_prefix):-len(suffix)]
    if not PRODUCTION_NAMESPACE_TOKEN.fullmatch(token):
        raise ValueError("NAMESPACE_BINDING_MISMATCH")
