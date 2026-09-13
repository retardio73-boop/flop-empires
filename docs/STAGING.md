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

Write staging is a library boundary until a site supplies an explicit manifest,
an allowlist, distinct `staging-*` mailbox/events rooms, and a matching external
signer. Receipt publication is an idempotent outbox workflow. A network publish
is not `PUBLISHED` until readback verifies. Exact network delivery is not assumed.

No production namespace, DID, mailbox, or signer is selected automatically.

The concrete `TechnocoreTransport` implements the detected current room JSON
protocol (`GET/POST /r/{room}`, generation/sequence cursor, and Ed25519 over
exact `room|nonce|text`). Publishing first searches for a semantically identical
verified readback, retries only bounded transient failures, posts a canonical
receipt envelope, and requires cryptographically verified readback.
