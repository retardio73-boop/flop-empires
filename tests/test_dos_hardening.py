from dataclasses import replace

import pytest
import httpx

from flop_empires.canonical import bytes_
from flop_empires.engine import Engine
from flop_empires.identity import EphemeralSigner
from flop_empires.models import SignedRecord
from flop_empires.store import Store
from flop_empires.technocore import (ErrorDisposition,MailboxItem,TechnocoreIngestor,
    ExpectedHostileInput,error_disposition,signed_record_body)


def record(record_id,signer,payload,seq,valid=True):
    unsigned=SignedRecord(record_id,signer.did,payload,"",seq=seq,ts=seq)
    return replace(unsigned,signature=signer.sign(bytes_(signed_record_body(unsigned))) if valid else "AAAA")


def test_expected_hostile_batch_advances_and_valid_next_action_executes():
    ref=EphemeralSigner(b"r"*32); allowed=EphemeralSigner(b"a"*32); outsider=EphemeralSigner(b"o"*32)
    store=Store(); engine=Engine.for_test(store,ref.did,ref,clock=lambda:100)
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
    assert error_disposition(ExpectedHostileInput("UNKNOWN_DID"))==ErrorDisposition.REJECT_AND_CONTINUE
    assert error_disposition(httpx.ReadTimeout("timeout"))==ErrorDisposition.RETRY_TRANSIENT
    assert error_disposition(TimeoutError())==ErrorDisposition.HALT_INTEGRITY_FAILURE


def test_event_chain_corruption_halts_new_engine():
    ref=EphemeralSigner(b"r"*32); actor=EphemeralSigner(b"a"*32); store=Store()
    engine=Engine.for_test(store,ref.did,ref,clock=lambda:100)
    engine.execute({"action":"register_actor","actor_did":actor.did,"request_id":"r","payload":{}})
    store.conn.execute("UPDATE events SET details_json='{}' WHERE seq=1")
    with pytest.raises(RuntimeError,match="invalid historical event chain"):
        Engine.for_test(store,ref.did,ref)


def test_valid_referee_frames_are_silently_skipped_in_duplex_room():
    ref=EphemeralSigner(b"q"*32); player=EphemeralSigner(b"p"*32)
    store=Store(); engine=Engine.for_test(store,ref.did,ref,clock=lambda:100)
    ingestor=TechnocoreIngestor(store,engine,"room",expected_season_id="season-b")
    referee_output=record("ref-output",ref,{"receipt":"not-a-command"},1)
    command={"action":"register_actor","actor_did":player.did,"request_id":"player","payload":{}}
    player_record=record("player",player,{"season_id":"season-b","command":command},2)
    class Source:
        def current_cursor(self): return "c0"
        def records_after(self,cursor): return [MailboxItem(referee_output,"c1"),MailboxItem(player_record,"c2")]
    receipts=ingestor.poll(Source())
    assert len(receipts)==1 and receipts[0].accepted
    assert store.one("SELECT COUNT(*) FROM technocore_rejections")[0]==0
    assert store.one("SELECT cursor FROM technocore_state")[0]=="c2"

def test_forged_referee_frame_is_not_silently_skipped():
    ref=EphemeralSigner(b"w"*32); store=Store(); engine=Engine.for_test(store,ref.did,ref,clock=lambda:100)
    ingestor=TechnocoreIngestor(store,engine,"room",expected_season_id="season-b")
    forged=record("forged",ref,{"receipt":"fake"},1,False)
    class Source:
        def current_cursor(self): return "c0"
        def records_after(self,cursor): return [MailboxItem(forged,"c1")]
    assert ingestor.poll(Source())==[]
    assert store.one("SELECT code FROM technocore_rejections WHERE record_id='forged'")[0]=="INVALID_SIGNATURE"
