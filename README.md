# FLOP Empires

Private, locally runnable alpha implementing FLOP Empires Protocol v0.1 and
Technical Yield v0.1. It is a Python 3.12 text/CLI referee with SQLite,
signed receipts, hostile-input verification, and a deterministic simulator.

```console
python -m pip install -e ".[test]"
pytest
flop-empires init game.db --referee-did did:key:YOUR_EXTERNALLY_MANAGED_PUBLIC_KEY
flop-empires simulate --actions 100000 --seed 0 --output simulation-report.json
flop-empires state game.db
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
