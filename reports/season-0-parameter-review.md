# Season 0 parameter review

Evidence is separated from recommendation. Simulation evidence is the integrated
150-run v0.2 sweep plus the 25-seed-per-profile comeback study. Rehearsal evidence
is the signed Technocore Season -1B report (162 processed commands, 161 verified
receipts, 46 epochs, and exact 161-event replay).

| Parameter | Current | Purpose | Observed effect | Evidence | Risk if increased | Risk if decreased | Status |
|---|---:|---|---|---|---|---|---|
| epoch duration | 5 s staging | accrual cadence | enabled bounded rehearsal | 46 live epochs, no double accrual | slower feedback | stockpile/transport races | CHANGE_BEFORE_SEASON_0 |
| linear threshold | 1000 | uncompressed small contribution | preserves small contributor relevance | 2x/5x/10x monotonic | more whale power | earlier compression | KEEP |
| square-root tail | exponent 1/2 | diminishing returns | 10x maps to 4x effective yield | sweep + live Prestige/yield ordering | weaker compression | stronger compression | KEEP |
| yield epoch divisor | 20 | accrual rate | live E1/E2/E3/E4 gross 49/100/149/200 after comeback | 46 live epochs | faster accumulation | slower strategy | REVIEW |
| cluster cap | 160 units | bound one contribution | prevents URL multiplication | evidence tests/sweep | cluster farming pressure | undervalues security work | KEEP |
| contributor cap | 320/epoch (v0.1 evidence boundary) | bound identity concentration | no Sybil benefit in adversarial suite | fixture + adversarial report | identity concentration | legitimate burst suppression | REVIEW |
| bootstrap multiplier | 2x for 30 days (v0.1 boundary) | early activity | not used by synthetic Season -1B Prestige | historical tests only | launch rush | weak activation | REVIEW |
| territory benefit | 20 | make territory useful | 34 effective from two non-capitals | live epoch ledger | map snowball | passive contribution dominates | REVIEW |
| overextension | 1600 bp/extra | compress expansion | 1104 penalty units live; dominance reversible 5/5 | sweep + live ledger | conquest becomes unattractive | irreversible expansion | KEEP |
| territory upkeep | 4 | recurring control cost | included in 1644 total live upkeep | live ledger | punishes map play | cheap sprawl | KEEP |
| fortification upkeep divisor | 20 | recurring fort cost | became non-zero only after 20-point fortification | live epoch 3 onward | defense unattractive | permanent turtle stock | REVIEW |
| stockpile soft limit | 5000 | discourage indefinite hoarding | first activated after threshold, never before | live epoch 36 | penalizes healthy reserves | late alpha strikes | REVIEW |
| carrying cost | 700 bp | soft stockpile control | 603 units charged live | live epochs 36–45 | forced spending | indefinite accumulation | KEEP |
| fatigue step | 2000 bp | increasing aggression cost | four territorial successes persisted | live combat + sweep | aggression stalls | conquest chains | KEEP |
| fatigue cap | 15000 bp | bound marginal cost | not reached live | sweep only | attacks too costly | cap too permissive | REVIEW |
| fatigue window | 400 events | automatic decay | fatigue survived restart; long live window | replay + sweep | long suppression | burst conquest | REVIEW |
| raid cost | committed power + fatigue | make raids costly | no combat minting; circular profit negative | live + sweep | raids disappear | farming improves | KEEP |
| raid reward divisor | 2 | bound transfer below cost | live raids transferred at most half base power | live combat | closer to farming break-even | raids lose utility | KEEP |
| siege cost | committed power + fatigue | territory transfer cost | four successful staged sieges | live combat | stagnant map | cheap conquest | REVIEW |
| defender modifier | 11000 bp | tie/defense value | additive defender + fort + ally path exercised | six live defense submissions | turtle advantage | offense snowball | KEEP |
| fortification | 1 ENGINEERING per point | durable defense | exercised before combat and upkeep | live ledger | turtle advantage | fortification irrelevant | REVIEW |
| alliance support | 10000 bp | coordinated defense | six eligible supports accepted | live staged combat | cartel risk | alliances cosmetic | REVIEW |
| max defensive alliances | 2 | cartel bound | manifest-selected limit; rehearsal used one/empire | CARTEL sweep + live | cartel concentration | diplomacy too narrow | REVIEW |
| minimum attack deadline | 1 s default | response window | 1 s rejected both defenses over real transport | live staged attack 0 | slower resolution | impossible defense | CHANGE_BEFORE_SEASON_0 |

Counts: **KEEP 10**, **REVIEW 12**, **CHANGE_BEFORE_SEASON_0 2**.
The candidate manifest applies a seven-day epoch and a 30-second minimum attack
deadline; neither becomes active without human review and a new production namespace.
