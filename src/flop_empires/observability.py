from __future__ import annotations

import json
import logging
from typing import Any

SAFE_STATES = {"REFEREE_READY", "REFEREE_SIGNER_UNAVAILABLE", "TECHNOCORE_UNAVAILABLE",
    "GITHUB_UNAVAILABLE", "STAGING_READ_ONLY", "STAGING_WRITE", "CURSOR_RECOVERED",
    "COMMAND_ACCEPTED", "COMMAND_REJECTED", "RECEIPT_SIGNED", "RECEIPT_PUBLISHED",
    "READBACK_VERIFIED"}


def log_state(logger: logging.Logger, state: str, **fields: Any) -> None:
    if state not in SAFE_STATES:
        raise ValueError("unknown observable state")
    forbidden = {"token", "secret", "private_key", "authorization"}
    if forbidden & {k.casefold() for k in fields}:
        raise ValueError("sensitive log field rejected")
    logger.info(json.dumps({"state": state, **fields}, sort_keys=True, separators=(",", ":")))


def health_summary(store, *, mode: str = "LOCAL_SIMULATION", signer_ready: bool = False) -> dict:
    cursor_rows = [dict(r) for r in store.conn.execute(
        "SELECT mailbox,cursor FROM technocore_state ORDER BY mailbox")]
    pending = store.one("SELECT COUNT(*) FROM receipt_outbox WHERE status='PENDING'")[0]
    return {"mode": mode, "database_ok": store.one("PRAGMA integrity_check")[0] == "ok",
        "event_count": store.one("SELECT COUNT(*) FROM events")[0], "pending_receipts": pending,
        "signer_ready": signer_ready, "cursors": cursor_rows}
