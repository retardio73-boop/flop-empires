"""Explicit, low-volume live Technocore staging rehearsal.

This module never selects an identity or namespace implicitly. Callers must pass
the hashed staging manifest and explicitly opt in to network writes.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from .canonical import dumps, loads, sha256
from .engine import Engine
from .events import verify_chain
from .receipts import verify_receipt
from .staging import ReceiptOutbox, StagingManifest, StagingMode
from .store import Store
from .technocore import TechnocoreIngestor, TechnocoreTransport
from .windows_signer import WindowsDpapiSigner


def _command(actor: str, request_id: str, action: str, **payload) -> dict:
    return {"action": action, "actor_did": actor, "request_id": request_id,
            "payload": payload}


def _message_count(transport: TechnocoreTransport, did: str, text: str) -> int:
    return sum(1 for message in transport._read(0)["messages"]
        if isinstance(message, dict) and transport._valid_readback(transport.room, message, did, text))


def _post_and_ingest(command: dict, action_transport: TechnocoreTransport,
                     ingestor: TechnocoreIngestor, *, semantic_dedupe: bool = True,
                     season_id: str | None = None):
    wire={"season_id":season_id,"command":command} if season_id else command
    text = dumps(wire); ref, verified = action_transport.post_canonical(
        sha256(wire), text, semantic_dedupe=semantic_dedupe)
    if not verified:
        raise RuntimeError("ACTION_READBACK_NOT_VERIFIED")
    receipts = []
    for attempt in range(20):
        receipts = ingestor.poll(action_transport)
        if receipts:
            break
        if attempt < 19:
            time.sleep(0.5)
    command_hash = sha256(command)
    prior = ingestor.store.one(
        "SELECT receipt_json FROM requests WHERE actor_did=? AND request_id=? AND command_hash=?",
        (command["actor_did"], command["request_id"], command_hash))
    if not prior:
        prior = ingestor.store.one(
            "SELECT receipt_json FROM request_conflicts WHERE actor_did=? AND request_id=? AND command_hash=?",
            (command["actor_did"], command["request_id"], command_hash))
    if not prior:
        raise RuntimeError("ACTION_NOT_OBSERVED_AFTER_POST")
    from .models import Receipt
    receipt = Receipt(**json.loads(prior[0]))
    if receipt.actor_did != command["actor_did"] or receipt.request_id != command["request_id"]:
        raise RuntimeError("ACTION_RECEIPT_MISMATCH")
    if not verify_receipt(receipt):
        raise RuntimeError("ACTION_RECEIPT_SIGNATURE_INVALID")
    return ref, receipt


def run_live_write_smoke(manifest_path: Path, database_path: Path, *,
                         confirm_live_write: bool = False) -> dict:
    if not confirm_live_write:
        raise RuntimeError("LIVE_STAGING_WRITE_REQUIRES_EXPLICIT_CONFIRMATION")
    manifest = StagingManifest.load(manifest_path)
    if manifest.mode != StagingMode.WRITE:
        raise RuntimeError("STAGING_WRITE_MANIFEST_REQUIRED")
    referee = WindowsDpapiSigner("referee", manifest.referee_did)
    player = WindowsDpapiSigner("player", manifest.allowed_dids[0])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    store = Store(database_path)
    engine = Engine(store, manifest.referee_did, referee)
    ingestor = TechnocoreIngestor(store, engine, manifest.mailbox,
                                  allowed_dids=manifest.allowed_dids)
    outbox = ReceiptOutbox(store)
    commands: list[dict] = []
    action_refs: list[str] = []
    receipt_refs: list[str] = []
    crash_results: dict[str, dict] = {}
    with httpx.Client(headers={"User-Agent":"flop-empires/0.2 season-minus-one-staging"}) as client:
        actions = TechnocoreTransport(client, manifest.mailbox, signer=player)
        events = TechnocoreTransport(client, manifest.events_room, signer=referee)
        ingestor.bootstrap(actions.current_cursor())

        register = _command(player.did, "smoke-register-001", "register_actor")
        create = _command(player.did, "smoke-create-001", "create_empire",
                          empire_id="smoke-empire", name="Smoke Empire", capital_id="smoke-capital")
        conflict = _command(player.did, "smoke-create-001", "create_empire",
                            empire_id="smoke-empire-ALTERED", name="Altered", capital_id="altered-capital")
        observed = []
        duplicate_already_present = _message_count(actions, player.did, dumps(create)) >= 2
        for command, semantic_dedupe in ((register, True), (create, True),
                                         (create, duplicate_already_present), (conflict, True)):
            ref, receipt = _post_and_ingest(command, actions, ingestor,
                                            semantic_dedupe=semantic_dedupe)
            commands.append(command); action_refs.append(ref); observed.append(receipt)
            outbox.recover()
            flushed = outbox.flush(events)
            if flushed["pending"]:
                raise RuntimeError("RECEIPT_READBACK_NOT_VERIFIED")

        original, duplicate, conflicting = observed[1], observed[2], observed[3]
        if duplicate != original or conflicting.accepted or conflicting.details.get("error") != "REQUEST_ID_CONFLICT":
            raise RuntimeError("LIVE_IDEMPOTENCY_ASSERTION_FAILED")
        if store.one("SELECT COUNT(*) FROM empires")[0] != 1:
            raise RuntimeError("LIVE_DUPLICATE_STATE_EFFECT")

        # Window A: DB and outbox commit, then process stops before publication.
        crash_a = _command(player.did, "smoke-crash-a-001", "recon", territory_id="smoke-capital")
        ref, receipt_a = _post_and_ingest(crash_a, actions, ingestor)
        commands.append(crash_a); action_refs.append(ref); outbox.recover()
        receipt_a_text = dumps(asdict(receipt_a))
        before_a = _message_count(events, referee.did, receipt_a_text)
        store.close()
        store = Store(database_path); engine = Engine(store, manifest.referee_did, referee)
        ingestor = TechnocoreIngestor(store, engine, manifest.mailbox,
                                      allowed_dids=manifest.allowed_dids)
        outbox = ReceiptOutbox(store); outbox.recover(); flushed_a = outbox.flush(events)
        after_a = _message_count(events, referee.did, receipt_a_text)
        crash_results["window_a"] = {"before_publish":before_a, "after_recovery":after_a,
            "published_by_recovery":flushed_a["published"], "semantic_publications":after_a}

        # Window B: receipt lands, then process stops before local readback commit.
        crash_b = _command(player.did, "smoke-crash-b-001", "recon", territory_id="smoke-capital")
        ref, receipt_b = _post_and_ingest(crash_b, actions, ingestor)
        commands.append(crash_b); action_refs.append(ref); outbox.recover()
        receipt_b_text = dumps(asdict(receipt_b)); receipt_b_hash = sha256(loads(receipt_b_text))
        publish_ref, verified = events.publish_and_verify(receipt_b_hash, receipt_b_text)
        if not verified:
            raise RuntimeError("WINDOW_B_INITIAL_READBACK_FAILED")
        before_b = _message_count(events, referee.did, receipt_b_text)
        store.close()
        store = Store(database_path); engine = Engine(store, manifest.referee_did, referee)
        outbox = ReceiptOutbox(store); outbox.recover(); flushed_b = outbox.flush(events)
        after_b = _message_count(events, referee.did, receipt_b_text)
        crash_results["window_b"] = {"initial_publish_ref":publish_ref,
            "before_reconcile":before_b, "after_recovery":after_b,
            "reconciled_by_recovery":flushed_b["published"], "semantic_publications":after_b}

        for row in store.conn.execute("SELECT publish_ref FROM publication_evidence ORDER BY publish_ref"):
            receipt_refs.append(row[0])

        durable_action_refs = [row[0] for row in store.conn.execute(
            "SELECT record_id FROM technocore_records WHERE mailbox=? ORDER BY seq", (manifest.mailbox,))]

    result = {
        "protocol":"technocore-room-json-signed-v1", "season_id":manifest.season_id,
        "manifest_hash":manifest.manifest_hash, "actions_namespace":manifest.mailbox,
        "events_namespace":manifest.events_room, "referee_did":manifest.referee_did,
        "player_did":player.did, "commands_sent":len(commands),
        "commands_accepted":sum(1 for r in observed + [receipt_a, receipt_b] if r.accepted),
        "commands_rejected":sum(1 for r in observed + [receipt_a, receipt_b] if not r.accepted),
        "duplicate_result":"same_receipt" if duplicate == original else "failed",
        "request_conflict_result":conflicting.details.get("error"),
        "action_positions":durable_action_refs, "receipt_positions":receipt_refs,
        "technocore_action_writes_observed":len(durable_action_refs),
        "verified_readbacks":len(receipt_refs), "crash_recovery":crash_results,
        "state_final_hash":store.state_hash(), "event_chain_verified":verify_chain(store),
        "empire_count":store.one("SELECT COUNT(*) FROM empires")[0],
        "secrets_in_report":False, "completed_at":int(time.time())}
    store.close()
    return result


def run_live_crash_a(manifest_path: Path, database_path: Path, *,
                     confirm_live_write: bool = False) -> dict:
    """Exercise commit-before-publish once with a dedicated request id."""
    if not confirm_live_write:
        raise RuntimeError("LIVE_STAGING_WRITE_REQUIRES_EXPLICIT_CONFIRMATION")
    manifest=StagingManifest.load(manifest_path)
    referee=WindowsDpapiSigner("referee",manifest.referee_did)
    player=WindowsDpapiSigner("player",manifest.allowed_dids[0])
    store=Store(database_path); engine=Engine(store,manifest.referee_did,referee)
    ingestor=TechnocoreIngestor(store,engine,manifest.mailbox,allowed_dids=manifest.allowed_dids)
    outbox=ReceiptOutbox(store)
    command=_command(player.did,"smoke-crash-a-002","recon",territory_id="smoke-capital")
    with httpx.Client(headers={"User-Agent":"flop-empires/0.2 crash-window-a"}) as client:
        actions=TechnocoreTransport(client,manifest.mailbox,signer=player)
        events=TechnocoreTransport(client,manifest.events_room,signer=referee)
        _,receipt=_post_and_ingest(command,actions,ingestor); outbox.recover()
        text=dumps(asdict(receipt)); before=_message_count(events,referee.did,text)
        if before != 0:
            raise RuntimeError("WINDOW_A_NOT_FRESH")
        state_hash=store.state_hash(); store.close()
        store=Store(database_path); engine=Engine(store,manifest.referee_did,referee)
        outbox=ReceiptOutbox(store); outbox.recover(); flushed=outbox.flush(events)
        after=_message_count(events,referee.did,text)
        result={"request_id":command["request_id"],"before_publish":before,
            "after_recovery":after,"published_by_recovery":flushed["published"],
            "semantic_publications":after,"state_hash_unchanged":state_hash==store.state_hash(),
            "event_chain_verified":verify_chain(store)}
    store.close(); return result


def write_report(report: dict, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    lines = ["# Technocore staging write E2E", "",
        f"- Protocol: `{report['protocol']}`", f"- Manifest: `{report['manifest_hash']}`",
        f"- Commands: {report['commands_sent']} ({report['commands_accepted']} accepted, {report['commands_rejected']} rejected)",
        f"- Verified receipt readbacks: {report['verified_readbacks']}",
        f"- Duplicate: `{report['duplicate_result']}`", f"- Conflict: `{report['request_conflict_result']}`",
        f"- Event chain: {report['event_chain_verified']}", "",
        "Crash window A and B both require exactly one semantic publication; see the JSON report for exact positions."]
    markdown_path.write_text("\n".join(lines)+"\n",encoding="utf-8")
