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


def validate_evidence_url(url: str, evidence_class: str) -> str:
    p = urlparse(url)
    if p.scheme != "https" or p.hostname not in ALLOWED_HOSTS or p.username or p.password or p.port:
        raise ValueError("unsupported GitHub evidence URL")
    if evidence_class not in BASE_UNITS:
        raise ValueError("unsupported evidence class")
    parts = [x for x in p.path.split("/") if x]
    if p.hostname == "api.github.com":
        if len(parts) < 4 or parts[0] != "repos":
            raise ValueError("unsupported GitHub API evidence path")
        owner, repository = parts[1], parts[2]
    elif len(parts) >= 4:
        owner, repository = parts[0], parts[1]
    else:
        raise ValueError("evidence URL lacks repository")
    return f"{owner}/{repository}"


class GitHubVerifier:
    """Narrow client boundary. Never pass room text; pass an explicit parsed URL."""
    def __init__(self, client: httpx.Client):
        self.client = client

    def fetch_json(self, url: str, evidence_class: str) -> dict:
        validate_evidence_url(url, evidence_class)
        response = self.client.get(url, follow_redirects=False)
        response.raise_for_status()
        if urlparse(str(response.url)).hostname not in ALLOWED_HOSTS:
            raise ValueError("GitHub response left allowlist")
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("invalid GitHub response")
        return value
