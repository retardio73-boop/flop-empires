import os

import pytest

from flop_empires.identity import verify
from flop_empires.windows_signer import (SecureSignerError, WindowsDpapiSigner,
    enroll)


@pytest.mark.skipif(os.name!="nt",reason="Windows DPAPI only")
def test_dpapi_one_time_enrollment_exact_identity_and_room_signing(tmp_path):
    public=enroll("referee",tmp_path)
    signer=WindowsDpapiSigner("referee",public["did"],tmp_path)
    assert verify(signer.did,b"x",signer.sign(b"x"))
    envelope=signer.sign_room("staging-test","{}")
    assert verify(signer.did,f"staging-test|{envelope.nonce}|{{}}".encode(),envelope.signature)
    with pytest.raises(SecureSignerError,match="ALREADY_ENROLLED"): enroll("referee",tmp_path)


@pytest.mark.skipif(os.name!="nt",reason="Windows DPAPI only")
def test_dpapi_signer_wrong_expected_did_fails_closed(tmp_path):
    enroll("player",tmp_path)
    with pytest.raises(SecureSignerError,match="IDENTITY_MISMATCH"):
        WindowsDpapiSigner("player","did:key:not-the-enrolled-key",tmp_path)
