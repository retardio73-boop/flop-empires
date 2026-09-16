from __future__ import annotations

import json
from pathlib import Path

EMPIRES = 16
TERRITORIES = 64
SEED = "flop-empires-season-0-world-v1"


def territory_id(index: int) -> str:
    return f"s0-n{index:02d}"


def empire_id(index: int) -> str:
    return f"season0-e{index + 1:02d}"


def build_world() -> dict:
    territories=[]
    for i in range(TERRITORIES):
        capital=i < EMPIRES
        strategic=(not capital) and i % 7 == 0
        territories.append({
            "id": territory_id(i),
            "owner": empire_id(i % EMPIRES),
            "capital": capital,
            "region": f"r{(i // 8) + 1}",
            "base_production": {"ENGINEERING": 20, "KNOWLEDGE": 0, "INFLUENCE": 0},
            "strategic_value": 3 if strategic else 1,
            "fortification": 0,
        })
    edges=set()
    for i in range(TERRITORIES):
        for offset in (1, 2):
            a, b = territory_id(i), territory_id((i + offset) % TERRITORIES)
            edges.add(tuple(sorted((a, b))))
    return {
        "schema": "flop-empires-world-v1",
        "seed": SEED,
        "empires": EMPIRES,
        "territories": territories,
        "edges": [list(edge) for edge in sorted(edges)],
    }


def write_world(path: Path) -> None:
    path.write_text(json.dumps(build_world(), separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_world(Path("season/world-season-0-v1.json"))
