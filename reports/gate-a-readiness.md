# Gate A Readiness — FLOP Empires Season 0

Status: READY_FOR_GATE_B_SIMULATION

Validated on 2026-09-15 local project state.

## Normative systems closed

- Territory/world: deterministic graph, capitals unconquerable, Siege-only transfer.
- Economy: ENGINEERING, KNOWLEDGE, INFLUENCE.
- POWER: derived exactly as ENGINEERING + KNOWLEDGE + INFLUENCE; not stored/spent/traded.
- Combat: deterministic; ties favor defender; Raid no conquest; Siege conquest; Recon temporary intel.
- Defense: alliance eligibility snapshot at attack creation; resources lock on accepted submit_defense; late defense rejected.
- Diplomacy: NAP, defensive alliance, mutual alliance, trade pact, coalition representation.
- Trade: atomic and resource-conserving; no POWER; no direct score/yield.
- Fog: public-safe projection plus Fresh/Aging/Stale Recon snapshots.
- Standing: Domain -> Regional -> Major -> Great -> Dominant -> Hegemon; max one Hegemon.
- Momentum: Ascending / Stable / Declining.
- Victory: composite inputs; Hegemon is not automatic victory.
- Contributor roles explicitly separated from in-game power.

## Verification

- Full test suite: 149 passed.
- Python compile/import smoke: passed.
- git diff --check: passed.
- No production Technocore writes performed.
- Freeze v2 lifecycle hardening remains candidate-only; operational freeze requires independent read-only audit.

## Gate B tunables

Map topology/size, production distribution, strategic values, fortification costs, combat costs/windows, upkeep/overextension, treaty cooldowns, trade limits/loop thresholds, Recon aging windows, Standing weights/cutoffs, Momentum deadband, Hegemon thresholds/sustain, victory weights, endgame length and late-join catch-up parameters.
