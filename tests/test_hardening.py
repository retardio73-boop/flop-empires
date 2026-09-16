from __future__ import annotations

import json
import time
from dataclasses import asdict, replace

import pytest

from flop_empires.canonical import CanonicalError, dumps, loads
from flop_empires.engine import Engine, RuleViolation
from flop_empires.events import require_valid_chain, verify_chain
from flop_empires.github_evidence import (_classify_file, parse_evidence_target,
    GitHubApiEvidenceProvider)
from flop_empires.identity import (EphemeralSigner, ExternalRefereeSigner,
    verify, verify_key_from_did)
from flop_empires.models import Receipt, SignedRecord
from flop_empires.protocol import parse_command
from flop_empires.receipts import verify_receipt
from flop_empires.staging import (ReceiptOutbox, StagingManifest, StagingMode,
    StagingWriteService)
from flop_empires.store import Store
from flop_empires.technical_yield import (BOOTSTRAP_MULTIPLIER,
    CONTRIBUTOR_EPOCH_CAP, EPOCH_SECONDS, LIFETIME_SECONDS, decayed_yield,
    epoch_yield)


@pytest.mark.parametrize("value,expected", [
    ({"b": 1, "a": 2}, '{"a":2,"b":1}'),
    ({"unicode": "á雪"}, '{"unicode":"á雪"}'),
    ({"n": 0}, '{"n":0}'),
    ({"n": -42}, '{"n":-42}'),
    ({"x": None}, '{"x":null}'),
    ({"t": True, "f": False}, '{"f":false,"t":true}'),
    ({"a": [{"z": 2, "a": 1}]}, '{"a":[{"a":1,"z":2}]}'),
    ({"slash": "a/b"}, '{"slash":"a/b"}'),
])
def test_canonical_meaningful_values(value, expected):
    assert dumps(value) == expected and loads(expected) == value


@pytest.mark.parametrize("raw", [
    '{"x":1,"x":2}', '{"x":1.0}', '{"x":NaN}', '{', '[1,]', '"unterminated',
])
def test_malformed_canonical_input_rejected(raw):
    with pytest.raises(CanonicalError):
        loads(raw)


def test_oversized_command_rejected():
    signer = EphemeralSigner(b"a" * 32)
    raw = dumps({"action":"x", "actor_did":signer.did, "request_id":"r",
                 "payload":{"x":"a" * 64_001}})
    with pytest.raises(CanonicalError, match="too large"):
        parse_command(raw)


@pytest.mark.parametrize("did", ["", "did:web:x", "did:key:", "did:key:!!!!", "did:key:YQ"])
def test_malformed_dids_rejected(did):
    with pytest.raises(ValueError):
        verify_key_from_did(did)


def test_valid_invalid_and_wrong_did_signatures():
    one, two = EphemeralSigner(b"1" * 32), EphemeralSigner(b"2" * 32)
    signature = one.sign(b"message")
    assert verify(one.did, b"message", signature)
    assert not verify(one.did, b"tampered", signature)
    assert not verify(two.did, b"message", signature)


class Backend:
    def __init__(self, signer, *, ready=True, did=None, invalid=False, delay=0):
        self.signer, self.ready, self.reported_did = signer, ready, did or signer.did
        self.invalid, self.delay = invalid, delay
    def status(self): return {"ready": self.ready, "did": self.reported_did}
    def sign(self, message):
        if self.delay: time.sleep(self.delay)
        return "AAAA" if self.invalid else self.signer.sign(message)


def test_external_signer_validates_every_signature():
    inner = EphemeralSigner(b"s" * 32)
    signer = ExternalRefereeSigner(inner.did, Backend(inner))
    assert verify(inner.did, b"x", signer.sign(b"x"))


@pytest.mark.parametrize("backend_factory", [
    lambda s: Backend(s, ready=False),
    lambda s: Backend(s, did=EphemeralSigner(b"z" * 32).did),
])
def test_external_signer_status_fails_closed(backend_factory):
    inner = EphemeralSigner(b"s" * 32)
    with pytest.raises(RuntimeError): ExternalRefereeSigner(inner.did, backend_factory(inner))


def test_external_signer_invalid_signature_and_timeout_fail_closed():
    inner = EphemeralSigner(b"s" * 32)
    with pytest.raises(RuntimeError): ExternalRefereeSigner(inner.did, Backend(inner, invalid=True)).sign(b"x")
    with pytest.raises(RuntimeError, match="timeout"):
        ExternalRefereeSigner(inner.did, Backend(inner, delay=.05), timeout=.005).sign(b"x")


@pytest.mark.parametrize("url,kind", [
    ("http://github.com/a/b/pull/1", "merged_pull_request"),
    ("https://evil.example/a/b/pull/1", "merged_pull_request"),
    ("https://github.com/a/b/issues/1", "merged_pull_request"),
    ("https://github.com/a/b/pull/no", "merged_pull_request"),
    ("https://github.com/a/b/pull/1?x=1", "merged_pull_request"),
    ("https://github.com/a/b/releases", "released_package"),
])
def test_unsupported_github_targets_rejected(url, kind):
    with pytest.raises(ValueError): parse_evidence_target(url, kind)


@pytest.mark.parametrize("path,category", [
    ("README.md", "docs"), ("docs/guide.txt", "docs"),
    ("tests/test_x.py", "tests"), ("src/test_helper.py", "tests"),
    ("spec/PROTOCOL.md", "docs"), ("specification/v1.json", "spec"),
    ("src/main.py", "code"), ("assets/data.json", "code"),
])
def test_changed_file_classification(path, category):
    assert _classify_file(path) == category


def test_github_provider_has_safe_default_headers(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "never-log-this")
    provider = GitHubApiEvidenceProvider()
    assert provider.client.headers["User-Agent"].startswith("flop-empires/")
    assert provider.client.headers["Authorization"] == "Bearer never-log-this"
    assert "never-log-this" not in repr(provider.__dict__)
    provider.client.close()


@pytest.mark.parametrize("base,verified,at,expected", [
    (100, 0, 0, 100), (100, 0, LIFETIME_SECONDS, 0),
    (100, 10, 0, 0), (0, 0, 0, 0),
])
def test_yield_epoch_boundaries(base, verified, at, expected):
    assert decayed_yield(base, verified, at) == expected


def test_epoch_caps_clusters_contributors_and_bootstrap():
    rows = [{"id":f"c{i}", "actor_did":"did:a", "base_units":160,
             "verified_at":0, "self_owned":False} for i in range(4)]
    assert epoch_yield(rows, 0, 0) == CONTRIBUTOR_EPOCH_CAP
    assert BOOTSTRAP_MULTIPLIER == 2
    assert epoch_yield(rows + [dict(rows[0])], 0, 0) == CONTRIBUTOR_EPOCH_CAP
    assert epoch_yield(rows, 1, 0) == 0


def test_future_contribution_cannot_affect_previous_epoch():
    rows = [{"id":"future", "actor_did":"did:a", "base_units":160,
             "verified_at":EPOCH_SECONDS+1, "self_owned":False}]
    assert epoch_yield(rows, EPOCH_SECONDS, 0) == 0


def make_game(clock):
    referee, a, b, c = [EphemeralSigner(bytes([n]) * 32) for n in range(1, 5)]
    store = Store()
    engine = Engine.for_test(store, referee.did, referee, clock=clock)
    def cmd(actor, rid, action, **payload):
        return engine.execute({"actor_did":actor.did, "request_id":rid, "action":action, "payload":payload})
    for i, actor in enumerate((referee, a, b, c)): cmd(actor, f"reg{i}", "register_actor")
    cmd(a, "ea", "create_empire", empire_id="a", name="A", capital_id="ca")
    cmd(b, "eb", "create_empire", empire_id="b", name="B", capital_id="cb")
    cmd(c, "ec", "create_empire", empire_id="c", name="C", capital_id="cc")
    cmd(referee, "field", "add_territory", territory_id="field", owner_empire_id="b", capital=False)
    cmd(referee, "edge", "add_edge", a="ca", b="field")
    for x in "abc": cmd(referee, "mint"+x, "mint_resources", empire_id=x, amount=100)
    cmd(referee, "active", "activate_season")
    return store, engine, cmd, referee, a, b, c


def test_staged_attack_locks_and_restart_resolution():
    now = [100]
    store, engine, cmd, referee, a, b, c = make_game(lambda: now[0])
    cmd(b, "alliance", "create_alliance", alliance_id="bc", members=["b","c"])
    cmd(b, "activate", "set_alliance_active", alliance_id="bc", active=True)
    created = cmd(a, "attack", "create_attack", attack_id="x", kind="SIEGE",
                  origin_id="ca", target_id="field", power=30, deadline_seconds=10,
                  alliance_id="bc")
    assert created.accepted and store.one("SELECT available,locked FROM balances WHERE empire_id='a'")[:] == (70,30)
    defense = cmd(c, "defense", "submit_defense", attack_id="x", amount=5)
    assert defense.accepted and store.one("SELECT locked FROM balances WHERE empire_id='c'")[0] == 5
    assert not cmd(a, "overspend", "fortify", territory_id="ca", amount=80).accepted
    now[0] = 110
    result = cmd(referee, "resolve", "resolve_attack", attack_id="x")
    assert result.accepted and result.details["success"]
    assert store.one("SELECT owner_empire_id FROM territories WHERE id='field'")[0] == "a"
    assert store.one("SELECT locked FROM balances WHERE empire_id='c'")[0] == 0


def test_alliance_created_after_attack_and_late_defense_rejected():
    now = [100]
    store, engine, cmd, referee, a, b, c = make_game(lambda: now[0])
    cmd(a, "attack", "create_attack", attack_id="x", kind="RAID", origin_id="ca",
        target_id="field", power=20, deadline_seconds=10)
    cmd(b, "alliance", "create_alliance", alliance_id="bc", members=["b","c"])
    cmd(b, "activate", "set_alliance_active", alliance_id="bc", active=True)
    assert not cmd(c, "defense", "submit_defense", attack_id="x", amount=5).accepted
    now[0] = 111
    assert not cmd(c, "late", "submit_defense", attack_id="x", amount=5).accepted


def test_raid_is_net_negative_and_never_transfers_territory():
    now = [100]
    store, engine, cmd, referee, a, b, c = make_game(lambda: now[0])
    before = sum(r[0]+r[1] for r in store.conn.execute("SELECT available,locked FROM balances"))
    cmd(a, "attack", "create_attack", attack_id="r", kind="RAID", origin_id="ca",
        target_id="field", power=20, deadline_seconds=1)
    now[0] = 101
    cmd(referee, "resolve", "resolve_attack", attack_id="r")
    after = sum(r[0]+r[1] for r in store.conn.execute("SELECT available,locked FROM balances"))
    assert after < before and store.one("SELECT owner_empire_id FROM territories WHERE id='field'")[0] == "b"


def test_event_and_receipt_tampering_detected():
    store, engine, cmd, referee, *_ = make_game(lambda: 100)
    receipt = cmd(referee, "more", "mint_resources", empire_id="a", amount=1)
    assert verify_receipt(receipt) and verify_chain(store)
    assert not verify_receipt(replace(receipt, state_after_hash="0"*64))
    store.conn.execute("UPDATE events SET details_json='{}' WHERE seq=1")
    assert not verify_chain(store)
    with pytest.raises(RuntimeError): require_valid_chain(store)


@pytest.mark.parametrize("season,mailbox,events", [
    ("prod", "mb-p-staging-flop-empires-in", "mb-p-staging-flop-empires-out"),
    ("staging-x", "prod", "mb-p-staging-flop-empires-out"),
    ("staging-x", "mb-p-staging-flop-empires-same", "mb-p-staging-flop-empires-same"),
])
def test_staging_manifest_namespace_guards(season, mailbox, events):
    did = EphemeralSigner(b"x"*32).did
    with pytest.raises(ValueError):
        StagingManifest(season, "staging", mailbox, events, did, (did,), StagingMode.WRITE,
            "technical-yield-v0.2", "season/world-0.example.json", "0"*64).validate()


def test_crash_after_commit_before_publish_recovers(tmp_path):
    path = tmp_path / "crash.db"
    signer = EphemeralSigner(b"r"*32)
    store = Store(path); engine = Engine.for_test(store, signer.did, signer, clock=lambda:1)
    engine.execute({"action":"register_actor","actor_did":signer.did,"request_id":"x","payload":{}})
    store.close()
    reopened = Store(path)
    assert ReceiptOutbox(reopened).recover() == 1
    assert reopened.one("SELECT COUNT(*) FROM receipt_outbox WHERE status='PENDING'")[0] == 1


def test_crash_after_network_publish_reconciles_without_reexecution(tmp_path):
    path = tmp_path / "publish.db"
    signer = EphemeralSigner(b"r"*32)
    store = Store(path); engine = Engine.for_test(store, signer.did, signer, clock=lambda:1)
    engine.execute({"action":"register_actor","actor_did":signer.did,"request_id":"x","payload":{}})
    outbox = ReceiptOutbox(store); outbox.recover()
    seen = set()
    class Transport:
        crash = True
        def publish_and_verify(self, digest, body):
            seen.add(digest)
            if self.crash:
                self.crash = False
                raise OSError("crash after publish")
            return "room/1/1", True
    transport = Transport()
    with pytest.raises(OSError): outbox.flush(transport)
    assert outbox.flush(transport)["published"] == 1 and len(seen) == 1
    assert store.one("SELECT COUNT(*) FROM actors")[0] == 1
