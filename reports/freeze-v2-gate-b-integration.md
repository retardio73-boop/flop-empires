# Freeze v2 / Gate B integration

Status: COMPLETE_CANDIDATE_NOT_ACTIVE
Date: 2026-09-15

## Bound artifacts
- Freeze v2 schema: `flop-empires-season-freeze-v2-candidate-v2`
- Manifest hash: `273974947f7f56c4d9ccf3028d81a780ad05650f99c46cbbb71062c05a319d80`
- Season 0 world: `season/world-season-0-v1.json`
- World hash: `e4f4e5d497ddb208508aa4fcba98395807e5f4806aa1b17f5f3365cecd29622d`
- Gate B parameters are embedded exactly in the manifest.

## Season 0 world
- 16 empires / 64 territories.
- Deterministic ring + second-neighbor graph.
- Capitals remain unconquerable.
- Territory production matches EconomicRulesV02: raw territory benefit is ENGINEERING-only.
- Strategic value affects map/victory only and does not mint extra resources.

## Final Gate B candidate
- Raid minimum POWER: 14.
- Siege minimum POWER: 24.
- NAP minimum: 4 epochs; exit cooldown: 2 epochs.
- Recon: fresh 1 epoch, aging 2 epochs.
- Hegemon: >=18% composite share, >=30% lead over #2, sustained 4 epochs.
- Endgame: 8 epochs.
- Late join: 187.5% production catch-up, 4 protected epochs.
- Victory weights: territory 30%, POWER 25%, production 15%, objectives 20%, hegemon epochs 10%.

## Final confirmation
- 600 scenario runs plus 200 mixed-strategy adversarial runs.
- Balanced: Raid 57.6%, Siege 63.9%, no Hegemon.
- Whale 5x: Hegemon in 37% of runs.
- Late join: 85.4% of median established POWER, 5.66 territories average.
- Adversarial: all 8 strategies won; max strategy win rate 32% (Territorial).
- Zero capital failures, negative balances, trade minting, or multi-Hegemon failures.

## Verification
- Full test suite: 158 passed.
- New regression coverage verifies exact Gate B embedding and world hash.
- Engine rejects Siege POWER 23 and accepts the frozen minimum 24 in regression test.
- Python compileall: passed.
- `git diff --check`: passed.
- No production Technocore writes performed.
- Freeze v1 historical artifact remains unchanged and loadable.

## Operational status
This completes Gate B integration into the Freeze v2 candidate. It does not activate Season 0. Activation Record, pristine namespace preflight, production runtime binding and independent read-only Freeze v2 audit remain launch gates.
