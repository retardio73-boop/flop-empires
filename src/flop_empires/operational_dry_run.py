from __future__ import annotations

import argparse,json,tempfile
from pathlib import Path
from types import SimpleNamespace

from .engine import Engine
from .events import verify_chain
from .identity import EphemeralSigner
from .manifest import FrozenSeasonManifest
from .operations import evaluate_monitoring
from .replay import replay_v02
from .store import Store
from .windows_signer import WindowsDpapiSigner


def command(did: str,request_id: str,action: str,**payload)->dict:
    return {"actor_did":did,"request_id":request_id,"action":action,"payload":payload}


def run(manifest_path: Path)->dict:
    manifest=FrozenSeasonManifest.load(manifest_path)
    referee=WindowsDpapiSigner("season0-referee",manifest.referee_did)
    local_value={**manifest.value,"activation":"LOCAL_DRY_RUN"}
    runtime_manifest=SimpleNamespace(**local_value,value=local_value,rules=manifest.rules)
    actors=[EphemeralSigner(bytes([number])*32) for number in (31,32,33)]
    wall=[1000];receipts=[]
    with tempfile.TemporaryDirectory(prefix="flop-empires-season0-dry-") as directory:
        store=Store(Path(directory)/"dry-run.db")
        engine=Engine.from_manifest(store,runtime_manifest,referee,clock=lambda:wall[0])
        def execute(value: dict,accepted: bool=True):
            receipt=engine.execute(value);receipts.append(receipt)
            if receipt.accepted is not accepted: raise RuntimeError(f"unexpected result: {value['request_id']}")
            return receipt
        for number,(actor,empire,capital) in enumerate(zip(actors,("s1b-e1","s1b-e2","s1b-e3"),
                ("s1b-c1","s1b-c2","s1b-c3")),1):
            execute(command(actor.did,f"register-{number}","register_actor"))
            execute(command(actor.did,f"empire-{number}","create_empire",empire_id=empire,
                name=f"Dry Empire {number}",capital_id=capital))
        execute(command(referee.did,"territory","add_territory",territory_id="s1b-t2a",owner_empire_id="s1b-e2"))
        execute(command(referee.did,"edge","add_edge",a="s1b-c1",b="s1b-t2a"))
        execute(command(actors[0].did,"github","bind_github",login="dry-run-contributor",verified=True))
        execute(command(referee.did,"activate","activate_season"));wall[0]=1100
        execute(command(referee.did,"contribution","add_contribution",contributor_did=actors[0].did,
            cluster_id="dry-run-cluster",evidence_class="merged_pull_request",
            url="https://github.com/flop-labs/yellowpaper/pull/1",verified=True,self_owned=False))
        execute(command(referee.did,"epoch-0","settle_epoch",epoch=0))
        execute(command(actors[1].did,"alliance","create_alliance",alliance_id="dry-alliance",
            members=["s1b-e2","s1b-e3"]))
        execute(command(actors[1].did,"alliance-active","set_alliance_active",alliance_id="dry-alliance",active=True))
        wall[0]=1200
        raid=execute(command(actors[0].did,"raid","create_attack",attack_id="dry-raid",
            origin_id="s1b-c1",target_id="s1b-t2a",kind="RAID",power=10))
        wall[0]=1500;execute(command(referee.did,"pause","pause_season"))
        wall[0]=5100;blocked=execute(command(actors[0].did,"blocked-during-pause","recon",territory_id="s1b-t2a"),False)
        store.close();store=Store(Path(directory)/"dry-run.db")
        engine=Engine.from_manifest(store,runtime_manifest,referee,clock=lambda:wall[0])
        execute(command(referee.did,"resume","resume_season"))
        wall[0]=6600
        raid_result=execute(command(referee.did,"resolve-raid","resolve_attack",attack_id="dry-raid"))
        wall[0]=6700
        siege=execute(command(actors[0].did,"siege","create_attack",attack_id="dry-siege",
            origin_id="s1b-c1",target_id="s1b-t2a",kind="SIEGE",power=15,alliance_id="dry-alliance"))
        execute(command(actors[2].did,"defense","submit_defense",attack_id="dry-siege",amount=2))
        wall[0]=28_300
        siege_result=execute(command(referee.did,"resolve-siege","resolve_attack",attack_id="dry-siege"))
        execute(command(referee.did,"epoch-1","settle_epoch",epoch=1))
        recon=execute(command(actors[0].did,"recon","recon",territory_id="s1b-t2a"))
        state_hash=store.state_hash();event_count=store.one("SELECT COUNT(*) FROM events")[0]
        chain=verify_chain(store);rebuilt,replay=replay_v02(store,runtime_manifest,referee)
        monitoring=evaluate_monitoring({"combat_frequency_per_epoch":2,
            "referee_processing_lag_seconds":1},manifest.monitoring_thresholds)
        result={"schema":"season-0-frozen-local-dry-run-v1","manifest_hash":manifest.manifest_hash,
            "referee_did":referee.did,"transport":"LOCAL_ONLY","production_writes":0,
            "registrations":3,"contributions":1,"epochs":2,"alliances":1,"raids":1,"sieges":1,
            "pause_resume":True,"restarts":1,"paused_command_rejected":not blocked.accepted,
            "raid_window_seconds":raid.details["deadline_at"]-1200,
            "siege_window_seconds":siege.details["deadline_at"]-(6700-3600),
            "recon_ttl_seconds":recon.details["expires_at"]-(28_300-3600),
            "raid_success":raid_result.details["success"],"siege_success":siege_result.details["success"],
            "event_count":event_count,"event_chain_verified":chain,
            "state_final_hash":state_hash,"reconstructed_state_hash":rebuilt.state_hash(),
            "replay_match":replay["match"],"monitoring_levels":monitoring,
            "invariant_failures":[]}
        store.close();rebuilt.close()
    return result


def write(report: dict,json_path: Path,markdown_path: Path)->None:
    json_path.parent.mkdir(parents=True,exist_ok=True)
    json_path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    lines=["# Season 0 frozen-manifest local dry-run","",
        "No Technocore production room was read or written by this run.","",
        f"- Manifest: `{report['manifest_hash']}`",f"- Referee DID matched: `{report['referee_did']}`",
        f"- Events: {report['event_count']}; event chain: {report['event_chain_verified']}",
        f"- Registration fixtures: {report['registrations']}; contributions: {report['contributions']}; epochs: {report['epochs']}",
        f"- Alliance/Raid/Siege: {report['alliances']}/{report['raids']}/{report['sieges']}",
        f"- Pause/resume: {report['pause_resume']}; restart: {report['restarts']}; paused mutation rejected: {report['paused_command_rejected']}",
        f"- Replay: {report['replay_match']}; final hash: `{report['state_final_hash']}`",
        f"- Production writes: {report['production_writes']}; invariant failures: {len(report['invariant_failures'])}"]
    markdown_path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def main(argv=None)->int:
    parser=argparse.ArgumentParser();parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--json-output",type=Path,required=True);parser.add_argument("--markdown-output",type=Path,required=True)
    args=parser.parse_args(argv);report=run(args.manifest);write(report,args.json_output,args.markdown_output)
    print(json.dumps({key:report[key] for key in ("state_final_hash","replay_match","event_chain_verified","production_writes")},sort_keys=True));return 0


if __name__=="__main__": raise SystemExit(main())
