import json
from pathlib import Path
from types import SimpleNamespace

from flop_empires.ecosystem_smoke import classify
from flop_empires.github_evidence import GitHubEvidence, StaticGitHubEvidenceProvider, verify_provider_evidence


def test_ecosystem_classification_docs_only():
    assert classify(SimpleNamespace(changed_files=(("CONTRIBUTING.md","docs"),)))[0] == "documentation-only merge"


def test_ecosystem_classification_code_and_fixtures():
    facts=SimpleNamespace(changed_files=(("src/x.ts","code"),("fixtures/x.json","tests")))
    assert classify(facts)[0] == "merged code plus tests/fixtures"


def test_real_response_fixture_is_deterministic_and_never_awards_self_owned_yield():
    fixture=json.loads((Path(__file__).parent/"fixtures"/"github-real-response-pr7.json").read_text(encoding="utf-8"))
    assert fixture["fixture_kind"] == "REAL_RESPONSE_FIXTURE"
    facts=fixture["observed_facts"]
    evidence=GitHubEvidence(facts["repository"],facts["kind"],facts["state"],facts["merged_at"],
        facts["author"],facts["merge_commit"],tuple(map(tuple,facts["changed_files"])),
        tuple(facts["labels"]),tuple(facts["linked_issues"]),tuple(facts["release_tags"]))
    provider=StaticGitHubEvidenceProvider({(fixture["source"],fixture["evidence_class"]):evidence})
    verified=verify_provider_evidence(provider,fixture["source"],fixture["evidence_class"],facts["author"],
        {facts["repository"]})
    assert verified.self_owned is True
    assert fixture["yield_would_be_eligible"] is False
