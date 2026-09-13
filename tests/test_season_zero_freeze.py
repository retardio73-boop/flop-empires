import json
from pathlib import Path


ROOT=Path(__file__).parents[1]


def test_cadence_report_covers_frozen_matrix_and_acceptance_gates():
    report=json.loads((ROOT/"reports/season-0-cadence-validation.json").read_text(encoding="utf-8"))
    assert report["season_days"]==14 and report["epochs"]==56
    assert report["epoch_duration_seconds"]==21_600
    assert len(report["scenarios"])==10 and len(report["seeds"])==10
    assert report["invariants"]=={"circular_raid_profit":-753276,
        "combat_resource_creation":0,"double_accrual":0,"failures":0,
        "max_observed_circular_raid_profit":0,"negative_balances":0,
        "replay_divergence":0,"sybil_advantage_without_contribution":0}
    assert report["comeback"]["productive_probability"]>0
    assert report["comeback"]["passive_probability"]<1
    assert report["selected_parameters"]=={"bootstrap":"A_NO_HISTORICAL",
        "alliance_support_bp":10_000,"min_deadline_seconds":30}


def test_freeze_documents_match_candidate_and_have_no_unresolved_parameter_status():
    manifest=json.loads((ROOT/"season/SEASON-0-MANIFEST-CANDIDATE.json").read_text(encoding="utf-8"))
    rules=(ROOT/"spec/SEASON-0-RULES-CANDIDATE.md").read_text(encoding="utf-8")
    review=(ROOT/"reports/season-0-parameter-review.md").read_text(encoding="utf-8")
    assert manifest["epoch_duration"]==21_600 and manifest["epoch_count"]==56
    assert manifest["bootstrap_policy"]["historical_spendable_weight_bp"]==0
    assert "6 hours" in rules and "56 epochs" in rules
    assert "no historical spendable bootstrap" in rules
    assert "| REVIEW |" not in review and "| CHANGE_BEFORE_SEASON_0 |" not in review
