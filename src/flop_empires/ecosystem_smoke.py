from __future__ import annotations

import argparse
import json
from pathlib import Path

from .github_evidence import GitHubApiEvidenceProvider

REPOSITORY = "retardio73-boop/flop-conformance-lab"
AUTHORITATIVE_DISCOVERY = [
    "https://github.com/retardio73-boop/flop-conformance-lab/blob/main/PROVENANCE.md",
    "https://github.com/flop-labs/yellowpaper",
]
PR_CASES = (7, 14, 15, 19)


def classify(facts) -> tuple[str, str]:
    categories = sorted({kind for _, kind in facts.changed_files})
    if categories == ["docs"]:
        return "documentation-only merge", "deterministic changed-file paths"
    if "tests" in categories and "code" in categories:
        return "merged code plus tests/fixtures", "deterministic changed-file paths"
    if "tests" in categories:
        return "merged tests/fixtures", "deterministic changed-file paths"
    return "merged code", "deterministic merge and changed-file paths"


def run(provider: GitHubApiEvidenceProvider) -> dict:
    cases = []
    base = f"https://github.com/{REPOSITORY}"
    for number in PR_CASES:
        url = f"{base}/pull/{number}"
        facts = provider.evidence(url, "merged_pull_request")
        classification, confidence = classify(facts)
        cases.append({"source":url,"observed_facts":facts.__dict__,
            "classification":classification,"confidence":confidence,
            "yield_would_be_eligible":False,
            "reason":"repository owner equals contributor; self-owned upstream base yield is zero"})
    release_url = f"{base}/releases/tag/v0.1.4-alpha"
    release = provider.evidence(release_url, "released_package")
    cases.append({"source":release_url,"observed_facts":release.__dict__,
        "classification":"published release","confidence":"deterministic published release response",
        "yield_would_be_eligible":False,"reason":"self-owned repository"})
    issue_url = "https://github.com/flop-labs/yellowpaper/issues/56"
    issue_response = provider._get("https://api.github.com/repos/flop-labs/yellowpaper/issues/56")
    cases.append({"source":issue_url,"observed_facts":{"state":issue_response.get("state") if isinstance(issue_response,dict) else None},
        "classification":"issue without deterministically linked merged resolution",
        "confidence":"official issue state and no supported linked-resolution evidence",
        "yield_would_be_eligible":False,"reason":"issues do not score and issue remains unresolved"})
    open_prs = provider._get(f"https://api.github.com/repos/{REPOSITORY}/pulls?state=open&per_page=100")
    first_open=open_prs[0] if isinstance(open_prs,list) and open_prs and isinstance(open_prs[0],dict) else None
    open_source=(str(first_open.get("html_url")) if first_open else f"https://github.com/{REPOSITORY}/pulls")
    observed={"open_pull_requests":len(open_prs) if isinstance(open_prs,list) else None}
    if first_open:
        observed.update({"number":first_open.get("number"),"state":first_open.get("state"),
            "draft":first_open.get("draft"),"author":(first_open.get("user") or {}).get("login")})
    cases.append({"source":open_source,
        "observed_facts":observed,
        "classification":"open/unmerged PR inventory","confidence":"official API list",
        "yield_would_be_eligible":False,
        "reason":"open PRs never score" if first_open else "no open PR existed at observation time; open PRs never score"})
    return {"schema":"flop-empires-ecosystem-smoke-v1","repository":REPOSITORY,
        "authoritative_discovery":AUTHORITATIVE_DISCOVERY,"read_only":True,
        "resources_awarded":0,"cases":cases}


def main(argv=None) -> int:
    p=argparse.ArgumentParser(); p.add_argument("--json-output",type=Path,required=True)
    p.add_argument("--markdown-output",type=Path,required=True); a=p.parse_args(argv)
    provider=GitHubApiEvidenceProvider(); report=run(provider); provider.client.close()
    a.json_output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    lines=["# FLOP/Technocore GitHub evidence smoke", "", "Read-only; resources awarded: `0`.", ""]
    for case in report["cases"]:
        lines += [f"- `{case['classification']}` — {case['source']}",
                  f"  Eligible: `{str(case['yield_would_be_eligible']).lower()}`; {case['reason']}."]
    a.markdown_output.write_text("\n".join(lines)+"\n",encoding="utf-8"); print(json.dumps({"cases":len(report["cases"]),"resources_awarded":0})); return 0


if __name__ == "__main__": raise SystemExit(main())
