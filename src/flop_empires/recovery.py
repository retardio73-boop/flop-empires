from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .activation import ActivationContext, _VERIFIED_MARKER
from .canonical import bytes_, dumps, loads
from .identity import Signer, verify
from .manifest import SeasonZeroFreezeV2CandidateManifest, validate_production_namespace

RECOVERY_FIELDS=frozenset({"version","recovery_id","season_id","frozen_manifest_hash","original_activation_id",
    "failed_state_hash","failed_event_head","reason_codes","referee_did","duplex_namespace",
    "registration_open","registration_close","season_start","season_end","issued_at","recovery_status","signature"})

class RecoveryError(RuntimeError): pass

@dataclass(frozen=True)
class RecoveryRecord:
    value: dict[str,Any]

    @classmethod
    def load(cls,path: str|Path,manifest: SeasonZeroFreezeV2CandidateManifest)->"RecoveryRecord":
        return cls.verify(loads(Path(path).read_text(encoding="utf-8")),manifest)

    @classmethod
    def verify(cls,value: dict[str,Any],manifest: SeasonZeroFreezeV2CandidateManifest)->"RecoveryRecord":
        if not isinstance(value,dict) or set(value)!=RECOVERY_FIELDS: raise RecoveryError("RECOVERY_FIELDS_MISMATCH")
        unsigned=dict(value); signature=unsigned.pop("signature")
        if value["version"]!="flop-empires-recovery-v1" or value["recovery_status"]!="AUTHORIZE_RECOVERY":
            raise RecoveryError("RECOVERY_STATUS_INVALID")
        for key in ("recovery_id","season_id","frozen_manifest_hash","original_activation_id","failed_state_hash","referee_did","duplex_namespace"):
            if not isinstance(value[key],str) or not value[key]: raise RecoveryError("RECOVERY_VALUE_INVALID")
        for key in ("registration_open","registration_close","season_start","season_end","issued_at"):
            if not isinstance(value[key],int) or isinstance(value[key],bool) or value[key]<0: raise RecoveryError("RECOVERY_TIME_INVALID")
        if not (value["issued_at"]<=value["registration_open"]<value["registration_close"]<=value["season_start"]<value["season_end"]):
            raise RecoveryError("RECOVERY_TIME_ORDER_INVALID")
        if value["season_end"]-value["season_start"]!=manifest.intended_duration_seconds:
            raise RecoveryError("RECOVERY_DURATION_MISMATCH")
        if value["season_id"]!=manifest.season_id or value["frozen_manifest_hash"]!=manifest.manifest_hash:
            raise RecoveryError("RECOVERY_MANIFEST_MISMATCH")
        if value["referee_did"]!=manifest.referee_did: raise RecoveryError("RECOVERY_REFEREE_MISMATCH")
        validate_production_namespace(manifest.namespace_policy,value["duplex_namespace"],"events")
        if not isinstance(value["reason_codes"],list) or not value["reason_codes"] or not all(isinstance(x,str) and x for x in value["reason_codes"]):
            raise RecoveryError("RECOVERY_REASONS_INVALID")
        if not isinstance(value["failed_event_head"],dict): raise RecoveryError("RECOVERY_FAILED_HEAD_INVALID")
        if not isinstance(signature,str) or not verify(value["referee_did"],bytes_(unsigned),signature):
            raise RecoveryError("RECOVERY_SIGNATURE_INVALID")
        return cls(dict(value))

    def context(self)->ActivationContext:
        v=self.value
        return ActivationContext(v["recovery_id"],v["season_id"],v["frozen_manifest_hash"],v["referee_did"],
            v["duplex_namespace"],v["duplex_namespace"],v["registration_open"],v["registration_close"],
            v["season_start"],v["season_end"],_VERIFIED_MARKER)

def sign_recovery_payload(payload: dict[str,Any],signer: Signer)->dict[str,Any]:
    if set(payload)!=RECOVERY_FIELDS-{"signature"}: raise RecoveryError("RECOVERY_FIELDS_MISMATCH")
    if payload.get("referee_did")!=signer.did: raise RecoveryError("RECOVERY_REFEREE_MISMATCH")
    return {**payload,"signature":signer.sign(bytes_(payload))}
