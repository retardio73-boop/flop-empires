import json
from pathlib import Path

from flop_empires.manifest import SeasonZeroCandidateManifest


def test_season_zero_candidate_is_hashed_and_cannot_activate():
    path=Path(__file__).parents[1]/"season/SEASON-0-MANIFEST-CANDIDATE.json"
    candidate=SeasonZeroCandidateManifest.load(path); value=candidate.value
    assert value["activation"]=="DISABLED_PENDING_FINAL_REVIEW"
    assert value["environment"]=="production-candidate-not-active"
    assert value["referee_did"].startswith("did:key:z")
    assert "staging" not in value["actions_namespace"] and "staging" not in value["events_namespace"]
    assert value["combat_parameters"]["min_deadline_seconds"]==30
    assert value["epoch_duration"]==21600
    assert value["epoch_count"]==56
    assert value["bootstrap_policy"]["historical_spendable_weight_bp"]==0
