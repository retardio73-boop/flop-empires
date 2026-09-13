# Season 0 parameter review

Evidence is separated from recommendation. This final freeze review combines the
integrated v0.2 sweep, the 10-scenario/10-seed 56-epoch cadence matrix, targeted
bootstrap and alliance matrices, and the signed Season -1B rehearsal. Season 0
remains disabled.

| Parameter | Current | Purpose | Observed effect | Evidence | Risk if increased | Risk if decreased | Status |
|---|---:|---|---|---|---|---|---|
| epoch duration | 21,600 s | accrual cadence | gives 56 economic cycles in 14 days | 100 cadence runs, no double accrual | slower feedback | settlement churn | CHANGED_AND_VALIDATED |
| linear threshold | 1000 | uncompressed small contribution | preserves small contributor relevance | 2x/5x/10x monotonic | more whale power | earlier compression | KEEP |
| square-root tail | exponent 1/2 | diminishing returns | 10x maps to 4x effective yield | sweep + live Prestige/yield ordering | weaker compression | stronger compression | KEEP |
| yield epoch divisor | 20 | accrual rate | supports combat without runaway balances | cadence attribution | faster accumulation | slower strategy | KEEP |
| cluster cap | 160 units | bound one contribution | prevents URL multiplication | evidence tests/sweep | cluster farming pressure | undervalues security work | KEEP |
| contributor cap | 320/epoch (v0.1 evidence boundary) | bound identity concentration | no Sybil benefit in adversarial suite | fixture + adversarial report | identity concentration | legitimate burst suppression | MONITOR_IN_SEASON_0 |
| historical bootstrap | none for spendable yield; full Prestige | prevent historical work deciding the map | option A removes historical stock advantage while retaining recognition | A/B/C/D matrix | historical dominance | weaker initial power | CHANGED_AND_VALIDATED |
| territory benefit | 20 | make territory useful | remains material under 56-epoch cadence | cadence territory metrics | map snowball | territory becomes cosmetic | KEEP |
| overextension | 1600 bp/extra | compress expansion | 1104 penalty units live; dominance reversible 5/5 | sweep + live ledger | conquest becomes unattractive | irreversible expansion | KEEP |
| territory upkeep | 4 | recurring control cost | included in 1644 total live upkeep | live ledger | punishes map play | cheap sprawl | KEEP |
| fortification upkeep divisor | 20 | recurring fort cost | became non-zero only after 20-point fortification | live epoch 3 onward | defense unattractive | permanent turtle stock | MONITOR_IN_SEASON_0 |
| stockpile soft limit | 5000 | discourage indefinite hoarding | affects large reserves without forcing ordinary spending | cadence matrix | penalizes healthy reserves | late alpha strikes | KEEP |
| carrying cost | 700 bp | soft stockpile control | 603 units charged live | live epochs 36–45 | forced spending | indefinite accumulation | KEEP |
| fatigue step | 2000 bp | increasing aggression cost | four territorial successes persisted | live combat + sweep | aggression stalls | conquest chains | KEEP |
| fatigue cap | 15000 bp | bound marginal cost | not reached live | sweep only | attacks too costly | cap too permissive | MONITOR_IN_SEASON_0 |
| fatigue window | 400 events | automatic decay | fatigue survived restart; long live window | replay + sweep | long suppression | burst conquest | MONITOR_IN_SEASON_0 |
| raid cost | committed power + fatigue | make raids costly | no combat minting; circular profit negative | live + sweep | raids disappear | farming improves | KEEP |
| raid reward divisor | 2 | bound transfer below cost | live raids transferred at most half base power | live combat | closer to farming break-even | raids lose utility | KEEP |
| siege cost | committed power + fatigue | territory transfer cost | remains viable across cadence scenarios | cadence + live combat | stagnant map | cheap conquest | MONITOR_IN_SEASON_0 |
| defender modifier | 11000 bp | tie/defense value | additive defender + fort + ally path exercised | six live defense submissions | turtle advantage | offense snowball | KEEP |
| fortification | 1 ENGINEERING per point | durable defense | exercised before combat and upkeep | live ledger | turtle advantage | fortification irrelevant | MONITOR_IN_SEASON_0 |
| alliance support | 10000 bp | coordinated defense | 95.18% cartel defense, but 119.1 average successful sieges and zero invulnerable runs | 100/75/60% matrix | cartel pressure | alliances cosmetic | KEEP |
| max defensive alliances | 2 | cartel bound | no effectively invulnerable bloc in targeted matrix | CARTEL sweep + live | cartel concentration | diplomacy too narrow | KEEP |
| minimum attack deadline | 30 s | response floor | 3 s headroom over observed 27 s two-defense path; 60/300 also usable | real Season -1B timing | slower minimum resolution | unreliable response | CHANGED_AND_VALIDATED |

Counts: **KEEP 15**, **CHANGED_AND_VALIDATED 3**,
**MONITOR_IN_SEASON_0 6**. There are zero unresolved pre-freeze changes.

The 30-second deadline is a protocol minimum, not the intended strategic window;
Raid and Siege defense windows may be larger. Activation remains disabled.
