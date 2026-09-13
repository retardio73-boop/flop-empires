import json
from pathlib import Path

from flop_empires.balance_analysis_v02 import analyze
from flop_empires.economics_v02 import EconomicRulesV02


def test_balance_analysis_has_fixed_seed_attribution_and_nontrivial_recovery_definition():
    rules=EconomicRulesV02.from_manifest(json.loads((Path(__file__).parents[1]/"season/economic-v02.example.json").read_text()))
    result=analyze(rules,actions=1500)
    assert set(result["whale"])=={"WHALE_2X","WHALE_5X","WHALE_10X"}
    assert len(result["comeback"]["continued"]["seeds"])==25
    assert ">=35%" in result["comeback_definition"]
    assert "combat_spend" in result["whale_10x_vs_5x_cost_deltas"]
