# Staging operations

FLOP Empires exposes five readiness labels. `LOCAL_SIMULATION` uses fixtures and
local SQLite only. `STAGING_READ_ONLY` may read GitHub and Technocore but cannot
mutate canonical game state or publish. `STAGING_WRITE` uses an isolated
`staging-*` season, allowlisted actors, an external matching signer, an outbox,
and verified receipt readback. `SEASON_READY` requires an operational review.
`LIVE` is reserved for an actually exercised public Season and is not claimed.

## Safe observation

```console
flop-empires staging observe staging.db --mailbox staging-example-inbox
flop-empires status staging.db
```

On first observation the current remote cursor is persisted without replaying
history. Later runs read after that cursor. The observer verifies signatures and
canonical commands, writes diagnostics only, never invokes the game engine, and
reports `writes_performed=0` (canonical state/network writes).

## Write staging

Write staging requires an explicit manifest, an allowlist, distinct
`mb-p-staging-flop-empires-*` mailbox/events rooms, and a matching external
signer. Receipt publication is an idempotent outbox workflow. A network publish
is not `PUBLISHED` until readback verifies. Exact network delivery is not assumed.

The low-volume live smoke is gated by `--confirm-live-write`:

```console
flop-empires staging write-smoke runtime/technocore-staging-write.db \
  --manifest season/staging-live.json --confirm-live-write
```

No production namespace, DID, mailbox, or signer is selected automatically.

The private Season -1 rehearsal uses a separate hashed manifest and separate
signed/unlisted rooms. Its deterministic rule-based plan is deliberately capped
at 56 action records because the goal is end-to-end correctness, not load testing.
It exercises four actors, shared empire membership, alliances, fortification,
recon, raid, siege, replay/conflict behavior, and DB/cursor restart.

The dedicated Season -1 identities are stored outside Git under Windows DPAPI
CurrentUser in `%LOCALAPPDATA%\FLOPEmpires\staging-identities-v1`. Enrollment is
one-time and refuses replacement. `season/staging-live.json` contains only the
public DIDs and a canonical manifest hash.

The concrete `TechnocoreTransport` implements the detected current room JSON
protocol (`GET/POST /r/{room}`, 48-character room bound, generation/sequence
cursor, standard Ed25519 `did:key:z6Mk...`, unpadded base64url signatures, and
signing over exact `room|nonce|text`). Publishing first searches for a semantically identical
verified readback, retries only bounded transient failures, posts a canonical
receipt envelope, and requires cryptographically verified readback. An ambiguous
delivery is reconciled by readback before retry so a landed nonce is not reposted.
