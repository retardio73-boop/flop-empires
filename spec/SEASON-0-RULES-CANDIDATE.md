# FLOP Empires Season 0 rules candidate

Status: **freeze candidate — not active**. Registration and start timestamps are
unset. This document does not launch Season 0.

## Season rhythm

The intended Season lasts 14 days. An economic epoch lasts 6 hours (21,600
seconds), producing 56 epochs. This replaces the earlier seven-day candidate
default: two epochs were insufficient to materialize yield, upkeep, stockpile
costs, fatigue, alliances, attacks, and productive comeback during a 14-day game.
Simulation advances deterministic clocks; it never waits six real hours.

The protocol minimum attack deadline is 30 seconds. It is only a transport-safety
floor. A Season may use longer Raid and Siege defense windows.

## Prestige and Strategic Power

Prestige is the uncompressed value of unique, verified, non-self-owned technical
contribution clusters. It cannot be transferred, spent, or used directly in
combat. Strategic Power is separate: it reflects spendable resources,
territories, and fortification. The leaderboards remain separate, so the highest
Prestige does not necessarily control the most territory.

Technical Yield v0.2 converts eligible contribution into ENGINEERING, KNOWLEDGE,
and INFLUENCE. It is linear through the manifest threshold and follows a
square-root tail above it, so useful contribution always increases production
but with diminishing marginal spendable power. Season 0 gives historical
pre-season contributions full Prestige but **no historical spendable bootstrap**.
Only in-Season eligible contribution produces new spendable yield; old work
therefore cannot create indefinite Season power.

## Territory and conflict

Territories add productive value, but overextension reduces marginal benefit and
territory/fortification upkeep consumes ENGINEERING without taking a balance
below zero. Reserves above the soft limit pay a deterministic carrying cost.
Repeated successful territorial aggression adds offensive fatigue that decays
within the manifest window; defense is not fatigued.

Fortification spends ENGINEERING for durable defense and later incurs upkeep.
Defense is additive: modified defending ENGINEERING, fortification, and eligible
alliance support. At most two defensive alliances contribute, and eligibility is
snapshotted when an attack is created. An alliance formed afterward cannot help.

Raids transfer a bounded amount below attacker cost, never territory, and cannot
mint resources. Sieges may transfer an eligible adjacent non-capital territory.
Ties go to the defender. Capitals cannot be conquered.

## Boundaries

Technocore supplies transport, signed identity records, and publication evidence;
it is not the game database, authoritative combat clock, or settlement system.
The referee uses its persisted accepted time for deadlines and its append-only
ledger for state and receipts.

There are no real-money or token rewards, no FLOP settlement, no TCLK payments,
no wallets or NFTs, and no COMPUTE resource in this candidate.
