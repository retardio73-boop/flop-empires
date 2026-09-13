from __future__ import annotations

import json

from .engine import Engine
from .events import require_valid_chain,verify_chain
from .store import Store


class ReplayDivergence(RuntimeError): pass


def replay_v02(source: Store,manifest,signer) -> tuple[Store,dict]:
    """Re-execute canonical v0.2 ledger commands at persisted referee times."""
    require_valid_chain(source)
    target=Store(); now=[0]
    engine=Engine.from_manifest(target,manifest,signer,clock=lambda:now[0])
    replayed=0
    for event in source.conn.execute("SELECT * FROM events ORDER BY seq"):
        details=json.loads(event["details_json"]); command=details.get("command")
        if not isinstance(command,dict):
            raise ReplayDivergence(f"v0.2 event {event['seq']} lacks canonical command")
        now[0]=event["accepted_at"]; receipt=engine.execute(command); replayed+=1
        if receipt.accepted != bool(event["accepted"]) or receipt.state_after_hash != event["state_after_hash"]:
            raise ReplayDivergence(f"state divergence at event {event['seq']}")
    if target.state_hash()!=source.state_hash(): raise ReplayDivergence("final state hash divergence")
    if not verify_chain(target): raise ReplayDivergence("replayed event chain invalid")
    return target,{"events_replayed":replayed,"persisted_state_hash":source.state_hash(),
        "reconstructed_state_hash":target.state_hash(),"match":True}


def verify_legacy_replay_compatibility(source: Store)->dict:
    """v0.1 ledgers remain byte-verifiable under their original event semantics."""
    require_valid_chain(source)
    return {"economic_rules_version":"technical-yield-v0.1","event_chain_verified":True,
        "materialized_reexecution":"requires original v0.1 command archive"}
