import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from flop_empires.canonical import dumps,loads,sha256
from flop_empires.economics_v02 import EconomicRulesV02
from flop_empires.engine import Engine,LifecycleViolation
from flop_empires.identity import EphemeralSigner
from flop_empires.manifest import FrozenSeasonManifest
from flop_empires.operations import AlertLevel,evaluate_monitoring
from flop_empires.replay import replay_v02
from flop_empires.store import Store

ROOT=Path(__file__).parents[1]


def command(did,rid,action,**payload):
    return {"actor_did":did,"request_id":rid,"action":action,"payload":payload}


def operational_manifest(referee,*,activation="LOCAL_DRY_RUN"):
    source=json.loads((ROOT/"season/SEASON-0-MANIFEST-FROZEN.json").read_text(encoding="utf-8"))
    source["referee_did"]=referee.did
    source["manifest_hash"]="t"*64
    source["activation"]=activation
    return SimpleNamespace(**source,value=source,rules=EconomicRulesV02.from_manifest(source))


def test_pause_freezes_attack_and_epoch_clocks_across_restart_and_replay():
    ref=EphemeralSigner(b"r"*32);a=EphemeralSigner(b"a"*32);b=EphemeralSigner(b"b"*32)
    now=[100];manifest=operational_manifest(ref);store=Store()
    engine=Engine.from_manifest(store,manifest,ref,clock=lambda:now[0])
    for actor,empire,capital in ((a,"a","ca"),(b,"b","cb")):
        assert engine.execute(command(actor.did,"reg-"+empire,"register_actor")).accepted
        assert engine.execute(command(actor.did,"emp-"+empire,"create_empire",
            empire_id=empire,name=empire,capital_id=capital)).accepted
    for item in [command(ref.did,"territory","add_territory",territory_id="tb",owner_empire_id="b"),
                 command(ref.did,"edge","add_edge",a="ca",b="tb"),
                 command(ref.did,"active","activate_season"),
                 command(ref.did,"epoch0","settle_epoch",epoch=0)]:
        assert engine.execute(item).accepted
    attack=engine.execute(command(a.did,"attack","create_attack",attack_id="raid",origin_id="ca",
        target_id="tb",kind="RAID",power=10))
    assert attack.accepted and attack.details["deadline_at"]==1900
    now[0]=400;assert engine.execute(command(ref.did,"pause","pause_season")).accepted
    now[0]=4000
    assert not engine.execute(command(b.did,"blocked","submit_defense",attack_id="raid",amount=1)).accepted
    deadline=store.one("SELECT deadline_at FROM attacks WHERE id='raid'")[0]
    engine=Engine.from_manifest(store,manifest,ref,clock=lambda:now[0])
    assert store.one("SELECT value FROM config WHERE key='season_status'")[0]=="PAUSED"
    assert store.one("SELECT deadline_at FROM attacks WHERE id='raid'")[0]==deadline
    assert engine.execute(command(ref.did,"resume","resume_season")).accepted
    now[0]=5499;assert not engine.execute(command(ref.did,"too-early","resolve_attack",attack_id="raid")).accepted
    now[0]=5500;assert engine.execute(command(ref.did,"resolved","resolve_attack",attack_id="raid")).accepted
    now[0]=21700;assert not engine.execute(command(ref.did,"epoch1-early","settle_epoch",epoch=1)).accepted
    now[0]=25300;assert engine.execute(command(ref.did,"epoch1","settle_epoch",epoch=1)).accepted
    rebuilt,result=replay_v02(store,manifest,ref)
    assert result["match"] and rebuilt.state_hash()==store.state_hash()


def test_frozen_attack_windows_and_recon_ttl_are_manifest_driven():
    ref=EphemeralSigner(b"r"*32);a=EphemeralSigner(b"a"*32);b=EphemeralSigner(b"b"*32)
    now=[100];manifest=operational_manifest(ref);store=Store();engine=Engine.from_manifest(store,manifest,ref,clock=lambda:now[0])
    for actor,empire,capital in ((a,"a","ca"),(b,"b","cb")):
        engine.execute(command(actor.did,"r"+empire,"register_actor"));engine.execute(command(actor.did,"e"+empire,"create_empire",empire_id=empire,name=empire,capital_id=capital))
    engine.execute(command(ref.did,"t","add_territory",territory_id="tb",owner_empire_id="b"));engine.execute(command(ref.did,"x","add_edge",a="ca",b="tb"));engine.execute(command(ref.did,"go","activate_season"))
    recon=engine.execute(command(a.did,"recon","recon",territory_id="tb"))
    assert recon.details["expires_at"]==1900
    raid=engine.execute(command(a.did,"raid","create_attack",attack_id="r",origin_id="ca",target_id="tb",kind="RAID",power=10))
    assert raid.details["deadline_at"]==1900
    wrong=engine.execute(command(a.did,"wrong","create_attack",attack_id="s",origin_id="ca",target_id="tb",kind="SIEGE",power=10,deadline_seconds=30))
    assert not wrong.accepted and wrong.details["error"]=="attack deadline differs from frozen manifest"
    instant=engine.execute(command(a.did,"instant","raid",attack_id="instant",origin_id="ca",target_id="tb",power=10))
    assert not instant.accepted and instant.details["error"]=="frozen Season attacks require create_attack"


def test_frozen_manifest_cannot_activate_engine():
    ref=EphemeralSigner(b"r"*32);manifest=operational_manifest(ref,activation="FROZEN_NOT_ACTIVE")
    engine=Engine.from_manifest(Store(),manifest,ref,clock=lambda:100)
    before=engine.store.state_hash()
    with pytest.raises(LifecycleViolation,match="SEASON_NOT_ACTIVATED"):
        engine.execute(command(ref.did,"activate","activate_season"))
    assert engine.store.state_hash()==before and engine.store.one("SELECT COUNT(*) FROM events")[0]==0


def test_frozen_manifest_hash_and_inactive_fields_are_tamper_evident(tmp_path):
    path=ROOT/"season/SEASON-0-MANIFEST-FROZEN.json";manifest=FrozenSeasonManifest.load(path)
    assert manifest.activation=="FROZEN_NOT_ACTIVE"
    assert manifest.registration_boundary is None and manifest.season_start is None and manifest.season_end is None
    assert manifest.referee_did=="did:key:z6MkkvjnHUEz5qmMHXZJiTg8BFSjm3KVqZtueNUMdp1FqMpx"
    assert manifest.actions_namespace=="mb-p-flop-empires-s0-1e24ce92-actions"
    assert manifest.events_namespace=="mb-p-flop-empires-s0-1e24ce92-events"
    assert "staging" not in manifest.actions_namespace+manifest.events_namespace
    assert dumps(loads(dumps(manifest.value)))==dumps(manifest.value)
    value=deepcopy(manifest.value);original=value.pop("manifest_hash")
    assert sha256(value)==original
    value["combat_parameters"]["raid_defense_window_seconds"]+=1
    assert sha256(value)!=original


def test_monitoring_is_advisory_and_has_all_alert_levels():
    manifest=FrozenSeasonManifest.load(ROOT/"season/SEASON-0-MANIFEST-FROZEN.json")
    thresholds=manifest.monitoring_thresholds
    baseline=evaluate_monitoring({},thresholds)
    assert set(baseline.values())=={AlertLevel.INFO}
    alerts=evaluate_monitoring({"whale_peak_resource_share_bp":5500,
        "receipt_readback_failures":3},thresholds)
    assert alerts["whale_peak_resource_share_bp"]==AlertLevel.REVIEW
    assert alerts["receipt_readback_failures"]==AlertLevel.PAUSE_RECOMMENDED
    assert len(thresholds)==17


def test_attack_window_report_covers_requested_matrix():
    report=json.loads((ROOT/"reports/season-0-attack-window-validation.json").read_text(encoding="utf-8"))
    assert set(report["raid"])=={"300","900","1800","3600"}
    assert set(report["siege"])=={"3600","10800","21600","43200"}
    assert report["selected"]=={"raid_defense_window_seconds":1800,
        "siege_defense_window_seconds":21600,"recon_ttl_seconds":1800}


def test_frozen_artifacts_record_local_only_dry_run_and_no_staging_reuse():
    dry=json.loads((ROOT/"reports/season-0-freeze-dry-run.json").read_text(encoding="utf-8"))
    frozen=json.loads((ROOT/"season/SEASON-0-MANIFEST-FROZEN.json").read_text(encoding="utf-8"))
    staging=json.loads((ROOT/"season/season-minus-one-b-live.json").read_text(encoding="utf-8"))
    assert dry["transport"]=="LOCAL_ONLY" and dry["production_writes"]==0
    assert dry["event_chain_verified"] and dry["replay_match"] and not dry["invariant_failures"]
    assert frozen["referee_did"]!=staging["referee_did"]
    assert frozen["actions_namespace"]!=staging["actions_namespace"]
    assert (ROOT/"spec/SEASON-0-RULES-FROZEN.md").is_file()
    assert (ROOT/"docs/SEASON-0-OPERATIONS.md").is_file()


def test_offline_signer_and_namespace_reports_record_no_writes_or_secrets():
    signer=json.loads((ROOT/"reports/season-0-signer-offline-verification.json").read_text(encoding="utf-8"))
    rooms=json.loads((ROOT/"reports/season-0-namespace-safety.json").read_text(encoding="utf-8"))
    assert signer["pass_1"]["local_signature_verified"] and signer["pass_2"]["local_signature_verified"]
    assert signer["same_did_across_processes"] and not signer["secret_exposure"]
    assert rooms["writes_performed"]==rooms["game_writes_performed"]==0
    assert not rooms["collision_observed"] and all(room["generation"]==0 for room in rooms["rooms"])
