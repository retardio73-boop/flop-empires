import json
from pathlib import Path

import pytest

from flop_empires.economics_v02 import EconomicRulesV02, prestige_from_clusters


@pytest.fixture
def rules():
    path = Path(__file__).parents[1] / "season" / "economic-v02.example.json"
    return EconomicRulesV02.from_manifest(json.loads(path.read_text()))


def test_prestige_unique_raw_and_nonself_owned():
    rows = [{"id":"a","base_units":100,"verified":True,"self_owned":False},
            {"id":"a","base_units":100,"verified":True,"self_owned":False},
            {"id":"b","base_units":160,"verified":True,"self_owned":True},
            {"id":"c","base_units":40,"verified":False,"self_owned":False}]
    assert prestige_from_clusters(rows) == 100


@pytest.mark.parametrize("low,high", [(0,1),(10,100),(999,1000),(1000,1001),(5000,10000),(10000,100000)])
def test_spendable_curve_is_monotonic(rules, low, high):
    assert rules.spendable_total(high) > rules.spendable_total(low)


def test_ten_x_prestige_is_compressed_not_equalized(rules):
    small, large = rules.spendable_total(1000), rules.spendable_total(10000)
    assert large > small and large < small * 10


def test_resource_allocation_preserves_total(rules):
    allocation = rules.allocate(10_000)
    assert set(allocation) == {"ENGINEERING","KNOWLEDGE","INFLUENCE"}
    assert sum(allocation.values()) == rules.spendable_total(10_000)


def test_defense_formula_is_additive_not_subtractive(rules):
    base = rules.defense_power(100, 20, 30)
    assert base == 110 + 20 + 30
    assert rules.defense_power(100, 21, 30) == base + 1
    assert rules.defense_power(100, 20, 31) == base + 1


def test_overextension_reduces_marginal_benefit(rules):
    one = rules.territory_benefit(1)
    five = rules.territory_benefit(5)
    assert five > one and five < one * 5


def test_upkeep_and_stockpile_cost_never_go_negative(rules):
    assert rules.upkeep(3, 50, 10000) == 3
    assert rules.upkeep(6000, 0, 0) > 0


def test_offensive_fatigue_increases_and_is_capped(rules):
    values = [rules.offensive_cost(100, n) for n in (0,1,5,100)]
    assert values[0] < values[1] < values[2] <= values[3]


def test_manifest_hash_is_deterministic(rules):
    assert rules.manifest_hash == rules.manifest_hash
