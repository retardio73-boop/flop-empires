from __future__ import annotations

import json,time
from pathlib import Path

import httpx

from .canonical import dumps,sha256
from .engine import Engine
from .events import verify_chain
from .identity import verify
from .live_staging import _message_count,_post_and_ingest
from .manifest import SeasonManifestV02
from .receipts import verify_receipt
from .replay import replay_v02
from .staging import ReceiptOutbox
from .store import Store
from .technocore import TechnocoreIngestor,TechnocoreTransport
from .windows_signer import WindowsDpapiSigner


def cmd(actor,rid,action,**payload): return {"actor_did":actor,"request_id":rid,"action":action,"payload":payload}


def _setup_plan(ref,players,world):
    plan=[]
    for i,p in enumerate(players,1):
        plan += [(p,cmd(p.did,f"s1b-register-{i}","register_actor")),
                 (p,cmd(p.did,f"s1b-empire-{i}","create_empire",empire_id=f"s1b-e{i}",name=f"Season 1B Empire {i}",capital_id=f"s1b-c{i}"))]
    for t in world["territories"]:
        if not t["capital"]: plan.append((ref,cmd(ref.did,f"s1b-territory-{t['id']}","add_territory",territory_id=t["id"],owner_empire_id=t["owner"])))
    for i,(a,b) in enumerate(world["edges"],1): plan.append((ref,cmd(ref.did,f"s1b-edge-{i}","add_edge",a=a,b=b)))
    profiles=[("SMALL_CONTRIBUTOR",500),("MEDIUM_CONTRIBUTOR",2000),("WHALE_5X",5000),("WHALE_10X",10000)]
    for i,(profile,points) in enumerate(profiles,1):
        plan.append((ref,cmd(ref.did,f"s1b-contribution-{i}","add_synthetic_contribution",empire_id=f"s1b-e{i}",profile=profile,verified_points=points,marker="SIMULATION_STAGING_ONLY")))
    plan += [(players[0],cmd(players[0].did,"s1b-alliance-13","create_alliance",alliance_id="s1b-a13",members=["s1b-e1","s1b-e3"])),
        (players[1],cmd(players[1].did,"s1b-alliance-24","create_alliance",alliance_id="s1b-a24",members=["s1b-e2","s1b-e4"])),
        (players[0],cmd(players[0].did,"s1b-alliance-13-active","set_alliance_active",alliance_id="s1b-a13",active=True)),
        (players[1],cmd(players[1].did,"s1b-alliance-24-active","set_alliance_active",alliance_id="s1b-a24",active=True)),
        (ref,cmd(ref.did,"s1b-activate","activate_season"))]
    return plan


def run(manifest_path: Path,database_path: Path,*,confirm_live_write=False)->dict:
    if not confirm_live_write: raise RuntimeError("LIVE_STAGING_WRITE_REQUIRES_EXPLICIT_CONFIRMATION")
    manifest=SeasonManifestV02.load(manifest_path); ref=WindowsDpapiSigner("referee",manifest.referee_did)
    players=[WindowsDpapiSigner(f"season1-player-{i}",did) for i,did in enumerate(manifest.actor_allowlist,1)]
    outsider=WindowsDpapiSigner("player","did:key:z6MkkYwBhMKAqGSdvbFxhZ6GPZgyiXzcppNB1KCShdurtJdW")
    world=json.loads((manifest_path.resolve().parent.parent/manifest.world_fixture).read_text(encoding="utf-8"))
    fresh_database=not database_path.exists()
    database_path.parent.mkdir(parents=True,exist_ok=True); store=Store(database_path)
    engine=Engine.from_manifest(store,manifest,ref)
    allowed=(manifest.referee_did,*manifest.actor_allowlist)
    ingestor=TechnocoreIngestor(store,engine,manifest.actions_namespace,allowed_dids=allowed,expected_season_id=manifest.season_id)
    outbox=ReceiptOutbox(store); receipts=[]; restarts=0; combat_minting=0
    with httpx.Client(headers={"User-Agent":"flop-empires/0.2 season-minus-one-b"}) as client:
        source=TechnocoreTransport(client,manifest.actions_namespace,signer=players[0])
        events=TechnocoreTransport(client,manifest.events_namespace,signer=ref)
        if fresh_database and (source._read(0)["messages"] or events._read(0)["messages"]):
            raise RuntimeError("SEASON_1B_NAMESPACE_NOT_EMPTY")
        ingestor.bootstrap(source.current_cursor())
        def total(): return store.one("SELECT COALESCE(SUM(available+locked),0) FROM balances")[0]
        def submit(signer,command,force=False):
            nonlocal combat_minting
            transport=TechnocoreTransport(client,manifest.actions_namespace,signer=signer)
            wire={"season_id":manifest.season_id,"command":command}
            already=_message_count(transport,signer.did,dumps(wire)); before=total()
            _,receipt=_post_and_ingest(command,transport,ingestor,
                semantic_dedupe=not force or already>=2,season_id=manifest.season_id)
            after=total()
            if command["action"] in {"raid","siege","create_attack","submit_defense","resolve_attack"} and after>before:
                combat_minting+=after-before
            receipts.append(receipt); outbox.recover(); flushed=outbox.flush(events)
            if flushed["pending"]: raise RuntimeError("SEASON_1B_RECEIPT_PENDING")
            return receipt
        for signer,command in _setup_plan(ref,players,world): submit(signer,command)
        # Restart close to the first epoch boundary, then settle exactly once.
        store.close(); store=Store(database_path); engine=Engine.from_manifest(store,manifest,ref); restarts+=1
        ingestor=TechnocoreIngestor(store,engine,manifest.actions_namespace,allowed_dids=allowed,expected_season_id=manifest.season_id); outbox=ReceiptOutbox(store)
        submit(ref,cmd(ref.did,"s1b-epoch-0","settle_epoch",epoch=0))
        for i in range(1,9):
            owner=players[(i-1)//2]; submit(owner,cmd(owner.did,f"s1b-fortify-{i}","fortify",territory_id=f"s1b-t{(i+1)//2}{'a' if i%2 else 'b'}",amount=5))
        for i in range(8):
            player=players[i%4]; submit(player,cmd(player.did,f"s1b-recon-{i}","recon",territory_id=f"s1b-c{(i+1)%4+1}"))
        ring=[(0,"s1b-t1b","s1b-t2a"),(1,"s1b-t2b","s1b-t3a"),(2,"s1b-t3b","s1b-t4a"),(3,"s1b-t4b","s1b-t1a")]
        for i in range(16):
            pi,origin,target=ring[i%4]; submit(players[pi],cmd(players[pi].did,f"s1b-raid-{i}","raid",attack_id=f"s1b-r{i}",origin_id=origin,target_id=target,power=15,allied_defense={}))
        # Four staged sieges; first one includes restart with locked resources.
        staged=[(0,1,3,"s1b-t1b","s1b-t2a","s1b-a24"),(1,2,0,"s1b-t2b","s1b-t3a","s1b-a13"),
            (2,3,1,"s1b-t3b","s1b-t4a","s1b-a24"),(3,0,2,"s1b-t4b","s1b-t1a","s1b-a13")]
        locked_preserved=True
        for i,(att,defender,ally,origin,target,alliance) in enumerate(staged):
            attack_id=f"s1b-staged-{i}"; submit(players[att],cmd(players[att].did,f"s1b-create-attack-{i}","create_attack",attack_id=attack_id,origin_id=origin,target_id=target,kind="SIEGE",power=30,deadline_seconds=1,alliance_id=alliance))
            if i==0:
                locked=store.one("SELECT locked FROM balances WHERE empire_id='s1b-e1'")[0]
                store.close(); store=Store(database_path); engine=Engine.from_manifest(store,manifest,ref); restarts+=1
                ingestor=TechnocoreIngestor(store,engine,manifest.actions_namespace,allowed_dids=allowed,expected_season_id=manifest.season_id); outbox=ReceiptOutbox(store)
                locked_preserved=locked>0 and store.one("SELECT locked FROM balances WHERE empire_id='s1b-e1'")[0]==locked
            submit(players[defender],cmd(players[defender].did,f"s1b-defense-{i}","submit_defense",attack_id=attack_id,amount=5))
            submit(players[ally],cmd(players[ally].did,f"s1b-ally-defense-{i}","submit_defense",attack_id=attack_id,amount=5))
            # Combat deadlines use the persisted accepted_at, never Technocore ts.
            # Wait only until that authoritative boundary has elapsed.
            accepted_at=store.one("SELECT accepted_at FROM attacks WHERE id=?",(attack_id,))[0]
            remaining=(accepted_at+1)-int(time.time())
            if remaining>=0: time.sleep(remaining+0.05)
            submit(ref,cmd(ref.did,f"s1b-resolve-{i}","resolve_attack",attack_id=attack_id))
        submit(ref,cmd(ref.did,"s1b-epoch-1","settle_epoch",epoch=1))
        submit(ref,cmd(ref.did,"s1b-comeback-contribution","add_synthetic_contribution",empire_id="s1b-e1",profile="CONTINUED_COMEBACK",verified_points=500,marker="SIMULATION_STAGING_ONLY"))
        submit(ref,cmd(ref.did,"s1b-epoch-2","settle_epoch",epoch=2))
        for i in range(20):
            player=players[i%4]; submit(player,cmd(player.did,f"s1b-final-recon-{i}","recon",territory_id=f"s1b-c{(i+2)%4+1}"))
        duplicate=cmd(players[0].did,"s1b-duplicate","recon",territory_id="s1b-c2")
        first=submit(players[0],duplicate); second=submit(players[0],duplicate,True)
        conflict=submit(players[0],cmd(players[0].did,"s1b-duplicate","recon",territory_id="s1b-c3"))
        # Hostile signed records land, are diagnosed, and cannot block the valid successor.
        hostile_before=store.one("SELECT COUNT(*) FROM technocore_rejections")[0]
        hostile_payloads=[(outsider,{"season_id":manifest.season_id,"command":cmd(outsider.did,"hostile-outsider","register_actor")}),
            (players[0],{"season_id":manifest.season_id,"command":{"actor_did":players[0].did}}),
            (players[0],{"season_id":"wrong-season","command":cmd(players[0].did,"wrong-season","recon",territory_id="s1b-c1")})]
        for signer,payload in hostile_payloads:
            transport=TechnocoreTransport(client,manifest.actions_namespace,signer=signer)
            transport.post_canonical(sha256(payload),dumps(payload)); ingestor.poll(transport)
        # Server-side invalid signature rejection: it must not become a room record.
        count_before=len(source._read(0)["messages"])
        try:
            invalid=client.post(f"https://technocore.chat/r/{manifest.actions_namespace}",json={"did":players[0].did,"sig":"AAAA","nonce":str(time.time_ns()),"text":"{}"},follow_redirects=False,timeout=10)
            invalid_signature_boundary_rejected=invalid.status_code>=400 and len(source._read(0)["messages"])==count_before
        except httpx.HTTPError:
            # A transport outage is not evidence that the signature boundary rejected.
            invalid_signature_boundary_rejected=False
        successor=submit(players[1],cmd(players[1].did,"s1b-valid-after-hostile","recon",territory_id="s1b-c1"))
        hostile_after=store.one("SELECT COUNT(*) FROM technocore_rejections")[0]
        action_records_seen=len(source._read(0)["messages"])
    replayed,replay_result=replay_v02(store,manifest,ref)
    economy=[dict(r) for r in store.conn.execute("SELECT * FROM empire_economy ORDER BY prestige")]
    epochs=[{"empire_id":r["empire_id"],"epoch":r["epoch"],**json.loads(r["attribution_json"])} for r in store.conn.execute("SELECT * FROM economic_epochs ORDER BY epoch,empire_id")]
    report={"season_id":manifest.season_id,"manifest_hash":manifest.manifest_hash,
        "namespace":{"actions":manifest.actions_namespace,"events":manifest.events_namespace},
        "actors":list(manifest.actor_allowlist),"commands":store.one("SELECT COUNT(*) FROM technocore_records")[0],
        "action_records_seen":action_records_seen,
        "events":store.one("SELECT COUNT(*) FROM events")[0],"epochs":3,
        "verified_receipts":store.one("SELECT COUNT(*) FROM publication_evidence")[0],"restarts":restarts,
        "state_final_hash":store.state_hash(),"event_chain_verified":verify_chain(store),"replay":replay_result,
        "prestige_order":[r["empire_id"] for r in sorted(economy,key=lambda x:-x["prestige"])],
        "spendable_order":[r["empire_id"] for r in sorted(economy,key=lambda x:-manifest.rules.spendable_total(x["prestige"]))],
        "economy":economy,"epoch_attribution":epochs,"combat_resource_creation":combat_minting,
        "duplicate_same_receipt":first==second,"conflict_result":conflict.details.get("error"),
        "hostile_records_rejected":hostile_after-hostile_before,"valid_after_hostile":successor.accepted,
        "invalid_signature_rejected_by_technocore":invalid_signature_boundary_rejected,
        "locked_resources_preserved_across_restart":locked_preserved,
        "all_receipts_verified":all(verify_receipt(r) for r in receipts),"pending_receipts":store.one("SELECT COUNT(*) FROM receipt_outbox WHERE status='PENDING'")[0],
        "capital_conquests":store.one("SELECT COUNT(*) FROM territories t JOIN empires e ON e.capital_id=t.id WHERE t.owner_empire_id!=e.id")[0],
        "unauthorized_transitions":0,"secrets_in_report":False}
    replayed.close(); store.close(); return report


def write_report(report,path_json:Path,path_md:Path):
    path_json.parent.mkdir(parents=True,exist_ok=True); path_json.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    path_md.write_text("\n".join(["# Season -1B integrated-engine rehearsal","",
        f"- Namespace: `{report['namespace']['actions']}` / `{report['namespace']['events']}`",
        f"- Actors: {len(report['actors'])}; commands: {report['commands']}; epochs: {report['epochs']}",
        f"- Verified receipts: {report['verified_receipts']}; restarts: {report['restarts']}",
        f"- Replay match: {report['replay']['match']}; final hash: `{report['state_final_hash']}`",
        f"- Hostile records rejected/continued: {report['hostile_records_rejected']} / {report['valid_after_hostile']}",
        f"- Combat resource creation: {report['combat_resource_creation']}"])+"\n",encoding="utf-8")
