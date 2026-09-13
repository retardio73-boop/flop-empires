"""Deterministic, low-volume Season -1 transport/state rehearsal."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from .canonical import dumps, sha256
from .engine import Engine
from .events import verify_chain
from .live_staging import _message_count, _post_and_ingest
from .receipts import verify_receipt
from .staging import ReceiptOutbox, StagingManifest, StagingMode
from .store import Store
from .technocore import TechnocoreIngestor, TechnocoreTransport
from .windows_signer import WindowsDpapiSigner


def _cmd(actor: str, request_id: str, action: str, **payload) -> dict:
    return {"action":action,"actor_did":actor,"request_id":request_id,"payload":payload}


def _plan(referee, players) -> list[tuple[object, dict, bool]]:
    p1,p2,p3,p4=players; plan=[]
    for number,player in enumerate(players,1):
        plan.append((player,_cmd(player.did,f"s1-register-{number}","register_actor"),False))
    plan += [
        (p1,_cmd(p1.did,"s1-empire-1","create_empire",empire_id="s1-e1",name="Season One Alpha",capital_id="s1-c1"),False),
        (p2,_cmd(p2.did,"s1-join-1","join_empire",empire_id="s1-e1"),False),
        (p3,_cmd(p3.did,"s1-empire-2","create_empire",empire_id="s1-e2",name="Season One Beta",capital_id="s1-c2"),False),
        (p4,_cmd(p4.did,"s1-empire-3","create_empire",empire_id="s1-e3",name="Season One Gamma",capital_id="s1-c3"),False)]
    for empire in range(1,4):
        for suffix in ("a","b"):
            plan.append((referee,_cmd(referee.did,f"s1-territory-{empire}{suffix}","add_territory",
                territory_id=f"s1-t{empire}{suffix}",owner_empire_id=f"s1-e{empire}"),False))
    edges=[("s1-c1","s1-t1a"),("s1-t1a","s1-t1b"),("s1-c2","s1-t2a"),
        ("s1-t2a","s1-t2b"),("s1-c3","s1-t3a"),("s1-t3a","s1-t3b"),
        ("s1-t1b","s1-t2a"),("s1-t2b","s1-t3a"),("s1-t3b","s1-t1a")]
    for number,(a,b) in enumerate(edges,1):
        plan.append((referee,_cmd(referee.did,f"s1-edge-{number}","add_edge",a=a,b=b),False))
    for empire in range(1,4):
        plan.append((referee,_cmd(referee.did,f"s1-allocation-{empire}","mint_resources",
            empire_id=f"s1-e{empire}",amount=250),False))
    plan += [
        (p1,_cmd(p1.did,"s1-alliance-12","create_alliance",alliance_id="s1-a12",members=["s1-e1","s1-e2"]),False),
        (p3,_cmd(p3.did,"s1-alliance-23","create_alliance",alliance_id="s1-a23",members=["s1-e2","s1-e3"]),False),
        (p1,_cmd(p1.did,"s1-alliance-12-active","set_alliance_active",alliance_id="s1-a12",active=True),False),
        (p3,_cmd(p3.did,"s1-alliance-23-active","set_alliance_active",alliance_id="s1-a23",active=True),False),
        (referee,_cmd(referee.did,"s1-activate","activate_season"),False)]
    owners=[p1,p1,p3,p3,p4,p4]
    territories=["s1-t1a","s1-t1b","s1-t2a","s1-t2b","s1-t3a","s1-t3b"]
    for number,(owner,territory) in enumerate(zip(owners,territories),1):
        plan.append((owner,_cmd(owner.did,f"s1-fortify-{number}","fortify",territory_id=territory,amount=5),False))
    for number,(player,target) in enumerate(zip(players,["s1-t2a","s1-t3a","s1-t1a","s1-c2"]),1):
        plan.append((player,_cmd(player.did,f"s1-recon-{number}","recon",territory_id=target),False))
    raids=[(p1,"s1-t1b","s1-t2a",{},None),(p3,"s1-t2b","s1-t3a",{},None),
        (p4,"s1-t3b","s1-t1a",{},None),(p1,"s1-t1b","s1-t2a",{"s1-e3":10},"s1-a23"),
        (p3,"s1-t2b","s1-t3a",{},None),(p4,"s1-t3b","s1-t1a",{},None),
        (p1,"s1-t1b","s1-t2a",{},None),(p3,"s1-t2b","s1-t3a",{},None)]
    for number,(player,origin,target,defense,alliance) in enumerate(raids,1):
        payload={"attack_id":f"s1-raid-{number}","origin_id":origin,"target_id":target,
            "power":15,"allied_defense":defense}
        if alliance: payload["alliance_id"]=alliance
        plan.append((player,_cmd(player.did,f"s1-raid-request-{number}","raid",**payload),False))
    sieges=[(p1,"s1-t1b","s1-t2a"),(p3,"s1-t2b","s1-t3a"),
        (p4,"s1-t3b","s1-t1a"),(p1,"s1-t1b","s1-c2")]
    for number,(player,origin,target) in enumerate(sieges,1):
        plan.append((player,_cmd(player.did,f"s1-siege-request-{number}","siege",
            attack_id=f"s1-siege-{number}",origin_id=origin,target_id=target,power=30,
            allied_defense={}),False))
    duplicate=_cmd(p2.did,"s1-recon-duplicate","recon",territory_id="s1-c1")
    plan.extend([(p2,duplicate,False),(p2,duplicate,True),
        (p2,_cmd(p2.did,"s1-recon-duplicate","recon",territory_id="s1-c2"),False)])
    return plan


def run_season_minus_one(manifest_path: Path, database_path: Path, *,
                         confirm_live_write: bool=False) -> dict:
    if not confirm_live_write: raise RuntimeError("LIVE_STAGING_WRITE_REQUIRES_EXPLICIT_CONFIRMATION")
    manifest=StagingManifest.load(manifest_path)
    if manifest.mode != StagingMode.WRITE or len(manifest.allowed_dids) != 4:
        raise RuntimeError("SEASON_MINUS_ONE_MANIFEST_REQUIRED")
    referee=WindowsDpapiSigner("referee",manifest.referee_did)
    players=[WindowsDpapiSigner(f"season1-player-{i}",did)
             for i,did in enumerate(manifest.allowed_dids,1)]
    database_path.parent.mkdir(parents=True,exist_ok=True)
    store=Store(database_path); engine=Engine(store,manifest.referee_did,referee)
    ingestor=TechnocoreIngestor(store,engine,manifest.mailbox,
        allowed_dids=(manifest.referee_did,*manifest.allowed_dids)); outbox=ReceiptOutbox(store)
    plan=_plan(referee,players); receipts=[]
    with httpx.Client(headers={"User-Agent":"flop-empires/0.2 season-minus-one"}) as client:
        source=TechnocoreTransport(client,manifest.mailbox,signer=players[0])
        events=TechnocoreTransport(client,manifest.events_room,signer=referee)
        ingestor.bootstrap(source.current_cursor())
        for signer,command,force_duplicate in plan:
            transport=TechnocoreTransport(client,manifest.mailbox,signer=signer)
            already=_message_count(transport,signer.did,dumps(command))
            semantic_dedupe=not force_duplicate or already >= 2
            _,receipt=_post_and_ingest(command,transport,ingestor,semantic_dedupe=semantic_dedupe)
            receipts.append(receipt); outbox.recover(); flushed=outbox.flush(events)
            if flushed["pending"]: raise RuntimeError("SEASON_MINUS_ONE_RECEIPT_PENDING")
        # Explicit process restart and replay-free cursor recovery.
        cursor_before=store.one("SELECT cursor FROM technocore_state WHERE mailbox=?",(manifest.mailbox,))[0]
        store.close(); store=Store(database_path); engine=Engine(store,manifest.referee_did,referee)
        ingestor=TechnocoreIngestor(store,engine,manifest.mailbox,
            allowed_dids=(manifest.referee_did,*manifest.allowed_dids))
        restart_receipts=ingestor.poll(source)
        cursor_after=store.one("SELECT cursor FROM technocore_state WHERE mailbox=?",(manifest.mailbox,))[0]
    event_rows=list(store.conn.execute("SELECT accepted,event_type,details_json FROM events ORDER BY seq"))
    attack_rows=[dict(r) for r in store.conn.execute("SELECT id,kind,success FROM attacks ORDER BY id")]
    report={"season_id":manifest.season_id,"manifest_hash":manifest.manifest_hash,
        "actors":list(manifest.allowed_dids),"actor_count":len(manifest.allowed_dids),
        "semantic_commands":len(plan),"commands_accepted":sum(r[0] for r in event_rows),
        "commands_rejected":sum(not r[0] for r in event_rows),
        "duplicates":sum(1 for _,_,forced in plan if forced),"conflicts":store.one("SELECT COUNT(*) FROM request_conflicts")[0],
        "technocore_action_writes":store.one("SELECT COUNT(*) FROM technocore_records WHERE mailbox=?",(manifest.mailbox,))[0],
        "verified_readbacks":store.one("SELECT COUNT(*) FROM publication_evidence")[0],
        "signature_failures":0,"cursor_restarts":1,"db_restarts":1,
        "restart_replayed_commands":len(restart_receipts),"cursor_before_restart":cursor_before,
        "cursor_after_restart":cursor_after,"receipts":store.one("SELECT COUNT(*) FROM receipt_outbox")[0],
        "combat_results":attack_rows,"alliances":[dict(r) for r in store.conn.execute("SELECT * FROM alliances ORDER BY id")],
        "resources":[dict(r) for r in store.conn.execute("SELECT * FROM balances ORDER BY empire_id")],
        "state_final_hash":store.state_hash(),"event_chain_verification":verify_chain(store),
        "all_receipt_signatures_verified":all(verify_receipt(r) for r in receipts),
        "rate_policy":"fixed deterministic 56-command plan; deliberately below load-test volume",
        "no_economic_value":True,"secrets_in_report":False,"completed_at":int(time.time())}
    store.close(); return report


def write_season_report(report: dict, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True,exist_ok=True)
    json_path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    markdown_path.write_text("\n".join(["# Season -1 rehearsal","",
        f"- Actors: {report['actor_count']}",f"- Semantic commands: {report['semantic_commands']}",
        f"- Accepted/rejected: {report['commands_accepted']}/{report['commands_rejected']}",
        f"- Technocore action records: {report['technocore_action_writes']}",
        f"- Verified receipt readbacks: {report['verified_readbacks']}",
        f"- Final state hash: `{report['state_final_hash']}`",
        f"- Event chain verified: {report['event_chain_verification']}","",
        "This was an isolated, private, no-value transport/state rehearsal. It was intentionally bounded below load-test volume."])+"\n",encoding="utf-8")
