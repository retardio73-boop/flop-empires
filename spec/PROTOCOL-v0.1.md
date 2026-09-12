# FLOP Empires Protocol v0.1

Status: alpha normative specification.

## Determinism and commands

Commands are UTF-8 JSON objects containing exactly `action`, `actor_did`,
`request_id`, and `payload`. Identifiers are non-empty bounded strings and
request IDs are unique per actor. Canonical bytes use the deterministic JSON
profile implemented by `canonical.py`: sorted Unicode keys, UTF-8, no optional
whitespace, JSON escaping, integers only, and rejection of duplicate keys,
floats, NaN, infinity, and non-JSON values.

Each accepted or rejected command has an append-only event and signed receipt.
The receipt commits to request ID, outcome, persisted referee `accepted_at`,
event sequence, prior state hash, resulting state hash, and details. Repeating
the same actor/request ID returns the original receipt without another effect.
Reuse with different canonical command bytes is rejected.

## Season, identity, and membership

Actors are Ed25519 DIDs (`did:key:` identifiers) with public verify keys.
Empires have one unconquerable Capital. Two or more DIDs may be members of an
empire. Membership may change only before a season becomes `ACTIVE`; it freezes
at activation. A configured referee DID must match the injected signer and the
process fails closed otherwise. Production key custody is external.

## State and economy

Balances contain `available` and `locked`, both non-negative integers.
Territories form an undirected graph and have exactly one owner. Fortification
spends available resources and permanently increases territory defense.
Combat never mints resources. Adapter boundaries for possible future settlement
systems are inert and outside v0.1.

## Alliances and intelligence

Alliances are explicit and may be activated or deactivated. Only an alliance
that was active when an attack was created may defend. Defense contribution is
locked at attack creation and cannot be double-spent. Recon reports deterministic
public military values; it uses no random number generation.

## Raid and Siege

Attacks use the referee's persisted acceptance time, never remote timestamps.
They require graph adjacency, an attacker-owned origin, and sufficient unlocked
resources. Resolution is deterministic; ties go to the defender.

A raid transfers at most half its committed attacker cost and never more than
the defender's available balance, making circular farming economically negative.
A siege may transfer a non-Capital territory only when attack strictly exceeds
defense. A Capital can never be conquered. Failed attack commitments are spent;
unused locked allied defense is unlocked. No combat path creates resources.

## Technocore boundary

Only independently verified signed mailbox records are commands. Display text
is untrusted and never executed. Cursor and accepted record IDs persist locally.
Normal startup bootstraps at the current cursor and does not replay history;
audit/replay is explicit. Duplicate records are harmless. Outages never rewind
state. `seq` and `ts` are evidence only; deadlines use persisted `accepted_at`.

## GitHub boundary

Only explicitly parsed HTTPS URLs hosted by `github.com` or `api.github.com`
and supported by Technical Yield v0.1 may be fetched. URLs found incidentally in
room text are never followed. Verification failure awards nothing.
