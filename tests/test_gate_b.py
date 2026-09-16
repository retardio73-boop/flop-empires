from dataclasses import replace

from flop_empires.gate_b import DEFAULT_PARAMS, simulate, run_matrix


def selected():
    return replace(DEFAULT_PARAMS, hegemon_min_share_bp=1800,
                   hegemon_lead_over_second_bp=3000, hegemon_sustain_epochs=4)


def test_gate_b_simulation_is_deterministic():
    a=simulate(7,"BALANCED",selected()); b=simulate(7,"BALANCED",selected())
    assert a==b


def test_gate_b_invariants_hold_across_matrix():
    report=run_matrix(selected())
    assert report["invariants"]=={"trade_resource_creation":0,"capital_failures":0,
        "negative_balance_failures":0,"multi_hegemon_failures":0}


def test_selected_combat_is_not_automatic():
    rows=[simulate(seed,"BALANCED",selected()) for seed in range(1,21)]
    raid=sum(r["raid_success_rate"] for r in rows)/len(rows)
    siege=sum(r["siege_success_rate"] for r in rows)/len(rows)
    assert .30 < raid < .70
    assert .35 < siege < .70


def test_late_join_is_viable_but_not_full_parity():
    rows=[simulate(seed,"LATE_JOIN",selected()) for seed in range(1,21)]
    ratio=sum(r["late_join_power_ratio"] for r in rows)/len(rows)
    assert .65 < ratio < 1.05
    assert sum(r["late_join_territories"] for r in rows)/len(rows) >= 3


def test_hegemon_is_rare_in_balanced_and_reachable_for_whale():
    balanced=[simulate(seed,"BALANCED",selected()) for seed in range(1,31)]
    whale=[simulate(seed,"WHALE",selected()) for seed in range(1,31)]
    assert sum(r["hegemon_count"] for r in balanced) <= 2
    assert 3 <= sum(r["hegemon_count"] for r in whale) <= 27
    assert all(r["hegemon_count"] <= 1 for r in balanced+whale)


def test_trade_ring_does_not_mint_or_directly_break_conservation():
    rows=[simulate(seed,"TRADER_RING",selected()) for seed in range(1,16)]
    assert sum(r["trade_created"] for r in rows)==0
    assert all(r["trades"]>0 for r in rows)


def test_endgame_objectives_accumulate_and_hegemon_is_not_victory_switch():
    rows=[simulate(seed,"WHALE",selected()) for seed in range(1,21)]
    assert any(max(v["objective_points"] for v in r["final_victory_inputs"])>5 for r in rows)
    assert all(len(r["final_scores"])==selected().empires for r in rows)


def test_freeze_v2_embeds_exact_gate_b_candidate_and_world_hash():
    import json
    from pathlib import Path
    from flop_empires.canonical import loads, sha256
    from flop_empires.manifest import SeasonZeroFreezeV2CandidateManifest
    root=Path(__file__).parents[1]
    manifest=SeasonZeroFreezeV2CandidateManifest.load(root/"season/SEASON-0-MANIFEST-FREEZE-V2-CANDIDATE.json")
    gate=json.loads((root/"season/GATE-B-PARAMETERS-CANDIDATE.json").read_text(encoding="utf-8"))
    world=loads((root/manifest.world_fixture).read_text(encoding="utf-8"))
    assert manifest.gate_b_parameters==gate
    assert manifest.world_graph_hash==sha256(world)
    assert manifest.combat_parameters["raid_min_power"]==14
    assert manifest.combat_parameters["siege_min_power"]==24
