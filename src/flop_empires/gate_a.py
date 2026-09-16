from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, Sequence

RESOURCES = ("ENGINEERING", "KNOWLEDGE", "INFLUENCE")


class TreatyType(StrEnum):
    NAP = "NAP"
    DEFENSIVE_ALLIANCE = "DEFENSIVE_ALLIANCE"
    MUTUAL_ALLIANCE = "MUTUAL_ALLIANCE"
    TRADE_PACT = "TRADE_PACT"
    COALITION = "COALITION"


class TreatyState(StrEnum):
    PROPOSED = "PROPOSED"
    ACTIVE = "ACTIVE"
    EXITING = "EXITING"
    EXPIRED = "EXPIRED"
    BREACHED = "BREACHED"
    TERMINATED = "TERMINATED"


class IntelFreshness(StrEnum):
    FRESH = "FRESH"
    AGING = "AGING"
    STALE = "STALE"


class Standing(StrEnum):
    DOMAIN = "Domain"
    REGIONAL = "Regional"
    MAJOR = "Major"
    GREAT = "Great"
    DOMINANT = "Dominant"
    HEGEMON = "Hegemon"


class Momentum(StrEnum):
    ASCENDING = "Ascending"
    STABLE = "Stable"
    DECLINING = "Declining"


class EndgamePhase(StrEnum):
    OPEN = "OPEN"
    ENDGAME = "ENDGAME"
    FINALIZED = "FINALIZED"


@dataclass(frozen=True)
class TerritorySpec:
    territory_id: str
    region: str
    capital: bool
    base_production: Mapping[str, int]
    strategic_value: int
    fortification: int = 0

    def __post_init__(self) -> None:
        if not self.territory_id or not self.region:
            raise ValueError("territory identity required")
        if set(self.base_production) - set(RESOURCES):
            raise ValueError("unknown production resource")
        if any((not isinstance(v, int) or v < 0) for v in self.base_production.values()):
            raise ValueError("invalid production")
        if self.strategic_value < 0 or self.fortification < 0:
            raise ValueError("negative territory value")


@dataclass(frozen=True)
class WorldGraph:
    seed: str
    territories: Mapping[str, TerritorySpec]
    edges: frozenset[tuple[str, str]]

    def __post_init__(self) -> None:
        if not self.seed:
            raise ValueError("map seed required")
        for a, b in self.edges:
            if a == b or a not in self.territories or b not in self.territories:
                raise ValueError("invalid world edge")

    def adjacent(self, a: str, b: str) -> bool:
        return (a, b) in self.edges or (b, a) in self.edges


def derive_power(balances: Mapping[str, int]) -> int:
    unknown = set(balances) - set(RESOURCES)
    if unknown:
        raise ValueError("POWER derives only from Season 0 resources")
    values = []
    for resource in RESOURCES:
        value = balances.get(resource, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("invalid resource balance")
        values.append(value)
    return sum(values)


@dataclass(frozen=True)
class Treaty:
    treaty_id: str
    treaty_type: TreatyType
    participants: tuple[str, ...]
    starts_at: int
    ends_at: int
    signed_by: frozenset[str] = frozenset()
    state: TreatyState = TreatyState.PROPOSED
    objective: str | None = None
    exit_effective_at: int | None = None
    breached_by: str | None = None

    def __post_init__(self) -> None:
        if len(set(self.participants)) != len(self.participants) or len(self.participants) < 2:
            raise ValueError("treaty requires distinct participants")
        if self.ends_at <= self.starts_at:
            raise ValueError("invalid treaty window")
        if not self.signed_by.issubset(set(self.participants)):
            raise ValueError("nonparticipant signature")
        if self.treaty_type == TreatyType.COALITION and len(self.participants) < 3:
            raise ValueError("coalition requires at least three participants")

    def activate(self, now: int) -> "Treaty":
        if self.state != TreatyState.PROPOSED or self.signed_by != frozenset(self.participants):
            raise ValueError("treaty not fully signed")
        if now < self.starts_at or now >= self.ends_at:
            raise ValueError("outside treaty activation window")
        return _replace_treaty(self, state=TreatyState.ACTIVE)

    def request_exit(self, actor: str, effective_at: int) -> "Treaty":
        if self.state != TreatyState.ACTIVE or actor not in self.participants:
            raise ValueError("active participant required")
        if effective_at >= self.ends_at:
            return _replace_treaty(self, state=TreatyState.EXPIRED, exit_effective_at=effective_at)
        return _replace_treaty(self, state=TreatyState.EXITING, exit_effective_at=effective_at)

    def breach(self, actor: str, now: int) -> "Treaty":
        if self.state not in {TreatyState.ACTIVE, TreatyState.EXITING}:
            raise ValueError("treaty is not breachable")
        if actor not in self.participants or now >= self.ends_at:
            raise ValueError("invalid treaty breach")
        return _replace_treaty(self, state=TreatyState.BREACHED, breached_by=actor)

    def effective(self, now: int) -> bool:
        if self.state == TreatyState.ACTIVE:
            return self.starts_at <= now < self.ends_at
        if self.state == TreatyState.EXITING:
            return self.starts_at <= now < min(self.ends_at, self.exit_effective_at or self.ends_at)
        return False


def _replace_treaty(t: Treaty, **changes) -> Treaty:
    values = {name: getattr(t, name) for name in t.__dataclass_fields__}
    values.update(changes)
    return Treaty(**values)


def nap_blocks_attack(attacker: str, defender: str, treaties: Sequence[Treaty], now: int) -> bool:
    pair = {attacker, defender}
    return any(t.treaty_type == TreatyType.NAP and pair.issubset(set(t.participants)) and t.effective(now)
               for t in treaties)


@dataclass(frozen=True)
class TradeOffer:
    trade_id: str
    proposer: str
    counterparty: str
    offered: Mapping[str, int]
    requested: Mapping[str, int]
    expires_at: int

    def __post_init__(self) -> None:
        if self.proposer == self.counterparty:
            raise ValueError("self trade forbidden")
        for leg in (self.offered, self.requested):
            if not leg or set(leg) - set(RESOURCES):
                raise ValueError("trade supports only Season 0 resources")
            if any((not isinstance(v, int) or isinstance(v, bool) or v <= 0) for v in leg.values()):
                raise ValueError("invalid trade amount")


def settle_trade(offer: TradeOffer, balances: Mapping[str, Mapping[str, int]], now: int) -> dict[str, dict[str, int]]:
    if now >= offer.expires_at:
        raise ValueError("trade expired")
    if offer.proposer not in balances or offer.counterparty not in balances:
        raise ValueError("unknown trade participant")
    result = {empire: {r: int(vals.get(r, 0)) for r in RESOURCES} for empire, vals in balances.items()}
    before = {r: sum(result[e][r] for e in result) for r in RESOURCES}
    for resource, amount in offer.offered.items():
        if result[offer.proposer][resource] < amount:
            raise ValueError("insufficient proposer balance")
    for resource, amount in offer.requested.items():
        if result[offer.counterparty][resource] < amount:
            raise ValueError("insufficient counterparty balance")
    for resource, amount in offer.offered.items():
        result[offer.proposer][resource] -= amount
        result[offer.counterparty][resource] += amount
    for resource, amount in offer.requested.items():
        result[offer.counterparty][resource] -= amount
        result[offer.proposer][resource] += amount
    after = {r: sum(result[e][r] for e in result) for r in RESOURCES}
    if before != after:
        raise RuntimeError("trade conservation failure")
    return result


@dataclass(frozen=True)
class IntelSnapshot:
    observed_at: int
    fresh_until: int
    stale_at: int
    payload: Mapping[str, object]

    def freshness(self, now: int) -> IntelFreshness:
        if now < self.fresh_until:
            return IntelFreshness.FRESH
        if now < self.stale_at:
            return IntelFreshness.AGING
        return IntelFreshness.STALE


def fog_safe_projection(*, territory_id: str, owner: str | None, capital: bool,
                        standing: Standing, public_conflicts: Sequence[str] = (),
                        public_treaties: Sequence[str] = (), intel: IntelSnapshot | None = None,
                        now: int = 0) -> dict[str, object]:
    view: dict[str, object] = {"territory_id": territory_id, "owner": owner, "capital": capital,
        "standing": standing.value, "public_conflicts": list(public_conflicts),
        "public_treaties": list(public_treaties)}
    if intel is not None:
        view["intel"] = {"freshness": intel.freshness(now).value, "observed_at": intel.observed_at,
                         "payload": dict(intel.payload)}
    return view


STANDING_ORDER = (Standing.DOMAIN, Standing.REGIONAL, Standing.MAJOR,
                  Standing.GREAT, Standing.DOMINANT, Standing.HEGEMON)


@dataclass(frozen=True)
class StandingInputs:
    power: int
    territory_value: int
    production: int
    fortification: int
    strategic_capacity: int

    def __post_init__(self) -> None:
        if min(self.power, self.territory_value, self.production, self.fortification,
               self.strategic_capacity) < 0:
            raise ValueError("standing inputs must be nonnegative")


def standing_score(inputs: StandingInputs, weights: Mapping[str, int]) -> int:
    names = ("power", "territory_value", "production", "fortification", "strategic_capacity")
    if set(weights) != set(names) or any((not isinstance(weights[n], int) or weights[n] < 0) for n in names):
        raise ValueError("complete nonnegative standing weights required")
    return sum(getattr(inputs, name) * weights[name] for name in names)


def assign_standings(scores: Mapping[str, int], cutoffs: Sequence[int], hegemon_id: str | None = None) -> dict[str, Standing]:
    if len(cutoffs) != 4 or list(cutoffs) != sorted(cutoffs):
        raise ValueError("four ordered non-hegemon cutoffs required")
    if hegemon_id is not None and hegemon_id not in scores:
        raise ValueError("hegemon must be present")
    result: dict[str, Standing] = {}
    for empire, score in scores.items():
        if score < 0:
            raise ValueError("negative standing score")
        if empire == hegemon_id:
            result[empire] = Standing.HEGEMON
            continue
        level = Standing.DOMAIN
        for cutoff, candidate in zip(cutoffs, (Standing.REGIONAL, Standing.MAJOR, Standing.GREAT, Standing.DOMINANT)):
            if score >= cutoff:
                level = candidate
        result[empire] = level
    return result


def momentum(current: int, prior: int, deadband: int) -> Momentum:
    if deadband < 0:
        raise ValueError("negative momentum deadband")
    delta = current - prior
    if delta > deadband:
        return Momentum.ASCENDING
    if delta < -deadband:
        return Momentum.DECLINING
    return Momentum.STABLE


@dataclass(frozen=True)
class VictoryInputs:
    territory_value: int
    power: int
    production: int
    objective_points: int
    hegemon_epochs: int

    def __post_init__(self) -> None:
        if min(self.territory_value, self.power, self.production, self.objective_points,
               self.hegemon_epochs) < 0:
            raise ValueError("victory inputs must be nonnegative")


def season_score(inputs: VictoryInputs, weights: Mapping[str, int]) -> int:
    names = ("territory_value", "power", "production", "objective_points", "hegemon_epochs")
    if set(weights) != set(names) or any((not isinstance(weights[n], int) or weights[n] < 0) for n in names):
        raise ValueError("complete nonnegative victory weights required")
    return sum(getattr(inputs, name) * weights[name] for name in names)


def can_transfer_territory(kind: str, target: TerritorySpec) -> bool:
    if target.capital:
        return False
    return kind.upper() == "SIEGE"


def validate_defense_submission(*, attack_created_at: int, defense_deadline: int,
                                submitted_at: int, alliance_eligible_at_creation: bool) -> bool:
    if defense_deadline <= attack_created_at:
        raise ValueError("invalid defense window")
    if submitted_at >= defense_deadline:
        return False
    return alliance_eligible_at_creation
