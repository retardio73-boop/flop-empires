from dataclasses import replace

import httpx

import pytest

from flop_empires.canonical import bytes_
from flop_empires.engine import Engine, RuleViolation
from flop_empires.identity import EphemeralSigner
from flop_empires.models import SignedRecord
from flop_empires.simulator import simulate
from flop_empires.store import Store
from flop_empires.canonical import dumps
from flop_empires.technocore import (MailboxItem, TechnocoreHttpMailbox,
    TechnocoreIngestor, signed_record_body, verify_signed_record)


def test_signed_mailbox_bootstrap_verification_and_duplicates():
    referee, actor = EphemeralSigner(b"r" * 32), EphemeralSigner(b"a" * 32)
    store = Store()
    engine = Engine(store, referee.did, referee, clock=lambda: 99)
    ingestor = TechnocoreIngestor(store, engine, "main")
    assert ingestor.bootstrap("cursor-now") == "cursor-now"
    payload = {"action":"register_actor", "actor_did":actor.did, "request_id":"r", "payload":{}}
    unsigned = SignedRecord("record-1", actor.did, payload, "", seq=123, ts=1)
    record = replace(unsigned, signature=actor.sign(bytes_(signed_record_body(unsigned))))
    first = ingestor.ingest(record, "cursor-next", 99)
    second = ingestor.ingest(record, "cursor-next", 99)
    assert first == second and first.accepted
    assert store.one("SELECT cursor FROM technocore_state WHERE mailbox='main'")[0] == "cursor-next"
    with pytest.raises(RuleViolation):
        ingestor.ingest(replace(record, record_id="bad", signature="AAAA"), "rewind", 99)
    assert store.one("SELECT cursor FROM technocore_state WHERE mailbox='main'")[0] == "cursor-next"


def test_poll_durably_advances_only_through_verified_records():
    referee, actor = EphemeralSigner(b"r" * 32), EphemeralSigner(b"a" * 32)
    store = Store()
    engine = Engine(store, referee.did, referee, clock=lambda: 101)
    ingestor = TechnocoreIngestor(store, engine, "poll")
    payload = {"action":"register_actor", "actor_did":actor.did, "request_id":"one", "payload":{}}
    unsigned = SignedRecord("one", actor.did, payload, "", seq=1, ts=999999)
    good = replace(unsigned, signature=actor.sign(bytes_(signed_record_body(unsigned))))
    bad = replace(good, record_id="two", signature="AAAA", seq=2)

    class Source:
        def current_cursor(self): return "head"
        def records_after(self, cursor):
            assert cursor == "head"
            return [MailboxItem(good, "c1"), MailboxItem(bad, "c2")]

    with pytest.raises(RuleViolation):
        ingestor.poll(Source())
    assert store.one("SELECT cursor FROM technocore_state WHERE mailbox='poll'")[0] == "c1"
    assert store.one("SELECT accepted_at FROM technocore_records WHERE record_id='one'")[0] == 101


def test_fixed_origin_http_mailbox_parses_and_verifies_exact_room_signature():
    actor = EphemeralSigner(b"a" * 32)
    payload = {"action":"register_actor", "actor_did":actor.did, "request_id":"live", "payload":{}}
    text = dumps(payload)
    signature = actor.sign(f"empire-room|9007199254740993123|{text}".encode())
    message = {"seq": 6, "ts": "2026-09-12T12:00:00Z", "from": actor.did,
               "nonce": 9007199254740993123, "sig": signature, "text": text}

    def handler(request):
        assert request.url.host == "technocore.chat" and request.method == "GET"
        return httpx.Response(200, json={"generation": 3, "messages": [message]}, request=request)

    mailbox = TechnocoreHttpMailbox(httpx.Client(transport=httpx.MockTransport(handler)),
                                    "empire-room")
    items = mailbox.records_after(dumps({"generation": 3, "seq": 5}))
    assert len(items) == 1 and items[0].next_cursor == '{"generation":3,"seq":6}'
    assert verify_signed_record(items[0].record)


def test_http_mailbox_rejects_generation_change():
    response = {"generation": 4, "messages": []}
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response, request=request)))
    mailbox = TechnocoreHttpMailbox(client, "empire-room")
    with pytest.raises(RuleViolation, match="generation changed"):
        mailbox.records_after(dumps({"generation": 3, "seq": 5}))


def test_100k_deterministic_simulation():
    report = simulate(seed=7, actions=100_000)
    assert report["generated_actions"] == 100_000
    assert report["detected_invariant_failures"] == []
    assert report["final_state_hash"] == simulate(seed=7, actions=100_000)["final_state_hash"]
