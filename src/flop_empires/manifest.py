from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import loads, sha256
from .economics_v02 import EconomicRulesV02


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
