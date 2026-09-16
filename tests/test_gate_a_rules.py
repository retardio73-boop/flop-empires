import pytest

from flop_empires.gate_a import (
    EndgamePhase, IntelFreshness, IntelSnapshot, Momentum, Standing, StandingInputs,
    TerritorySpec, TradeOffer, Treaty, TreatyState, TreatyType, VictoryInputs,
    assign_standings, can_transfer_territory, derive_power, fog_safe_projection,
    momentum, nap_blocks_attack, season_score, settle_trade, standing_score,
    validate_defense_submission,
)


def test_power_is_exact_sum_and_not_a_resource():
    assert derive_power({"ENGINEERING": 3, "KNOWLEDGE": 4, "INFLUENCE": 5}) == 12
    with pytest.raises(ValueError):
        derive_power({"ENGINEERING": 1, "POWER": 99})


def test_nap_blocks_attack_only_while_effective():
    t = Treaty("t", TreatyType.NAP, ("a", "b"), 10, 100,
               signed_by=frozenset({"a", "b"})).activate(10)
    assert nap_blocks_attack("a", "b", [t], 50)
    assert not nap_blocks_attack("a", "b", [t], 100)
    assert t.breach("a", 50).state == TreatyState.BREACHED


def test_coalition_is_multiparty_and_objective_capable():
    t = Treaty("c", TreatyType.COALITION, ("a", "b", "c"), 0, 50,
               signed_by=frozenset({"a", "b", "c"}), objective="contain-x")
    assert t.activate(0).objective == "contain-x"


def test_trade_is_atomic_conservative_and_power_cannot_trade():
    balances = {"a": {"ENGINEERING": 10, "KNOWLEDGE": 0, "INFLUENCE": 0},
                "b": {"ENGINEERING": 0, "KNOWLEDGE": 8, "INFLUENCE": 0}}
    offer = TradeOffer("x", "a", "b", {"ENGINEERING": 4}, {"KNOWLEDGE": 3}, 100)
    out = settle_trade(offer, balances, 10)
    assert out["a"]["ENGINEERING"] == 6 and out["a"]["KNOWLEDGE"] == 3
    assert sum(x["ENGINEERING"] for x in out.values()) == 10
    assert sum(x["KNOWLEDGE"] for x in out.values()) == 8
    with pytest.raises(ValueError):
        TradeOffer("p", "a", "b", {"POWER": 1}, {"KNOWLEDGE": 1}, 100)
    bad = TradeOffer("bad", "a", "b", {"ENGINEERING": 99}, {"KNOWLEDGE": 1}, 100)
    with pytest.raises(ValueError):
        settle_trade(bad, balances, 10)
    assert balances["a"]["ENGINEERING"] == 10


def test_fog_projection_contains_only_public_plus_permitted_intel():
    intel = IntelSnapshot(10, 20, 30, {"estimated_power_band": "high"})
    view = fog_safe_projection(territory_id="t", owner="a", capital=False,
                               standing=Standing.MAJOR, public_conflicts=("war-1",),
                               public_treaties=("nap-1",), intel=intel, now=25)
    assert view["intel"]["freshness"] == IntelFreshness.AGING.value
    assert "stockpile" not in view and "fortification" not in view


def test_standing_order_unique_hegemon_and_momentum():
    inputs = StandingInputs(10, 5, 3, 2, 1)
    assert standing_score(inputs, {"power":1,"territory_value":1,"production":1,
                                   "fortification":1,"strategic_capacity":1}) == 21
    levels = assign_standings({"a": 5, "b": 50, "c": 500}, [10, 25, 100, 250], hegemon_id="c")
    assert levels == {"a": Standing.DOMAIN, "b": Standing.MAJOR, "c": Standing.HEGEMON}
    assert list(levels.values()).count(Standing.HEGEMON) == 1
    assert momentum(120, 100, 5) == Momentum.ASCENDING
    assert momentum(98, 100, 5) == Momentum.STABLE


def test_victory_inputs_exclude_trade_and_activity_metrics():
    v = VictoryInputs(territory_value=10, power=20, production=5, objective_points=7, hegemon_epochs=2)
    score = season_score(v, {"territory_value":1,"power":1,"production":1,
                             "objective_points":1,"hegemon_epochs":1})
    assert score == 44


def test_capital_and_raid_never_transfer_territory():
    capital = TerritorySpec("cap", "r", True, {"ENGINEERING":1}, 5)
    normal = TerritorySpec("n", "r", False, {"KNOWLEDGE":1}, 5)
    assert not can_transfer_territory("SIEGE", capital)
    assert not can_transfer_territory("RAID", normal)
    assert can_transfer_territory("SIEGE", normal)


def test_defense_submission_uses_creation_eligibility_and_deadline():
    assert validate_defense_submission(attack_created_at=10, defense_deadline=100,
                                       submitted_at=99, alliance_eligible_at_creation=True)
    assert not validate_defense_submission(attack_created_at=10, defense_deadline=100,
                                           submitted_at=100, alliance_eligible_at_creation=True)
    assert not validate_defense_submission(attack_created_at=10, defense_deadline=100,
                                           submitted_at=50, alliance_eligible_at_creation=False)
