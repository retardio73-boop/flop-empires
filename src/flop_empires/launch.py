from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .activation import ActivationContext, is_verified_activation_context
from .canonical import bytes_, loads
from .identity import Signer, verify
from .manifest import SeasonZeroFreezeV2CandidateManifest

LAUNCH_FIELDS=frozenset({"version","launch_id","season_id","binding_id","frozen_manifest_hash",
    "referee_did","authorized_at","effective_start","effective_end","launch_status","signature"})
_LAUNCH_MARKER=object()

class LaunchAuthorizationError(RuntimeError): pass

@dataclass(frozen=True)
class LaunchAuthorizationContext:
    launch_id: str
    binding_id: str
    effective_start: int
    effective_end: int
    _marker: object

def is_verified_launch_context(value: object)->bool:
    return isinstance(value,LaunchAuthorizationContext) and value._marker is _LAUNCH_MARKER

@dataclass(frozen=True)
class LaunchAuthorization:
    value: dict[str,Any]

    @classmethod
    def load(cls,path: str|Path,manifest: SeasonZeroFreezeV2CandidateManifest,
             binding: ActivationContext)->"LaunchAuthorization":
        return cls.verify(loads(Path(path).read_text(encoding="utf-8")),manifest,binding)

    @classmethod
    def verify(cls,value: dict[str,Any],manifest: SeasonZeroFreezeV2CandidateManifest,
               binding: ActivationContext)->"LaunchAuthorization":
        if not is_verified_activation_context(binding):
            raise LaunchAuthorizationError("VERIFIED_BINDING_REQUIRED")
        if not isinstance(value,dict) or set(value)!=LAUNCH_FIELDS:
            raise LaunchAuthorizationError("LAUNCH_FIELDS_MISMATCH")
        unsigned=dict(value); signature=unsigned.pop("signature")
        if value["version"]!="flop-empires-launch-authorization-v1" or value["launch_status"]!="AUTHORIZE_LAUNCH":
            raise LaunchAuthorizationError("LAUNCH_STATUS_INVALID")
        for key in ("launch_id","season_id","binding_id","frozen_manifest_hash","referee_did"):
            if not isinstance(value[key],str) or not value[key]:
                raise LaunchAuthorizationError("LAUNCH_VALUE_INVALID")
        for key in ("authorized_at","effective_start","effective_end"):
            if not isinstance(value[key],int) or isinstance(value[key],bool) or value[key]<0:
                raise LaunchAuthorizationError("LAUNCH_TIME_INVALID")
        if not (value["authorized_at"]<=value["effective_start"]<value["effective_end"]):
            raise LaunchAuthorizationError("LAUNCH_TIME_ORDER_INVALID")
        if value["effective_start"]<binding.season_start:
            raise LaunchAuthorizationError("LAUNCH_BEFORE_EARLIEST_START")
        if value["effective_end"]-value["effective_start"]!=manifest.intended_duration_seconds:
            raise LaunchAuthorizationError("LAUNCH_DURATION_MISMATCH")
        if (value["season_id"]!=binding.season_id or value["binding_id"]!=binding.activation_id or
                value["frozen_manifest_hash"]!=manifest.manifest_hash or
                value["referee_did"]!=binding.referee_did):
            raise LaunchAuthorizationError("LAUNCH_BINDING_MISMATCH")
        if not isinstance(signature,str) or not verify(value["referee_did"],bytes_(unsigned),signature):
            raise LaunchAuthorizationError("LAUNCH_SIGNATURE_INVALID")
        return cls(dict(value))

    def context(self)->LaunchAuthorizationContext:
        v=self.value
        return LaunchAuthorizationContext(v["launch_id"],v["binding_id"],v["effective_start"],v["effective_end"],_LAUNCH_MARKER)

def sign_launch_payload(payload: dict[str,Any],signer: Signer)->dict[str,Any]:
    if set(payload)!=LAUNCH_FIELDS-{"signature"}:
        raise LaunchAuthorizationError("LAUNCH_FIELDS_MISMATCH")
    if payload.get("referee_did")!=signer.did:
        raise LaunchAuthorizationError("LAUNCH_REFEREE_MISMATCH")
    return {**payload,"signature":signer.sign(bytes_(payload))}
