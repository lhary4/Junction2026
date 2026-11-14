"""Proof of an accepted order: Valio signs a receipt that points at the closed checkout mandate (its `reference`).

The payload matches AP2's CheckoutReceipt. `iat` reads common.clock, so replay mode stamps the recorded time.
"""

from jwcrypto.jwk import JWK
from pydantic import ValidationError

from common import clock
from contract.models import Receipt
from trust import TrustError
from trust.keys import MERCHANT_ID, sign, verify


def sign_receipt(order_id: str, reference: str, merchant_key: JWK) -> str:
    receipt = Receipt(
        status="Success", iss=MERCHANT_ID, iat=int(clock.now().timestamp()), reference=reference, order_id=order_id
    )
    return sign(receipt.model_dump(mode="json", exclude_none=True), merchant_key)


def verify_receipt(receipt_jwt: str, merchant_jwks: dict) -> dict:
    """Returns the receipt payload, or raises TrustError."""
    payload = verify(receipt_jwt, merchant_jwks)
    try:
        Receipt.model_validate(payload)
    except ValidationError as e:
        raise TrustError(f"signed payload is not a receipt: {e.error_count()} errors") from e
    return payload
