import json
from pathlib import Path

from flop_empires.balance_search import SCENARIOS, run_sweep, simulate_scenario
from flop_empires.economics_v02 import EconomicRulesV02


def rules():
    return EconomicRulesV02.from_manifest(json.loads((Path(__file__).parents[1]/"season/economic-v02.example.json").read_text()))


def test_all_required_scenarios_present():
    assert set(SCENARIOS) == {"BALANCED","WHALE_2X","WHALE_5X","WHALE_10X","CARTEL","RAIDER","TURTLE","CONTRIBUTOR","OPPORTUNIST","COMEBACK"}


def test_scenario_determinism_and_invariants():
    one=simulate_scenario(rules(),"WHALE_10X",7,2000)
    two=simulate_scenario(rules(),"WHALE_10X",7,2000)
    assert one==two and not one["invariant_failures"] and one["combat_resource_creation"]==0


def test_productive_comeback_is_nonzero():
    result=simulate_scenario(rules(),"COMEBACK",7,10_000)
    assert result["comeback_recovery"] > 0


def test_sweep_records_every_seed_manifest_and_scenario():
    result=run_sweep(rules(),1000)
    assert len(result["candidates"])==3
    assert all(len(x["runs"])==len(SCENARIOS)*5 for x in result["candidates"])
