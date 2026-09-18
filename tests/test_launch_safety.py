import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from flop_empires.activation import ActivationError, ActivationRecord, sign_activation_payload
from flop_empires.canonical import sha256
from flop_empires.identity import EphemeralSigner
from flop_empires.manifest import SeasonZeroFreezeV2CandidateManifest
from flop_empires.production import NamespaceAbort, NamespacePreflight, ProductionRuntime
from flop_empires.store import Store

ROOT=Path(__file__).parents[1]


def manifest_for(signer):
    value=json.loads((ROOT/'season/SEASON-0-MANIFEST-FREEZE-V2-CANDIDATE.json').read_text())
    value=deepcopy(value); value['referee_did']=signer.did
    unsigned=dict(value); unsigned.pop('manifest_hash',None)
    value['manifest_hash']=sha256(unsigned)
    return SeasonZeroFreezeV2CandidateManifest(value)
def activation_for(manifest, signer):
    p={
        'version':'flop-empires-activation-v1','activation_id':'a1','season_id':'season-0',
        'frozen_manifest_hash':manifest.manifest_hash,'referee_did':signer.did,
        'actions_namespace':'mb-p-flop-empires-s0-0123456789abcdef-actions',
        'events_namespace':'mb-p-flop-empires-s0-0123456789abcdef-events',
        'registration_open':90,'registration_close':110,'season_start':120,
        'season_end':120+manifest.intended_duration_seconds,'issued_at':80,
        'activation_status':'AUTHORIZE_SEASON'}
    return ActivationRecord.verify(sign_activation_payload(p,signer),manifest)


def pristine_client(change_on_call=None):
    calls={'n':0}
    def handler(request):
        calls['n']+=1
        body={'generation':0,'messages':[]}
        if change_on_call and calls['n']>=change_on_call:
            body={'generation':1,'messages':[{'seq':1}]}
        return httpx.Response(200,json=body,request=request)
    return httpx.Client(transport=httpx.MockTransport(handler)),calls
def test_activation_rejects_bad_signature_and_rule_fields():
    signer=EphemeralSigner(b'a'*32); manifest=manifest_for(signer)
    record=activation_for(manifest,signer)
    bad=dict(record.value); bad['signature']='x'
    with pytest.raises(ActivationError): ActivationRecord.verify(bad,manifest)
    bad=dict(record.value); bad['economic_parameters']={}
    with pytest.raises(ActivationError): ActivationRecord.verify(bad,manifest)


def test_namespace_preflight_requires_exact_pristine_shape():
    signer=EphemeralSigner(b'b'*32); manifest=manifest_for(signer); record=activation_for(manifest,signer)
    client,_=pristine_client()
    evidence=NamespacePreflight(client,manifest).check_pair(record.context().actions_namespace,record.context().events_namespace)
    assert evidence.actions_namespace==record.context().actions_namespace
    client.close()


def test_runtime_aborts_if_namespace_changes_between_checks():
    signer=EphemeralSigner(b'c'*32); manifest=manifest_for(signer); record=activation_for(manifest,signer)
    client,_=pristine_client(change_on_call=3)
    evidence=NamespacePreflight(client,manifest).check_pair(record.context().actions_namespace,record.context().events_namespace)
    with pytest.raises(NamespaceAbort):
        ProductionRuntime.from_verified_activation(manifest,record,evidence,Store(),signer,client,clock=lambda:100)
    client.close()
def test_verified_runtime_binds_exact_rooms_and_referee():
    signer=EphemeralSigner(b'd'*32); manifest=manifest_for(signer); record=activation_for(manifest,signer)
    client,calls=pristine_client()
    ctx=record.context(); evidence=NamespacePreflight(client,manifest).check_pair(ctx.actions_namespace,ctx.events_namespace)
    store=Store(); runtime=ProductionRuntime.from_verified_activation(manifest,record,evidence,store,signer,client,clock=lambda:100)
    assert runtime.binding.manifest_hash==manifest.manifest_hash
    assert runtime.actions.room==ctx.actions_namespace and runtime.events.room==ctx.events_namespace
    cursor=store.one("SELECT cursor FROM technocore_state WHERE mailbox=?",(ctx.actions_namespace,))[0]
    assert json.loads(cursor)=={'generation':0,'seq':0}
    assert calls['n']==4
    client.close()


def test_runtime_refuses_before_registration_window():
    signer=EphemeralSigner(b'e'*32); manifest=manifest_for(signer); record=activation_for(manifest,signer)
    client,_=pristine_client(); ctx=record.context()
    evidence=NamespacePreflight(client,manifest).check_pair(ctx.actions_namespace,ctx.events_namespace)
    with pytest.raises(Exception,match='ACTIVATION_NOT_EFFECTIVE'):
        ProductionRuntime.from_verified_activation(manifest,record,evidence,Store(),signer,client,clock=lambda:89)
    client.close()
def test_restart_uses_persisted_binding_without_requiring_pristine_rooms():
    signer=EphemeralSigner(b'f'*32); manifest=manifest_for(signer); record=activation_for(manifest,signer)
    store=Store(); client,_=pristine_client(); ctx=record.context()
    first=NamespacePreflight(client,manifest).check_pair(ctx.actions_namespace,ctx.events_namespace)
    ProductionRuntime.from_verified_activation(manifest,record,first,store,signer,client,clock=lambda:100)
    client.close()
    dirty,_=pristine_client(change_on_call=1)
    runtime=ProductionRuntime.from_verified_activation(manifest,record,None,store,signer,dirty,clock=lambda:100)
    assert runtime.binding.context.activation_id=='a1'
    dirty.close()


def test_restart_rejects_different_activation_binding():
    signer=EphemeralSigner(b'g'*32); manifest=manifest_for(signer); record=activation_for(manifest,signer)
    store=Store(); client,_=pristine_client(); ctx=record.context()
    first=NamespacePreflight(client,manifest).check_pair(ctx.actions_namespace,ctx.events_namespace)
    ProductionRuntime.from_verified_activation(manifest,record,first,store,signer,client,clock=lambda:100)
    other=dict(record.value); other['activation_id']='a2'; other.pop('signature')
    other=ActivationRecord.verify(sign_activation_payload(other,signer),manifest)
    with pytest.raises(RuntimeError,match='PRODUCTION_BINDING_MISMATCH'):
        ProductionRuntime.from_verified_activation(manifest,other,None,store,signer,client,clock=lambda:100)
    client.close()

from flop_empires.launch import LaunchAuthorization, LaunchAuthorizationError, sign_launch_payload

def launch_for(manifest, signer, binding, *, effective_start=130):
    payload={
        'version':'flop-empires-launch-authorization-v1','launch_id':'launch-test',
        'season_id':binding.season_id,'binding_id':binding.activation_id,
        'frozen_manifest_hash':manifest.manifest_hash,'referee_did':signer.did,
        'authorized_at':125,'effective_start':effective_start,
        'effective_end':effective_start+manifest.intended_duration_seconds,
        'launch_status':'AUTHORIZE_LAUNCH'}
    return LaunchAuthorization.verify(sign_launch_payload(payload,signer),manifest,binding)

def test_clock_cannot_start_production_without_launch_authorization():
    signer=EphemeralSigner(b'h'*32); manifest=manifest_for(signer); record=activation_for(manifest,signer)
    client,_=pristine_client(); ctx=record.context()
    evidence=NamespacePreflight(client,manifest).check_pair(ctx.actions_namespace,ctx.events_namespace)
    store=Store()
    runtime=ProductionRuntime.from_verified_activation(manifest,record,evidence,store,signer,client,clock=lambda:999)
    assert runtime.engine._status()=='REGISTRATION'
    assert store.one("SELECT value FROM config WHERE key='season_started_at'") is None
    client.close()

def test_signed_launch_authorization_is_required_for_active():
    signer=EphemeralSigner(b'i'*32); manifest=manifest_for(signer); record=activation_for(manifest,signer)
    client,_=pristine_client(); ctx=record.context()
    evidence=NamespacePreflight(client,manifest).check_pair(ctx.actions_namespace,ctx.events_namespace)
    launch=launch_for(manifest,signer,ctx,effective_start=130)
    store=Store()
    runtime=ProductionRuntime.from_verified_activation(manifest,record,evidence,store,signer,client,clock=lambda:130,launch=launch)
    assert runtime.engine._status()=='ACTIVE'
    assert store.one("SELECT value FROM config WHERE key='season_started_at'")[0]=='130'
    client.close()

def test_launch_authorization_rejects_wrong_binding():
    signer=EphemeralSigner(b'j'*32); manifest=manifest_for(signer); record=activation_for(manifest,signer)
    payload=launch_for(manifest,signer,record.context()).value
    bad=dict(payload); bad['binding_id']='other'; bad.pop('signature')
    with pytest.raises(LaunchAuthorizationError):
        LaunchAuthorization.verify(sign_launch_payload(bad,signer),manifest,record.context())
