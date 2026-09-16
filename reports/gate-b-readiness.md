# Gate B Readiness — FLOP Empires Season 0

Status: READY_AS_SIMULATION_CANDIDATE — NOT FROZEN.

## Selected candidate

- World: 16 empires, 64 territories, deterministic graph.
- POWER: ENGINEERING + KNOWLEDGE + INFLUENCE, derived only.
- Combat: defense base 6; Raid cost 14; Siege cost 26; fortify cost 12; Raid transfer cap 12%.
- Diplomacy: NAP minimum 4 epochs; early-exit cooldown 2 epochs.
- Trade: max 25% of stockpile per offer; one-epoch pair cooldown; zero direct score/yield.
- Recon: cost 8 KNOWLEDGE; Fresh 1 epoch, Aging 2, then Stale.
- Hegemon: >=18% composite world share, >=30% lead over #2, sustained 4 epochs; never automatic victory.
- Endgame: final 8 epochs.
- Late join: 150% production while catching up plus 2-epoch protection.
- Victory score: world-share normalized: territory 30%, POWER 25%, production 15%, objectives 20%, sustained hegemony 10%.

## 600-run confirmation

- 6 scenarios x 100 deterministic seeds.
- Zero capital conquest, negative balances, trade-created resources, or multiple simultaneous Hegemons.
- Balanced: Raid success ~45%, Siege ~54%, final leader territory share ~8.8%, POWER Gini ~0.104.
- Whale 5x: final leader territory share ~17.6%, Hegemon in 42% of runs; not guaranteed.
- Cartel: alliance support exercised ~14.4 times/run; Raid ~42%, Siege ~50%.
- Late join: ~84.8% of median established POWER and 4.64 territories average by Season end.
- Trade-ring: no minting; high trade volume stress remained resource-conserving.
- Endgame leader changed in 7% balanced and 12% late-join runs.

## Remaining limitations before freeze

- Bots are generic; distinct human strategic archetypes are not yet sufficient to prove independent territorial/economic/diplomatic victory paths.
- Coalition behavior is represented but needs a dedicated adversarial multi-bloc simulation.
- Trade collusion/gifting is economically zero-sum but needs policy review if gifting itself should be restricted.
- UI/map usability is outside numerical Gate B and still requires product testing.
- Freeze v2 operational security still requires its independent read-only audit.
