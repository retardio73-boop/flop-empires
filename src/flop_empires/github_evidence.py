from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx

from .technical_yield import BASE_UNITS

ALLOWED_HOSTS = {"github.com", "api.github.com"}
MAX_RESPONSE_BYTES = 1_048_576
USER_AGENT = "flop-empires/0.1 (read-only evidence verifier)"


@dataclass(frozen=True)
class VerifiedEvidence:
    url: str
    evidence_class: str
    repository: str
    cluster_id: str
    github_login: str
    self_owned: bool


@dataclass(frozen=True)
class EvidenceTarget:
    repository: str
    kind: str
    number_or_tag: str
    api_url: str


@dataclass(frozen=True)
class GitHubEvidence:
    repository: str
    kind: str
    state: str
    merged_at: str | None
    author: str
    merge_commit: str | None
    changed_files: tuple[tuple[str, str], ...]
    labels: tuple[str, ...]
    linked_issues: tuple[int, ...]
    release_tags: tuple[str, ...]


class GitHubEvidenceProvider(Protocol):
    def evidence(self, url: str, evidence_class: str) -> GitHubEvidence: ...


class StaticGitHubEvidenceProvider:
    def __init__(self, records: dict[tuple[str, str], GitHubEvidence]):
        self.records = dict(records)

    def evidence(self, url: str, evidence_class: str) -> GitHubEvidence:
        try:
            return self.records[(url, evidence_class)]
        except KeyError as exc:
            raise ValueError("static GitHub evidence not found") from exc


class GitHubApiEvidenceProvider:
    """Official GitHub REST API reader. It never mutates GitHub state."""
    def __init__(self, *, token: str | None = None, client: httpx.Client | None = None,
                 timeout: float = 10.0):
        if timeout <= 0 or timeout > 30:
            raise ValueError("GitHub timeout must be between 0 and 30 seconds")
        token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT,
                   "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(headers=headers, timeout=timeout,
            follow_redirects=False)
        self.timeout = timeout

    def _get(self, url: str) -> dict | list:
        response = self.client.get(url, follow_redirects=False, timeout=self.timeout)
        if 300 <= response.status_code < 400:
            raise ValueError("GitHub redirect rejected")
        response.raise_for_status()
        if response.url.scheme != "https" or response.url.host != "api.github.com":
            raise ValueError("GitHub response left official API origin")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ValueError("GitHub response too large")
        value = response.json()
        if not isinstance(value, (dict, list)):
            raise ValueError("invalid GitHub response")
        return value

    def evidence(self, url: str, evidence_class: str) -> GitHubEvidence:
        target = parse_evidence_target(url, evidence_class)
        primary = self._get(target.api_url)
        if not isinstance(primary, dict):
            raise ValueError("invalid primary GitHub evidence")
        if target.kind == "release":
            author = primary.get("author") or {}
            return GitHubEvidence(target.repository, "release", "published",
                primary.get("published_at"), str(author.get("login", "")), None, (), (), (),
                (str(primary.get("tag_name", target.number_or_tag)),))
        files_raw = self._get(target.api_url + "/files")
        if not isinstance(files_raw, list):
            raise ValueError("invalid GitHub changed-files response")
        changed = tuple(sorted((str(x.get("filename", "")), _classify_file(str(x.get("filename", ""))))
            for x in files_raw if isinstance(x, dict) and x.get("filename")))
        body = str(primary.get("body") or "")
        linked = tuple(sorted({int(n) for n in re.findall(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b", body)}))
        labels = {str(x.get("name", "")).casefold() for x in primary.get("labels", []) if isinstance(x, dict)}
        release_tags: tuple[str, ...] = ()
        if primary.get("merge_commit_sha"):
            releases = self._get(f"https://api.github.com/repos/{target.repository}/releases?per_page=100")
            if isinstance(releases, list):
                release_tags = tuple(sorted(str(x.get("tag_name")) for x in releases
                    if isinstance(x, dict) and x.get("tag_name") and not x.get("draft") and not x.get("prerelease")
                    and primary.get("merge_commit_sha") in str(x.get("body") or "")))
        author = primary.get("user") or {}
        return GitHubEvidence(target.repository, "pull", str(primary.get("state", "")),
            primary.get("merged_at"), str(author.get("login", "")), primary.get("merge_commit_sha"),
            changed, tuple(sorted(labels)), linked, release_tags)


def _classify_file(path: str) -> str:
    p = path.casefold()
    if p.startswith(("docs/", "doc/")) or p.endswith((".md", ".rst")):
        return "docs"
    if p.startswith(("tests/", "test/", "fixtures/")) or "/test" in p or "/fixtures/" in p:
        return "tests"
    if p.startswith("spec/") or "specification" in p:
        return "spec"
    return "code"


def verify_provider_evidence(provider: GitHubEvidenceProvider, url: str,
                             evidence_class: str, github_login: str,
                             self_owned_repositories: set[str] | frozenset[str] = frozenset()) -> VerifiedEvidence:
    target = parse_evidence_target(url, evidence_class)
    facts = provider.evidence(url, evidence_class)
    if facts.repository.casefold() != target.repository.casefold():
        raise ValueError("GitHub repository identity mismatch")
    if facts.author.casefold() != github_login.casefold():
        raise ValueError("evidence author does not match GitHub binding")
    if target.kind == "pull":
        if facts.state != "closed" or not facts.merged_at or not facts.merge_commit:
            raise ValueError("pull request is not merged")
        categories = {category for _, category in facts.changed_files}
        if evidence_class == "accepted_documentation" and not ({"docs", "spec"} & categories):
            raise ValueError("documentation evidence has no docs/spec changes")
        if evidence_class == "accepted_security_fix" and not ({"security", "security-fix"} & set(facts.labels)):
            raise ValueError("security evidence lacks an accepted security label")
    elif facts.state != "published" or not facts.merged_at or not facts.release_tags:
        raise ValueError("release is not a published stable release")
    return VerifiedEvidence(url, evidence_class, target.repository,
        f"github:{target.repository}:{target.kind}:{target.number_or_tag}", github_login,
        target.repository.casefold() in {x.casefold() for x in self_owned_repositories})


def validate_evidence_url(url: str, evidence_class: str) -> str:
    return parse_evidence_target(url, evidence_class).repository


def parse_evidence_target(url: str, evidence_class: str) -> EvidenceTarget:
    p = urlparse(url)
    if (p.scheme != "https" or p.hostname not in ALLOWED_HOSTS or p.username or
            p.password or p.port or p.query or p.fragment):
        raise ValueError("unsupported GitHub evidence URL")
    if evidence_class not in BASE_UNITS:
        raise ValueError("unsupported evidence class")
    parts = [x for x in p.path.split("/") if x]
    if p.hostname == "api.github.com":
        if len(parts) < 4 or parts[0] != "repos":
            raise ValueError("unsupported GitHub API evidence path")
        owner, repository = parts[1], parts[2]
        rest = parts[3:]
    elif len(parts) >= 4:
        owner, repository = parts[0], parts[1]
        rest = parts[2:]
    else:
        raise ValueError("evidence URL lacks repository")
    repo = f"{owner}/{repository}"
    if evidence_class == "released_package":
        if p.hostname == "github.com" and len(rest) == 3 and rest[:2] == ["releases", "tag"]:
            tag = rest[2]
        elif p.hostname == "api.github.com" and len(rest) == 3 and rest[:2] == ["releases", "tags"]:
            tag = rest[2]
        else:
            raise ValueError("release evidence must identify one release tag")
        return EvidenceTarget(repo, "release", tag,
            f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    if p.hostname == "github.com" and len(rest) == 2 and rest[0] == "pull" and rest[1].isdigit():
        number = rest[1]
    elif p.hostname == "api.github.com" and len(rest) == 2 and rest[0] == "pulls" and rest[1].isdigit():
        number = rest[1]
    else:
        raise ValueError("pull-request evidence must identify one pull request")
    return EvidenceTarget(repo, "pull", number,
        f"https://api.github.com/repos/{repo}/pulls/{number}")


class GitHubVerifier:
    """Narrow client boundary. Never pass room text; pass an explicit parsed URL."""
    def __init__(self, client: httpx.Client):
        self.client = client

    def fetch_json(self, url: str, evidence_class: str) -> dict:
        target = parse_evidence_target(url, evidence_class)
        response = self.client.get(target.api_url, follow_redirects=False)
        response.raise_for_status()
        if urlparse(str(response.url)).hostname not in ALLOWED_HOSTS:
            raise ValueError("GitHub response left allowlist")
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("invalid GitHub response")
        return value

    def verify_evidence(self, url: str, evidence_class: str, github_login: str,
                        self_owned_repositories: set[str] | frozenset[str] = frozenset()) -> VerifiedEvidence:
        """Verify only explicit supported evidence; never accepts discovered room URLs."""
        target = parse_evidence_target(url, evidence_class)
        data = self.fetch_json(url, evidence_class)
        author = data.get("user") if target.kind == "pull" else data.get("author")
        if not isinstance(author, dict) or author.get("login", "").casefold() != github_login.casefold():
            raise ValueError("evidence author does not match GitHub binding")
        if target.kind == "pull":
            if not isinstance(data.get("merged_at"), str) or not data["merged_at"]:
                raise ValueError("pull request is not merged")
            labels = {x.get("name", "").casefold() for x in data.get("labels", []) if isinstance(x, dict)}
            if evidence_class == "accepted_security_fix" and not ({"security", "security-fix"} & labels):
                raise ValueError("security evidence lacks an accepted security label")
            if evidence_class == "accepted_documentation" and not ({"documentation", "docs"} & labels):
                raise ValueError("documentation evidence lacks an accepted documentation label")
        elif (data.get("draft") is not False or data.get("prerelease") is not False or
              not isinstance(data.get("published_at"), str) or not data["published_at"]):
            raise ValueError("release is not a published stable release")
        cluster_id = f"github:{target.repository}:{target.kind}:{target.number_or_tag}"
        return VerifiedEvidence(url, evidence_class, target.repository, cluster_id,
            github_login, target.repository.casefold() in {x.casefold() for x in self_owned_repositories})
