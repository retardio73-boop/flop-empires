from __future__ import annotations


def raid_reward(cost: int, defender_available: int) -> int:
    """Strictly bounded below cost (zero for a one-unit commitment)."""
    return min(defender_available, cost // 2)


def attack_succeeds(attack: int, defense: int) -> bool:
    return attack > defense  # ties belong to defender
