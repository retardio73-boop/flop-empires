from __future__ import annotations

import json
from dataclasses import asdict
from typing import Protocol

from .canonical import bytes_, dumps
from .engine import Engine, RuleViolation
from .identity import verify
from .models import Receipt, SignedRecord
from .store import Store


class SignedMailbox(Protocol):
    def current_cursor(self) -> str: ...
    def records_after(self, cursor: str) -> list[SignedRecord]: ...


def signed_record_body(record: SignedRecord) -> dict:
    return {"record_id": record.record_id, "signer_did": record.signer_did,
            "payload": record.payload, "seq": record.seq, "ts": record.ts}


class TechnocoreIngestor:
    def __init__(self, store: Store, engine: Engine, mailbox: str):
        self.store, self.engine, self.mailbox = store, engine, mailbox

    def bootstrap(self, current_cursor: str, *, replay: bool = False) -> str:
        row = self.store.one("SELECT cursor FROM technocore_state WHERE mailbox=?", (self.mailbox,))
        if row:
            return row[0]
        cursor = "" if replay else current_cursor
        self.store.conn.execute("INSERT INTO technocore_state VALUES(?,?,1)", (self.mailbox, cursor))
        return cursor

    def ingest(self, record: SignedRecord, next_cursor: str, accepted_at: int) -> Receipt:
        old = self.store.one("SELECT receipt_json FROM technocore_records WHERE record_id=?", (record.record_id,))
        if old:
            return Receipt(**json.loads(old[0]))
        if not verify(record.signer_did, bytes_(signed_record_body(record)), record.signature):
            raise RuleViolation("Technocore signed-record verification failed")
        command = record.payload
        if not isinstance(command, dict) or command.get("actor_did") != record.signer_did:
            raise RuleViolation("signed record actor mismatch")
        # Remote seq/ts remain stored evidence; Engine persists its own accepted_at.
        receipt = self.engine.execute(command)
        with self.store.transaction():
            if receipt.accepted_at != accepted_at:
                # The caller must pass the persisted referee time it observed, never remote ts.
                accepted_at = receipt.accepted_at
            self.store.conn.execute("INSERT INTO technocore_records VALUES(?,?,?,?,?,?)",
                (record.record_id, self.mailbox, record.seq, record.ts, accepted_at, dumps(asdict(receipt))))
            self.store.conn.execute("UPDATE technocore_state SET cursor=? WHERE mailbox=?", (next_cursor, self.mailbox))
        return receipt
