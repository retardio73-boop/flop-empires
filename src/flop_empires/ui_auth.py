from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass

from .identity import verify, verify_key_from_did

AUTH_DOMAIN = "FLOP-Empires-UI"
AUTH_VERSION = "auth-v1"
CHALLENGE_TTL_SECONDS = 90
SESSION_TTL_SECONDS = 900


@dataclass(frozen=True)
class Challenge:
    did: str
    nonce: str
    expires_at: int
    message: str


@dataclass(frozen=True)
class Session:
    did: str
    expires_at: int

class AuthManager:
    def __init__(self, clock=None):
        self.clock = clock or (lambda: int(time.time()))
        self._challenges: dict[str, Challenge] = {}
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def _prune(self, now: int) -> None:
        self._challenges = {k: v for k, v in self._challenges.items() if v.expires_at >= now}
        self._sessions = {k: v for k, v in self._sessions.items() if v.expires_at >= now}

    @staticmethod
    def _session_key(token: str) -> str:
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def issue(self, did: str) -> dict:
        verify_key_from_did(did)
        now = int(self.clock())
        challenge_id = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        expires_at = now + CHALLENGE_TTL_SECONDS
        message = f"{AUTH_DOMAIN}|{AUTH_VERSION}|{did}|{nonce}|{expires_at}"
        with self._lock:
            self._prune(now)
            if len(self._challenges) >= 1024:
                raise RuntimeError("AUTH_CHALLENGE_CAPACITY")
            self._challenges[challenge_id] = Challenge(did, nonce, expires_at, message)
        return {"challenge_id": challenge_id, "message": message, "expires_at": expires_at}

    def verify_challenge(self, challenge_id: str, did: str, signature: str) -> tuple[str, int]:
        now = int(self.clock())
        with self._lock:
            self._prune(now)
            challenge = self._challenges.pop(challenge_id, None)
        if challenge is None or challenge.did != did or challenge.expires_at < now:
            raise ValueError("AUTH_CHALLENGE_INVALID")
        if not verify(did, challenge.message.encode("utf-8"), signature):
            raise ValueError("AUTH_SIGNATURE_INVALID")
        token = secrets.token_urlsafe(32)
        expires_at = now + SESSION_TTL_SECONDS
        with self._lock:
            self._sessions[self._session_key(token)] = Session(did, expires_at)
        return token, expires_at

    def session_did(self, token: str | None) -> str | None:
        if not token:
            return None
        now = int(self.clock())
        key = self._session_key(token)
        with self._lock:
            self._prune(now)
            session = self._sessions.get(key)
        return session.did if session and session.expires_at >= now else None

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(self._session_key(token), None)
