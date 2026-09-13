from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
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


class ExternalSigningBackend(Protocol):
    def status(self) -> dict: ...
    def sign(self, message: bytes) -> str: ...


class ExternalRefereeSigner:
    """Fail-closed adapter around externally managed key custody."""
    def __init__(self, configured_did: str, backend: ExternalSigningBackend,
                 *, timeout: float = 5.0):
        if timeout <= 0 or timeout > 30:
            raise ValueError("signer timeout must be between 0 and 30 seconds")
        self._did, self.backend, self.timeout = configured_did, backend, timeout
        status = self._call(backend.status)
        if not isinstance(status, dict) or status.get("ready") is not True or status.get("did") != configured_did:
            raise RuntimeError("external referee signer unavailable or DID mismatch")

    @property
    def did(self) -> str:
        return self._did

    def _call(self, fn, *args):
        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(fn, *args)
        try:
            return future.result(timeout=self.timeout)
        except FutureTimeout as exc:
            future.cancel()
            raise RuntimeError("external referee signer timeout") from exc
        except Exception as exc:
            raise RuntimeError("external referee signer unavailable") from exc
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def sign(self, message: bytes) -> str:
        signature = self._call(self.backend.sign, message)
        if not isinstance(signature, str) or not verify(self._did, message, signature):
            raise RuntimeError("external referee signer returned invalid signature")
        return signature


def require_signer(configured_did: str, signer: Signer | None) -> Signer:
    if signer is None or signer.did != configured_did:
        raise RuntimeError("configured referee DID cannot sign; refusing to start")
    return signer
