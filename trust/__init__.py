"""Signing and verifying for the gateway and the harness. Only this package calls the AP2 SDK.

keys.py: the three demo keys. checkout.py: the signed quote. mandates.py: who may order it. receipts.py: proof of an order.
"""

from typing import Literal


class TrustError(Exception):
    """A signature, a key or an expiry does not check out. `rule` names the verdict rule it fails."""

    def __init__(self, message: str, rule: Literal["quote-signature", "quote-not-expired"] = "quote-signature"):
        super().__init__(message)
        self.rule = rule
