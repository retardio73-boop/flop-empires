from __future__ import annotations
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'season/SEASON-0-MANIFEST-FREEZE-V2-CANDIDATE.json'
GATE_B=ROOT/'season/GATE-B-PARAMETERS-CANDIDATE.json'


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def fail(message):
    raise AssertionError(message)

def main():
    m=json.loads(MANIFEST.read_text(encoding='utf-8'))
    supplied=m['manifest_hash']; unsigned=dict(m); unsigned.pop('manifest_hash')
    if digest(unsigned)!=supplied: fail('manifest hash mismatch')
    if m['activation']!='FROZEN_NOT_ACTIVE': fail('candidate unexpectedly active')
    if any(m[k] is not None for k in ('registration_open','registration_close','season_start','season_end')):
        fail('candidate contains launch timestamps')
    world_path=ROOT/m['world_fixture']
    world=json.loads(world_path.read_text(encoding='utf-8'))
    if digest(world)!=m['world_graph_hash']: fail('world hash mismatch')
    gate=json.loads(GATE_B.read_text(encoding='utf-8'))
    if gate!=m['gate_b_parameters']: fail('Gate B embedding mismatch')
    policy=m['namespace_policy']
    if policy.get('require_empty_namespace') is not True: fail('namespace pristine policy disabled')
    if any(k in m for k in ('actions_namespace','events_namespace')):
        fail('concrete production rooms leaked into frozen rules manifest')
    combat=m['combat_parameters']
    if combat.get('raid_min_power')!=14 or combat.get('siege_min_power')!=24:
        fail('combat minima mismatch')
    if gate.get('late_join')!={'production_boost_bp':18750,'protection_epochs':4}:
        fail('catch-up parameters mismatch')

    pyproject=(ROOT/'pyproject.toml').read_text(encoding='utf-8')
    if 'httpx==0.28.1' not in pyproject or 'PyNaCl==1.6.2' not in pyproject or 'pytest==9.1.1' not in pyproject:
        fail('top-level dependencies are not exact')
    production=(ROOT/'src/flop_empires/production.py').read_text(encoding='utf-8')
    required_fragments=(
        'ABORT_NAMESPACE: first preflight missing or mismatched',
        'namespace changed between checks',
        'production_activation_id',
        '{"generation":0,"seq":0}',
        'PRODUCTION_BINDING_MISMATCH',
    )
    for fragment in required_fragments:
        if fragment not in production: fail(f'missing launch guard: {fragment}')
    cli=(ROOT/'src/flop_empires/cli.py').read_text(encoding='utf-8')
    for fragment in ('verify-activation','production','preflight','--confirm-production-run','--signer-backend'):
        if fragment not in cli: fail(f'missing production CLI guard: {fragment}')

    result={
        'status':'FREEZE_V2_LAUNCH_AUDIT_PASS',
        'manifest_hash':supplied,
        'world_hash':m['world_graph_hash'],
        'schema':m['manifest_schema_version'],
        'activation':m['activation'],
    }
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
