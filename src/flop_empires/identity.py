from __future__ import annotations

import base64
from typing import Protocol, runtime_checkable

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey


@runtime_checkable
class Signer(Protocol):
    @property
    def did(self) -> str: ...
    def sign(self, message: bytes) -> str: ...


def did_from_verify_key(key: bytes) -> str:
    return "did:key:" + base64.urlsafe_b64encode(key).decode().rstrip("=")


def verify_key_from_did(did: str) -> VerifyKey:
    if not did.startswith("did:key:"):
        raise ValueError("unsupported DID")
    raw = did[8:]
    try:
        return VerifyKey(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except Exception as exc:
        raise ValueError("invalid did:key") from exc


def verify(did: str, message: bytes, signature: str) -> bool:
    try:
        verify_key_from_did(did).verify(message, base64.b64decode(signature, validate=True))
        return True
    except (ValueError, BadSignatureError):
        return False


class EphemeralSigner:
    """In-memory signer for tests and local simulations only."""
    def __init__(self, seed: bytes | None = None):
        self._key = SigningKey(seed) if seed is not None else SigningKey.generate()

    @property
    def did(self) -> str:
        return did_from_verify_key(bytes(self._key.verify_key))

    def sign(self, message: bytes) -> str:
        return base64.b64encode(self._key.sign(message).signature).decode()


def require_signer(configured_did: str, signer: Signer | None) -> Signer:
    if signer is None or signer.did != configured_did:
        raise RuntimeError("configured referee DID cannot sign; refusing to start")
    return signer
