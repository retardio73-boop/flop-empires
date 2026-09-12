# FLOP Empires Technical Yield Specification v0.1

Status: alpha normative specification.

## Eligible evidence

Only these verified, merged/accepted contribution classes produce base yield:

| Class | Base units |
|---|---:|
| `merged_pull_request` | 100 |
| `accepted_security_fix` | 160 |
| `accepted_documentation` | 40 |
| `released_package` | 120 |

Commits, lines, stars, opened pull requests, opened issues, and Technocore
messages do not score. There is no heuristic or AI scoring.

GitHub evidence must be an explicitly submitted supported URL on `github.com`
or `api.github.com`, independently verified, tied to a registered GitHub
binding, and assigned to one contribution cluster. Self-owned community
repositories have zero base yield. All URLs representing the same underlying
contribution share one cluster and cannot multiply yield.

## Deterministic decay

Time is integer UTC seconds persisted by the referee. Yield at `at` is:

`base * max(0, lifetime - (at - verified_at)) // lifetime`

where `lifetime = 7,776,000` seconds (90 days), future ages are clamped to zero,
and expired contributions yield zero. Integer arithmetic is mandatory. Each
cluster is counted once. Verification failure or an unsupported class yields
zero.
