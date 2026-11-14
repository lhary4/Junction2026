"""Deterministic guardrails rules engine (step L3).

Pure function turning a BuyerPolicy, a verified AimoCheckout, the current timestamp,
the quote-signature check result, and an optional substitution judge into a Verdict.
No network, no cryptographic signing, and no persistent state.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ap2.sdk.utils import compute_sha256_b64url

from contract.models import (
    AimoCheckout,
    BuyerPolicy,
    Decision,
    JudgeAnswer,
    JudgeSubject,
    LineClaims,
    RuleResult,
    Signer,
    Verdict,
)

JudgeFn = Callable[..., list[dict[str, Any]]]


def _default_checkout_hash(checkout: AimoCheckout, signature: RuleResult) -> str:
    if signature.evidence.get("checkout_hash"):
        return str(signature.evidence["checkout_hash"])
    canonical = json.dumps(
        checkout.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    return compute_sha256_b64url(canonical)


def _format_code_list(codes: list[str]) -> str:
    if not codes:
        return "no declared allergens"
    if len(codes) == 1:
        return codes[0]
    return f"{', '.join(codes[:-1])} and {codes[-1]}"


def _check_not_expired(checkout: AimoCheckout, now: datetime) -> RuleResult:
    expires_at = checkout.expires_at
    if expires_at is None:
        return RuleResult(
            rule_id="quote-not-expired",
            outcome="deny",
            message="Quote has no expiry timestamp.",
            evidence={"expires_at": None},
        )
    if expires_at <= now:
        return RuleResult(
            rule_id="quote-not-expired",
            outcome="deny",
            message=f"Quote expired at {expires_at:%Y-%m-%d %H:%M}.",
            evidence={"expires_at": expires_at.isoformat(), "now": now.isoformat()},
        )
    return RuleResult(
        rule_id="quote-not-expired",
        outcome="pass",
        message=f"Quote valid until {expires_at:%Y-%m-%d %H:%M}.",
        evidence={"expires_at": expires_at.isoformat()},
    )


def _check_merchant_allowed(policy: BuyerPolicy, checkout: AimoCheckout) -> RuleResult:
    merchant_id = checkout.merchant.id
    merchant_name = checkout.merchant.name or merchant_id
    allowed_ids = {m.id for m in policy.allowed_merchants}
    if merchant_id in allowed_ids:
        return RuleResult(
            rule_id="merchant-allowed",
            outcome="pass",
            message=f"{merchant_name} is an allowed merchant.",
            evidence={"merchant_id": merchant_id},
        )
    return RuleResult(
        rule_id="merchant-allowed",
        outcome="deny",
        message=f"Merchant {merchant_id} is not in the allowed merchants list.",
        evidence={"merchant_id": merchant_id, "allowed": sorted(allowed_ids)},
    )


def _ordered_lines(checkout: AimoCheckout) -> list[tuple[str, LineClaims]]:
    return [(item.id, checkout.aimo.lines[item.id]) for item in checkout.line_items]


def _check_allergen_not_blocked(policy: BuyerPolicy, lines: list[tuple[str, LineClaims]]) -> RuleResult:
    contains = sorted({code for _, lc in lines for code in lc.allergens.contains})
    blocked = list(policy.blocked_allergens)
    matched = sorted(set(contains) & set(blocked))
    if matched:
        return RuleResult(
            rule_id="allergen-not-blocked",
            outcome="deny",
            message=f"Order contains blocked allergen(s): {_format_code_list(matched)}.",
            evidence={"contains": contains, "blocked": blocked, "matched": matched},
        )
    return RuleResult(
        rule_id="allergen-not-blocked",
        outcome="pass",
        message="No blocked allergen in the order.",
        evidence={"contains": contains, "blocked": blocked},
    )


def _check_allergen_data_known(policy: BuyerPolicy, lines: list[tuple[str, LineClaims]]) -> RuleResult:
    missing: list[str] = []
    for _, lc in lines:
        if lc.allergens.data != "complete":
            missing.append(lc.product_id)
        if lc.substitute_for is not None and lc.substitute_for.allergens.data != "complete":
            missing.append(lc.substitute_for.product_id)
    if missing:
        return RuleResult(
            rule_id="allergen-data-known",
            outcome=policy.unknown_allergen_data,
            message=f"Allergen data is missing for {', '.join(missing)}: unknown is never read as safe.",
            evidence={"missing_products": missing},
        )
    return RuleResult(
        rule_id="allergen-data-known",
        outcome="pass",
        message="Allergen data is complete for every line.",
        evidence={},
    )


def _check_allergen_unchanged_on_substitution(
    policy: BuyerPolicy,
    sub_lines: list[tuple[str, LineClaims]],
) -> RuleResult:
    for _, lc in sub_lines:
        orig = lc.substitute_for
        assert orig is not None
        orig_contains = sorted(set(orig.allergens.contains))
        sub_contains = sorted(set(lc.allergens.contains))
        if (
            orig.allergens.data != "complete"
            or lc.allergens.data != "complete"
            or orig_contains != sub_contains
        ):
            action_word = "a human must sign" if policy.allergen_change_on_substitution == "human" else "denied"
            return RuleResult(
                rule_id="allergen-unchanged-on-substitution",
                outcome=policy.allergen_change_on_substitution,
                message=(
                    f"Substitute {lc.product_id} contains {_format_code_list(sub_contains)}, "
                    f"the original {orig.product_id} contains {_format_code_list(orig_contains)}: "
                    f"the allergens change, {action_word}."
                ),
                evidence={
                    "original": orig.product_id,
                    "substitute": lc.product_id,
                    "original_contains": orig_contains,
                    "substitute_contains": sub_contains,
                },
            )

    first = sub_lines[0][1]
    assert first.substitute_for is not None
    same = sorted(set(first.allergens.contains))
    return RuleResult(
        rule_id="allergen-unchanged-on-substitution",
        outcome="pass",
        message=f"Substitute {first.product_id} has the same allergens as {first.substitute_for.product_id}.",
        evidence={
            "original": first.substitute_for.product_id,
            "substitute": first.product_id,
            "contains": same,
        },
    )


def _check_delivery_on_time(policy: BuyerPolicy, checkout: AimoCheckout) -> RuleResult:
    requested = checkout.aimo.requested_delivery_date
    promised = checkout.aimo.delivery_date
    if promised > requested:
        action_word = "a human must sign" if policy.late_delivery == "human" else "denied"
        return RuleResult(
            rule_id="delivery-on-time",
            outcome=policy.late_delivery,
            message=f"Delivery on {promised.isoformat()} is later than requested {requested.isoformat()}: {action_word}.",
            evidence={"requested": requested.isoformat(), "promised": promised.isoformat()},
        )
    return RuleResult(
        rule_id="delivery-on-time",
        outcome="pass",
        message=f"Delivery on {promised.isoformat()}, as requested.",
        evidence={"requested": requested.isoformat(), "promised": promised.isoformat()},
    )


def _check_spend_limit(policy: BuyerPolicy, checkout: AimoCheckout) -> RuleResult:
    total = checkout.total_minor()
    limit = policy.autonomous_limit_minor
    if checkout.currency != policy.currency:
        return RuleResult(
            rule_id="spend-limit",
            outcome="deny",
            message=f"Quote currency {checkout.currency} does not match policy currency {policy.currency}.",
            evidence={"currency": checkout.currency, "policy_currency": policy.currency},
        )
    if total > limit:
        return RuleResult(
            rule_id="spend-limit",
            outcome="human",
            message=f"{total / 100:.2f} {checkout.currency} is above the {limit / 100:.2f} {policy.currency} limit: a human must sign.",
            evidence={"total_minor": total, "limit_minor": limit},
        )
    return RuleResult(
        rule_id="spend-limit",
        outcome="pass",
        message=f"{total / 100:.2f} {checkout.currency} is within the {limit / 100:.2f} {policy.currency} limit.",
        evidence={"total_minor": total, "limit_minor": limit},
    )


def _is_pre_accepted(policy: BuyerPolicy, lc: LineClaims) -> bool:
    orig = lc.substitute_for
    if orig is None or policy.substitution.pre_accepted != "same_category_and_same_allergens":
        return False
    return (
        lc.category == orig.category
        and lc.allergens.data == "complete"
        and orig.allergens.data == "complete"
        and sorted(set(lc.allergens.contains)) == sorted(set(orig.allergens.contains))
    )


def _invoke_judge(
    judge: JudgeFn,
    original_card: dict[str, Any],
    candidate_card: dict[str, Any],
    preferences_text: str,
    auto_threshold: float,
    floor: float,
) -> list[JudgeAnswer]:
    try:
        sig = inspect.signature(judge)
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        kwargs: dict[str, Any] = {}
        if has_var_kw or "auto_threshold" in sig.parameters:
            kwargs["auto_threshold"] = auto_threshold
        if has_var_kw or "floor" in sig.parameters:
            kwargs["floor"] = floor
    except (TypeError, ValueError):
        kwargs = {}

    try:
        raw_list = judge(original_card, candidate_card, preferences_text, **kwargs)
    except Exception:  # noqa: BLE001 — fail closed if custom/live judge raises
        return _unreachable_judge_answers(
            str(original_card["id"]),
            str(candidate_card["id"]),
            auto_threshold,
            floor,
        )

    if not raw_list:
        return _unreachable_judge_answers(
            str(original_card["id"]),
            str(candidate_card["id"]),
            auto_threshold,
            floor,
        )

    normalized: list[JudgeAnswer] = []
    for raw in raw_list:
        item = dict(raw)
        prob = item.get("probability")
        item["auto_threshold"] = auto_threshold
        item["floor"] = floor
        item["routed"] = "auto" if (prob is not None and float(prob) >= auto_threshold) else "human"
        normalized.append(JudgeAnswer.model_validate(item))
    return normalized


def _unreachable_judge_answers(
    original_id: str,
    candidate_id: str,
    auto_threshold: float,
    floor: float,
) -> list[JudgeAnswer]:
    subject = JudgeSubject(original=original_id, candidate=candidate_id)
    return [
        JudgeAnswer(
            question_key="within_preferences",
            type="noul",
            instructions="Does the candidate product respect every preference the buyer stated for this purchase?",
            subject=subject,
            probability=None,
            confidence=None,
            auto_threshold=auto_threshold,
            floor=floor,
            routed="human",
            model="gemini-decision-1",
        ),
        JudgeAnswer(
            question_key="same_use",
            type="noul",
            instructions="Can the kitchen use the candidate exactly as it would have used the original, without changing anything?",
            subject=subject,
            probability=None,
            confidence=None,
            auto_threshold=auto_threshold,
            floor=floor,
            routed="human",
            model="gemini-decision-1",
        ),
    ]


def _check_substitution_within_preferences(
    policy: BuyerPolicy,
    checkout: AimoCheckout,
    sub_lines: list[tuple[str, LineClaims]],
    judge: JudgeFn | None,
) -> tuple[RuleResult, list[JudgeAnswer]]:
    sub_policy = policy.substitution
    first_lc = sub_lines[0][1]
    assert first_lc.substitute_for is not None

    if not sub_policy.allowed:
        return (
            RuleResult(
                rule_id="substitution-within-preferences",
                outcome="human",
                message="Substitutions require human approval under the buyer policy.",
                evidence={"original": first_lc.substitute_for.product_id, "substitute": first_lc.product_id},
            ),
            [],
        )

    non_pre_accepted = [(lid, lc) for lid, lc in sub_lines if not _is_pre_accepted(policy, lc)]
    if not non_pre_accepted:
        return (
            RuleResult(
                rule_id="substitution-within-preferences",
                outcome="pass",
                message=(
                    f"Substitute {first_lc.product_id} is pre-accepted "
                    f"(same category {first_lc.category} and same allergens as {first_lc.substitute_for.product_id})."
                ),
                evidence={"original": first_lc.substitute_for.product_id, "substitute": first_lc.product_id},
            ),
            [],
        )

    titles = {item.id: item.item.title for item in checkout.line_items}
    auto_threshold = sub_policy.judge_auto_threshold
    floor = sub_policy.judge_floor

    target_lc = non_pre_accepted[0][1]
    assert target_lc.substitute_for is not None
    evidence = {"original": target_lc.substitute_for.product_id, "substitute": target_lc.product_id}

    if judge is None:
        return (
            RuleResult(
                rule_id="substitution-within-preferences",
                outcome="human",
                message="The substitution judge was unreachable: a human must sign.",
                evidence=evidence,
            ),
            [],
        )

    all_answers: list[JudgeAnswer] = []
    for lid, lc in non_pre_accepted:
        orig = lc.substitute_for
        assert orig is not None
        original_card = {
            "id": orig.product_id,
            "name": orig.name,
            "category": orig.category,
            "allergens": orig.allergens.model_dump(),
        }
        candidate_card = {
            "id": lc.product_id,
            "name": titles.get(lid, ""),
            "category": lc.category,
            "allergens": lc.allergens.model_dump(),
            "labels": list(lc.labels),
        }
        all_answers.extend(
            _invoke_judge(
                judge,
                original_card,
                candidate_card,
                sub_policy.preferences_text,
                auto_threshold,
                floor,
            )
        )

    if any(a.probability is None for a in all_answers):
        return (
            RuleResult(
                rule_id="substitution-within-preferences",
                outcome="human",
                message="The substitution judge was unreachable: a human must sign.",
                evidence=evidence,
            ),
            all_answers,
        )

    probs = [a.probability for a in all_answers if a.probability is not None]
    min_prob = min(probs)
    if all(a.routed == "auto" for a in all_answers):
        return (
            RuleResult(
                rule_id="substitution-within-preferences",
                outcome="pass",
                message=(
                    f"The judge accepts this substitute within the buyer's preferences "
                    f"({min_prob:.2f}, threshold {auto_threshold:.2f})."
                ),
                evidence=evidence,
            ),
            all_answers,
        )

    if min_prob < floor:
        msg = f"The judge puts this substitute outside the buyer's stated preferences ({min_prob:.2f}, floor {floor:.2f})."
    else:
        msg = f"The judge is unsure about this substitute ({min_prob:.2f}, threshold {auto_threshold:.2f}): a human must sign."

    return (
        RuleResult(
            rule_id="substitution-within-preferences",
            outcome="human",
            message=msg,
            evidence=evidence,
        ),
        all_answers,
    )


def evaluate(
    policy: BuyerPolicy,
    checkout: AimoCheckout,
    now: datetime,
    signature: RuleResult,
    judge: JudgeFn | None = None,
    *,
    checkout_hash: str | None = None,
) -> Verdict:
    """Turn a policy and a quote into a deterministic Verdict (`deny` > `human` > `auto`).

    Evaluation order and invariants:
    1. If Valio's signature check failed (`signature.outcome != "pass"`), stop immediately:
       we never run business rules on an unsigned or tampered quote.
    2. Otherwise run every applicable rule (even if an earlier rule already failed) so the
       audit log and approval page can show the full list of reasons at once.
    3. Combine outcomes strictly: one `deny` -> `deny`; else one `human` -> `human`; else `auto`.
    """
    if now.tzinfo is None:
        raise ValueError("evaluate requires a timezone-aware `now` datetime")
    if signature.rule_id != "quote-signature":
        raise ValueError(f"signature RuleResult must have rule_id='quote-signature', got {signature.rule_id!r}")

    resolved_hash = checkout_hash if checkout_hash is not None else _default_checkout_hash(checkout, signature)

    # Short-circuit on invalid quote signature: untrusted cart numbers must not be evaluated.
    if signature.outcome != "pass":
        return Verdict(
            decision=signature.outcome,
            checkout_id=checkout.id,
            checkout_hash=resolved_hash,
            total_minor=checkout.total_minor(),
            currency=checkout.currency,
            signer=None,
            deadline=None,
            decided_at=now,
            rules=[signature],
            judge=[],
        )

    lines = _ordered_lines(checkout)
    sub_lines = [(lid, lc) for lid, lc in lines if lc.substitute_for is not None]

    # Run all deterministic rules on the verified quote facts.
    rules: list[RuleResult] = [
        signature,
        _check_not_expired(checkout, now),
        _check_merchant_allowed(policy, checkout),
        _check_allergen_not_blocked(policy, lines),
        _check_allergen_data_known(policy, lines),
    ]

    if sub_lines:
        rules.append(_check_allergen_unchanged_on_substitution(policy, sub_lines))

    rules.append(_check_delivery_on_time(policy, checkout))
    rules.append(_check_spend_limit(policy, checkout))

    # Only call the Gemini judge when a quote actually contains a substitute that is not pre-accepted.
    judge_answers: list[JudgeAnswer] = []
    if sub_lines:
        sub_rule, judge_answers = _check_substitution_within_preferences(policy, checkout, sub_lines, judge)
        rules.append(sub_rule)

    # Strict precedence: `deny` beats `human`, and `human` beats `auto`.
    outcomes = {r.outcome for r in rules}
    if "deny" in outcomes:
        decision: Decision = "deny"
    elif "human" in outcomes:
        decision = "human"
    else:
        decision = "auto"

    # Only `auto` names a signer right away ("agent"); `human` waits for the approval page, `deny` has none.
    signer: Signer | None = "agent" if decision == "auto" else None
    deadline = None if decision == "deny" else (checkout.aimo.closing_time or checkout.expires_at)

    return Verdict(
        decision=decision,
        checkout_id=checkout.id,
        checkout_hash=resolved_hash,
        total_minor=checkout.total_minor(),
        currency=checkout.currency,
        signer=signer,
        deadline=deadline,
        decided_at=now,
        rules=rules,
        judge=judge_answers,
    )
