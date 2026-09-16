from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Protocol, runtime_checkable

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    zeroes = len(data) - len(data.lstrip(b"\0")); number = int.from_bytes(data, "big")
    out = ""
    while number:
        number, remainder = divmod(number, 58); out = BASE58[remainder] + out
    return "1" * zeroes + (out or ("" if zeroes else "1"))


def _b58decode(text: str) -> bytes:
    if not text or any(c not in BASE58 for c in text):
        raise ValueError("invalid base58btc")
    number = 0
    for char in text: number = number * 58 + BASE58.index(char)
    body = number.to_bytes((number.bit_length()+7)//8, "big") if number else b""
    return b"\0" * (len(text)-len(text.lstrip("1"))) + body


@runtime_checkable
class Signer(Protocol):
    @property
    def did(self) -> str: ...
    def sign(self, message: bytes) -> str: ...


def did_from_verify_key(key: bytes) -> str:
    if len(key) != 32:
        raise ValueError("Ed25519 verify key must be 32 bytes")
    return "did:key:z" + _b58encode(b"\xed\x01" + key)


def legacy_did_from_verify_key(key: bytes) -> str:
    return "did:key:" + base64.urlsafe_b64encode(key).decode().rstrip("=")


def verify_key_from_did(did: str) -> VerifyKey:
    if not did.startswith("did:key:"):
        raise ValueError("unsupported DID")
    raw = did[8:]
    try:
        if raw.startswith("z"):
            decoded = _b58decode(raw[1:])
            if not decoded.startswith(b"\xed\x01") or len(decoded) != 34:
                raise ValueError("unsupported did:key multicodec")
            return VerifyKey(decoded[2:])
        return VerifyKey(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except Exception as exc:
        raise ValueError("invalid did:key") from exc


def verify(did: str, message: bytes, signature: str) -> bool:
    try:
        if not isinstance(signature, str):
            return False
        if len(signature) == 86 and "=" not in signature:
            raw_signature = base64.urlsafe_b64decode(signature + "==")
        else:
            # Historical v0.1 receipts used padded standard base64. Keep them
            # verifiable for replay while new signatures use Technocore's
            # canonical unpadded base64url spelling.
            raw_signature = base64.b64decode(signature, validate=True)
        if len(raw_signature) != 64:
            return False
        verify_key_from_did(did).verify(message, raw_signature)
        return True
    except (ValueError, BadSignatureError, base64.binascii.Error):
        return False


class EphemeralSigner:
    """In-memory signer for tests and local simulations only."""
    def __init__(self, seed: bytes | None = None):
        self._key = SigningKey(seed) if seed is not None else SigningKey.generate()

    @property
    def did(self) -> str:
        return did_from_verify_key(bytes(self._key.verify_key))

    def sign(self, message: bytes) -> str:
        return base64.urlsafe_b64encode(self._key.sign(message).signature).decode().rstrip("=")


class ExternalSigningBackend(Protocol):
    def status(self) -> dict: ...
    def sign(self, message: bytes) -> str: ...
    def sign_room(self, room: str, canonical_text: str): ...


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

    def sign_room(self, room: str, canonical_text: str):
        envelope=self._call(self.backend.sign_room,room,canonical_text)
        did=getattr(envelope,"did",None);nonce=getattr(envelope,"nonce",None)
        text=getattr(envelope,"text",None);signature=getattr(envelope,"signature",None)
        if (did!=self._did or text!=canonical_text or not isinstance(nonce,str) or not nonce or
                not isinstance(signature,str) or not verify(self._did,
                    f"{room}|{nonce}|{canonical_text}".encode("utf-8"),signature)):
            raise RuntimeError("external referee signer returned invalid room envelope")
        return envelope


def require_signer(configured_did: str, signer: Signer | None) -> Signer:
    if signer is None or signer.did != configured_did:
        raise RuntimeError("configured referee DID cannot sign; refusing to start")
    return signer
