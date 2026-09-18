import json
import sqlite3
import time
from pathlib import Path

import pytest

from flop_empires.final_artifact import build_final_artifact
from flop_empires.readiness import readiness_report
from flop_empires.season_insights import descriptive_scoreboard, replay_timeline
from flop_empires.season_verifier import verify_season_artifacts
from flop_empires.store import Store
from flop_empires.world_bootstrap import bootstrap_frozen_world

ROOT=Path(__file__).parents[1]
MANIFEST=ROOT/'season'/'SEASON-0-MANIFEST-FREEZE-V2-CANDIDATE.json'
ACTIVATION=ROOT/'season'/'SEASON-0-ACTIVATION-v1.json'
WORLD=ROOT/'season'/'world-season-0-v1.json'
MANIFEST_JSON=json.loads(MANIFEST.read_text())


def prepared_store(path):
    s=Store(path)
    s.conn.execute("INSERT OR REPLACE INTO config VALUES('activation_manifest_hash',?)",(MANIFEST_JSON['manifest_hash'],))
    bootstrap_frozen_world(s,WORLD,expected_hash=MANIFEST_JSON['world_graph_hash'],initial_balances=MANIFEST_JSON['initial_balances'],now=1)
    return s

def test_readonly_store_cannot_write(tmp_path):
    path=tmp_path/'db.sqlite3'; s=Store(path); s.conn.execute("INSERT INTO config VALUES('x','1')"); s.close()
    ro=Store(path,readonly=True)
    assert ro.one("SELECT value FROM config WHERE key='x'")[0]=='1'
    with pytest.raises(sqlite3.OperationalError): ro.conn.execute("INSERT INTO config VALUES('y','2')")
    ro.close()


def test_verifier_and_readiness_on_prepared_world(tmp_path):
    path=tmp_path/'season.sqlite3'; s=prepared_store(path)
    result=verify_season_artifacts(s,MANIFEST,ACTIVATION,WORLD)
    assert result['ok'] is True and result['event_count']==0
    status=tmp_path/'runner.json'; status.write_text(json.dumps({'runner':'RUNNING','heartbeat':int(time.time())}))
    ready=readiness_report(s,MANIFEST,ACTIVATION,WORLD,status)
    assert ready['ok'] is True
    s.close()


def test_scoreboard_replay_and_final_artifact_are_explicitly_non_authoritative(tmp_path):
    s=prepared_store(tmp_path/'season.sqlite3')
    board=descriptive_scoreboard(s,WORLD)
    assert len(board['rows'])==16 and board['authoritative'] is False
    assert replay_timeline(s)['events']==[]
    final=build_final_artifact(s,MANIFEST,ACTIVATION,WORLD)
    assert final['authoritative_winner'] is None
    assert final['verification']['ok'] is True
    s.close()

RECOVERY=ROOT/'season'/'SEASON-0-RECOVERY-v1.json'
LAUNCH=ROOT/'season'/'SEASON-0-LAUNCH-AUTHORIZATION-v1.json'

def test_final_artifact_reports_recovery_lineage_without_implying_launch(tmp_path):
    s=prepared_store(tmp_path/'season.sqlite3')
    final=build_final_artifact(s,MANIFEST,ACTIVATION,WORLD,RECOVERY,LAUNCH)
    assert final['verification']['recovery_active'] is True
    assert final['verification']['launch_authorized'] is False
    assert final['effective_binding_id']==json.loads(RECOVERY.read_text())['recovery_id']
    assert final['lineage']['activation_id']==json.loads(ACTIVATION.read_text())['activation_id']
    assert final['lineage']['recovery_id']==json.loads(RECOVERY.read_text())['recovery_id']
    assert final['lineage']['launch_id'] is None
    s.close()
