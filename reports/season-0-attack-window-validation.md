# Season 0 attack-window validation

This is an operational opportunity model, not a precise prediction of human response.
It assumes uniformly phased attack arrival relative to four explicit check intervals.

## Raid candidates

| Window | Active-human opportunity | Alliance profiles >=50% | Concurrent at 1/hour | Epoch overlap |
|---:|---:|---:|---:|---:|
| 5 min | 17% | 1 | 0.08 | 1.4% |
| 15 min | 50% | 3 | 0.25 | 4.2% |
| 30 min | 100% | 3 | 0.50 | 8.3% |
| 60 min | 100% | 4 | 1.00 | 16.7% |

## Siege candidates

| Window | Casual-human opportunity | Alliance profiles >=50% | Concurrent at 1/hour | Epoch overlap |
|---:|---:|---:|---:|---:|
| 1 h | 50% | 4 | 1.0 | 17% |
| 3 h | 100% | 4 | 3.0 | 50% |
| 6 h | 100% | 4 | 6.0 | 100% |
| 12 h | 100% | 4 | 12.0 | 100% |

Selected: Raid 30 minutes, Siege 6 hours, Recon TTL 30 minutes. Raid gives an active human one full check interval and keeps lock exposure to half an hour. Siege spans one economic epoch and gives every modeled profile a response opportunity without the 12-hour stale-lock pressure.

The 30-second protocol minimum remains only a lower bound; it is not a normal Season 0 defense window.
