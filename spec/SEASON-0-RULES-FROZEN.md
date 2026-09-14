# FLOP Empires Season 0 frozen rules

Status: **FROZEN — NOT ACTIVE**. These rules do not open registration or start a
Season. Activation requires a separate, explicitly authorized launch record that
references the frozen manifest hash.

## Season and Technical Yield

The intended Season length is 14 days: 56 epochs of 6 hours each. Verified,
unique, non-self-owned technical contribution produces Prestige. Prestige is
uncompressed recognition: it is non-transferable, non-spendable, and separate
from Strategic Power.

Technical Yield v0.2 converts eligible in-Season contribution into ENGINEERING,
KNOWLEDGE, and INFLUENCE using a linear threshold and square-root tail. Historical
verified work retains full Prestige but provides zero historical spendable
bootstrap. Useful new contribution can support a comeback; doing nothing receives
no free loser bonus.

## Territory, costs, and combat

Territory adds strategic production, while overextension reduces marginal
benefit. Controlled territory and fortification incur upkeep. ENGINEERING above
the soft stockpile limit incurs a carrying cost. None of these charges can make a
balance negative. Successful territorial aggression adds bounded offensive
fatigue that decays within the fixed window.

Recon results expire after 30 minutes. A Raid has a 30-minute defense window; it
can transfer only bounded resources and never territory. A Siege has a 6-hour
defense window and may transfer an eligible adjacent non-capital territory. The
30-second protocol deadline is only a technical lower bound, not a normal combat
window. Instant legacy combat is disabled by this manifest.

Fortification spends ENGINEERING and adds durable defense. Defense is additive:
modified defending ENGINEERING, fortification, and eligible alliance support.
Alliance eligibility is snapshotted at attack creation, support is 100%, and at
most two defensive alliances may contribute. Ties go to the defender. Capitals
cannot be conquered.

## Immutable operation and pause

The manifest is immutable during Season 0. Operators may OBSERVE, WARN, PAUSE,
and RESUME. They may not live-rebalance, mutate parameters silently, replace the
manifest, rewrite resources, alter past scores, or rewrite combat results.

Pause uses `authoritative-clock-freeze-v1`: state-changing player commands are
rejected while health/read processing continues. The authoritative game clock,
attack deadlines, and epoch accrual freeze. On explicit Resume, every open attack
has exactly the same remaining response duration and epochs continue without
double accrual. A severe exploit preserves state and ledger and pauses for public
reason/investigation. If unchanged rules cannot safely resume, the experimental
Season terminates and any balance correction belongs to Season 1.

Monitoring alerts are INFO, REVIEW, or PAUSE_RECOMMENDED. Economic alerts never
auto-rebalance or auto-pause. Existing cryptographic, database, event-chain, and
replay integrity failures remain fail-closed.

## Boundaries

Technocore is signed transport, identity, and publication evidence. It is not the
game database, authoritative game clock, or settlement. Season 0 has no real-money
rewards, FLOP token, TCLK settlement, wallets, NFTs, or COMPUTE resource.
