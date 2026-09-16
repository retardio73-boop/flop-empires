from dataclasses import asdict

import pytest

from flop_empires.engine import Engine, RuleViolation
from flop_empires.events import verify_chain
from flop_empires.identity import EphemeralSigner
from flop_empires.receipts import verify_receipt
from flop_empires.store import Store
from flop_empires.technical_yield import LIFETIME_SECONDS, empire_yield


def command(actor, request, action, **payload):
    return {"actor_did": actor, "request_id": request, "action": action, "payload": payload}


@pytest.fixture
def game():
    referee = EphemeralSigner(b"r" * 32)
    alice = EphemeralSigner(b"a" * 32)
    bob = EphemeralSigner(b"b" * 32)
    carol = EphemeralSigner(b"c" * 32)
    store = Store()
    engine = Engine.for_test(store, referee.did, referee, clock=lambda: 1_000)
    for i, actor in enumerate((referee, alice, bob, carol)):
        assert engine.execute(command(actor.did, f"reg-{i}", "register_actor")).accepted
    engine.execute(command(alice.did, "ea", "create_empire", empire_id="a", name="A", capital_id="ca"))
    engine.execute(command(bob.did, "eb", "create_empire", empire_id="b", name="B", capital_id="cb"))
    engine.execute(command(carol.did, "ec", "create_empire", empire_id="c", name="C", capital_id="cc"))
    return store, engine, referee, alice, bob, carol


def test_idempotency_hashes_receipts_and_membership_freeze(game):
    store, engine, referee, alice, *_ = game
    cmd = command(referee.did, "mint", "mint_resources", empire_id="a", amount=100)
    first, second = engine.execute(cmd), engine.execute(cmd)
    assert asdict(first) == asdict(second)
    assert store.one("SELECT available FROM balances WHERE empire_id='a'")[0] == 100
    assert verify_receipt(first) and verify_chain(store)
    assert first.state_before_hash != first.state_after_hash
    conflict = engine.execute(command(referee.did, "mint", "mint_resources", empire_id="a", amount=101))
    assert not conflict.accepted and conflict.details["error"] == "REQUEST_ID_CONFLICT"
    assert conflict.state_before_hash == conflict.state_after_hash
    engine.execute(command(referee.did, "active", "activate_season"))
    rejected = engine.execute(command(alice.did, "late", "join_empire", empire_id="b"))
    assert not rejected.accepted and rejected.state_before_hash == rejected.state_after_hash


def test_yield_cluster_decay_and_failed_verification(game):
    store, engine, referee, alice, *_ = game
    engine.execute(command(alice.did, "gh", "bind_github", login="alice", verified=True))
    engine.execute(command(referee.did, "active-yield", "activate_season"))
    base = dict(contributor_did=alice.did, cluster_id="cluster-1", evidence_class="merged_pull_request", verified=True, self_owned=False)
    assert engine.execute(command(referee.did, "e1", "add_contribution", url="https://github.com/org/repo/pull/1", **base)).accepted
    assert engine.execute(command(referee.did, "e2", "add_contribution", url="https://api.github.com/repos/org/repo/pulls/1", **base)).accepted
    assert empire_yield(store, "a", 1_000) == 100
    assert empire_yield(store, "a", 1_000 + LIFETIME_SECONDS) == 0
    bad = engine.execute(command(referee.did, "bad", "add_contribution", contributor_did=alice.did, cluster_id="bad", evidence_class="merged_pull_request", url="https://evil.example/x/y", verified=False))
    assert not bad.accepted and store.one("SELECT 1 FROM contribution_clusters WHERE id='bad'") is None
    own = dict(base, cluster_id="own", self_owned=True)
    assert engine.execute(command(referee.did, "own", "add_contribution", url="https://github.com/alice/own/pull/2", **own)).accepted
    assert store.one("SELECT base_units FROM contribution_clusters WHERE id='own'")[0] == 0


def test_combat_alliance_and_capital(game):
    store, engine, referee, alice, bob, carol = game
    for empire in "abc": engine.execute(command(referee.did, f"m-{empire}", "mint_resources", empire_id=empire, amount=100))
    engine.execute(command(referee.did, "t", "add_territory", territory_id="field", owner_empire_id="b", capital=False))
    engine.execute(command(referee.did, "e1", "add_edge", a="ca", b="field"))
    engine.execute(command(referee.did, "e2", "add_edge", a="ca", b="cb"))
    engine.execute(command(referee.did, "active-combat", "activate_season"))
    engine.execute(command(bob.did, "al", "create_alliance", alliance_id="bc", members=["b", "c"]))
    inactive = engine.execute(command(alice.did, "r0", "raid", attack_id="r0", origin_id="ca", target_id="field", power=20, alliance_id="bc", allied_defense={"c": 5}))
    assert not inactive.accepted
    engine.execute(command(bob.did, "on", "set_alliance_active", alliance_id="bc", active=True))
    before = sum(r[0] + r[1] for r in store.conn.execute("SELECT available,locked FROM balances"))
    raid = engine.execute(command(alice.did, "r1", "raid", attack_id="r1", origin_id="ca", target_id="field", power=20, alliance_id="bc", allied_defense={"c": 5}))
    after = sum(r[0] + r[1] for r in store.conn.execute("SELECT available,locked FROM balances"))
    assert raid.accepted and raid.details["success"] and after < before
    assert store.one("SELECT locked FROM balances WHERE empire_id='c'")[0] == 0
    capital = engine.execute(command(alice.did, "s0", "siege", attack_id="s0", origin_id="ca", target_id="cb", power=30, allied_defense={}))
    assert not capital.accepted and store.one("SELECT owner_empire_id FROM territories WHERE id='cb'")[0] == "b"
    siege = engine.execute(command(alice.did, "s1", "siege", attack_id="s1", origin_id="ca", target_id="field", power=30, allied_defense={}))
    assert siege.accepted and store.one("SELECT owner_empire_id FROM territories WHERE id='field'")[0] == "a"


def test_multi_did_membership_fortification_tie_and_fail_closed(game):
    store, engine, referee, alice, bob, _ = game
    extra = EphemeralSigner(b"d" * 32)
    engine.execute(command(extra.did, "reg-extra", "register_actor"))
    assert engine.execute(command(extra.did, "join", "join_empire", empire_id="a")).accepted
    assert store.one("SELECT COUNT(*) FROM memberships WHERE empire_id='a'")[0] == 2
    engine.execute(command(referee.did, "mint-a", "mint_resources", empire_id="a", amount=20))
    engine.execute(command(referee.did, "mint-b", "mint_resources", empire_id="b", amount=20))
    engine.execute(command(referee.did, "edge-cap", "add_edge", a="cb", b="ca"))
    engine.execute(command(referee.did, "active-multi", "activate_season"))
    assert engine.execute(command(extra.did, "fort", "fortify", territory_id="ca", amount=10)).accepted
    tied = engine.execute(command(bob.did, "tie", "raid", attack_id="tie", origin_id="cb", target_id="ca", power=10, allied_defense={}))
    assert tied.accepted and not tied.details["success"]
    with pytest.raises(RuntimeError): Engine.for_test(Store(), referee.did, None)
