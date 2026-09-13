from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from .canonical import dumps, loads, sha256
from .engine import Engine
from .models import Receipt
from .protocol import parse_command
from .store import Store
from .technocore import SignedMailbox, TechnocoreIngestor, verify_signed_record


class StagingMode(StrEnum):
    READ_ONLY = "STAGING_READ_ONLY"
    WRITE = "STAGING_WRITE"


@dataclass(frozen=True)
class StagingManifest:
    season_id: str
    mailbox: str
    events_room: str
    referee_did: str
    allowed_dids: tuple[str, ...]
    mode: StagingMode

    @classmethod
    def load(cls, path: str | Path) -> "StagingManifest":
        value = loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("invalid staging manifest")
        manifest = cls(value["season_id"], value["mailbox"], value["events_room"],
            value["referee_did"], tuple(value["allowed_dids"]), StagingMode(value["mode"]))
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if not self.season_id.startswith("staging-"):
            raise ValueError("staging season namespace must start with staging-")
        if not self.mailbox.startswith("staging-") or not self.events_room.startswith("staging-"):
            raise ValueError("staging rooms require staging- namespace")
        if self.mailbox == self.events_room:
            raise ValueError("mailbox and events room must differ")
        if not self.referee_did.startswith("did:key:"):
            raise ValueError("invalid staging referee DID")
        if not self.allowed_dids or any(not x.startswith("did:key:") for x in self.allowed_dids):
            raise ValueError("staging DID allowlist required")


class ReadOnlyObserver:
    def __init__(self, store: Store, mailbox_name: str, clock=None):
        self.store, self.mailbox_name = store, mailbox_name
        self.clock = clock or (lambda: int(time.time()))

    def observe(self, source: SignedMailbox) -> dict:
        state = self.store.one("SELECT cursor FROM technocore_state WHERE mailbox=?", (self.mailbox_name,))
        if not state:
            cursor = source.current_cursor()
            self.store.conn.execute("INSERT INTO technocore_state VALUES(?,?,1)",
                (self.mailbox_name, cursor))
            return self._summary(cursor)
        cursor = state[0]
        for item in source.records_after(cursor):
            duplicate = self.store.one("SELECT 1 FROM staging_diagnostics WHERE mailbox=? AND record_id=?",
                (self.mailbox_name, item.record.record_id))
            if duplicate:
                continue
            outcome, details = "COMMAND_REJECTED", {}
            if verify_signed_record(item.record):
                details["signed_valid"] = True
                try:
                    command = parse_command(item.record.payload)
                    details.update({"commands_valid": True, "action": command.action,
                        "actor_did": command.actor_did, "candidate_transition": True})
                    outcome = "CANDIDATE_TRANSITION"
                except ValueError as exc:
                    details["reason"] = str(exc)
            else:
                details["reason"] = "signature_invalid"
            self.store.conn.execute("INSERT INTO staging_diagnostics(observed_at,mailbox,record_id,outcome,details_json) VALUES(?,?,?,?,?)",
                (self.clock(), self.mailbox_name, item.record.record_id, outcome, dumps(details)))
            self.store.conn.execute("UPDATE technocore_state SET cursor=? WHERE mailbox=?",
                (item.next_cursor, self.mailbox_name))
            cursor = item.next_cursor
        return self._summary(cursor)

    def _summary(self, cursor: str) -> dict:
        rows = list(self.store.conn.execute("SELECT outcome,details_json FROM staging_diagnostics WHERE mailbox=?",
            (self.mailbox_name,)))
        details = [json.loads(r[1]) for r in rows]
        return {"records_seen": len(rows), "signed_valid": sum(bool(x.get("signed_valid")) for x in details),
            "commands_valid": sum(bool(x.get("commands_valid")) for x in details),
            "commands_rejected": sum(r[0] == "COMMAND_REJECTED" for r in rows),
            "duplicates": 0, "cursor": cursor, "github_evidence_checked": 0,
            "candidate_transitions": sum(bool(x.get("candidate_transition")) for x in details),
            "writes_performed": 0}


class ReceiptPublicationTransport(Protocol):
    def publish_and_verify(self, receipt_hash: str, canonical_receipt: str) -> tuple[str, bool]: ...


class ReceiptOutbox:
    def __init__(self, store: Store):
        self.store = store

    def recover(self) -> int:
        inserted = 0
        for row in self.store.conn.execute("SELECT actor_did,request_id,receipt_json FROM requests ORDER BY actor_did,request_id"):
            digest = sha256(loads(row["receipt_json"]))
            cur = self.store.conn.execute("INSERT OR IGNORE INTO receipt_outbox(receipt_hash,actor_did,request_id,receipt_json,status) VALUES(?,?,?,?, 'PENDING')",
                (digest, row["actor_did"], row["request_id"], row["receipt_json"]))
            inserted += cur.rowcount
        return inserted

    def flush(self, transport: ReceiptPublicationTransport, clock=None) -> dict:
        clock = clock or (lambda: int(time.time()))
        published = 0
        for row in self.store.conn.execute("SELECT * FROM receipt_outbox WHERE status='PENDING' ORDER BY receipt_hash"):
            self.store.conn.execute("UPDATE receipt_outbox SET attempts=attempts+1 WHERE receipt_hash=?",
                (row["receipt_hash"],))
            ref, verified = transport.publish_and_verify(row["receipt_hash"], row["receipt_json"])
            if not verified:
                continue
            with self.store.transaction():
                self.store.conn.execute("UPDATE receipt_outbox SET status='PUBLISHED',publish_ref=?,readback_verified=1 WHERE receipt_hash=?",
                    (ref, row["receipt_hash"]))
                self.store.conn.execute("INSERT OR REPLACE INTO publication_evidence VALUES(?,?,?)",
                    (row["receipt_hash"], ref, clock()))
            published += 1
        return {"published": published, "pending": self.store.one(
            "SELECT COUNT(*) FROM receipt_outbox WHERE status='PENDING'")[0]}


class StagingWriteService:
    def __init__(self, manifest: StagingManifest, engine: Engine, outbox: ReceiptOutbox):
        manifest.validate()
        if manifest.mode != StagingMode.WRITE or engine.signer.did != manifest.referee_did:
            raise RuntimeError("STAGING_WRITE manifest/signer mismatch")
        self.manifest, self.engine, self.outbox = manifest, engine, outbox

    def execute(self, command: dict) -> Receipt:
        if command.get("actor_did") not in self.manifest.allowed_dids:
            raise ValueError("actor not allowlisted for staging")
        receipt = self.engine.execute(command)
        self.outbox.recover()
        return receipt
