from pathlib import Path

import pytest

from flop_empires.staging import StagingManifest, StagingMode


def test_live_staging_manifest_hash_and_guards():
    manifest=StagingManifest.load(Path(__file__).parents[1]/"season/staging-live.json")
    assert manifest.environment=="staging" and manifest.mode==StagingMode.WRITE
    assert manifest.mailbox.startswith("staging-flop-empires-")
    assert manifest.events_room.startswith("staging-flop-empires-")


def test_manifest_hash_tampering_fails(tmp_path):
    source=(Path(__file__).parents[1]/"season/staging-live.json").read_text()
    path=tmp_path/"bad.json"; path.write_text(source.replace("season-minus-one","season-minus-two"))
    with pytest.raises(ValueError,match="hash mismatch"): StagingManifest.load(path)
