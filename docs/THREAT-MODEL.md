# Threat model

- Malicious Technocore input is bounded, parsed as canonical JSON, signature
  checked over exact `room|nonce|text`, never executed, and never used to follow URLs.
- Forged signatures and actor-field spoofing fail before command execution.
- Replays are neutralized by stable record IDs plus actor/request idempotency.
- A request ID collision with altered bytes is rejected.
- GitHub spoofing is constrained to explicit official API URLs, bounded bodies,
  deterministic evidence fields, merge/publication status, and bound authors.
- Sybil actors cannot churn membership after `ACTIVE`; staging write is allowlisted.
- Self-owned contribution evidence has zero upstream base yield; clusters score once.
- Circular raids destroy at least half their committed cost and cannot mint.
- Alliance eligibility is snapshotted when a staged attack is created.
- A referee compromise remains a trusted-computing-base failure. Receipts and the
  event chain make it detectable but cannot prevent a valid stolen-key signature.
- Signer outage, mismatch, timeout, or invalid returned signature fails closed.
- Network partitions retain the last durable cursor and pending receipt outbox;
  ambiguous delivery is checked by signed readback before any retry.
- Cursor generation changes or gaps require explicit audit/bootstrap.
- SQLite tampering is detected by integrity checks, state hashes, receipt signatures,
  and the event hash chain; operators must retain independent receipt copies.
