# FLOP Empires Season 0 — Gate A Rules v0.1

Status: NORMATIVE_CANDIDATE. Gate A defines behavior and invariants. Gate B tunes numeric parameters by simulation.

## Economy and POWER

Spendable resources are ENGINEERING, KNOWLEDGE and INFLUENCE. POWER is derived only:

`POWER = ENGINEERING + KNOWLEDGE + INFLUENCE`

POWER is never stored, transferred or spent. COMPUTE is deferred to testnet. Combat, diplomacy and trade cannot mint resources.

## Territory and world

The world is a deterministic graph generated from a recorded seed. Territories expose identity, region, adjacency, owner, base production, strategic value and fortification. Each empire has one capital. Capitals are unconquerable. Raid never transfers territory. Siege is the only territory-transfer action.

## Combat and intelligence

Combat is deterministic and ties favor the defender. Recon creates temporary intelligence; it does not reveal permanent truth. Alliance eligibility is snapshotted at attack creation. Defense resources may be submitted during the defense window and lock only when `submit_defense` is accepted. Submissions at or after the deadline are rejected.

## Diplomacy

Treaties are auditable signed state machines. Season 0 treaty kinds are NAP, DEFENSIVE_ALLIANCE, MUTUAL_ALLIANCE, TRADE_PACT and COALITION. Every treaty has participants, start/end, signatures, state and optional objective. A coalition is a multiparty treaty with objective and expiry.

An active NAP blocks attacks between its participants. Early exit/breach is explicit and leaves factual history. There is no subjective karma score in Gate A.

## Trade

Trade is `offer -> accept -> atomic settlement`. Only the three spendable resources may be exchanged. POWER cannot be traded. Insufficient balance rejects the whole settlement. Trade conserves each resource globally and gives no direct yield or Season Score.

## Fog of war

Public: ownership, capitals, Standing, public conflicts and public treaties. Hidden by default: exact stockpiles, exact fortification, committed force and sensitive production data. Recon may expose permitted snapshots. Intelligence ages `Fresh -> Aging -> Stale`. Season 0 never inserts false information into canonical state.

## Standing and Momentum

Standing is derived only from in-game geopolitical state and is independent of contributor roles:

`Domain -> Regional -> Major -> Great -> Dominant -> Hegemon`

Standing inputs are POWER, territory value, production, fortification and strategic/military capacity. Hegemon may be absent and at most one empire may hold it. Momentum is `Ascending`, `Stable` or `Declining` and measures direction, not rank.

## Victory and endgame

Hegemon is not automatic victory. Final Season Score is built only from territory/strategic value, POWER/economy, strategic objectives and sustained hegemony. Trade volume, messages, commits and contributor activity do not score. Endgame may restrict late treaty creation without changing economic or combat rules mid-Season.

## Contributor separation

Contributor roles recognize work on FLOP Empires but never grant resources, territory, POWER, Standing, combat advantage or Season Score in the same Season.

## Visual map contract

The visual map is a fog-safe projection of canonical headless state. It may expose nodes/edges, owner, capital marker, public conflicts, public diplomacy, Standing and permitted Recon intel. The UI must never reveal hidden backend values merely because they exist in storage.

## Gate B tunables — explicitly not frozen here

Gate B must determine numeric values for: map size/topology mix; territory production distribution; strategic-value distribution; fortification costs; Raid/Siege/Recon costs and windows; upkeep/overextension; treaty cooldowns; trade volume/cooldown/loop thresholds; Recon freshness windows; Standing weights and relative cutoffs; Momentum deadband; Hegemon dominance/sustain requirements; victory weights; endgame length; late-join/catch-up parameters.

These values may change during Gate B simulation without changing Gate A semantics.

## Gate A invariants

1. No command mutates production state while lifecycle is `FROZEN_NOT_ACTIVE`.
2. POWER is derived and cannot be persisted as a spendable balance.
3. Trade, combat and diplomacy conserve resources except explicit sinks defined by the economy.
4. Capitals never change owner.
5. Raid never transfers territory; Siege is the only transfer action.
6. NAP blocks hostile initiation while effective.
7. Defense eligibility is frozen at attack creation; actual resources lock on accepted defense submission.
8. Fog-safe projections do not expose hidden state.
9. At most one Hegemon exists and Hegemon does not itself end the Season.
10. Contributor roles never affect in-game economic or geopolitical power.
