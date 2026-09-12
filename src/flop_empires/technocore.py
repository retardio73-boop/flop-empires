from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Protocol

import httpx

from .canonical import bytes_, dumps, loads
from .engine import Engine, RuleViolation
from .identity import verify
from .models import Receipt, SignedRecord
from .store import Store


@dataclass(frozen=True)
class MailboxItem:
    record: SignedRecord
    next_cursor: str


class SignedMailbox(Protocol):
    def current_cursor(self) -> str: ...
    def records_after(self, cursor: str) -> list[MailboxItem]: ...


def signed_record_body(record: SignedRecord) -> dict:
    return {"record_id": record.record_id, "signer_did": record.signer_did,
            "payload": record.payload, "seq": record.seq, "ts": record.ts}


def verify_signed_record(record: SignedRecord) -> bool:
    if record.room is not None or record.nonce is not None or record.raw_text is not None:
        if not all(isinstance(x, str) and x for x in (record.room, record.nonce, record.raw_text)):
            return False
        if record.raw_text != dumps(record.payload):
            return False
        return verify(record.signer_did,
            f"{record.room}|{record.nonce}|{record.raw_text}".encode("utf-8"), record.signature)
    return verify(record.signer_did, bytes_(signed_record_body(record)), record.signature)


class TechnocoreHttpMailbox:
    """Bounded, read-only adapter for the fixed Technocore room JSON endpoint."""
    ORIGIN = "https://technocore.chat"
    ROOM = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

    def __init__(self, client: httpx.Client, room: str, *, limit: int = 200):
        if not self.ROOM.fullmatch(room) or not 1 <= limit <= 200:
            raise ValueError("invalid Technocore room or limit")
        self.client, self.room, self.limit = client, room, limit

    def _read(self, since: int) -> dict:
        response = self.client.get(f"{self.ORIGIN}/r/{self.room}",
            params={"format": "json", "since": since, "limit": self.limit},
            follow_redirects=False, timeout=10.0)
        response.raise_for_status()
        if response.url.scheme != "https" or response.url.host != "technocore.chat":
            raise ValueError("Technocore response left fixed origin")
        if len(response.content) > 524_288:
            raise ValueError("Technocore response too large")
        value = response.json()
        if not isinstance(value, dict) or not isinstance(value.get("generation"), int) or isinstance(value["generation"], bool):
            raise ValueError("invalid Technocore room response")
        if not isinstance(value.get("messages", []), list):
            raise ValueError("invalid Technocore messages")
        return value

    @staticmethod
    def _cursor(generation: int, seq: int) -> str:
        return dumps({"generation": generation, "seq": seq})

    @staticmethod
    def _parse_cursor(cursor: str) -> tuple[int, int]:
        value = loads(cursor)
        if (not isinstance(value, dict) or set(value) != {"generation", "seq"} or
                not all(isinstance(value[x], int) and not isinstance(value[x], bool) and value[x] >= 0
                        for x in ("generation", "seq"))):
            raise ValueError("invalid Technocore cursor")
        return value["generation"], value["seq"]

    def current_cursor(self) -> str:
        seq, generation = 0, None
        for _ in range(100):
            value = self._read(seq)
            if generation is not None and value["generation"] != generation:
                raise RuleViolation("Technocore generation changed during bootstrap")
            generation = value["generation"]
            seqs = [m.get("seq") for m in value["messages"] if isinstance(m, dict)]
            valid = [x for x in seqs if isinstance(x, int) and not isinstance(x, bool) and x > seq]
            if not valid:
                return self._cursor(generation, seq)
            seq = max(valid)
            if len(value["messages"]) < self.limit:
                return self._cursor(generation, seq)
        raise RuleViolation("Technocore bootstrap exceeded bounded history scan")

    def records_after(self, cursor: str) -> list[MailboxItem]:
        generation, seq = self._parse_cursor(cursor)
        value = self._read(seq)
        if value["generation"] != generation:
            raise RuleViolation("Technocore generation changed; explicit audit/bootstrap required")
        messages = sorted(value["messages"], key=lambda x: x.get("seq", -1) if isinstance(x, dict) else -1)
        items: list[MailboxItem] = []
        expected = seq + 1
        for message in messages:
            if not isinstance(message, dict):
                raise RuleViolation("invalid Technocore message")
            msg_seq = message.get("seq")
            if not isinstance(msg_seq, int) or isinstance(msg_seq, bool) or msg_seq != expected:
                raise RuleViolation("Technocore sequence gap")
            signer, nonce, signature, text = (message.get("from"), str(message.get("nonce", "")),
                message.get("sig"), message.get("text"))
            if not all(isinstance(x, str) and x for x in (signer, nonce, signature, text)):
                raise RuleViolation("unsigned Technocore message")
            try:
                payload = loads(text)
            except ValueError as exc:
                raise RuleViolation("Technocore text is not a canonical command") from exc
            if not isinstance(payload, dict) or text != dumps(payload):
                raise RuleViolation("Technocore command is not canonical")
            record = SignedRecord(f"{self.room}/{generation}/{msg_seq}", signer, payload,
                signature, seq=msg_seq, ts=message.get("ts"), room=self.room,
                nonce=nonce, raw_text=text)
            items.append(MailboxItem(record, self._cursor(generation, msg_seq)))
            expected += 1
        return items


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
        if not verify_signed_record(record):
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

    def poll(self, source: SignedMailbox, *, replay: bool = False) -> list[Receipt]:
        """Read one finite batch; a failure leaves the cursor at the last durable item."""
        persisted = self.store.one("SELECT cursor FROM technocore_state WHERE mailbox=?", (self.mailbox,))
        cursor = persisted[0] if persisted else self.bootstrap(source.current_cursor(), replay=replay)
        receipts: list[Receipt] = []
        for item in source.records_after(cursor):
            if not isinstance(item, MailboxItem) or not item.next_cursor:
                raise RuleViolation("invalid Technocore mailbox item")
            receipt = self.ingest(item.record, item.next_cursor, accepted_at=0)
            receipts.append(receipt)
            cursor = item.next_cursor
        return receipts
