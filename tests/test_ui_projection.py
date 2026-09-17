import json
from pathlib import Path

from flop_empires.store import Store
from flop_empires.ui_projection import build_public_state

ROOT = Path(__file__).parents[1]
WORLD = ROOT / "season" / "world-season-0-v1.json"
ACTIVATION = ROOT / "season" / "SEASON-0-ACTIVATION-v1.json"


def test_public_projection_uses_frozen_world_without_mutating_db(tmp_path):
    db = tmp_path / "ui.db"
    store = Store(db)
    store.conn.execute("INSERT INTO config(key,value) VALUES('season_status','REGISTRATION')")
    before = store.conn.execute("SELECT COUNT(*) FROM territories").fetchone()[0]
    store.close()

    state = build_public_state(db, WORLD, ACTIVATION)
    assert state["season"]["status"] == "REGISTRATION"
    assert len(state["world"]["territories"]) == 64
    assert len(state["world"]["edges"]) == 128
    assert state["world"]["live_materialized"] is False
    assert state["registration"]["actors"] == 0

    check = Store(db)
    assert check.conn.execute("SELECT COUNT(*) FROM territories").fetchone()[0] == before
    check.close()


def test_public_projection_is_fog_safe(tmp_path):
    db = tmp_path / "fog.db"
    store = Store(db)
    store.conn.execute("INSERT INTO config(key,value) VALUES('season_status','ACTIVE')")
    store.close()
    state = build_public_state(db, WORLD, ACTIVATION)
    territory = state["world"]["territories"][0]
    empire = state["world"]["empires"][0]
    assert "fortification" not in territory
    assert "production" not in territory
    assert territory["fog"] == {"fortification": "HIDDEN", "production": "HIDDEN"}
    assert "engineering" not in empire and "knowledge" not in empire and "influence" not in empire
    assert "power" not in empire
    assert state["capabilities"]["fog_safe_public_projection"] is True
    assert state["evidence"]["projection_schema"] == "flop-empires-public-state-v1"


def test_public_projection_redacts_combat_force_and_event_details(tmp_path):
    db = tmp_path / "redact.db"
    store = Store(db)
    store.conn.execute("INSERT INTO empires(id,name,capital_id,created_at) VALUES('season0-e01','A',NULL,1)")
    store.conn.execute("INSERT INTO empires(id,name,capital_id,created_at) VALUES('season0-e02','B',NULL,1)")
    store.conn.execute("INSERT INTO territories(id,owner_empire_id,is_capital,fortification) VALUES('season0-t01','season0-e01',0,99)")
    store.conn.execute("INSERT INTO attacks(id,kind,attacker_empire_id,defender_empire_id,origin_id,target_id,attack_power,allied_defense,created_at,resolved,deadline_at,attacker_cost_locked) VALUES('x','RAID','season0-e01','season0-e02','season0-t01','season0-t02',777,555,1,0,100,12)")
    store.conn.execute("INSERT INTO events(event_type,actor_did,request_id,accepted_at,accepted,command_hash,state_before_hash,state_after_hash,details_json,prev_event_hash,event_hash) VALUES('create_attack','did:key:test','r1',1,1,'c','b','a','{\"secret\":999}','p','e')")
    store.close()
    state = build_public_state(db, WORLD, ACTIVATION)
    attack = state["activity"]["active_attacks"][0]
    event = state["activity"]["recent_events"][0]
    assert "attack_power" not in attack and "allied_defense" not in attack
    assert "attacker_cost_locked" not in attack
    assert "details" not in event and "details_json" not in event and "actor_did" not in event
    assert state["evidence"]["event_head_hash"] == "e"


def test_public_projection_uses_regional_layout_and_keeps_private_view_locked(tmp_path):
    db = tmp_path / "layout.db"
    store = Store(db)
    store.conn.execute("INSERT INTO config(key,value) VALUES('season_status','REGISTRATION')")
    store.close()
    state = build_public_state(db, WORLD, ACTIVATION)
    assert state["world"]["layout"] == "regional-v2"
    assert len({t["region"] for t in state["world"]["territories"]}) == 8
    first_region = [t for t in state["world"]["territories"] if t["region"] == "r1"]
    second_region = [t for t in state["world"]["territories"] if t["region"] == "r2"]
    assert max(t["x"] for t in first_region) < max(t["x"] for t in second_region)
    assert state["capabilities"]["viewer_highlight_without_private_reveal"] is True
    assert state["capabilities"]["signed_private_view"] is True
