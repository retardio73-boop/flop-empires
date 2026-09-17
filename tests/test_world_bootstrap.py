import json
from pathlib import Path

from flop_empires.canonical import sha256
from flop_empires.store import Store
from flop_empires.world_bootstrap import bootstrap_frozen_world

ROOT=Path(__file__).parents[1]


def test_bootstrap_frozen_world_materializes_exact_fixture(tmp_path):
    store=Store(tmp_path/'world.db')
    world_path=ROOT/'season/world-season-0-v1.json'
    world=json.loads(world_path.read_text(encoding='utf-8'))
    result=bootstrap_frozen_world(store,world_path,expected_hash=sha256(world),initial_balances={'ENGINEERING':100,'KNOWLEDGE':0,'INFLUENCE':0},now=1)
    assert result['empires']==16 and result['territories']==64 and result['edges']==128
    assert store.one('SELECT COUNT(*) FROM empires')[0]==16
    assert store.one('SELECT COUNT(*) FROM territories')[0]==64
    assert store.one('SELECT COUNT(*) FROM territory_edges')[0]==128
