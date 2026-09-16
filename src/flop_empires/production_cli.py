from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import httpx

from .activation import ActivationRecord
from .identity import ExternalRefereeSigner
from .manifest import SeasonZeroFreezeV2CandidateManifest
from .production import NamespacePreflight, ProductionRuntime
from .store import Store


def load_external_backend(spec: str) -> Any:
    if ':' not in spec:
        raise ValueError('signer backend must be module:factory')
    module_name,factory_name=spec.split(':',1)
    module=importlib.import_module(module_name)
    factory=getattr(module,factory_name,None)
    if not callable(factory):
        raise ValueError('signer backend factory not callable')
    return factory()


def load_verified(manifest_path: Path, activation_path: Path):
    manifest=SeasonZeroFreezeV2CandidateManifest.load(manifest_path)
    activation=ActivationRecord.load(activation_path,manifest)
    return manifest,activation
def verify_activation(manifest_path: Path, activation_path: Path) -> dict:
    manifest,activation=load_verified(manifest_path,activation_path)
    ctx=activation.context()
    return {
        'status':'VERIFIED_NOT_RUN',
        'manifest_hash':manifest.manifest_hash,
        'activation_id':ctx.activation_id,
        'actions_namespace':ctx.actions_namespace,
        'events_namespace':ctx.events_namespace,
    }


def preflight(manifest_path: Path, activation_path: Path, client: httpx.Client) -> dict:
    manifest,activation=load_verified(manifest_path,activation_path)
    ctx=activation.context()
    evidence=NamespacePreflight(client,manifest).check_pair(ctx.actions_namespace,ctx.events_namespace)
    return {
        'status':'PRISTINE_READ_ONLY',
        'actions_namespace':evidence.actions_namespace,
        'events_namespace':evidence.events_namespace,
        'observations':[list(x) for x in evidence.observations],
    }
def run_once(manifest_path: Path, activation_path: Path, database: Path,
             signer_backend: str, client: httpx.Client, *, clock=None) -> dict:
    manifest,activation=load_verified(manifest_path,activation_path)
    backend=load_external_backend(signer_backend)
    signer=ExternalRefereeSigner(manifest.referee_did,backend)
    ctx=activation.context(); store=Store(database)
    persisted=store.one("SELECT value FROM config WHERE key='production_activation_id'")
    first=None if persisted else NamespacePreflight(client,manifest).check_pair(
        ctx.actions_namespace,ctx.events_namespace)
    runtime=ProductionRuntime.from_verified_activation(
        manifest,activation,first,store,signer,client,clock=clock)
    receipts=runtime.ingestor.poll(runtime.actions)
    flushed=runtime.outbox.flush(runtime.events)
    return {
        'status':'PRODUCTION_ONCE_COMPLETE',
        'manifest_hash':manifest.manifest_hash,
        'activation_id':ctx.activation_id,
        'receipts':len(receipts),
        'outbox':flushed,
    }
