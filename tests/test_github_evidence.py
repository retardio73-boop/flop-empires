import httpx
import pytest

from flop_empires.github_evidence import GitHubVerifier, parse_evidence_target


def client_for(payload):
    return httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload, request=request)))


def test_merged_pr_semantics_and_stable_cluster():
    verifier = GitHubVerifier(client_for({
        "user": {"login": "Alice"}, "merged_at": "2026-01-01T00:00:00Z",
        "labels": [{"name": "documentation"}],
    }))
    evidence = verifier.verify_evidence(
        "https://github.com/community/project/pull/42", "accepted_documentation", "alice")
    assert evidence.cluster_id == "github:community/project:pull:42"
    assert evidence.repository == "community/project" and not evidence.self_owned


def test_failed_or_self_owned_evidence():
    verifier = GitHubVerifier(client_for({
        "user": {"login": "alice"}, "merged_at": None, "labels": [],
    }))
    with pytest.raises(ValueError, match="not merged"):
        verifier.verify_evidence("https://api.github.com/repos/org/repo/pulls/3",
                                 "merged_pull_request", "alice")
    published = GitHubVerifier(client_for({
        "author": {"login": "alice"}, "draft": False, "prerelease": False,
        "published_at": "2026-01-01T00:00:00Z",
    })).verify_evidence("https://github.com/alice/pkg/releases/tag/v1.0.0",
                        "released_package", "alice", {"alice/pkg"})
    assert published.self_owned
    with pytest.raises(ValueError):
        parse_evidence_target("https://github.com/org/repo/issues/1", "merged_pull_request")
    with pytest.raises(ValueError):
        parse_evidence_target("https://evil.example/org/repo/pull/1", "merged_pull_request")
