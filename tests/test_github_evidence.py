import httpx
import pytest

from flop_empires.github_evidence import (GitHubApiEvidenceProvider, GitHubEvidence,
    GitHubVerifier, StaticGitHubEvidenceProvider, parse_evidence_target,
    verify_provider_evidence)


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


def test_real_provider_shape_and_semantic_verification_with_mock_transport():
    def handler(request):
        path = request.url.path
        if path.endswith("/files"):
            value = [{"filename":"docs/guide.md"}, {"filename":"tests/test_guide.py"}]
        elif path.endswith("/releases"):
            value = []
        else:
            value = {"state":"closed", "merged_at":"2026-01-01T00:00:00Z",
                "merge_commit_sha":"abc", "user":{"login":"alice"},
                "labels":[{"name":"documentation"}], "body":"Fixes #12"}
        return httpx.Response(200, json=value, request=request)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = GitHubApiEvidenceProvider(client=client)
    facts = provider.evidence("https://github.com/org/repo/pull/4", "accepted_documentation")
    assert facts.linked_issues == (12,) and ("docs/guide.md", "docs") in facts.changed_files
    verified = verify_provider_evidence(StaticGitHubEvidenceProvider({
        ("https://github.com/org/repo/pull/4", "accepted_documentation"): facts}),
        "https://github.com/org/repo/pull/4", "accepted_documentation", "alice")
    assert verified.cluster_id == "github:org/repo:pull:4"


def test_open_pr_and_provider_outage_fail_closed():
    url = "https://github.com/org/repo/pull/9"
    open_pr = GitHubEvidence("org/repo", "pull", "open", None, "alice", None,
        (("src/x.py","code"),), (), (), ())
    provider = StaticGitHubEvidenceProvider({(url,"merged_pull_request"):open_pr})
    with pytest.raises(ValueError, match="not merged"):
        verify_provider_evidence(provider, url, "merged_pull_request", "alice")
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(503, request=request)))
    with pytest.raises(httpx.HTTPStatusError):
        GitHubApiEvidenceProvider(client=client).evidence(url, "merged_pull_request")


def test_redirect_and_oversized_github_response_rejected():
    url = "https://github.com/org/repo/pull/9"
    redirect = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"Location":"https://evil.example"}, request=request)))
    with pytest.raises(ValueError, match="redirect"):
        GitHubApiEvidenceProvider(client=redirect).evidence(url, "merged_pull_request")
    oversized = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"x" * 1_048_577, request=request)))
    with pytest.raises(ValueError, match="too large"):
        GitHubApiEvidenceProvider(client=oversized).evidence(url, "merged_pull_request")
