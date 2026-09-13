# FLOP Empires Technical Yield v0.2

Version selection is explicit in the Season manifest. Version 0.1 remains
unchanged for historical events and replay.

## Prestige

Prestige is the cumulative verified base value of unique, non-self-owned
contribution clusters. It is visible but non-transferable, non-spendable, and is
never combat power. It is not compressed for balance.

## Spendable resources

Let `P` be Prestige and `T` the manifest `linear_threshold`:

`Spendable(P) = P`, when `P <= T`.

`Spendable(P) = T + floor(sqrt((P - T) * T))`, when `P > T`.

The curve is deterministic, monotonic, linear below the threshold, and strictly
sublinear above it. Manifest basis-point weights allocate the result among
ENGINEERING, KNOWLEDGE, and INFLUENCE.

## Structural expansion costs

Non-capital territory benefit is multiplied by
`10000 / (10000 + max(0,N-1)*overextension_penalty_bp)`, using integer floor.
Upkeep consumes at most available ENGINEERING and combines per-territory,
fortification, and soft stockpile carrying costs. It cannot make balances negative.

Each successful territorial attack inside the rolling manifest window adds
`fatigue_step_bp` to subsequent offensive cost, capped by `fatigue_max_bp`.
Expired successes leave the window automatically. Defense has no fatigue penalty.

Defense is strictly additive:

`DefensePower = floor(EngineeringDefense * defender_modifier_bp / 10000)`
`             + FortificationPower`
`             + EligibleAllianceSupport`

Loss of territory does not erase Prestige or verified contribution history.
