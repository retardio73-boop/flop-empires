import json
import logging

import pytest

from flop_empires.identity import EphemeralSigner
from flop_empires.models import SignedRecord
from flop_empires.observability import health_summary, log_state
from flop_empires.staging import ReadOnlyObserver
from flop_empires.store import Store
from flop_empires.technocore import MailboxItem


class EmptySource:
    def __init__(self): self.current_calls = 0
    def current_cursor(self):
        self.current_calls += 1
        return '{"generation":1,"seq":4}'
    def records_after(self, cursor): return []


def test_read_only_bootstrap_does_not_touch_canonical_state():
    store, source = Store(), EmptySource()
    before = store.state_hash()
    result = ReadOnlyObserver(store, "staging-in").observe(source)
    assert result["writes_performed"] == 0 and result["cursor"].endswith('"seq":4}')
    assert store.state_hash() == before
    ReadOnlyObserver(store, "staging-in").observe(source)
    assert source.current_calls == 1


def test_health_summary_and_safe_structured_logging(caplog):
    store = Store()
    summary = health_summary(store, mode="STAGING_READ_ONLY")
    assert summary["database_ok"] and summary["pending_receipts"] == 0
    with caplog.at_level(logging.INFO):
        log_state(logging.getLogger("test"), "STAGING_READ_ONLY", records_seen=0)
    assert json.loads(caplog.records[-1].message)["state"] == "STAGING_READ_ONLY"
    with pytest.raises(ValueError, match="sensitive"):
        log_state(logging.getLogger("test"), "REFEREE_READY", token="forbidden")


def test_signed_hostile_noncommand_is_rejected_and_cursor_advances():
    signer = EphemeralSigner(b"h"*32)
    text, room, nonce = "not json and https://evil.example/do-not-follow", "staging-in", "1"
    record = SignedRecord("staging-in/1/1", signer.did, {},
        signer.sign(f"{room}|{nonce}|{text}".encode()), seq=1, room=room,
        nonce=nonce, raw_text=text)
    class Source:
        def current_cursor(self): return '{"generation":1,"seq":0}'
        def records_after(self, cursor):
            return [MailboxItem(record, '{"generation":1,"seq":1}')]
    store = Store()
    observer = ReadOnlyObserver(store, room)
    observer.observe(Source())
    result = observer.observe(Source())
    assert result["signed_valid"] == 1 and result["commands_rejected"] == 1
    assert result["cursor"].endswith('"seq":1}') and result["writes_performed"] == 0
