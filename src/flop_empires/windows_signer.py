from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import sqlite3
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

from nacl.signing import SigningKey

from .identity import did_from_verify_key, legacy_did_from_verify_key, verify
from .technocore import RoomEnvelope

MAGIC = b"FLOP-EMPIRES-DPAPI-V1\x00"
ENTROPY = b"FLOPEmpires/StagingSigner/DPAPI/v1"
UI_FORBIDDEN = 0x1
ROLES = {"referee", "player", *(f"season1-player-{number}" for number in range(1, 9))}


class SecureSignerError(RuntimeError):
    pass


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def default_directory() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if not root:
        raise SecureSignerError("LOCAL_APP_DATA_UNAVAILABLE")
    return Path(root) / "FLOPEmpires" / "staging-identities-v1"


def _blob(data: bytes | bytearray):
    buffer = ctypes.create_string_buffer(bytes(data), len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi(protect: bool, data: bytes | bytearray) -> bytes:
    if os.name != "nt":
        raise SecureSignerError("WINDOWS_DPAPI_UNAVAILABLE")
    source, source_buffer = _blob(data); entropy, entropy_buffer = _blob(ENTROPY)
    output = _Blob(); crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
            UI_FORBIDDEN, ctypes.byref(output))
    del source_buffer, entropy_buffer
    if not ok:
        raise SecureSignerError("DPAPI_OPERATION_FAILED")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def _prepare(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    principal = f"{os.environ.get('USERDOMAIN','')}\\{os.environ.get('USERNAME','')}".strip("\\")
    if not principal:
        raise SecureSignerError("WINDOWS_USER_UNAVAILABLE")
    result = subprocess.run(["icacls.exe", str(directory), "/inheritance:r", "/grant:r",
        f"{principal}:(OI)(CI)F", "SYSTEM:(OI)(CI)F"], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise SecureSignerError("SECURE_DIRECTORY_ACL_FAILED")


def enroll(role: str, directory: Path | None = None) -> dict[str, str]:
    if role not in ROLES:
        raise SecureSignerError("INVALID_STAGING_ROLE")
    directory = directory or default_directory(); _prepare(directory)
    credential, public = directory / f"{role}.dpapi", directory / f"{role}.public.json"
    if credential.exists() or public.exists():
        raise SecureSignerError("STAGING_IDENTITY_ALREADY_ENROLLED")
    key = SigningKey.generate(); seed = bytearray(bytes(key)); did = did_from_verify_key(bytes(key.verify_key))
    protected = bytearray()
    try:
        protected = bytearray(_dpapi(True, seed))
        temporary = credential.with_suffix(".tmp")
        with temporary.open("xb") as handle:
            handle.write(MAGIC); handle.write(protected); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, credential)
        public.write_text(json.dumps({"role":role,"did":did,"provider":"windows_dpapi_current_user"},
            sort_keys=True,separators=(",", ":")), encoding="utf-8")
    finally:
        seed[:] = b"\x00" * len(seed)
        protected[:] = b"\x00" * len(protected)
    return {"role":role,"did":did,"provider":"windows_dpapi_current_user"}


class WindowsDpapiSigner:
    def __init__(self, role: str, expected_did: str, directory: Path | None = None):
        if role not in ROLES:
            raise SecureSignerError("INVALID_STAGING_ROLE")
        self.role, self._did = role, expected_did
        self.directory = directory or default_directory()
        self.credential = self.directory / f"{role}.dpapi"
        self.nonce_db = self.directory / "nonces.sqlite3"
        self._verify_identity()
        with sqlite3.connect(self.nonce_db) as db:
            db.execute("CREATE TABLE IF NOT EXISTS nonce_state(did TEXT,room TEXT,last_nonce TEXT,PRIMARY KEY(did,room))")

    @property
    def did(self) -> str:
        return self._did

    def _seed(self) -> bytearray:
        try: encoded = self.credential.read_bytes()
        except OSError as exc: raise SecureSignerError("SECURE_CREDENTIAL_UNAVAILABLE") from exc
        if not encoded.startswith(MAGIC): raise SecureSignerError("SECURE_CREDENTIAL_CORRUPT")
        seed = bytearray(_dpapi(False, encoded[len(MAGIC):]))
        if len(seed) != 32: seed[:] = b"\x00"*len(seed); raise SecureSignerError("SECURE_CREDENTIAL_CORRUPT")
        return seed

    def _verify_identity(self) -> None:
        seed=self._seed()
        try: actual=did_from_verify_key(bytes(SigningKey(bytes(seed)).verify_key))
        finally: seed[:]=b"\x00"*len(seed)
        if actual != self._did: raise SecureSignerError("SECURE_CREDENTIAL_IDENTITY_MISMATCH")

    def sign(self, message: bytes) -> str:
        seed=self._seed()
        try: signature=base64.urlsafe_b64encode(SigningKey(bytes(seed)).sign(message).signature).decode().rstrip("=")
        finally: seed[:]=b"\x00"*len(seed)
        if not verify(self._did,message,signature): raise SecureSignerError("LOCAL_SIGNATURE_VERIFICATION_FAILED")
        return signature

    def _nonce(self, room: str) -> str:
        with sqlite3.connect(self.nonce_db,isolation_level=None) as db:
            db.execute("BEGIN IMMEDIATE"); row=db.execute("SELECT last_nonce FROM nonce_state WHERE did=? AND room=?",(self.did,room)).fetchone()
            value=str(max(int(row[0])+1 if row else 1,time.time_ns()))
            if len(value)>19: db.rollback(); raise SecureSignerError("NONCE_RANGE_EXHAUSTED")
            db.execute("INSERT INTO nonce_state VALUES(?,?,?) ON CONFLICT(did,room) DO UPDATE SET last_nonce=excluded.last_nonce",(self.did,room,value)); db.commit(); return value

    def sign_room(self, room: str, canonical_text: str) -> RoomEnvelope:
        nonce=self._nonce(room); payload=f"{room}|{nonce}|{canonical_text}".encode("utf-8")
        return RoomEnvelope(self.did,nonce,self.sign(payload),canonical_text)


def public_status(role: str, directory: Path | None = None) -> dict:
    directory=directory or default_directory(); path=directory/f"{role}.public.json"
    try:
        value=json.loads(path.read_text(encoding="utf-8")); WindowsDpapiSigner(role,value["did"],directory)
        return {**value,"available":True,"secret_exposed":False}
    except Exception:
        return {"role":role,"available":False,"secret_exposed":False}


def migrate_public_did_encoding(role: str, directory: Path | None = None) -> dict:
    """One-time representation repair; preserves the exact enrolled private seed."""
    directory=directory or default_directory(); public_path=directory/f"{role}.public.json"
    current=json.loads(public_path.read_text(encoding="utf-8")); credential=directory/f"{role}.dpapi"
    encoded=credential.read_bytes()
    if not encoded.startswith(MAGIC): raise SecureSignerError("SECURE_CREDENTIAL_CORRUPT")
    seed=bytearray(_dpapi(False,encoded[len(MAGIC):]))
    try:
        verify_key=bytes(SigningKey(bytes(seed)).verify_key)
        legacy,standard=legacy_did_from_verify_key(verify_key),did_from_verify_key(verify_key)
    finally: seed[:]=b"\x00"*len(seed)
    if current.get("did") not in {legacy,standard}:
        raise SecureSignerError("SECURE_CREDENTIAL_IDENTITY_MISMATCH")
    value={"role":role,"did":standard,"provider":"windows_dpapi_current_user"}
    public_path.write_text(json.dumps(value,sort_keys=True,separators=(",",":")),encoding="utf-8")
    return {**value,"private_material_replaced":False}


def main(argv=None) -> int:
    p=argparse.ArgumentParser(); p.add_argument("command",choices=("enroll","status","migrate-did-encoding")); p.add_argument("--role",choices=sorted(ROLES),required=True); a=p.parse_args(argv)
    result=enroll(a.role) if a.command=="enroll" else migrate_public_did_encoding(a.role) if a.command=="migrate-did-encoding" else public_status(a.role)
    print(json.dumps(result,sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
