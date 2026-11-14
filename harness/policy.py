"""Buyer policy loader for the guardrails harness (step L3).

Loads scenarios/policy.demo.json once Colette writes it, falling back to
contract/examples/policy.demo.json until then.
"""

from __future__ import annotations

from pathlib import Path

from contract.models import BuyerPolicy

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_POLICY = ROOT / "scenarios" / "policy.demo.json"
EXAMPLE_POLICY = ROOT / "contract" / "examples" / "policy.demo.json"


def load_policy(path: str | Path | None = None) -> BuyerPolicy:
    """Load and validate a BuyerPolicy from JSON.

    Prefers `scenarios/policy.demo.json` (owned by Colette for the live demo) and
    automatically falls back to `contract/examples/policy.demo.json` until it exists.
    """
    if path is None:
        target = SCENARIO_POLICY if SCENARIO_POLICY.exists() else EXAMPLE_POLICY
    else:
        target = Path(path)
        if not target.exists() and target.resolve() == SCENARIO_POLICY.resolve():
            target = EXAMPLE_POLICY
    return BuyerPolicy.model_validate_json(target.read_text(encoding="utf-8"))
