from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from .canonical import sha256


@dataclass(frozen=True)
class EconomicRulesV02:
    version: str
    linear_threshold: int
    engineering_weight_bp: int
    knowledge_weight_bp: int
    influence_weight_bp: int
    overextension_penalty_bp: int
    territory_benefit_units: int
    territory_upkeep_units: int
    fortification_upkeep_divisor: int
    fatigue_step_bp: int
    fatigue_max_bp: int
    fatigue_window_actions: int
    stockpile_soft_limit: int
    stockpile_carry_cost_bp: int
    defender_modifier_bp: int
    yield_epoch_divisor: int

    @classmethod
    def from_manifest(cls, manifest: dict[str, Any]) -> "EconomicRulesV02":
        if manifest.get("economic_rules_version") != "technical-yield-v0.2":
            raise ValueError("manifest does not select technical-yield-v0.2")
        rules = cls(version=manifest["economic_rules_version"], **manifest["economic_parameters"])
        rules.validate()
        return rules

    def validate(self) -> None:
        values = asdict(self); values.pop("version")
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in values.values()):
            raise ValueError("economic parameters must be non-negative integers")
        if self.linear_threshold < 1 or self.fortification_upkeep_divisor < 1 or self.yield_epoch_divisor < 1:
            raise ValueError("invalid economic divisor/threshold")
        if self.engineering_weight_bp + self.knowledge_weight_bp + self.influence_weight_bp != 10_000:
            raise ValueError("resource weights must total 10000 basis points")
        if self.defender_modifier_bp < 1:
            raise ValueError("defender modifier must be positive")

    @property
    def manifest_hash(self) -> str:
        return sha256(asdict(self))

    def spendable_total(self, prestige: int) -> int:
        """Linear through T, then T + floor(sqrt((P-T)*T))."""
        if prestige < 0:
            raise ValueError("prestige cannot be negative")
        if prestige <= self.linear_threshold:
            return prestige
        return self.linear_threshold + math.isqrt((prestige - self.linear_threshold) * self.linear_threshold)

    def allocate(self, prestige: int) -> dict[str, int]:
        total = self.spendable_total(prestige)
        engineering = total * self.engineering_weight_bp // 10_000
        knowledge = total * self.knowledge_weight_bp // 10_000
        return {"ENGINEERING": engineering, "KNOWLEDGE": knowledge,
            "INFLUENCE": total - engineering - knowledge}

    def epoch_allocation(self, prestige: int) -> dict[str,int]:
        """Per-epoch spendable accrual derived from the manifest curve."""
        allocation=self.allocate(prestige)
        return {resource:value//self.yield_epoch_divisor for resource,value in allocation.items()}

    def overextension_efficiency_bp(self, noncapital_territories: int) -> int:
        extra = max(0, noncapital_territories - 1)
        return 10_000 * 10_000 // (10_000 + extra * self.overextension_penalty_bp)

    def territory_benefit(self, noncapital_territories: int) -> int:
        raw = max(0, noncapital_territories) * self.territory_benefit_units
        return raw * self.overextension_efficiency_bp(noncapital_territories) // 10_000

    def upkeep(self, available_engineering: int, noncapital_territories: int,
               fortification_power: int) -> int:
        return self.upkeep_components(available_engineering, noncapital_territories,
            fortification_power)["total"]

    def upkeep_components(self, available_engineering: int, noncapital_territories: int,
                          fortification_power: int) -> dict[str, int]:
        if min(available_engineering, noncapital_territories, fortification_power) < 0:
            raise ValueError("upkeep inputs cannot be negative")
        territorial = noncapital_territories * self.territory_upkeep_units
        fortified = fortification_power // self.fortification_upkeep_divisor
        excess = max(0, available_engineering - self.stockpile_soft_limit)
        carrying = excess * self.stockpile_carry_cost_bp // 10_000
        total = min(available_engineering, territorial + fortified + carrying)
        # Charge deterministic components in protocol order without exceeding balance.
        charged_territorial = min(total, territorial)
        charged_fortified = min(total - charged_territorial, fortified)
        charged_carrying = total - charged_territorial - charged_fortified
        return {"territory_upkeep":charged_territorial,"fortification_upkeep":charged_fortified,
            "stockpile_cost":charged_carrying,"total":total}

    def epoch_attribution(self, prestige: int, available_engineering: int,
                          noncapital_territories: int, fortification_power: int, *,
                          effective_prestige: int | None = None) -> dict[str, Any]:
        """Single normative epoch formula shared by engine and simulations."""
        effective=prestige if effective_prestige is None else effective_prestige
        if effective<0 or effective>prestige: raise ValueError("effective prestige out of range")
        spendable = self.spendable_total(effective)
        allocation = self.epoch_allocation(effective)
        territory_raw = noncapital_territories * self.territory_benefit_units
        territory_effective = self.territory_benefit(noncapital_territories)
        before_cost = available_engineering + allocation["ENGINEERING"] + territory_effective
        costs = self.upkeep_components(before_cost,noncapital_territories,fortification_power)
        result={"raw_contribution":prestige,"prestige":prestige,
            "effective_spendable_yield":spendable,
            "gross_spendable_yield":sum(allocation.values()),
            "diminishing_return_loss":max(0,prestige-spendable),
            "allocation":allocation,"territory_production_raw":territory_raw,
            "territory_production":territory_effective,
            "overextension_penalty":territory_raw-territory_effective,
            "upkeep":costs["territory_upkeep"]+costs["fortification_upkeep"],
            "stockpile_cost":costs["stockpile_cost"],"total_cost":costs["total"]}
        if effective_prestige is not None and effective!=prestige:
            result["effective_contribution_for_spendable"]=effective
            result["bootstrap_excluded_or_discounted"]=prestige-effective
        return result

    def offensive_cost(self, base_cost: int, recent_successes: int) -> int:
        fatigue = min(self.fatigue_max_bp, max(0, recent_successes) * self.fatigue_step_bp)
        return (base_cost * (10_000 + fatigue) + 9_999) // 10_000

    def defense_power(self, engineering_defense: int, fortification_power: int,
                      eligible_alliance_support: int) -> int:
        if min(engineering_defense, fortification_power, eligible_alliance_support) < 0:
            raise ValueError("defense inputs cannot be negative")
        modified = engineering_defense * self.defender_modifier_bp // 10_000
        return modified + fortification_power + eligible_alliance_support


def prestige_from_clusters(clusters: list[dict[str, Any]]) -> int:
    """Cumulative verified value: visible, non-transferable, and never spendable."""
    seen: set[str] = set(); total = 0
    for row in sorted(clusters, key=lambda x: str(x["id"])):
        cluster = str(row["id"])
        if cluster in seen or row.get("self_owned") or not row.get("verified", True):
            continue
        seen.add(cluster)
        total += max(0, int(row["base_units"]))
    return total


def economic_leaderboard(store, rules: EconomicRulesV02) -> list[dict[str, Any]]:
    result = []
    for empire in store.conn.execute("SELECT id FROM empires ORDER BY id"):
        clusters = [dict(r) | {"verified": True} for r in store.conn.execute(
            "SELECT id,base_units,self_owned FROM contribution_clusters WHERE empire_id=? ORDER BY id",
            (empire["id"],))]
        prestige = prestige_from_clusters(clusters)
        result.append({"empire_id": empire["id"], "prestige": prestige,
            "spendable_yield": rules.allocate(prestige)})
    return sorted(result, key=lambda x: (-x["prestige"], x["empire_id"]))


def prestige_leaderboard(store) -> list[dict[str,Any]]:
    rows=[{"empire_id":r["empire_id"],"prestige":r["prestige"]}
          for r in store.conn.execute("SELECT empire_id,prestige FROM empire_economy")]
    return sorted(rows,key=lambda x:(-x["prestige"],x["empire_id"]))


def strategic_power_leaderboard(store,rules: EconomicRulesV02)->list[dict[str,Any]]:
    rows=[]
    for economy in store.conn.execute("SELECT * FROM empire_economy ORDER BY empire_id"):
        empire=economy["empire_id"]
        noncap=store.one("SELECT COUNT(*) FROM territories WHERE owner_empire_id=? AND is_capital=0",(empire,))[0]
        fort=store.one("SELECT COALESCE(SUM(fortification),0) FROM territories WHERE owner_empire_id=?",(empire,))[0]
        power=economy["engineering"]+economy["knowledge"]+economy["influence"]+fort+rules.territory_benefit(noncap)
        rows.append({"empire_id":empire,"strategic_power":power,"territories":noncap+1,
            "engineering":economy["engineering"],"fortification":fort})
    return sorted(rows,key=lambda x:(-x["strategic_power"],x["empire_id"]))
