# Freeze v2 launch-safety readiness

Status: **READY_FOR_EXPLICIT_ACTIVATION_PREP — NOT ACTIVE**

## Verified

- Freeze v2 manifest remains `FROZEN_NOT_ACTIVE`.
- Independent standard-library audit: PASS.
- Manifest hash: `273974947f7f56c4d9ccf3028d81a780ad05650f99c46cbbb71062c05a319d80`.
- World hash: `e4f4e5d497ddb208508aa4fcba98395807e5f4806aa1b17f5f3365cecd29622d`.
- Gate B parameters are hash-covered by Freeze v2.
- Concrete Technocore namespaces are absent from the frozen rules manifest.
- Activation Record v1 is closed-field, signed, manifest/referee/season bound.
- Unknown/normative activation fields fail closed.
- Namespace preflight is read-only and requires generation=0 + empty messages.
- First launch performs two pristine checks.
- Initial actions cursor is pinned to `{generation:0, seq:0}` so a message cannot be skipped between preflight and first poll.
- Production binding is persisted: manifest hash + activation id + referee DID + exact actions/events namespaces.
- Restart does not require rooms to be pristine again, but mismatched activation/binding aborts.
- Actions transport is bound to the exact actions namespace.
- Events transport requires exact events namespace and exact referee signer DID.
- Production CLI is isolated under `flop-empires production`.
- CLI supports `verify-activation`, read-only `preflight`, and explicit `run`.
- `run` requires both `--signer-backend` and `--confirm-production-run`.
- Production signer remains externally managed; no private key is stored in this repository.
- Exact direct dependency versions and a transitive `requirements.lock` are present.

## QA

- 165 tests passing.
- `compileall`: PASS.
- `git diff --check`: PASS.
- `tools/audit_freeze_v2_launch.py`: `FREEZE_V2_LAUNCH_AUDIT_PASS`.
