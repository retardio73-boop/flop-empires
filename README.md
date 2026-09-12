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

No router, conformance-lab, token, payment, wallet, staking, NFT, or browser UI
integration is included.
