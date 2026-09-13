# FLOP Empires

Private, locally runnable Season 0 candidate implementing FLOP Empires Protocol
v0.1 plus replay-compatible Technical Yield v0.1 and manifest-selected v0.2. It
is a Python 3.12 text/CLI referee with SQLite,
signed receipts, hostile-input verification, and a deterministic simulator.

```console
python -m pip install -e ".[test]"
pytest
flop-empires init game.db --referee-did did:key:YOUR_EXTERNALLY_MANAGED_PUBLIC_KEY
flop-empires simulate --actions 100000 --seed 0 --output simulation-report.json
flop-empires state game.db
flop-empires status game.db
flop-empires staging observe staging.db --mailbox staging-example-inbox
```

`init` records only the public referee DID. It never creates or stores a signing
key; adjudicating applications inject a matching signer implementation.

Live boundaries are deliberately narrow: `GitHubVerifier.verify_evidence`
converts an explicit supported GitHub URL into typed, semantically verified
evidence, and `TechnocoreIngestor.poll` consumes finite batches from an injected
read-only `SignedMailbox`. Network credentials and production signing remain in
the injected clients; neither is persisted by FLOP Empires.

`TechnocoreHttpMailbox` is the fixed-origin live reader. It accepts only canonical
JSON commands carried in room messages, verifies the exact Ed25519
`room|nonce|text` signature again inside the ingestor, tracks generation and
sequence, rejects retention gaps, and never follows or executes message content.

No router, conformance-lab, token, payment, wallet, staking, NFT, or browser UI
integration is included.

Current exercised capability includes `SEASON_MINUS_ONE_READY`: official GitHub API,
fixed-origin Technocore reads, dedicated DPAPI-protected staging identities,
signed action POST, signed receipt POST, verified readback, duplicate/conflict
semantics, both controlled crash windows, and a four-actor private Season -1
have been exercised. Season -1B additionally ran the integrated v0.2 engine for
165 real action records and 46 epochs with exact replay. This remains an isolated
no-value staging rehearsal. The Season 0 artifacts are non-operational candidates;
registration has not started. See `docs/STAGING.md`; this repository does not
claim `LIVE`.
