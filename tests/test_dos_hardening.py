from dataclasses import replace

import pytest

from flop_empires.canonical import bytes_
from flop_empires.engine import Engine
from flop_empires.identity import EphemeralSigner
from flop_empires.models import SignedRecord
from flop_empires.store import Store
from flop_empires.technocore import (ErrorDisposition,MailboxItem,TechnocoreIngestor,
    signed_record_body)


def record(record_id,signer,payload,seq,valid=True):
    unsigned=SignedRecord(record_id,signer.did,payload,"",seq=seq,ts=seq)
    return replace(unsigned,signature=signer.sign(bytes_(signed_record_body(unsigned))) if valid else "AAAA")


def test_expected_hostile_batch_advances_and_valid_next_action_executes():
    ref=EphemeralSigner(b"r"*32); allowed=EphemeralSigner(b"a"*32); outsider=EphemeralSigner(b"o"*32)
    store=Store(); engine=Engine(store,ref.did,ref,clock=lambda:100)
    ingestor=TechnocoreIngestor(store,engine,"room",allowed_dids=(allowed.did,),expected_season_id="season-b")
    good={"action":"register_actor","actor_did":allowed.did,"request_id":"good","payload":{}}
    items=[
        record("bad-signature",allowed,{"season_id":"season-b","command":good},1,False),
        record("outsider",outsider,{"season_id":"season-b","command":{**good,"actor_did":outsider.did,"request_id":"out"}},2),
        record("malformed",allowed,{"season_id":"season-b","command":{"actor_did":allowed.did}},3),
        record("wrong-season",allowed,{"season_id":"other","command":good},4),
        record("valid",allowed,{"season_id":"season-b","command":good},5)]
    class Source:
        def current_cursor(self): return "c0"
        def records_after(self,cursor): return [MailboxItem(item,f"c{i}") for i,item in enumerate(items,1)]
    receipts=ingestor.poll(Source())
    assert len(receipts)==1 and receipts[0].accepted
    assert store.one("SELECT COUNT(*) FROM technocore_rejections")[0]==4
    assert store.one("SELECT cursor FROM technocore_state")[0]=="c5"
    assert store.one("SELECT 1 FROM actors WHERE did=?",(allowed.did,))


def test_error_taxonomy_is_explicit():
    assert set(ErrorDisposition)=={ErrorDisposition.REJECT_AND_CONTINUE,
        ErrorDisposition.RETRY_TRANSIENT,ErrorDisposition.HALT_INTEGRITY_FAILURE}


def test_event_chain_corruption_halts_new_engine():
    ref=EphemeralSigner(b"r"*32); actor=EphemeralSigner(b"a"*32); store=Store()
    engine=Engine(store,ref.did,ref,clock=lambda:100)
    engine.execute({"action":"register_actor","actor_did":actor.did,"request_id":"r","payload":{}})
    store.conn.execute("UPDATE events SET details_json='{}' WHERE seq=1")
    with pytest.raises(RuntimeError,match="invalid historical event chain"):
        Engine(store,ref.did,ref)
