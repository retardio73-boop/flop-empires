from types import SimpleNamespace

from flop_empires.ecosystem_smoke import classify


def test_ecosystem_classification_docs_only():
    assert classify(SimpleNamespace(changed_files=(("CONTRIBUTING.md","docs"),)))[0] == "documentation-only merge"


def test_ecosystem_classification_code_and_fixtures():
    facts=SimpleNamespace(changed_files=(("src/x.ts","code"),("fixtures/x.json","tests")))
    assert classify(facts)[0] == "merged code plus tests/fixtures"
