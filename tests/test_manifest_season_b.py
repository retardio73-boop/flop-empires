from pathlib import Path

import pytest

from flop_empires.manifest import SeasonManifestV02
from flop_empires.season_minus_one_b import run


ROOT=Path(__file__).parents[1]


def test_complete_season_minus_one_b_manifest_selects_normative_v02():
    manifest=SeasonManifestV02.load(ROOT/"season/season-minus-one-b-live.json")
    assert manifest.rules.version=="technical-yield-v0.2"
    assert manifest.manifest_hash=="0f73e91358d8bb8f487c0996985ca9bfe9726e331c151bd282a0ab6c81f83d58"
    assert manifest.actions_namespace!=manifest.events_namespace


def test_season_minus_one_b_requires_explicit_confirmation(tmp_path):
    with pytest.raises(RuntimeError,match="EXPLICIT_CONFIRMATION"):
        run(ROOT/"season/season-minus-one-b-live.json",tmp_path/"db.sqlite")


def test_manifest_combat_and_alliance_safety_parameters_are_normative():
    manifest=SeasonManifestV02.load(ROOT/"season/season-minus-one-b-live.json")
    assert manifest.combat_parameters=={"capital_conquest":False,"max_deadline_seconds":86400,
        "raid_reward_divisor":2,"tie_goes_to_defender":True}
    assert manifest.alliance_parameters["eligibility_snapshotted"] is True
    assert manifest.alliance_parameters["support_coefficient_bp"]==10000
