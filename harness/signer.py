"""Buyer-side mandate signer held by the harness (step L4).

The agent never sees a private key or a raw token:
- Verdict `auto`: `sign_auto` closes the manager's open AP2 mandates with the agent's key.
- Verdict `human`: `sign_human` signs closed AP2 mandates directly with the manager's key
  for that exact quote hash (triggered by the Approve button on the surface in the demo;
  in production, backed by a WebAuthn passkey on the approval surface).
"""

from __future__ import annotations

from pathlib import Path

from contract.models import Authorization, BuyerPolicy
from harness.policy import load_policy
from trust.keys import KEYS_DIR, private_key, public_jwk
from trust.mandates import OpenMandates, close_as_agent, close_as_human, issue_open_mandates


class HarnessSigner:
    """Holds the buyer-side keys and open mandates issued under the current BuyerPolicy."""

    def __init__(self, policy: BuyerPolicy | None = None, keys_dir: Path = KEYS_DIR) -> None:
        self._keys_dir = keys_dir
        self._manager_key = private_key("manager", directory=keys_dir)
        self._agent_key = private_key("agent", directory=keys_dir)
        self._agent_pub = public_jwk("agent", directory=keys_dir)
        self._policy: BuyerPolicy | None = None
        self._open_mandates: OpenMandates | None = None
        if policy is not None:
            self.refresh_policy(policy)

    def refresh_policy(self, policy: BuyerPolicy) -> OpenMandates:
        self._policy = policy
        self._open_mandates = issue_open_mandates(policy, self._manager_key, self._agent_pub)
        return self._open_mandates

    def open_mandates(self, policy: BuyerPolicy | None = None) -> OpenMandates:
        target_policy = policy or self._policy or load_policy()
        if self._open_mandates is None or self._policy != target_policy:
            return self.refresh_policy(target_policy)
        return self._open_mandates

    def sign_auto(self, checkout_jwt: str, policy: BuyerPolicy | None = None) -> Authorization:
        """Close the manager's open mandates with the agent's key for a verified quote."""
        mandates = self.open_mandates(policy)
        return close_as_agent(mandates, self._agent_key, checkout_jwt)

    def sign_human(self, checkout_jwt: str) -> Authorization:
        """Sign closed mandates directly with the manager's key for this exact quote."""
        return close_as_human(self._manager_key, checkout_jwt)


_default_signer: HarnessSigner | None = None


def _get_default_signer() -> HarnessSigner:
    global _default_signer
    if _default_signer is None:
        _default_signer = HarnessSigner()
    return _default_signer


def sign_auto(checkout_jwt: str, policy: BuyerPolicy | None = None) -> Authorization:
    return _get_default_signer().sign_auto(checkout_jwt, policy=policy)


def sign_human(checkout_jwt: str) -> Authorization:
    return _get_default_signer().sign_human(checkout_jwt)
