# Season 0 operations runbook

This runbook began as the prepare-only Season 0 launch runbook. Season 0 is now
operating under signed `Recovery v1`; the frozen manifest remains unchanged. The
original failed launch is preserved rather than rewritten. For the current recovery
binding, timeline, hashes, public receipts, and health evidence, see
`reports/season-0-recovery-evidence-v1.md`.

## Pre-flight

1. Verify the checkout/tag and a clean worktree.
2. Load the frozen manifest and verify its canonical SHA-256.
3. Recover the exact configured referee DID through DPAPI and complete a fresh
   local sign/verify challenge. Never generate a replacement.
4. Recheck both Technocore rooms read-only. They must still be collision-free;
   the protocol has no ownership reservation.
5. Run SQLite `quick_check`, event-chain verification, replay comparison, and an
   offline backup/restore check on the intended database path.
6. Check Technocore and GitHub with bounded read-only requests, disk free space,
   UTC/system-clock sanity, and process permissions.
7. Confirm registration, start, and end remain null. Stop if any differ.

## Startup

Startup is a separate future authorization. It must consume a versioned launch
record referencing the frozen hash; never edit the frozen manifest. Bootstrap at
the current Technocore cursor and do not replay historic room traffic. Confirm the
signer DID, isolated production DB, namespace, and activation record before
enabling state-changing ingestion.

## Health check

Check signer availability, DB quick-check, event chain, outbox/readback state,
Technocore generation/cursor lag, processing lag, GitHub availability, disk, and
the monitoring metrics frozen in the manifest. Alerts are advisory: INFO, REVIEW,
and PAUSE_RECOMMENDED. Economic alerts do not trigger automatic mutation or pause.

## Pause

Issue one explicit referee `pause_season` action. Confirm a signed receipt and
persisted `PAUSED` state. Continue bounded mailbox processing and health reads;
state-changing game commands receive deterministic rejection. Preserve DB,
ledger, outbox, open attacks, and the wall-clock pause anchor. Publish the reason
through the separately approved communications process.

## Resume

Verify integrity and confirm rules did not change. Issue explicit
`resume_season`. Confirm the accumulated paused duration and signed receipt.
Validate one open attack's remaining time and the next epoch boundary. Never
backfill or double-accrue paused time.

## Referee restart

Stop intake cleanly where possible, preserve DB/WAL files together, restart with
the same manifest hash and exact DID, verify event chain, recover cursor/outbox,
and reconcile published receipts before accepting more records. A paused restart
must remain paused with the same game-clock anchor.

## Technocore outage

Classify bounded timeout/5xx failures as transient, retain cursor and committed
state, and retry with backoff. Do not rewind or invent delivery. If duration or
lag threatens fairness, recommend Pause. Resume only after cursor generation and
gaps verify.

## GitHub outage

Fail closed for new evidence: award no yield and retain the evidence request for
later explicit retry. Existing verified state remains unchanged. Do not replace
facts with heuristic scoring.

## Signer unavailable

Stop transitions requiring receipts/publication and report
`REFEREE_SIGNER_UNAVAILABLE`. Do not generate a new identity or use staging keys.
Recover only the exact configured DID.

## DB integrity or event-chain failure

HALT_FAIL_CLOSED. Make a read-only forensic copy, preserve WAL and logs, and do
not repair history in place. Compare backup/replay and obtain human review before
any further action.

## Readback failure

Leave the durable outbox entry pending. Search for an exact signed semantic
readback before retrying. A posted-but-unverified receipt is not fully published;
never repeat the game transition.

## Season finalization

Stop new commands at the separately authorized end boundary, resolve only actions
allowed by frozen rules, drain and verify the outbox, verify event chain and full
replay, snapshot final state/hash, and archive public receipts. Do not settle
tokens or monetary value. Any rule change is versioned for Season 1.

## Explicit launch gate

Season 0 Recovery v1 does **not** authorize gameplay to start.

Production may remain in `REGISTRATION` indefinitely after the recovery record's original `season_start`.
The wall clock alone must never transition the recovered season to `ACTIVE`.

A transition to `ACTIVE` requires a separate, referee-signed
`flop-empires-launch-authorization-v1` artifact bound to the exact current production binding
(Recovery ID when recovery is active), frozen manifest hash, season ID, and referee DID.

If `season/SEASON-0-LAUNCH-AUTHORIZATION-v1.json` is absent, the runner fails closed:
registration remains open, gameplay actions remain unavailable, and the watchdog reports
`launch_authorized: false`.

When a launch authorization is eventually issued, its `effective_start` becomes the real
registration close / gameplay start and its `effective_end` preserves the full frozen
Season 0 duration. Never create or sign this artifact merely to test the UI.
