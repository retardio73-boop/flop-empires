from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SeasonStatus(StrEnum):
    REGISTRATION = "REGISTRATION"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


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
    ts: int | None = None


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
