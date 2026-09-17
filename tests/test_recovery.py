import copy,time
from pathlib import Path
import pytest
from flop_empires.identity import EphemeralSigner
from flop_empires.manifest import SeasonZeroFreezeV2CandidateManifest
from flop_empires.recovery import RecoveryRecord,RecoveryError,sign_recovery_payload

ROOT=Path(__file__).parents[1]
MANIFEST=SeasonZeroFreezeV2CandidateManifest.load(ROOT/'season'/'SEASON-0-MANIFEST-FREEZE-V2-CANDIDATE.json')

def manifest_for(signer):
    value=copy.deepcopy(MANIFEST.value); value['referee_did']=signer.did
    return SeasonZeroFreezeV2CandidateManifest(value)

def payload(signer,manifest):
    now=1_800_000_000
    return {'version':'flop-empires-recovery-v1','recovery_id':'recovery-test','season_id':MANIFEST.season_id,
        'frozen_manifest_hash':manifest.manifest_hash,'original_activation_id':'activation-test','failed_state_hash':'a'*64,
        'failed_event_head':{'seq':1,'event_hash':'b'*64},'reason_codes':['ZERO_PLAYER_FAILED_LAUNCH'],
        'referee_did':signer.did,'duplex_namespace':'mb-p-flop-empires-s0-ba02b3dadb3962c9-events',
        'registration_open':now,'registration_close':now+3600,'season_start':now+3600,
        'season_end':now+3600+manifest.intended_duration_seconds,'issued_at':now,'recovery_status':'AUTHORIZE_RECOVERY'}

def test_recovery_signature_binds_operational_fields():
    signer=EphemeralSigner(); manifest=manifest_for(signer); data=payload(signer,manifest); signed=sign_recovery_payload(data,signer)
    recovered=RecoveryRecord.verify(signed,manifest)
    assert recovered.context().actions_namespace==signed['duplex_namespace']
    tampered=copy.deepcopy(signed); tampered['registration_close']+=1
    with pytest.raises(RecoveryError): RecoveryRecord.verify(tampered,manifest)
