from flop_empires.adversarial import gini, run_adversarial


def test_gini_boundaries():
    assert gini([1,1,1]) == 0
    assert 0 < gini([0,0,10]) < 1


def test_adversarial_profiles_are_deterministic_and_safe():
    one = run_adversarial(7, 20_000)
    two = run_adversarial(7, 20_000)
    assert one["final_state_hash"] == two["final_state_hash"]
    assert one["invariant_failures"] == []
    assert one["repeated_raid_profitability"] < 0
    assert one["sybil_profitability"] == 0
    assert one["contribution_farming_profitability"] == 0
