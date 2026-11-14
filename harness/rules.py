"""Deterministic guardrails rules engine (step L3).

Pure function turning a BuyerPolicy, a verified AimoCheckout, the current timestamp,
the quote-signature check result, and an optional substitution judge into a Verdict.
No network, no cryptographic signing, and no persistent state.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping
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
    Shortfall,
    Signer,
    SubstituteFor,
    Verdict,
)

JudgeFn = Callable[..., list[dict[str, Any]]]

# Key dietary and plainness promises: if an original product declares one of these and a
# candidate drops it (e.g. plain milk -> sweetened vanilla milk), never pre-accept without the judge.
KEY_DIETARY_CLAIMS: frozenset[str] = frozenset(
    {
        "FREE_FROM_LACTOSE",
        "FREE_FROM_GLUTEN",
        "VEGAN",
        "FREE_FROM_SOY",
        "NO_ADDED_SUGARS",
        "FREE_FROM_SWEETENERS",
        "FREE_FROM_FAT",
        "LOW_FAT",
    }
)


def _default_checkout_hash(checkout: AimoCheckout, signature: RuleResult) -> str:
    if signature.evidence.get("checkout_hash"):
        return str(signature.evidence["checkout_hash"])
    canonical = json.dumps(
        checkout.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    return compute_sha256_b64url(canonical)


def _effective_deadline(checkout: AimoCheckout) -> datetime | None:
    """An approval can never outlive either the quote's expiry or the order cut-off."""
    exp = checkout.expires_at
    closing = checkout.aimo.closing_time
    if exp is not None and closing is not None:
        return min(exp, closing)
    return exp or closing


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
        if lc.allergens.data != "complete" and lc.product_id not in missing:
            missing.append(lc.product_id)
        if (
            lc.substitute_for is not None
            and lc.substitute_for.allergens.data != "complete"
            and lc.substitute_for.product_id not in missing
        ):
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
    """Check every substitute line on the quote, not only the first one."""
    changed: list[tuple[SubstituteFor, LineClaims, list[str], list[str]]] = []
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
            changed.append((orig, lc, orig_contains, sub_contains))

    if changed:
        action_word = "a human must sign" if policy.allergen_change_on_substitution == "human" else "denied"
        orig0, lc0, orig_c0, sub_c0 = changed[0]
        if len(changed) == 1:
            return RuleResult(
                rule_id="allergen-unchanged-on-substitution",
                outcome=policy.allergen_change_on_substitution,
                message=(
                    f"Substitute {lc0.product_id} contains {_format_code_list(sub_c0)}, "
                    f"the original {orig0.product_id} contains {_format_code_list(orig_c0)}: "
                    f"the allergens change, {action_word}."
                ),
                evidence={
                    "original": orig0.product_id,
                    "substitute": lc0.product_id,
                    "original_contains": orig_c0,
                    "substitute_contains": sub_c0,
                },
            )

        parts = [
            f"{lc.product_id} ({_format_code_list(sub_c)}) for {orig.product_id} ({_format_code_list(orig_c)})"
            for orig, lc, orig_c, sub_c in changed
        ]
        return RuleResult(
            rule_id="allergen-unchanged-on-substitution",
            outcome=policy.allergen_change_on_substitution,
            message=f"Substitutes change allergens ({'; '.join(parts)}): {action_word}.",
            evidence={
                "original": orig0.product_id,
                "substitute": lc0.product_id,
                "original_contains": orig_c0,
                "substitute_contains": sub_c0,
                "changes": [
                    {
                        "original": orig.product_id,
                        "substitute": lc.product_id,
                        "original_contains": orig_c,
                        "substitute_contains": sub_c,
                    }
                    for orig, lc, orig_c, sub_c in changed
                ],
            },
        )

    first = sub_lines[0][1]
    assert first.substitute_for is not None
    same = sorted(set(first.allergens.contains))
    if len(sub_lines) == 1:
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

    pairs_desc = ", ".join(f"{lc.product_id}->{lc.substitute_for.product_id}" for _, lc in sub_lines if lc.substitute_for)
    return RuleResult(
        rule_id="allergen-unchanged-on-substitution",
        outcome="pass",
        message=f"All substitutes ({pairs_desc}) keep the same allergens as the replaced products.",
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


def _check_spend_limit(policy: BuyerPolicy, checkout: AimoCheckout, now: datetime) -> RuleResult:
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
    # AP2 open mandates expire at `policy.valid_until`; after that timestamp a human must sign directly.
    if now >= policy.valid_until:
        return RuleResult(
            rule_id="spend-limit",
            outcome="human",
            message=f"Autonomous policy {policy.policy_id} expired at {policy.valid_until:%Y-%m-%d %H:%M}: a human must sign.",
            evidence={
                "total_minor": total,
                "limit_minor": limit,
                "valid_until": policy.valid_until.isoformat(),
                "now": now.isoformat(),
            },
        )
    return RuleResult(
        rule_id="spend-limit",
        outcome="pass",
        message=f"{total / 100:.2f} {checkout.currency} is within the {limit / 100:.2f} {policy.currency} limit.",
        evidence={"total_minor": total, "limit_minor": limit},
    )


def _uncovered_shortfalls(
    checkout: AimoCheckout,
    sub_lines: list[tuple[str, LineClaims]],
) -> list[tuple[Shortfall, float]]:
    """Return shortfalls whose missing quantity is not covered by substitute lines in the quote."""
    uncovered: list[tuple[Shortfall, float]] = []
    for sf in checkout.aimo.shortfalls:
        covered_by_subs = sum(
            lc.base_quantity
            for _, lc in sub_lines
            if lc.substitute_for is not None
            and lc.substitute_for.product_id == sf.product_id
            and lc.base_unit == sf.base_unit
        )
        still_missing = round(sf.missing_base_quantity - covered_by_subs, 3)
        if still_missing > 1e-6:
            uncovered.append((sf, still_missing))
    return uncovered


def _build_original_card(
    checkout: AimoCheckout,
    orig: SubstituteFor,
    product_cards: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Build structured facts for the replaced product; signed quote fields always win over catalog metadata."""
    card: dict[str, Any] = dict(product_cards.get(orig.product_id, {})) if product_cards else {}
    # If partial stock put the original product on its own line (like `li-1` in Act 3),
    # pull its signed `origin`, `labels`, `sales_unit`, and `base_unit` directly from the quote!
    orig_line = next(
        (lc for lc in checkout.aimo.lines.values() if lc.product_id == orig.product_id and lc.substitute_for is None),
        None,
    )
    if orig_line is not None:
        card["origin"] = orig_line.origin.model_dump(mode="json")
        card["labels"] = list(orig_line.labels)
        card["sales_unit"] = orig_line.sales_unit
        card["base_unit"] = orig_line.base_unit
        signed_claims = getattr(orig_line, "nutritional_claims", None)
        if signed_claims is not None:
            card["nutritional_claims"] = list(signed_claims)

    # Support `labels` / `nutritional_claims` directly on `SubstituteFor` if added to the contract later.
    for attr in ("labels", "nutritional_claims", "brand", "origin"):
        val = getattr(orig, attr, None)
        if val is not None:
            card[attr] = list(val) if isinstance(val, list) else val

    card["id"] = orig.product_id
    card["name"] = orig.name
    card["category"] = orig.category
    card["allergens"] = orig.allergens.model_dump(mode="json")
    return card


def _build_candidate_card(
    lid: str,
    lc: LineClaims,
    titles: dict[str, str],
    product_cards: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Build structured facts for the substitute product; signed quote fields always win over catalog metadata."""
    card: dict[str, Any] = dict(product_cards.get(lc.product_id, {})) if product_cards else {}
    card["id"] = lc.product_id
    card["name"] = titles.get(lid) or str(card.get("name") or "")
    card["category"] = lc.category
    card["allergens"] = lc.allergens.model_dump(mode="json")
    card["origin"] = lc.origin.model_dump(mode="json")
    card["labels"] = list(lc.labels)
    card["sales_unit"] = lc.sales_unit
    card["base_unit"] = lc.base_unit
    signed_claims = getattr(lc, "nutritional_claims", None)
    if signed_claims is not None:
        card["nutritional_claims"] = list(signed_claims)
    return card


def _origin_code(raw: Any) -> str | None:
    if isinstance(raw, dict):
        val = raw.get("value")
        return str(val) if val else None
    if isinstance(raw, str) and raw.strip() and raw.strip() != "unknown":
        return raw.strip()
    return None


def _is_pre_accepted(
    policy: BuyerPolicy,
    checkout: AimoCheckout,
    lc: LineClaims,
    orig_card: dict[str, Any],
    cand_card: dict[str, Any],
) -> bool:
    """Return True only when a substitute can safely skip the Gemini judge.

    In food service, sharing a GS1 category (`10400` = all milk drinks) and `contains: ["AM"]`
    is far too broad on its own (it would auto-approve coffee milk, skimmed milk, or 10 L boxes).
    So pre-acceptance additionally requires:
    1. The agent did NOT override Valio's default choice with `substitute_with`.
    2. In the signed `alternatives` list, Valio marked this product `tier == "best"` AND
       explicitly `"listed as a substitute in the catalog"` (not a cheapest-in-category guess).
    3. No known origin, sustainability/quality label, non-lactose free-from allergen, or
       key dietary/plainness claim of the original product is lost.
    """
    orig = lc.substitute_for
    if orig is None or policy.substitution.pre_accepted != "same_category_and_same_allergens":
        return False
    if (
        lc.category != orig.category
        or lc.allergens.data != "complete"
        or orig.allergens.data != "complete"
        or sorted(set(lc.allergens.contains)) != sorted(set(orig.allergens.contains))
    ):
        return False

    # 1) Never pre-accept an explicit `substitute_with` pick from the agent without asking the judge.
    if any(
        req.product_id == orig.product_id and req.substitute_with == lc.product_id
        for req in checkout.aimo.requested
    ):
        return False

    # 2) Require Valio's signed `alternatives` entry to be a catalog-listed `best` substitute.
    alts_for_orig = [a for a in checkout.aimo.alternatives if a.for_product_id == orig.product_id]
    if alts_for_orig:
        chosen_alt = next((a for a in alts_for_orig if a.product_id == lc.product_id and a.chosen), None)
        if (
            chosen_alt is None
            or chosen_alt.tier != "best"
            or "listed as a substitute in the catalog" not in chosen_alt.why
        ):
            return False

    # 3) Never pre-accept if non-lactose `free_from` promises, origin, labels, or key dietary claims are lost.
    if (set(orig.allergens.free_from) - {"ML"}) - set(lc.allergens.free_from):
        return False

    orig_labels = set(orig_card.get("labels") or [])
    cand_labels = set(cand_card.get("labels") or [])
    if orig_labels - cand_labels:
        return False

    orig_origin = _origin_code(orig_card.get("origin"))
    cand_origin = _origin_code(cand_card.get("origin"))
    if orig_origin is not None and cand_origin != orig_origin:
        return False

    if "nutritional_claims" in orig_card and "nutritional_claims" in cand_card:
        orig_claims = set(orig_card.get("nutritional_claims") or []) & KEY_DIETARY_CLAIMS
        cand_claims = set(cand_card.get("nutritional_claims") or [])
        if orig_claims - cand_claims:
            return False

    return True


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
    uncovered: list[tuple[Shortfall, float]],
    judge: JudgeFn | None,
    product_cards: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[RuleResult, list[JudgeAnswer]]:
    sub_policy = policy.substitution
    titles = {item.id: item.item.title for item in checkout.line_items}
    auto_threshold = sub_policy.judge_auto_threshold
    floor = sub_policy.judge_floor

    if not sub_lines and uncovered:
        sf0, missing0 = uncovered[0]
        details = "; ".join(f"{missing:g} {sf.base_unit} of {sf.product_id} ({sf.reason})" for sf, missing in uncovered)
        return (
            RuleResult(
                rule_id="substitution-within-preferences",
                outcome="human",
                message=f"Order leaves an uncovered shortfall ({details}): a human must sign.",
                evidence={
                    "product_id": sf0.product_id,
                    "missing_base_quantity": missing0,
                    "base_unit": sf0.base_unit,
                    "reason": sf0.reason,
                },
            ),
            [],
        )

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

    prepared: list[tuple[str, LineClaims, dict[str, Any], dict[str, Any]]] = []
    for lid, lc in sub_lines:
        assert lc.substitute_for is not None
        o_card = _build_original_card(checkout, lc.substitute_for, product_cards)
        c_card = _build_candidate_card(lid, lc, titles, product_cards)
        prepared.append((lid, lc, o_card, c_card))

    non_pre_accepted = [
        (lid, lc, o_card, c_card)
        for lid, lc, o_card, c_card in prepared
        if not _is_pre_accepted(policy, checkout, lc, o_card, c_card)
    ]

    if not non_pre_accepted:
        if uncovered:
            sf0, missing0 = uncovered[0]
            details = "; ".join(
                f"{missing:g} {sf.base_unit} of {sf.product_id} ({sf.reason})" for sf, missing in uncovered
            )
            return (
                RuleResult(
                    rule_id="substitution-within-preferences",
                    outcome="human",
                    message=f"Order leaves an uncovered shortfall ({details}): a human must sign.",
                    evidence={
                        "original": first_lc.substitute_for.product_id,
                        "substitute": first_lc.product_id,
                        "uncovered_product_id": sf0.product_id,
                        "missing_base_quantity": missing0,
                    },
                ),
                [],
            )
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

    target_lc = non_pre_accepted[0][1]
    assert target_lc.substitute_for is not None
    evidence: dict[str, Any] = {"original": target_lc.substitute_for.product_id, "substitute": target_lc.product_id}
    if len(non_pre_accepted) > 1:
        evidence["substitutions"] = [
            {"original": lc.substitute_for.product_id, "substitute": lc.product_id}
            for _, lc, _, _ in non_pre_accepted
            if lc.substitute_for is not None
        ]

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
    for _, _, o_card, c_card in non_pre_accepted:
        all_answers.extend(
            _invoke_judge(
                judge,
                o_card,
                c_card,
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
    if all(a.routed == "auto" for a in all_answers) and not uncovered:
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

    if uncovered and all(a.routed == "auto" for a in all_answers):
        details = "; ".join(f"{missing:g} {sf.base_unit} of {sf.product_id} ({sf.reason})" for sf, missing in uncovered)
        msg = f"Substitute accepted ({min_prob:.2f}), but order still leaves an uncovered shortfall ({details}): a human must sign."
    elif min_prob < floor:
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
    product_cards: Mapping[str, Mapping[str, Any]] | None = None,
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
    uncovered = _uncovered_shortfalls(checkout, sub_lines)

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
    rules.append(_check_spend_limit(policy, checkout, now))

    # Run substitution & shortfall check whenever a quote substitutes a product or leaves a shortfall uncovered.
    judge_answers: list[JudgeAnswer] = []
    if sub_lines or uncovered:
        sub_rule, judge_answers = _check_substitution_within_preferences(
            policy,
            checkout,
            sub_lines,
            uncovered,
            judge,
            product_cards,
        )
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
    deadline = None if decision == "deny" else _effective_deadline(checkout)

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
