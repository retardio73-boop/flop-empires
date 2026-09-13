import json
from pathlib import Path

from flop_empires.canonical import sha256


def test_season_zero_candidate_is_hashed_and_cannot_activate():
    path=Path(__file__).parents[1]/"season/SEASON-0-MANIFEST-CANDIDATE.json"
    value=json.loads(path.read_text(encoding="utf-8")); supplied=value.pop("candidate_hash")
    assert sha256(value)==supplied
    assert value["activation"]=="DISABLED_PENDING_HUMAN_REVIEW"
    assert value["environment"]=="production-candidate-not-active"
    assert value["referee_did"].startswith("UNASSIGNED_")
    assert value["combat_parameters"]["min_deadline_seconds"]==30
    assert value["epoch_duration"]==604800
