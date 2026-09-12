from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from .technical_yield import BASE_UNITS

ALLOWED_HOSTS = {"github.com", "api.github.com"}


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
