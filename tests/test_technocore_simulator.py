from dataclasses import replace

import httpx

import pytest

from flop_empires.canonical import bytes_
from flop_empires.engine import Engine, RuleViolation
from flop_empires.identity import EphemeralSigner
from flop_empires.models import SignedRecord
from flop_empires.simulator import simulate
from flop_empires.store import Store
from flop_empires.canonical import dumps, sha256
from flop_empires.technocore import (MailboxItem, TechnocoreHttpMailbox,
    RoomEnvelope, TechnocoreIngestor, TechnocoreTransport, signed_record_body,
    verify_signed_record)


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

    receipts=ingestor.poll(Source())
    assert len(receipts)==1 and receipts[0].accepted
    assert store.one("SELECT cursor FROM technocore_state WHERE mailbox='poll'")[0] == "c2"
    assert store.one("SELECT code FROM technocore_rejections WHERE record_id='two'")[0] == "INVALID_SIGNATURE"
    assert store.one("SELECT accepted_at FROM technocore_records WHERE record_id='one'")[0] == 101


def test_staging_ingestor_rejects_valid_but_non_allowlisted_signer():
    referee, allowed, outsider = (EphemeralSigner(b"r" * 32), EphemeralSigner(b"a" * 32),
                                  EphemeralSigner(b"o" * 32))
    store = Store(); engine = Engine(store, referee.did, referee, clock=lambda: 101)
    ingestor = TechnocoreIngestor(store, engine, "mb-p-staging-flop-empires-test",
                                  allowed_dids=(allowed.did,))
    payload = {"action":"register_actor", "actor_did":outsider.did,
               "request_id":"outsider", "payload":{}}
    unsigned = SignedRecord("outside", outsider.did, payload, "", seq=1, ts=1)
    record = replace(unsigned, signature=outsider.sign(bytes_(signed_record_body(unsigned))))
    before = store.state_hash()
    with pytest.raises(RuleViolation, match="DID_NOT_ALLOWLISTED"):
        ingestor.ingest(record, "next", 101)
    assert store.state_hash() == before


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


def test_http_mailbox_accepts_only_initial_room_creation_generation_transition():
    actor = EphemeralSigner(b"a" * 32)
    payload = {"action":"register_actor", "actor_did":actor.did,
               "request_id":"first", "payload":{}}
    text = dumps(payload); signature = actor.sign(f"new-room|1|{text}".encode())
    message = {"seq":1,"ts":"now","from":actor.did,"nonce":1,
               "sig":signature,"text":text}
    client = httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(200,json={"generation":1,"messages":[message]},request=request)))
    mailbox = TechnocoreHttpMailbox(client,"new-room")
    items = mailbox.records_after('{"generation":0,"seq":0}')
    assert len(items) == 1 and items[0].next_cursor == '{"generation":1,"seq":1}'


def test_concrete_transport_publish_readback_and_semantic_dedupe():
    key = EphemeralSigner(b"p" * 32)
    messages, posts = [], [0]
    class RoomSigner:
        did = key.did
        def sign_room(self, room, text):
            nonce = "77"
            return RoomEnvelope(self.did, nonce, key.sign(f"{room}|{nonce}|{text}".encode()), text)
    def handler(request):
        if request.method == "POST":
            posts[0] += 1
            body = __import__("json").loads(request.content)
            messages.append({"seq":1,"ts":"now","from":body["did"],"nonce":body["nonce"],
                             "sig":body["sig"],"text":body["text"]})
            return httpx.Response(200, json={"ok":True}, request=request)
        return httpx.Response(200, json={"generation":1,"messages":messages}, request=request)
    transport = TechnocoreTransport(httpx.Client(transport=httpx.MockTransport(handler)),
                                    "staging-events", signer=RoomSigner())
    body = dumps({"receipt":"safe"}); digest = sha256({"receipt":"safe"})
    assert transport.publish_and_verify(digest, body) == ("staging-events/1/1", True)
    assert transport.publish_and_verify(digest, body) == ("staging-events/1/1", True)
    assert posts[0] == 1


def test_forced_duplicate_returns_new_exact_position():
    key=EphemeralSigner(b"d"*32); messages=[]
    class RoomSigner:
        did=key.did
        def sign_room(self,room,text):
            nonce=str(70+len(messages)); return RoomEnvelope(self.did,nonce,
                key.sign(f"{room}|{nonce}|{text}".encode()),text)
    def handler(request):
        if request.method == "POST":
            body=__import__("json").loads(request.content); seq=len(messages)+1
            messages.append({"seq":seq,"ts":"now","from":body["did"],"nonce":body["nonce"],
                "sig":body["sig"],"text":body["text"]})
            return httpx.Response(200,json={"ok":True},request=request)
        return httpx.Response(200,json={"generation":1,"messages":messages},request=request)
    transport=TechnocoreTransport(httpx.Client(transport=httpx.MockTransport(handler)),
        "staging-events",signer=RoomSigner())
    body=dumps({"x":1}); digest=sha256({"x":1})
    assert transport.post_canonical(digest,body) == ("staging-events/1/1",True)
    assert transport.post_canonical(digest,body,semantic_dedupe=False) == ("staging-events/1/2",True)


def test_transport_reconciles_ambiguous_delivery_before_retry(monkeypatch):
    key = EphemeralSigner(b"p" * 32); messages=[]; posts=[0]
    class RoomSigner:
        did=key.did
        def sign_room(self,room,text):
            return RoomEnvelope(self.did,"77",key.sign(f"{room}|77|{text}".encode()),text)
    def handler(request):
        if request.method == "POST":
            posts[0] += 1; body=__import__("json").loads(request.content)
            messages.append({"seq":1,"ts":"now","from":body["did"],"nonce":body["nonce"],
                "sig":body["sig"],"text":body["text"]})
            raise httpx.ReadTimeout("response lost",request=request)
        return httpx.Response(200,json={"generation":1,"messages":messages},request=request)
    monkeypatch.setattr("flop_empires.technocore.time.sleep",lambda _:None)
    transport=TechnocoreTransport(httpx.Client(transport=httpx.MockTransport(handler)),
        "staging-events",signer=RoomSigner())
    body=dumps({"receipt":"safe"})
    assert transport.publish_and_verify(sha256({"receipt":"safe"}),body) == ("staging-events/1/1",True)
    assert posts[0] == 1


def test_concrete_transport_write_disabled_without_signer():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"generation":1,"messages":[]}, request=request)))
    transport = TechnocoreTransport(client, "staging-events")
    with pytest.raises(RuntimeError, match="write disabled"):
        transport.publish_and_verify(sha256({"x":1}), dumps({"x":1}))


def test_transport_enforces_current_room_and_message_bounds():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"generation":1,"messages":[]}, request=request)))
    with pytest.raises(ValueError, match="room"):
        TechnocoreTransport(client, "a" * 49)
    key = EphemeralSigner(b"p" * 32)
    class RoomSigner:
        did = key.did
        def sign_room(self, room, text):
            return RoomEnvelope(self.did, "1", key.sign(f"{room}|1|{text}".encode()), text)
    transport = TechnocoreTransport(client, "staging-events", signer=RoomSigner())
    text = dumps({"x":"a" * 4097})
    with pytest.raises(ValueError, match="bounded"):
        transport.post_canonical(sha256({"x":"a" * 4097}), text)


def test_100k_deterministic_simulation():
    report = simulate(seed=7, actions=100_000)
    assert report["generated_actions"] == 100_000
    assert report["detected_invariant_failures"] == []
    assert report["final_state_hash"] == simulate(seed=7, actions=100_000)["final_state_hash"]
