import json

import pytest

from flop_empires.identity import EphemeralSigner
from flop_empires.store import Store
from flop_empires.ui_auth import AuthManager
from flop_empires.ui_projection import build_public_state


def test_challenge_is_one_time_and_session_is_bound_to_did():
    now = [1000]
    auth = AuthManager(clock=lambda: now[0])
    signer = EphemeralSigner(b"a" * 32)
    challenge = auth.issue(signer.did)
    signature = signer.sign(challenge["message"].encode())
    token, expires = auth.verify_challenge(challenge["challenge_id"], signer.did, signature)
    assert auth.session_did(token) == signer.did
    assert expires > now[0]
    with pytest.raises(ValueError, match="AUTH_CHALLENGE_INVALID"):
        auth.verify_challenge(challenge["challenge_id"], signer.did, signature)
    now[0] = expires + 1
    assert auth.session_did(token) is None


def test_wrong_key_cannot_authenticate():
    auth = AuthManager(clock=lambda: 1000)
    owner = EphemeralSigner(b"b" * 32)
    attacker = EphemeralSigner(b"c" * 32)
    challenge = auth.issue(owner.did)
    with pytest.raises(ValueError, match="AUTH_SIGNATURE_INVALID"):
        auth.verify_challenge(challenge["challenge_id"], owner.did, attacker.sign(challenge["message"].encode()))


def test_private_projection_reveals_only_viewers_own_state(tmp_path):
    db = tmp_path / "private.db"
    store = Store(db)
    signer = EphemeralSigner(b"d" * 32)
    store.conn.execute("INSERT INTO actors VALUES(?,1)", (signer.did,))
    store.conn.execute("INSERT INTO empires VALUES('season0-e01','One','s0-n00',1)")
    store.conn.execute("INSERT INTO memberships VALUES(?, 'season0-e01', 1)", (signer.did,))
    store.conn.execute("INSERT INTO balances VALUES('season0-e01',100,0)")
    store.conn.execute("INSERT INTO empire_economy VALUES('season0-e01',7,80,9,11,-1)")
    store.conn.execute("INSERT INTO territories VALUES('s0-n00','season0-e01',1,23)")
    store.close()
    root = __import__('pathlib').Path(__file__).parents[1]
    world = root / 'season/world-season-0-v1.json'
    activation = root / 'season/SEASON-0-ACTIVATION-v1.json'
    public = build_public_state(db, world, activation)
    private = build_public_state(db, world, activation, signer.did)
    pub_t = next(t for t in public['world']['territories'] if t['id'] == 's0-n00')
    own_t = next(t for t in private['world']['territories'] if t['id'] == 's0-n00')
    assert 'private' not in pub_t
    assert own_t['private']['fortification'] == 23
    assert private['viewer']['empire_id'] == 'season0-e01'
    assert private['viewer']['economy']['engineering'] == 80
