import json
from pathlib import Path
from types import SimpleNamespace

from flop_empires.economics_v02 import (EconomicRulesV02,prestige_leaderboard,
    strategic_power_leaderboard)
from flop_empires.engine import Engine
from flop_empires.identity import EphemeralSigner
from flop_empires.replay import replay_v02
from flop_empires.store import Store


def rules():
    return EconomicRulesV02.from_manifest(json.loads((Path(__file__).parents[1]/"season/economic-v02.example.json").read_text()))


def command(did,rid,action,**payload):
    return {"actor_did":did,"request_id":rid,"action":action,"payload":payload}


def manifest(referee,r):
    return SimpleNamespace(referee_did=referee.did,rules=r,manifest_hash="m"*64,
        initial_balances={"ENGINEERING":100,"KNOWLEDGE":0,"INFLUENCE":0},
        epoch_duration=10,environment="staging",
        combat_parameters={"capital_conquest":False,"max_deadline_seconds":86400,
            "raid_reward_divisor":2,"tie_goes_to_defender":True},
        alliance_parameters={"eligibility_snapshotted":True,
            "max_defensive_alliances":2,"support_coefficient_bp":10000})


def bootstrap_manifest(referee,r):
    value={"bootstrap_policy":{"lookback_days":0,"historical_spendable_weight_bp":0,
        "prestige_retains_full_verified_value":True}}
    base=manifest(referee,r)
    return SimpleNamespace(**base.__dict__,value=value)


def test_v02_prestige_epoch_attribution_and_no_double_settlement():
    r=rules(); ref=EphemeralSigner(b"r"*32); actor=EphemeralSigner(b"a"*32); now=[100]
    store=Store(); engine=Engine.from_manifest(store,manifest(ref,r),ref,clock=lambda:now[0])
    engine.execute(command(actor.did,"reg","register_actor"))
    engine.execute(command(actor.did,"emp","create_empire",empire_id="e",name="E",capital_id="c"))
    engine.execute(command(ref.did,"points","add_synthetic_contribution",empire_id="e",
        profile="WHALE_10X",verified_points=10_000,marker="SIMULATION_STAGING_ONLY"))
    engine.execute(command(ref.did,"active","activate_season"))
    receipt=engine.execute(command(ref.did,"epoch-0","settle_epoch",epoch=0))
    assert receipt.accepted
    row=store.one("SELECT * FROM empire_economy WHERE empire_id='e'")
    assert row["prestige"]==10_000 and row["engineering"]>100
    before=store.state_hash()
    duplicate=engine.execute(command(ref.did,"epoch-0-again","settle_epoch",epoch=0))
    assert not duplicate.accepted and store.state_hash()==before
    attr=json.loads(store.one("SELECT attribution_json FROM economic_epochs")[0])
    assert attr==r.epoch_attribution(10_000,100,0,0)


def test_v02_separate_leaderboards_and_sublinear_ordering():
    r=rules(); ref=EphemeralSigner(b"r"*32); store=Store()
    engine=Engine.from_manifest(store,manifest(ref,r),ref,clock=lambda:100)
    actors=[EphemeralSigner(bytes([i])*32) for i in (1,2)]
    for i,a in enumerate(actors,1):
        engine.execute(command(a.did,f"r{i}","register_actor")); engine.execute(command(a.did,f"e{i}","create_empire",empire_id=f"e{i}",name=f"E{i}",capital_id=f"c{i}"))
    engine.execute(command(ref.did,"p1","add_synthetic_contribution",empire_id="e1",profile="WHALE",verified_points=10_000,marker="SIMULATION_STAGING_ONLY"))
    engine.execute(command(ref.did,"p2","add_synthetic_contribution",empire_id="e2",profile="SMALL",verified_points=1_000,marker="SIMULATION_STAGING_ONLY"))
    assert prestige_leaderboard(store)[0]=={"empire_id":"e1","prestige":10_000}
    assert strategic_power_leaderboard(store,r)[0]["empire_id"] in {"e1","e2"}
    assert r.spendable_total(10_000)>r.spendable_total(1_000)
    assert r.spendable_total(10_000)<10*r.spendable_total(1_000)


def test_v02_replay_reconstructs_full_materialized_state():
    r=rules(); ref=EphemeralSigner(b"r"*32); actor=EphemeralSigner(b"a"*32); now=[100]
    m=manifest(ref,r); source=Store(); engine=Engine.from_manifest(source,m,ref,clock=lambda:now[0])
    for c in [command(actor.did,"reg","register_actor"),
              command(actor.did,"emp","create_empire",empire_id="e",name="E",capital_id="c"),
              command(ref.did,"points","add_synthetic_contribution",empire_id="e",profile="MEDIUM",verified_points=2000,marker="SIMULATION_STAGING_ONLY"),
              command(ref.did,"active","activate_season"),command(ref.did,"epoch","settle_epoch",epoch=0)]:
        assert engine.execute(c).accepted
    rebuilt,result=replay_v02(source,m,ref)
    assert result["match"] and rebuilt.state_hash()==source.state_hash()


def test_v02_pending_lock_restart_and_fatigue_survive():
    r=rules(); ref=EphemeralSigner(b"r"*32); a=EphemeralSigner(b"a"*32); b=EphemeralSigner(b"b"*32); now=[100]
    store=Store(); engine=Engine.from_manifest(store,manifest(ref,r),ref,clock=lambda:now[0])
    for actor,e,c in ((a,"a","ca"),(b,"b","cb")):
        engine.execute(command(actor.did,"reg"+e,"register_actor")); engine.execute(command(actor.did,"emp"+e,"create_empire",empire_id=e,name=e,capital_id=c))
    engine.execute(command(ref.did,"t","add_territory",territory_id="tb",owner_empire_id="b"))
    engine.execute(command(ref.did,"edge","add_edge",a="ca",b="tb"))
    created=engine.execute(command(a.did,"attack","create_attack",attack_id="x",origin_id="ca",target_id="tb",kind="SIEGE",power=20,deadline_seconds=5))
    assert created.accepted and store.one("SELECT locked FROM balances WHERE empire_id='a'")[0]==20
    engine=Engine.from_manifest(store,manifest(ref,r),ref,clock=lambda:now[0])
    assert store.one("SELECT locked FROM balances WHERE empire_id='a'")[0]==20
    now[0]=106; resolved=engine.execute(command(ref.did,"resolve","resolve_attack",attack_id="x"))
    assert resolved.accepted and store.one("SELECT COUNT(*) FROM offensive_fatigue")[0]==1


def test_v02_epoch_restart_boundaries_are_sequential_and_never_double_charge():
    r=rules(); ref=EphemeralSigner(b"r"*32); actor=EphemeralSigner(b"a"*32); now=[100]
    m=manifest(ref,r); store=Store(); engine=Engine.from_manifest(store,m,ref,clock=lambda:now[0])
    for c in [command(actor.did,"reg","register_actor"),
              command(actor.did,"emp","create_empire",empire_id="e",name="E",capital_id="c"),
              command(ref.did,"points","add_synthetic_contribution",empire_id="e",profile="MEDIUM",verified_points=2000,marker="SIMULATION_STAGING_ONLY"),
              command(ref.did,"active","activate_season")]: assert engine.execute(c).accepted
    assert not engine.execute(command(ref.did,"skip","settle_epoch",epoch=1)).accepted
    engine=Engine.from_manifest(store,m,ref,clock=lambda:now[0])
    first=engine.execute(command(ref.did,"epoch0","settle_epoch",epoch=0)); assert first.accepted
    balance=store.one("SELECT engineering FROM empire_economy WHERE empire_id='e'")[0]
    engine=Engine.from_manifest(store,m,ref,clock=lambda:now[0])
    assert not engine.execute(command(ref.did,"epoch0-again","settle_epoch",epoch=0)).accepted
    assert store.one("SELECT engineering FROM empire_economy WHERE empire_id='e'")[0]==balance


def test_v02_engine_halts_when_materialized_state_diverges_from_ledger():
    r=rules(); ref=EphemeralSigner(b"r"*32); actor=EphemeralSigner(b"a"*32); m=manifest(ref,r)
    store=Store(); engine=Engine.from_manifest(store,m,ref,clock=lambda:100)
    assert engine.execute(command(actor.did,"reg","register_actor")).accepted
    store.conn.execute("UPDATE config SET value='tampered' WHERE key='environment'")
    try:
        Engine.from_manifest(store,m,ref,clock=lambda:100)
    except RuntimeError as exc:
        assert str(exc)=="impossible replay divergence"
    else:
        raise AssertionError("tampered materialized state must halt")


def test_v02_no_historical_bootstrap_preserves_prestige_but_excludes_spendable_yield():
    r=rules(); ref=EphemeralSigner(b"r"*32); actor=EphemeralSigner(b"a"*32); now=[100]
    store=Store(); engine=Engine.from_manifest(store,bootstrap_manifest(ref,r),ref,clock=lambda:now[0])
    for c in [command(actor.did,"reg","register_actor"),
              command(actor.did,"emp","create_empire",empire_id="e",name="E",capital_id="c"),
              command(actor.did,"bind","bind_github",login="author",verified=True),
              command(ref.did,"contribution","add_contribution",contributor_did=actor.did,
                cluster_id="cluster",evidence_class="merged_pull_request",
                url="https://github.com/upstream/repo/pull/1",verified=True,self_owned=False)]:
        assert engine.execute(c).accepted
    now[0]=200; assert engine.execute(command(ref.did,"active","activate_season")).accepted
    receipt=engine.execute(command(ref.did,"epoch","settle_epoch",epoch=0)); assert receipt.accepted
    economy=store.one("SELECT * FROM empire_economy WHERE empire_id='e'")
    attr=json.loads(store.one("SELECT attribution_json FROM economic_epochs")[0])
    assert economy["prestige"]>0
    assert attr["prestige"]==economy["prestige"]
    assert attr["effective_contribution_for_spendable"]==0
    assert attr["gross_spendable_yield"]==0


def test_v01_state_projection_excludes_v02_migration_tables():
    ref=EphemeralSigner(b"r"*32); store=Store(); engine=Engine(store,ref.did,ref,clock=lambda:100)
    before=store.state_hash(); assert engine.execute(command(ref.did,"bad","unsupported")).accepted is False
    assert "empire_economy" not in store.state() and "economic_epochs" not in store.state()
    assert before == store.state_hash()
