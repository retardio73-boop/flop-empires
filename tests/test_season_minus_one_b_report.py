import json
from pathlib import Path


def test_real_season_minus_one_b_acceptance_report():
    report=json.loads((Path(__file__).parents[1]/"reports/season-minus-one-b.json").read_text(encoding="utf-8"))
    assert 100<=report["commands"]<=250
    assert report["action_records_seen"]==165
    assert report["events"]==report["verified_receipts"]==161
    assert report["replay"]["match"] and report["event_chain_verified"]
    assert report["state_final_hash"]=="cd3527f6af01c695948a615e4ad369d6fa77bba396348592d5da848efb09fd2e"
    assert report["prestige_order"]==["s1b-e4","s1b-e3","s1b-e2","s1b-e1"]
    assert report["spendable_order"]==report["prestige_order"]
    assert report["stockpile_cost_total"]>0 and report["upkeep_total"]>0
    assert report["overextension_penalty_total"]>0 and report["alliance_defenses_accepted"]==6
    assert report["hostile_records_rejected"]==3 and report["valid_after_hostile"]
    assert report["duplicate_same_receipt"] and report["conflict_result"]=="REQUEST_ID_CONFLICT"
    assert report["locked_resources_preserved_across_restart"] and report["restarts"]>=3
    assert report["combat_resource_creation"]==report["capital_conquests"]==0
    assert report["pending_receipts"]==report["unauthorized_transitions"]==0
    assert report["all_receipts_verified"] and report["invalid_signature_rejected_by_technocore"]
    assert report["secrets_in_report"] is False
