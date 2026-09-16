from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import bytes_,dumps,loads
from .identity import Signer,verify
from .manifest import SeasonZeroFreezeV2CandidateManifest,validate_production_namespace


ACTIVATION_FIELDS=frozenset({"version","activation_id","season_id","frozen_manifest_hash",
    "referee_did","actions_namespace","events_namespace","registration_open",
    "registration_close","season_start","season_end","issued_at","activation_status","signature"})
FORBIDDEN_RULE_FIELDS=frozenset({"economic_parameters","combat_parameters","alliance_parameters",
    "technical_yield_rules","technical_yield_version","bootstrap_policy","world_graph_rules",
    "world_graph_hash","resource_weights","epoch_duration","raid_rules","siege_rules",
    "prestige_rules"})
_VERIFIED_MARKER=object()


class ActivationError(RuntimeError): pass


@dataclass(frozen=True)
class ActivationRecord:
    value: dict[str,Any]

    @classmethod
    def load(cls,path: str|Path,manifest: SeasonZeroFreezeV2CandidateManifest)->"ActivationRecord":
        value=loads(Path(path).read_text(encoding="utf-8"))
        return cls.verify(value,manifest)

    @classmethod
    def verify(cls,value: dict[str,Any],manifest: SeasonZeroFreezeV2CandidateManifest)->"ActivationRecord":
        if not isinstance(value,dict) or set(value)!=ACTIVATION_FIELDS:
            raise ActivationError("ACTIVATION_FIELDS_MISMATCH")
        if set(value)&FORBIDDEN_RULE_FIELDS: raise ActivationError("ACTIVATION_RULE_FIELD_FORBIDDEN")
        unsigned=dict(value);signature=unsigned.pop("signature")
        if dumps(loads(dumps(unsigned)))!=dumps(unsigned): raise ActivationError("ACTIVATION_NOT_CANONICAL")
        if value["version"]!="flop-empires-activation-v1" or value["activation_status"]!="AUTHORIZE_SEASON":
            raise ActivationError("ACTIVATION_STATUS_INVALID")
        for key in ("activation_id","season_id","frozen_manifest_hash","referee_did",
                    "actions_namespace","events_namespace"):
            if not isinstance(value[key],str) or not value[key]: raise ActivationError("ACTIVATION_VALUE_INVALID")
        for key in ("registration_open","registration_close","season_start","season_end","issued_at"):
            if not isinstance(value[key],int) or isinstance(value[key],bool) or value[key]<0:
                raise ActivationError("ACTIVATION_TIME_INVALID")
        if not (value["issued_at"]<=value["registration_open"]<value["registration_close"]<=
                value["season_start"]<value["season_end"]):
            raise ActivationError("ACTIVATION_TIME_ORDER_INVALID")
        if value["season_end"]-value["season_start"]!=manifest.intended_duration_seconds:
            raise ActivationError("ACTIVATION_DURATION_MISMATCH")
        if value["frozen_manifest_hash"]!=manifest.manifest_hash:
            raise ActivationError("ACTIVATION_MANIFEST_MISMATCH")
        if value["season_id"]!=manifest.season_id: raise ActivationError("ACTIVATION_SEASON_MISMATCH")
        if value["referee_did"]!=manifest.referee_did: raise ActivationError("ACTIVATION_REFEREE_MISMATCH")
        validate_production_namespace(manifest.namespace_policy,value["actions_namespace"],"actions")
        validate_production_namespace(manifest.namespace_policy,value["events_namespace"],"events")
        if value["actions_namespace"]==value["events_namespace"]: raise ActivationError("ACTIVATION_NAMESPACES_COLLIDE")
        if not isinstance(signature,str) or not verify(value["referee_did"],bytes_(unsigned),signature):
            raise ActivationError("ACTIVATION_SIGNATURE_INVALID")
        return cls(dict(value))

    def context(self)->"ActivationContext":
        return ActivationContext(self.value["activation_id"],self.value["season_id"],
            self.value["frozen_manifest_hash"],self.value["referee_did"],
            self.value["actions_namespace"],self.value["events_namespace"],
            self.value["registration_open"],self.value["registration_close"],
            self.value["season_start"],self.value["season_end"],_VERIFIED_MARKER)


@dataclass(frozen=True)
class ActivationContext:
    activation_id: str
    season_id: str
    frozen_manifest_hash: str
    referee_did: str
    actions_namespace: str
    events_namespace: str
    registration_open: int
    registration_close: int
    season_start: int
    season_end: int
    _marker: object


def is_verified_activation_context(value: object)->bool:
    return isinstance(value,ActivationContext) and value._marker is _VERIFIED_MARKER


def sign_activation_payload(payload: dict[str,Any],signer: Signer)->dict[str,Any]:
    """Explicit helper for controlled fixture/operator tooling; it never chooses values."""
    if set(payload)!=ACTIVATION_FIELDS-{"signature"}: raise ActivationError("ACTIVATION_FIELDS_MISMATCH")
    if payload.get("referee_did")!=signer.did: raise ActivationError("ACTIVATION_REFEREE_MISMATCH")
    return {**payload,"signature":signer.sign(bytes_(payload))}
