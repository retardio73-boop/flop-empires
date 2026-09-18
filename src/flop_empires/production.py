from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import secrets

import httpx

from .activation import ActivationContext,ActivationRecord,is_verified_activation_context
from .recovery import RecoveryRecord
from .launch import LaunchAuthorization
from .engine import Engine,LifecycleViolation
from .identity import Signer,require_signer
from .manifest import SeasonZeroFreezeV2CandidateManifest,validate_production_namespace
from .models import Receipt,SeasonStatus
from .receipts import verify_receipt
from .staging import ReceiptOutbox
from .store import Store
from .technocore import SignedMailbox,TechnocoreHttpMailbox,TechnocoreIngestor,TechnocoreTransport


_PREFLIGHT_MARKER=object()
_BINDING_KEYS=("production_manifest_hash","production_activation_id","production_referee_did",
    "production_actions_namespace","production_events_namespace")


class NamespaceAbort(RuntimeError):
    def __init__(self,detail: str="ABORT_NAMESPACE"):
        self.code="ABORT_NAMESPACE";super().__init__(detail)


@dataclass(frozen=True)
class NamespacePreflightEvidence:
    actions_namespace: str
    events_namespace: str
    observations: tuple[tuple[str,int,int,int],...]
    _marker: object


class NamespacePreflight:
    """Strict read-only pristine-room check. Uncertainty is an abort, never a retry-to-accept."""
    def __init__(self,client: httpx.Client,manifest: SeasonZeroFreezeV2CandidateManifest):
        self.client,self.manifest=client,manifest

    def _check(self,room: str,kind: str)->tuple[str,int,int,int]:
        try:
            validate_production_namespace(self.manifest.namespace_policy,room,kind)
            value=TechnocoreHttpMailbox(self.client,room,limit=1)._read(0)
            minimal={"generation","messages"}
            detailed={"room","generation","first_seq","last_seq","count","messages"}
            if set(value) not in {frozenset(minimal),frozenset(detailed)}:
                raise NamespaceAbort("ABORT_NAMESPACE: ambiguous response")
            generation=value["generation"];messages=value["messages"]
            if set(value)==detailed:
                if (value["room"]!=room or value["count"]!=0 or value["first_seq"] is not None or
                        value["last_seq"]!=0):
                    raise NamespaceAbort("ABORT_NAMESPACE: namespace metadata is not pristine")
            if generation!=0 or messages!=[]:
                raise NamespaceAbort("ABORT_NAMESPACE: namespace is not pristine")
            return (room,generation,0,0)
        except NamespaceAbort: raise
        except Exception as exc:
            raise NamespaceAbort("ABORT_NAMESPACE: preflight not verified") from exc

    def check_pair(self,actions: str,events: str)->NamespacePreflightEvidence:
        if actions==events: raise NamespaceAbort("ABORT_NAMESPACE: rooms collide")
        observations=(self._check(actions,"actions"),self._check(events,"events"))
        return NamespacePreflightEvidence(actions,events,observations,_PREFLIGHT_MARKER)


def generate_candidate_namespaces(manifest: SeasonZeroFreezeV2CandidateManifest)->tuple[str,str]:
    token=secrets.token_hex(manifest.namespace_policy["namespace_token_hex_length"]//2)
    prefix=manifest.namespace_policy["namespace_prefix"]
    return f"{prefix}{token}-actions",f"{prefix}{token}-events"


@dataclass(frozen=True)
class ProductionBinding:
    manifest_hash: str
    environment: str
    context: ActivationContext

    def validate(self,manifest: SeasonZeroFreezeV2CandidateManifest)->None:
        if (self.environment!="production" or self.manifest_hash!=manifest.manifest_hash or
                not is_verified_activation_context(self.context) or
                self.context.frozen_manifest_hash!=manifest.manifest_hash or
                self.context.referee_did!=manifest.referee_did):
            raise RuntimeError("PRODUCTION_BINDING_MISMATCH")


class BoundActionsMailbox(SignedMailbox):
    def __init__(self,transport: TechnocoreTransport,binding: ProductionBinding):
        if transport.room!=binding.context.actions_namespace:
            raise RuntimeError("NAMESPACE_BINDING_MISMATCH")
        self._transport,self.binding=transport,binding
        self.room=transport.room
    def current_cursor(self)->str:return self._transport.current_cursor()
    def records_after(self,cursor: str):return self._transport.records_after(cursor)


class BoundEventsTransport:
    def __init__(self,transport: TechnocoreTransport,binding: ProductionBinding):
        if transport.room!=binding.context.events_namespace or transport.signer is None or \
                transport.signer.did!=binding.context.referee_did:
            raise RuntimeError("NAMESPACE_BINDING_MISMATCH")
        self._transport,self.binding=transport,binding
        self.room=transport.room
    def publish_and_verify(self,receipt_hash: str,canonical_receipt: str):
        return self._transport.publish_and_verify(receipt_hash,canonical_receipt)


class ProductionReceiptOutbox:
    def __init__(self,store: Store,engine: Engine,binding: ProductionBinding,
                 manifest: SeasonZeroFreezeV2CandidateManifest):
        binding.validate(manifest)
        self.store,self.engine,self.binding,self.manifest=store,engine,binding,manifest
        self._outbox=ReceiptOutbox(store)

    def recover(self)->int:
        self._require_publishable()
        return self._outbox.recover()

    def _require_publishable(self)->None:
        self.binding.validate(self.manifest)
        if self.engine.runtime_mode.value!="PRODUCTION" or self.engine._status()==SeasonStatus.FROZEN_NOT_ACTIVE:
            raise LifecycleViolation("SEASON_NOT_ACTIVATED")
        for row in self.store.conn.execute("SELECT receipt_json FROM receipt_outbox"):
            from .canonical import loads
            receipt=Receipt(**loads(row[0]))
            if receipt.referee_did!=self.binding.context.referee_did or not verify_receipt(receipt):
                raise RuntimeError("RECEIPT_BINDING_MISMATCH")

    def flush(self,transport: BoundEventsTransport,clock=None)->dict:
        self._require_publishable()
        if not isinstance(transport,BoundEventsTransport) or transport.binding!=self.binding:
            raise RuntimeError("NAMESPACE_BINDING_MISMATCH")
        return self._outbox.flush(transport,clock=clock)


class ProductionIngestor:
    def __init__(self,store: Store,engine: Engine,binding: ProductionBinding,
                 manifest: SeasonZeroFreezeV2CandidateManifest):
        binding.validate(manifest)
        if engine.runtime_mode.value!="PRODUCTION": raise RuntimeError("PRODUCTION_ENGINE_REQUIRED")
        self.engine,self.binding,self.manifest=engine,binding,manifest
        self._ingestor=TechnocoreIngestor(store,engine,binding.context.actions_namespace,
            expected_season_id=binding.context.season_id)

    def poll(self,source: BoundActionsMailbox,*,replay: bool=False)->list[Receipt]:
        self.binding.validate(self.manifest)
        if self.engine._status()==SeasonStatus.FROZEN_NOT_ACTIVE:
            raise LifecycleViolation("SEASON_NOT_ACTIVATED")
        if not isinstance(source,BoundActionsMailbox) or source.binding!=self.binding:
            raise RuntimeError("NAMESPACE_BINDING_MISMATCH")
        self.engine.advance_production_lifecycle()
        return self._ingestor.poll(source,replay=replay)


def _binding_values(binding: ProductionBinding)->dict[str,str]:
    return {
        "production_manifest_hash":binding.manifest_hash,
        "production_activation_id":binding.context.activation_id,
        "production_referee_did":binding.context.referee_did,
        "production_actions_namespace":binding.context.actions_namespace,
        "production_events_namespace":binding.context.events_namespace,
    }

def _read_persisted_binding(store: Store)->dict[str,str] | None:
    rows={r["key"]:r["value"] for r in store.conn.execute(
        "SELECT key,value FROM config WHERE key IN (?,?,?,?,?)",_BINDING_KEYS)}
    if not rows:return None
    if set(rows)!=set(_BINDING_KEYS):raise RuntimeError("PRODUCTION_BINDING_PARTIAL")
    return rows

def _persist_initial_binding(store: Store,binding: ProductionBinding)->None:
    from .canonical import dumps
    values=_binding_values(binding)
    with store.transaction():
        for key,value in values.items():
            store.conn.execute("INSERT INTO config(key,value) VALUES(?,?)",(key,value))
        store.conn.execute("INSERT INTO technocore_state(mailbox,cursor,bootstrapped) VALUES(?,?,1)",
            (binding.context.actions_namespace,dumps({"generation":0,"seq":0})))


@dataclass
class ProductionRuntime:
    manifest: SeasonZeroFreezeV2CandidateManifest
    activation: ActivationRecord
    binding: ProductionBinding
    store: Store
    engine: Engine
    actions: BoundActionsMailbox
    events: BoundEventsTransport
    ingestor: ProductionIngestor
    outbox: ProductionReceiptOutbox

    @classmethod
    def from_verified_activation(cls,manifest: SeasonZeroFreezeV2CandidateManifest,
            activation: ActivationRecord,preflight: NamespacePreflightEvidence | None,store: Store,
            signer: Signer,client: httpx.Client,clock=None,launch: LaunchAuthorization | None=None)->"ProductionRuntime":
        context=activation.context()
        require_signer(manifest.referee_did,signer)
        binding=ProductionBinding(manifest.manifest_hash,"production",context);binding.validate(manifest)
        persisted=_read_persisted_binding(store)
        if persisted is None:
            if preflight is None or preflight._marker is not _PREFLIGHT_MARKER or (preflight.actions_namespace,
                    preflight.events_namespace)!=(context.actions_namespace,context.events_namespace):
                raise NamespaceAbort("ABORT_NAMESPACE: first preflight missing or mismatched")
            second=NamespacePreflight(client,manifest).check_pair(context.actions_namespace,context.events_namespace)
            if second.observations!=preflight.observations:
                raise NamespaceAbort("ABORT_NAMESPACE: namespace changed between checks")
            _persist_initial_binding(store,binding)
        elif persisted!=_binding_values(binding):
            raise RuntimeError("PRODUCTION_BINDING_MISMATCH")
        engine=Engine._for_verified_production(store,manifest,signer,context,clock=clock,launch_context=launch.context() if launch else None)
        now=int(engine.clock())
        if now<context.registration_open:
            raise LifecycleViolation("ACTIVATION_NOT_EFFECTIVE")
        engine.advance_production_lifecycle(now)
        action_transport=TechnocoreTransport(client,context.actions_namespace)
        event_transport=TechnocoreTransport(client,context.events_namespace,signer=signer)
        actions=BoundActionsMailbox(action_transport,binding)
        events=BoundEventsTransport(event_transport,binding)
        ingestor=ProductionIngestor(store,engine,binding,manifest)
        outbox=ProductionReceiptOutbox(store,engine,binding,manifest)
        return cls(manifest,activation,binding,store,engine,actions,events,ingestor,outbox)

    @classmethod
    def from_verified_recovery(cls,manifest: SeasonZeroFreezeV2CandidateManifest, recovery: RecoveryRecord,
            store: Store, signer: Signer, client: httpx.Client, clock=None, launch: LaunchAuthorization | None=None)->"ProductionRuntime":
        context=recovery.context(); require_signer(manifest.referee_did,signer)
        binding=ProductionBinding(manifest.manifest_hash,"production",context); binding.validate(manifest)
        persisted=_read_persisted_binding(store)
        action_transport=TechnocoreTransport(client,context.actions_namespace)
        if persisted is None:
            values=_binding_values(binding)
            with store.transaction():
                for key,value in values.items(): store.conn.execute("INSERT INTO config(key,value) VALUES(?,?)",(key,value))
                store.conn.execute("INSERT INTO technocore_state(mailbox,cursor,bootstrapped) VALUES(?,?,1)",
                    (context.actions_namespace,action_transport.current_cursor()))
        elif persisted!=_binding_values(binding):
            raise RuntimeError("PRODUCTION_BINDING_MISMATCH")
        engine=Engine._for_verified_production(store,manifest,signer,context,clock=clock,launch_context=launch.context() if launch else None)
        now=int(engine.clock())
        if now<context.registration_open: raise LifecycleViolation("ACTIVATION_NOT_EFFECTIVE")
        engine.advance_production_lifecycle(now)
        event_transport=TechnocoreTransport(client,context.events_namespace,signer=signer)
        actions=BoundActionsMailbox(action_transport,binding); events=BoundEventsTransport(event_transport,binding)
        ingestor=ProductionIngestor(store,engine,binding,manifest); outbox=ProductionReceiptOutbox(store,engine,binding,manifest)
        return cls(manifest,recovery,binding,store,engine,actions,events,ingestor,outbox)
