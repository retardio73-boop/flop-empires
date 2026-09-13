# FLOP Empires Season 0 rules candidate

Status: **CANDIDATE — NOT ACTIVE**. This document does not open registration,
create a namespace, or make production claims. Human review and an explicit
immutable production manifest are required.

Season 0 selects FLOP Empires Protocol v0.1 with `technical-yield-v0.2` for
Prestige and spendable resources. Historical v0.1 ledgers keep their original
state projection and event-chain verification.

Prestige is the uncompressed sum of unique verified non-self-owned contribution
clusters. It is non-transferable, non-spendable, hashed in state, and shown on a
leaderboard separate from Strategic Power. Spendable yield uses the manifest
threshold and square-root tail, resource weights, and epoch divisor defined in
Technical Yield v0.2.

Every epoch is a single sequential `ECONOMIC_EPOCH_SETTLED` transition containing
gross yield, diminishing-return loss, territory production, overextension,
upkeep, and carrying-cost attribution. Combat costs and successful offensive
fatigue are ledgered in their attack transitions. Replay must reproduce the
persisted state hash exactly.

Defense is additive: modified defender ENGINEERING + fortification + eligible
alliance support. Eligibility is snapshotted at attack creation. Ties go to the
defender, raids cannot mint, circular raids are net-negative, and Capitals cannot
be conquered.

Expected hostile room records are rejected and processing continues. Integrity
corruption, signer/DID mismatch, and replay divergence halt fail-closed.

The accompanying JSON is intentionally non-operational: production DID and rooms
remain unassigned, activation is disabled, and the staging identities/namespaces
must not be reused.
