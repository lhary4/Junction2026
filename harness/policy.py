"""Buyer policy for the guardrails harness: the repo file, and the change the chef saved from the settings page.

- `load_policy` reads the policy file of the repo: `scenarios/policy.demo.json` once Colette writes it,
  falling back to `contract/examples/policy.demo.json` until then.
- `policy_in_force` is what the harness enforces: the policy saved in `state/buyer/policy.json`
  if the chef changed a rule on the page, else the repo file.
- `apply_change` merges a partial change (`PolicyChange`) into a policy and validates the result.

The repo file is never written. `scripts/dev.py --fresh` empties `state/buyer/`, so a fresh start
goes back to the repo file.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, field_validator

from contract.models import BuyerPolicy, ContractModel, Escalation
from harness.approvals import buyer_state_dir

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
SCENARIO_POLICY = ROOT / "scenarios" / "policy.demo.json"
EXAMPLE_POLICY = ROOT / "contract" / "examples" / "policy.demo.json"
SAVED_POLICY_NAME = "policy.json"

# How each escalation value reads in the audit log.
ESCALATION_WORDS: dict[str, str] = {"human": "a human signs", "deny": "refused"}
ESCALATION_LABELS: dict[str, str] = {
    "unknown_allergen_data": "missing allergen data",
    "allergen_change_on_substitution": "a substitute that changes the allergens",
    "late_delivery": "a late delivery",
}


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


# ---------- The change saved from the settings page ----------


class SubstitutionChange(ContractModel):
    """The substitution rules the chef may change. A field left out (or null) stays as it is."""

    allowed: StrictBool | None = None
    # Same values as `SubstitutionPolicy.pre_accepted` in contract/models.py.
    pre_accepted: Literal["same_category_and_same_allergens", "none"] | None = None
    preferences_text: str | None = None
    judge_auto_threshold: StrictFloat | None = Field(None, ge=0, le=1)
    judge_floor: StrictFloat | None = Field(None, ge=0, le=1)


class PolicyChange(ContractModel):
    """Body of PUT /policy: a partial change. A field left out (or null) stays as it is.

    Who the policy is for, who approves, which merchants are allowed, the currency and the end
    date are not here on purpose: this route cannot change them, and an unknown field is refused.
    """

    decided_by: str = Field(min_length=1)
    autonomous_limit_minor: StrictInt | None = Field(None, ge=1)
    blocked_allergens: list[str] | None = None
    unknown_allergen_data: Escalation | None = None
    allergen_change_on_substitution: Escalation | None = None
    late_delivery: Escalation | None = None
    substitution: SubstitutionChange | None = None

    @field_validator("blocked_allergens")
    @classmethod
    def clean_allergen_codes(cls, codes: list[str] | None) -> list[str] | None:
        """Refuse an empty code and drop repeated ones, keeping the order they came in."""
        if codes is None:
            return None
        cleaned: list[str] = []
        for raw in codes:
            code = raw.strip()
            if not code:
                raise ValueError("an allergen code cannot be empty")
            if code not in cleaned:
                cleaned.append(code)
        return cleaned


class LimitChange(ContractModel):
    """Body of PUT /policy/autonomous-limit: the spending limit alone, in cents."""

    autonomous_limit_minor: StrictInt = Field(ge=1)
    decided_by: str = Field(min_length=1)


class PolicyReset(ContractModel):
    """Optional body of POST /policy/reset: who asked for it."""

    decided_by: str | None = Field(None, min_length=1)


class PolicyChangeError(ValueError):
    """A change that is well-formed JSON but cannot be applied. The service answers HTTP 422."""


def saved_policy_path() -> Path:
    """Where a change is kept: `state/buyer/policy.json`, next to the approvals and the buyer audit log."""
    return buyer_state_dir() / SAVED_POLICY_NAME


def policy_in_force(policy_path: str | Path | None = None, saved_path: Path | None = None) -> BuyerPolicy:
    """The policy the harness enforces: the saved one if it exists and validates, else the repo file."""
    saved = saved_path if saved_path is not None else saved_policy_path()
    if saved.exists():
        try:
            return BuyerPolicy.model_validate_json(saved.read_text(encoding="utf-8"))
        except (ValueError, OSError) as err:  # a pydantic ValidationError is a ValueError
            logger.warning("Saved policy %s is unreadable (%s): using the policy file.", saved, type(err).__name__)
    return load_policy(policy_path)


def save_policy(policy: BuyerPolicy, saved_path: Path | None = None) -> None:
    """Write the policy in force to the state folder. Never writes to the repo file."""
    saved = saved_path if saved_path is not None else saved_policy_path()
    saved.parent.mkdir(parents=True, exist_ok=True)
    # Write next to the file, then swap: a request reading at the same moment never sees half a file.
    draft = saved.with_name(saved.name + ".tmp")
    draft.write_text(policy.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(draft, saved)


def forget_saved_policy(saved_path: Path | None = None) -> bool:
    """Remove the saved policy. True if there was one."""
    saved = saved_path if saved_path is not None else saved_policy_path()
    if not saved.exists():
        return False
    saved.unlink()
    return True


def apply_change(current: BuyerPolicy, change: PolicyChange) -> BuyerPolicy:
    """Merge a partial change into `current` and validate the result as a BuyerPolicy.

    Raises `PolicyChangeError` (or pydantic's `ValidationError`, also a `ValueError`) when the
    body names no editable field or the merged policy makes no sense.
    """
    fields = change.model_dump(mode="json", exclude_none=True, exclude={"decided_by"})
    substitution = fields.pop("substitution", None) or {}
    if not fields and not substitution:
        raise PolicyChangeError("the body changes nothing: give at least one editable field next to decided_by")

    merged = current.model_dump(mode="json")
    merged.update(fields)
    merged["substitution"].update(substitution)
    updated = BuyerPolicy.model_validate(merged)

    floor, threshold = updated.substitution.judge_floor, updated.substitution.judge_auto_threshold
    if floor > threshold:
        raise PolicyChangeError(f"judge_floor ({floor:g}) cannot be above judge_auto_threshold ({threshold:g})")
    return updated


def _money(minor: int, currency: str) -> str:
    return f"{minor / 100:.2f} {currency}"


def _codes(codes: list[str]) -> str:
    return ", ".join(codes) if codes else "none"


def describe_changes(before: BuyerPolicy, after: BuyerPolicy) -> list[str]:
    """What differs between two policies, one short phrase per field, for the audit log."""
    parts: list[str] = []
    if before.autonomous_limit_minor != after.autonomous_limit_minor:
        old = _money(before.autonomous_limit_minor, before.currency)
        new = _money(after.autonomous_limit_minor, after.currency)
        parts.append(f"spending limit from {old} to {new}")
    if before.blocked_allergens != after.blocked_allergens:
        parts.append(f"blocked allergens from {_codes(before.blocked_allergens)} to {_codes(after.blocked_allergens)}")
    for field, label in ESCALATION_LABELS.items():
        old, new = getattr(before, field), getattr(after, field)
        if old != new:
            parts.append(f"{label} from '{ESCALATION_WORDS[old]}' to '{ESCALATION_WORDS[new]}'")

    sub_before, sub_after = before.substitution, after.substitution
    if sub_before.allowed != sub_after.allowed:
        words = {True: "allowed", False: "always signed by a human"}
        parts.append(f"substitutes from '{words[sub_before.allowed]}' to '{words[sub_after.allowed]}'")
    if sub_before.pre_accepted != sub_after.pre_accepted:
        words = {"same_category_and_same_allergens": "same category and same allergens", "none": "none"}
        parts.append(
            f"substitutes accepted without the judge from '{words[sub_before.pre_accepted]}' "
            f"to '{words[sub_after.pre_accepted]}'"
        )
    if sub_before.preferences_text != sub_after.preferences_text:
        # The text can be long: the log says it was rewritten, the policy holds the words.
        parts.append(
            f"substitution preferences rewritten ({len(sub_before.preferences_text)} characters "
            f"before, {len(sub_after.preferences_text)} after)"
        )
    if sub_before.judge_auto_threshold != sub_after.judge_auto_threshold:
        parts.append(
            f"judge threshold to accept a substitute alone from {sub_before.judge_auto_threshold:g} "
            f"to {sub_after.judge_auto_threshold:g}"
        )
    if sub_before.judge_floor != sub_after.judge_floor:
        parts.append(f"judge floor from {sub_before.judge_floor:g} to {sub_after.judge_floor:g}")
    return parts
