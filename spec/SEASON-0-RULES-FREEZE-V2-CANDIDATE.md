# FLOP Empires Season 0 rules — freeze v2 candidate

Status: **CANDIDATE — FROZEN, NOT ACTIVE**. This document does not open
registration or start Season 0. The rejected freeze v1 remains historical
evidence and is not deployable.

## Activation and transport boundary

Activation is external to game commands. While the lifecycle is
`FROZEN_NOT_ACTIVE`, the engine, production ingestor, and production receipt
outbox reject every game-state operation before an event or publicable receipt
is created.

A closed-schema, canonically signed Activation Record must reference the exact
freeze v2 manifest hash. It supplies only operational times and the concrete
Technocore actions/events namespaces. Those namespaces must match the frozen
production naming policy and pass two pristine, read-only checks. Any existing
message, nonzero generation/sequence, malformed response, or network uncertainty
aborts activation. Technocore has no atomic namespace reservation, so a residual
race remains between the second check and first legitimate use.

## Season and Technical Yield

The intended Season length remains 14 days: 56 epochs of 6 hours each. Verified,
unique, non-self-owned technical contribution produces uncompressed Prestige.
Prestige is non-transferable, non-spendable, and separate from Strategic Power.

Technical Yield v0.2 remains unchanged. Eligible in-Season contribution produces
ENGINEERING, KNOWLEDGE, and INFLUENCE through the frozen linear-threshold and
square-root-tail curve. Historical verified work retains full Prestige but
provides zero historical spendable bootstrap.

## Territory, costs, and combat

All economic and combat parameters are identical to freeze v1. Territory benefit,
overextension, upkeep, carrying cost, fatigue, fortification, Raid/Siege costs,
the defender modifier, and alliance coefficients are unchanged.

Recon expires after 30 minutes. Raid has a 30-minute response window and cannot
transfer territory. Siege has a 6-hour response window and may transfer only an
eligible adjacent non-capital territory. The protocol minimum remains 30 seconds.
Ties go to the defender and Capitals cannot be conquered.

Defense is additive: modified defending ENGINEERING, fortification, and eligible
alliance support. Alliance eligibility is snapshotted when the attack opens.
Eligible defenders and allies submit defense during the response window; each
accepted submission locks its resources immediately. Defense after the deadline
is rejected. Up to two defensive alliances may contribute at 100% support.

## Lifecycle and immutable operation

Registration accepts only the explicitly defined registration actions. Combat
and epoch settlement require `ACTIVE`. `PAUSED` freezes authoritative game time,
attack windows, and epochs. `FINALIZED` is read-only. Production activation can
only originate from a verified Activation Record and operator preflight, never a
mailbox game command.

Monitoring remains advisory (`INFO`, `REVIEW`, `PAUSE_RECOMMENDED`) and cannot
rebalance or mutate state. Season 0 parameters remain immutable; balance changes
belong to Season 1.

Technocore is signed transport, identity, and publication evidence—not the game
database, clock, or settlement. Season 0 has no real-money rewards, FLOP token,
TCLK settlement, wallets, NFTs, marketplace, or COMPUTE resource.
