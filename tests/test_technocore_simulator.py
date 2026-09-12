from dataclasses import replace

import pytest

from flop_empires.canonical import bytes_
from flop_empires.engine import Engine, RuleViolation
from flop_empires.identity import EphemeralSigner
from flop_empires.models import SignedRecord
from flop_empires.simulator import simulate
from flop_empires.store import Store
from flop_empires.technocore import TechnocoreIngestor, signed_record_body


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
    with pytest.raises(RuleViolation): ingestor.ingest(replace(record, record_id="bad", signature="AAAA"), "rewind", 99)
    assert store.one("SELECT cursor FROM technocore_state WHERE mailbox='main'")[0] == "cursor-next"


def test_100k_deterministic_simulation():
    report = simulate(seed=7, actions=100_000)
    assert report["generated_actions"] == 100_000
    assert report["detected_invariant_failures"] == []
    assert report["final_state_hash"] == simulate(seed=7, actions=100_000)["final_state_hash"]
