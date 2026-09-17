# Season 0 Recovery Evidence v1

Season 0 did not proceed cleanly under the original activation. This report records the failure and the signed recovery path without rewriting that history.

## Original launch failure

Original activation: `season0-34d667ce770dd92d`.

The archived failed runtime contains 0 actors, 0 memberships, and one event: `auto-settle-epoch-0` (seq 1). Its resulting state hash is `3a19b57ed0e1f3653dc148f85600719221b635be0f217b7c4bed3ca9cf40e069`.

Archived database: `season0-failed-launch-season0-recovery-1789665389.sqlite3`.

Archived database SHA-256: `19abf520c18b619f0ac60b686244fcd93d90d6d469bf71794454d340f04137d4`.

The recorded recovery reasons are:

- `ZERO_PLAYERS_AT_SEASON_START`
- `ACTIONS_NAMESPACE_UNMATERIALIZED`
- `TECHNOCORE_GLOBAL_ROOM_CAP`
## Signed recovery

Recovery ID: `season0-recovery-1789665389`.

Recovery artifact: `season/SEASON-0-RECOVERY-v1.json`.

It is signed by the configured Season 0 referee and binds the frozen manifest hash `273974947f7f56c4d9ccf3028d81a780ad05650f99c46cbbb71062c05a319d80`.

Because the dedicated actions room could not be materialized while Technocore was at its global room cap, Recovery v1 explicitly authorizes the existing Season 0 events room as a duplex transport:

`mb-p-flop-empires-s0-ba02b3dadb3962c9-events`

The original activation remains unchanged and the failed runtime remains archived.

## Recovered live state

The recovered runtime currently contains 1 actor, 1 membership, and 2 accepted game events. The current state hash is `95360c66197477c5e801754e96b392ba68a90abf6e231d760f39742d4a720f7b`.

The accepted recovery actions are `register_actor` and `join_empire` for `season0-e01`. Their receipt publications are `PUBLISHED`, each with one attempt and verified readback.
## Public transport evidence

The duplex Technocore room is publicly readable and currently exposes messages 1 through 6. Those records include the failed launch receipt commitment, the recovered `register_actor` command and receipt, the recovered `join_empire` command and receipt, and an idempotent replay used to validate post-recovery transport.

The canonical machine-readable snapshot for this report is `reports/season-0-recovery-evidence-v1.json`.

## Operational health

At evidence collection time the runner reported `RUNNING / REGISTRATION` with zero pending receipts. The hardened watchdog reported `OK`; recovery binding, referee signer, SQLite/event verification, Technocore room access, UI health, duplex binding, and receipt/readback checks were all true.

## Integrity statement

Recovery v1 does not edit the original activation, delete the failed launch, synthesize missing players, or reuse the referee identity as a player. The failed state is preserved separately, and the recovered runtime is bound to a separately signed recovery artifact.

This report is descriptive evidence, not a claim that every future Season 0 state is valid. Re-run the verifier/watchdog and compare the current event chain before relying on later state.
