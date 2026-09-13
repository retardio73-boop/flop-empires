# Season 0 cadence validation

Frozen observation run: 14 days, 56 epochs, six hours per epoch; no parameters were tuned during the matrix.

- Scenarios: 10; fixed seeds per scenario: 10
- Invariant failures: 0; combat creation: 0
- WHALE_2X: final resource 22.14%, peak 79.69%, reversible 90%
- WHALE_5X: final resource 29.74%, peak 90.28%, reversible 100%
- WHALE_10X: final resource 35.87%, peak 93.77%, reversible 100%
- Productive comeback: 100%; passive: 0%; median productive epochs: 3.0
- Maximum observed circular-raid profit: 0

## Bootstrap review

The matrix compared A) none, B) 30 days at 25%, C) 30 days at 50%, and D) 14 days at 50%. Prestige remains full in every option; only spendable power changes.

- A_NO_HISTORICAL: WHALE_10X final resource 11.52%; duration above 50% 0.9 actions; reversible 0%
- B_30_DAY_25_PERCENT: WHALE_10X final resource 95.27%; duration above 50% 28000.0 actions; reversible 0%
- C_30_DAY_50_PERCENT: WHALE_10X final resource 47.32%; duration above 50% 23177.8 actions; reversible 60%
- D_14_DAY_50_PERCENT: WHALE_10X final resource 96.26%; duration above 50% 28000.0 actions; reversible 0%

Selected: A, no historical spendable bootstrap. Even 25% allowed the historical WHALE_10X cohort to finish above 95% liquid share with no reversal in this matrix. Historical contribution still receives full Prestige.

## Alliance support review

- 100% support: cartel defense 95.18%; successful raids 65.5; successful sieges 119.1; effectively invulnerable 0%
- 75% support: cartel defense 94.76%; successful raids 66.8; successful sieges 129.6; effectively invulnerable 0%
- 60% support: cartel defense 94.33%; successful raids 72.0; successful sieges 138.8; effectively invulnerable 0%

Selected: keep 100%. It is strong, but the per-run threshold found no effectively invulnerable cartel and offense remained viable. Monitor during Season 0 rather than reducing without evidence.

## Attack deadline

Persisted Season -1B evidence measured 26–27 seconds for two signed defense round trips. The 30/60/300-second values are all usable; 30 seconds remains the protocol minimum with three seconds observed headroom. Strategic windows may be longer.

## Acceptance

Zero invariant failures, double accrual, combat minting, negative balances, replay divergence, or Sybil advantage without contribution were observed. Upkeep did not dominate all production; raids and sieges remained active; productive comeback was possible while passive comeback was not guaranteed.
