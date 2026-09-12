from __future__ import annotations

from .store import Store


def adjacent(store: Store, a: str, b: str) -> bool:
    x, y = sorted((a, b))
    return store.one("SELECT 1 FROM territory_edges WHERE a=? AND b=?", (x, y)) is not None


def add_edge(store: Store, a: str, b: str) -> None:
    if a == b:
        raise ValueError("self edge forbidden")
    x, y = sorted((a, b))
    store.conn.execute("INSERT INTO territory_edges(a,b) VALUES(?,?)", (x, y))
