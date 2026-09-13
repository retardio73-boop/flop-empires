# Economic adversarial analysis

The deterministic adversarial simulator includes FARMER, SYBIL, WHALE, CARTEL,
RAIDER, TURTLE, CONTRIBUTOR, and OPPORTUNIST strategies. It reports resource
sources and sinks rather than hiding initial asymmetry.

Duplicate evidence and same-cluster fragmentation award no additional yield.
Membership freeze makes simulated DID churn unprofitable. A successful raid
returns at most half its cost, so repeated circular raiding is net-negative.
Capitals remain unconquerable and combat cannot create resources.

Technical Yield v0.2 uses one authoritative `epoch_attribution` transition in
the materialized engine, replay, and simulator. It preserves raw Prestige while
applying the manifest's square-root tail and per-epoch divisor to spendable
resources. Territory benefit, overextension, upkeep, fortification upkeep, and
stockpile cost are attributed by the same transition. Offensive fatigue calls
the same manifest-selected cost function in simulation and combat execution.

The targeted attribution run found that the earlier WHALE_10X result below
WHALE_5X came from simulator strategy bias: agents could spend far more often
than the simulated income cadence. After correcting only the strategy reserve,
final liquid resource share is monotonic (2x 21.59%, 5x 29.70%, 10x 36.74%).
Peak concentration remains high and is a Season 0 review risk, but map dominance
reversed in all five fixed seeds and seven other empires remained viable.

Comeback is not a loser bonus. Across 25 fixed seeds, a passive damaged empire
never recovered, while profiles with continued technical contribution recovered
under the stricter multi-epoch definition. The uniform productive outcome is
useful evidence but remains subject to rehearsal validation.

Generated results live in `reports/economic-adversarial-report.json` and `.md`.
The integrated attribution reports are `reports/balance-analysis-v02.json`,
`reports/whale-attribution-v02.md`, and `reports/comeback-v02.md`.
