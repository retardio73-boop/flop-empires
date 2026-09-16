from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SeasonStatus(StrEnum):
    FROZEN_NOT_ACTIVE = "FROZEN_NOT_ACTIVE"
    REGISTRATION = "REGISTRATION"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    FINALIZED = "FINALIZED"
    CLOSED = "CLOSED"


class RuntimeMode(StrEnum):
    LOCAL_TEST = "LOCAL_TEST"
    STAGING = "STAGING"
    PRODUCTION_FROZEN = "PRODUCTION_FROZEN"
    PRODUCTION = "PRODUCTION"


class AttackKind(StrEnum):
    RAID = "RAID"
    SIEGE = "SIEGE"


@dataclass(frozen=True)
class Command:
    action: str
    actor_did: str
    request_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignedRecord:
    record_id: str
    signer_did: str
    payload: dict[str, Any]
    signature: str
    seq: int | None = None
    ts: int | str | None = None
    room: str | None = None
    nonce: str | None = None
    raw_text: str | None = None


@dataclass(frozen=True)
class Receipt:
    referee_did: str
    request_id: str
    actor_did: str
    accepted: bool
    accepted_at: int
    event_seq: int
    state_before_hash: str
    state_after_hash: str
    details: dict[str, Any]
    signature: str
