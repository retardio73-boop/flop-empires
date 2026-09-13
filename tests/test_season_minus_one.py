from flop_empires.identity import EphemeralSigner
from flop_empires.season_minus_one import _plan, run_season_minus_one


def test_season_minus_one_plan_is_bounded_deterministic_and_covers_protocol():
    referee=EphemeralSigner(b"r"*32)
    players=[EphemeralSigner(bytes([number])*32) for number in range(1,5)]
    first=_plan(referee,players); second=_plan(referee,players)
    assert [(command,forced) for _,command,forced in first] == [
        (command,forced) for _,command,forced in second]
    assert len(first) == 56
    actions={command["action"] for _,command,_ in first}
    assert {"register_actor","create_empire","join_empire","fortify","create_alliance",
            "set_alliance_active","recon","raid","siege"} <= actions
    assert sum(forced for _,_,forced in first) == 1


def test_season_minus_one_requires_explicit_live_write_confirmation(tmp_path):
    import pytest
    with pytest.raises(RuntimeError,match="EXPLICIT_CONFIRMATION"):
        run_season_minus_one(tmp_path/"manifest.json",tmp_path/"db.sqlite")
