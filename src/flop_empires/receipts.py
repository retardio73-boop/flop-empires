from __future__ import annotations

from dataclasses import asdict
from typing import Any, Protocol

from .canonical import bytes_, dumps
from .identity import Signer, verify
from .models import Receipt


def issue_receipt(signer: Signer, unsigned: dict[str, Any]) -> Receipt:
    signature = signer.sign(bytes_(unsigned))
    return Receipt(**unsigned, signature=signature)


def verify_receipt(receipt: Receipt) -> bool:
    body = asdict(receipt)
    signature = body.pop("signature")
    return verify(receipt.referee_did, bytes_(body), signature)


class ReceiptPublisher(Protocol):
    def publish(self, canonical_receipt: str) -> None: ...


def publish_receipt(receipt: Receipt, publisher: ReceiptPublisher) -> None:
    """Explicit public boundary; callers inject transport and no secrets exist in body."""
    publisher.publish(dumps(asdict(receipt)))
