import json

import pytest

from flop_empires.canonical import CanonicalError, dumps, loads
from flop_empires.identity import EphemeralSigner, verify
from flop_empires.protocol import parse_command


def test_canonical_and_strict_command():
    assert dumps({"z": 1, "é": [True, None]}) == '{"z":1,"é":[true,null]}'
    with pytest.raises(CanonicalError): loads('{"x":1,"x":2}')
    with pytest.raises(CanonicalError): loads('{"x":1.2}')
    signer = EphemeralSigner(bytes(range(32)))
    cmd = parse_command({"action": "register_actor", "actor_did": signer.did, "request_id": "1", "payload": {}})
    assert cmd.action == "register_actor"


def test_ed25519_roundtrip():
    signer = EphemeralSigner(bytes(range(32)))
    sig = signer.sign(b"hello")
    assert verify(signer.did, b"hello", sig)
    assert not verify(signer.did, b"other", sig)
    assert signer.did.startswith("did:key:z6Mk") and len(signer.did) == 56
