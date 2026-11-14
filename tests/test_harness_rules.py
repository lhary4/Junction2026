"""Table-driven and example-parity tests for harness/policy.py and harness/rules.py (step L3)."""

from __future__ import annotations

import copy
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from contract.models import AimoCheckout, BuyerPolicy, Decision, RuleResult, Verdict
from harness.policy import load_policy
from harness.rules import evaluate

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "contract" / "examples"

NOW = datetime.fromisoformat("2026-11-14T13:15:04+02:00")
AFTER_EXPIRY = datetime.fromisoformat("2026-11-15T17:00:01+02:00")

SIG_PASS = RuleResult(
    rule_id="quote-signature",
    outcome="pass",
    message="Quote signed by valio-aimo with key valio-aimo-gateway-1.",
    evidence={"kid": "valio-aimo-gateway-1"},
)
SIG_DENY = RuleResult(
    rule_id="quote-signature",
    outcome="deny",
    message="The quote does not match Valio Aimo's signature: it was changed after signing. Nothing is signed, nothing is ordered.",
    evidence={"kid": "valio-aimo-gateway-1", "error": "InvalidJWSSignature"},
)


def _example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _fake_judge(wp: float | None, su: float | None):
    def _judge(original: dict, candidate: dict, preferences_text: str) -> list[dict]:
        def _entry(key: str, instructions: str, prob: float | None) -> dict:
            conf = None if prob is None else round(max(prob, 1.0 - prob), 4)
            return {
                "question_key": key,
                "type": "noul",
                "instructions": instructions,
                "subject": {"original": original["id"], "candidate": candidate["id"]},
                "probability": prob,
                "confidence": conf,
                "auto_threshold": 0.85,
                "floor": 0.15,
                "routed": "auto" if (prob is not None and prob >= 0.85) else "human",
                "model": "gemini-decision-1",
            }

        return [
            _entry(
                "within_preferences",
                "Does the candidate product respect every preference the buyer stated for this purchase?",
                wp,
            ),
            _entry(
                "same_use",
                "Can the kitchen use the candidate exactly as it would have used the original, without changing anything?",
                su,
            ),
        ]

    return _judge


def _build_oat_substitution_checkout() -> AimoCheckout:
    """Act 3 quote when Oatly iKaffe (464320) substitutes for Arla milk (469363), matching verdict.human.substitution."""
    data = copy.deepcopy(_example("checkout.act3.json"))
    data["id"] = "chk_act3_oat_demo"
    data["line_items"][1]["item"] = {
        "id": "464320",
        "title": "Oatly iKaffe Oat drink 1L",
        "price": 178,
    }
    data["line_items"][1]["totals"] = [
        {"type": "subtotal", "amount": 38448},
        {"type": "total", "amount": 38448},
    ]
    data["totals"] = [
        {"type": "subtotal", "amount": 133680},
        {"type": "total", "amount": 133680},
    ]
    li2 = data["aimo"]["lines"]["li-2"]
    li2["product_id"] = "464320"
    li2["category"] = "10402"
    li2["comparison_price_minor"] = 178
    li2["allergens"] = {"contains": ["AW", "GO"], "free_from": [], "data": "complete"}
    li2["labels"] = []
    return AimoCheckout.model_validate(data)


def _mutate_act1(**kind: Any) -> AimoCheckout:
    data = copy.deepcopy(_example("checkout.act1.json"))
    if "missing_allergen" in kind:
        data["aimo"]["lines"]["li-1"]["allergens"] = {"contains": [], "free_from": [], "data": "missing"}
    if "blocked_allergen" in kind:
        data["aimo"]["lines"]["li-1"]["allergens"]["contains"] = ["AM", kind["blocked_allergen"]]
    if "promised_date" in kind:
        data["aimo"]["delivery_date"] = kind["promised_date"]
    if "total_minor" in kind:
        amt = kind["total_minor"]
        data["line_items"][0]["totals"] = [{"type": "subtotal", "amount": amt}, {"type": "total", "amount": amt}]
        data["totals"] = [{"type": "subtotal", "amount": amt}, {"type": "total", "amount": amt}]
    if "merchant_id" in kind:
        data["merchant"] = {"id": kind["merchant_id"], "name": "Untrusted Supplier"}
    return AimoCheckout.model_validate(data)


# ---------- Policy loader ----------


def test_load_policy_reads_default_and_explicit_path(tmp_path, monkeypatch):
    import harness.policy as policy_module

    example_pol = BuyerPolicy.model_validate_json((EXAMPLES / "policy.demo.json").read_text(encoding="utf-8"))

    default_pol = load_policy()
    assert isinstance(default_pol, BuyerPolicy)
    assert default_pol.policy_id == "pol_demo_hotel_1"
    assert default_pol.autonomous_limit_minor == 150000

    # When scenarios/policy.demo.json exists, the default and the explicit path both read it
    scenario_path = ROOT / "scenarios" / "policy.demo.json"
    if scenario_path.exists():
        assert load_policy(scenario_path) == default_pol

    # When the scenario file is missing, both fall back cleanly to the contract example
    missing = tmp_path / "scenarios" / "policy.demo.json"
    monkeypatch.setattr(policy_module, "SCENARIO_POLICY", missing)
    assert load_policy() == example_pol
    assert load_policy(missing) == example_pol

    custom_path = tmp_path / "custom.policy.json"
    custom_path.write_text((EXAMPLES / "policy.demo.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert load_policy(custom_path) == example_pol


# ---------- Table of required L3 rule cases ----------


@pytest.mark.parametrize(
    ("case_name", "checkout_fn", "now_ts", "sig", "judge_fn", "expected_decision", "expected_triggered"),
    [
        (
            "eur_1010_auto",
            lambda: AimoCheckout.model_validate(_example("checkout.act1.json")),
            NOW,
            SIG_PASS,
            None,
            "auto",
            set(),
        ),
        (
            "eur_2020_human",
            lambda: AimoCheckout.model_validate(_example("checkout.act2.json")),
            NOW,
            SIG_PASS,
            None,
            "human",
            {"spend-limit"},
        ),
        (
            "missing_allergen_data_human",
            lambda: _mutate_act1(missing_allergen=True),
            NOW,
            SIG_PASS,
            None,
            "human",
            {"allergen-data-known"},
        ),
        (
            "blocked_allergen_deny",
            lambda: _mutate_act1(blocked_allergen="AP"),
            NOW,
            SIG_PASS,
            None,
            "deny",
            {"allergen-not-blocked"},
        ),
        (
            "allergens_changed_by_substitute_human",
            _build_oat_substitution_checkout,
            NOW,
            SIG_PASS,
            _fake_judge(0.95, 0.95),  # even if judge says auto, allergen change keeps verdict at human
            "human",
            {"allergen-unchanged-on-substitution"},
        ),
        (
            "delivery_later_than_requested_human",
            lambda: _mutate_act1(promised_date="2026-11-17"),
            NOW,
            SIG_PASS,
            None,
            "human",
            {"delivery-on-time"},
        ),
        (
            "expired_quote_deny",
            lambda: AimoCheckout.model_validate(_example("checkout.act1.json")),
            AFTER_EXPIRY,
            SIG_PASS,
            None,
            "deny",
            {"quote-not-expired"},
        ),
        (
            "bad_signature_deny",
            lambda: _mutate_act1(total_minor=71000),
            NOW,
            SIG_DENY,
            None,
            "deny",
            {"quote-signature"},
        ),
        (
            "two_rules_at_once_keep_stricter_deny_beats_human",
            lambda: _mutate_act1(total_minor=202000, blocked_allergen="AN"),
            NOW,
            SIG_PASS,
            None,
            "deny",
            {"spend-limit", "allergen-not-blocked"},
        ),
        (
            "judge_unreachable_human",
            _build_oat_substitution_checkout,
            NOW,
            SIG_PASS,
            _fake_judge(None, None),
            "human",
            {"allergen-unchanged-on-substitution", "substitution-within-preferences"},
        ),
    ],
    ids=lambda val: val if isinstance(val, str) else "",
)
def test_rules_table(
    case_name: str,
    checkout_fn,
    now_ts: datetime,
    sig: RuleResult,
    judge_fn,
    expected_decision: Decision,
    expected_triggered: set[str],
):
    policy = load_policy()
    verdict = evaluate(policy, checkout_fn(), now_ts, sig, judge=judge_fn)

    assert verdict.decision == expected_decision, f"{case_name}: got {verdict.decision}"
    assert verdict.signer == ("agent" if expected_decision == "auto" else None)
    if expected_decision == "deny":
        assert verdict.deadline is None
    else:
        assert verdict.deadline is not None

    triggered = {r.rule_id for r in verdict.rules if r.outcome != "pass"}
    assert triggered == expected_triggered


# ---------- Substitution pre-acceptance and judge routing ----------


def test_pre_accepted_substitution_passes_without_calling_judge():
    policy = load_policy()
    checkout = AimoCheckout.model_validate(_example("checkout.act3.json"))

    def _exploding_judge(*_args, **_kwargs):
        raise AssertionError("Judge should not be called for a pre-accepted substitute")

    verdict = evaluate(policy, checkout, NOW, SIG_PASS, judge=_exploding_judge)
    assert verdict.decision == "auto"
    assert verdict.signer == "agent"
    assert verdict.judge == []
    by_id = {r.rule_id: r.outcome for r in verdict.rules}
    assert by_id["allergen-unchanged-on-substitution"] == "pass"
    assert by_id["substitution-within-preferences"] == "pass"


def test_non_pre_accepted_same_allergens_goes_to_judge_and_respects_exception():
    policy = load_policy().model_copy(
        update={"substitution": load_policy().substitution.model_copy(update={"pre_accepted": "none"})}
    )
    checkout = AimoCheckout.model_validate(_example("checkout.act3.json"))

    verdict_auto = evaluate(policy, checkout, NOW, SIG_PASS, judge=_fake_judge(0.96, 0.97))
    assert verdict_auto.decision == "auto"
    assert len(verdict_auto.judge) == 2

    verdict_unsure = evaluate(policy, checkout, NOW, SIG_PASS, judge=_fake_judge(0.45, 0.90))
    assert verdict_unsure.decision == "human"
    sub_rule = next(r for r in verdict_unsure.judge if r.question_key == "within_preferences")
    assert sub_rule.routed == "human"

    def _raising_judge(*_args, **_kwargs):
        raise TimeoutError("judge timed out")

    verdict_err = evaluate(policy, checkout, NOW, SIG_PASS, judge=_raising_judge)
    assert verdict_err.decision == "human"
    assert [a.probability for a in verdict_err.judge] == [None, None]


def test_unallowed_merchant_is_denied():
    policy = load_policy()
    verdict = evaluate(policy, _mutate_act1(merchant_id="rogue-wholesaler"), NOW, SIG_PASS)
    assert verdict.decision == "deny"
    assert date.fromisoformat("2026-11-16") == _mutate_act1().aimo.delivery_date


# ---------- Parity with all four contract/examples/verdict.*.json ----------


def test_matches_verdict_auto_example():
    expected = Verdict.model_validate(_example("verdict.auto.json"))
    checkout = AimoCheckout.model_validate(_example("checkout.act1.json"))
    actual = evaluate(
        load_policy(),
        checkout,
        expected.decided_at,
        SIG_PASS,
        checkout_hash=expected.checkout_hash,
    )
    assert actual == expected


def test_matches_verdict_human_spend_example():
    expected = Verdict.model_validate(_example("verdict.human.spend.json"))
    checkout = AimoCheckout.model_validate(_example("checkout.act2.json"))
    actual = evaluate(
        load_policy(),
        checkout,
        expected.decided_at,
        SIG_PASS,
        checkout_hash=expected.checkout_hash,
    )
    assert actual == expected


def test_matches_verdict_human_substitution_example():
    expected = Verdict.model_validate(_example("verdict.human.substitution.json"))
    checkout = _build_oat_substitution_checkout()
    actual = evaluate(
        load_policy(),
        checkout,
        expected.decided_at,
        SIG_PASS,
        judge=_fake_judge(0.07, 0.22),
        checkout_hash=expected.checkout_hash,
    )
    assert actual == expected


def test_matches_verdict_deny_example():
    expected = Verdict.model_validate(_example("verdict.deny.json"))
    checkout = _mutate_act1(total_minor=71000)
    actual = evaluate(
        load_policy(),
        checkout,
        expected.decided_at,
        SIG_DENY,
        checkout_hash=expected.checkout_hash,
    )
    assert actual == expected


# ---------- Real-world edge cases & anti-bypass checks ----------


def test_agent_picked_substitute_or_unlisted_substitute_is_never_pre_accepted():
    """Arla Cafe milk (463380) shares category 10400 and allergen AM with 469363,
    but must call the judge instead of slipping through on `auto`."""
    policy = load_policy()
    data = copy.deepcopy(_example("checkout.act3.json"))
    # Case 1: agent explicitly requested `substitute_with` -> must call judge
    data["aimo"]["requested"][0]["substitute_with"] = "463380"
    data["line_items"][1]["item"] = {"id": "463380", "title": "Arla Cafè milk 1 L UHT lactose free", "price": 265}
    data["aimo"]["lines"]["li-2"]["product_id"] = "463380"
    data["aimo"]["alternatives"] = [
        {
            "for_product_id": "469363",
            "product_id": "463380",
            "tier": "best",
            "comparison_price_minor": 265,
            "comparison_unit": "L",
            "why": "same category, same declared allergens",
            "chosen": True,
        }
    ]
    checkout_override = AimoCheckout.model_validate(data)
    verdict = evaluate(policy, checkout_override, NOW, SIG_PASS, judge=_fake_judge(0.09, 0.38))
    assert verdict.decision == "human"
    assert len(verdict.judge) == 2

    # Case 2: even without `substitute_with`, a cheapest-in-category guess not listed in catalog calls the judge
    data2 = copy.deepcopy(data)
    data2["aimo"]["requested"][0].pop("substitute_with", None)
    checkout_unlisted = AimoCheckout.model_validate(data2)
    verdict2 = evaluate(policy, checkout_unlisted, NOW, SIG_PASS, judge=_fake_judge(0.09, 0.38))
    assert verdict2.decision == "human"
    assert len(verdict2.judge) == 2


def test_lost_label_origin_or_dietary_claim_is_never_pre_accepted():
    policy = load_policy()
    # Dropping GOODS_FROM_FINLAND_BLUE_SWAN on li-2 forces judge evaluation
    data = copy.deepcopy(_example("checkout.act3.json"))
    data["aimo"]["lines"]["li-2"]["labels"] = []
    checkout_no_label = AimoCheckout.model_validate(data)
    verdict = evaluate(policy, checkout_no_label, NOW, SIG_PASS, judge=_fake_judge(0.50, 0.90))
    assert verdict.decision == "human"
    assert len(verdict.judge) == 2

    # Dropping NO_ADDED_SUGARS in enriched product_cards (e.g. plain coffee milk -> vanilla coffee milk) calls judge
    intact = AimoCheckout.model_validate(_example("checkout.act3.json"))
    cards = {
        "469363": {"nutritional_claims": ["FREE_FROM_LACTOSE", "NO_ADDED_SUGARS"]},
        "464201": {"nutritional_claims": ["FREE_FROM_LACTOSE"]},
    }
    verdict_claims = evaluate(policy, intact, NOW, SIG_PASS, judge=_fake_judge(0.02, 0.10), product_cards=cards)
    assert verdict_claims.decision == "human"
    assert len(verdict_claims.judge) == 2


def test_uncovered_shortfall_requires_human_approval():
    """If alternatives are disabled and only 384 L of 600 L can be delivered, never auto-sign silently."""
    policy = load_policy()
    data = copy.deepcopy(_example("checkout.act3.json"))
    data["line_items"] = [data["line_items"][0]]
    data["aimo"]["lines"] = {"li-1": data["aimo"]["lines"]["li-1"]}
    data["totals"] = data["line_items"][0]["totals"]
    data["aimo"]["alternatives"] = []
    partial_checkout = AimoCheckout.model_validate(data)

    verdict = evaluate(policy, partial_checkout, NOW, SIG_PASS)
    assert verdict.decision == "human"
    sub_rule = next(r for r in verdict.rules if r.rule_id == "substitution-within-preferences")
    assert sub_rule.outcome == "human"
    assert "uncovered shortfall" in sub_rule.message
    assert "216" in sub_rule.message


def test_approval_deadline_never_exceeds_quote_expiry_and_expired_policy_requires_human():
    policy = load_policy()
    data = copy.deepcopy(_example("checkout.act2.json"))
    # Replay quotes expire 24h after recording (13:29:07), earlier than the 17:00 cut-off
    data["expires_at"] = "2026-11-15T13:29:07+02:00"
    data["aimo"]["closing_time"] = "2026-11-15T17:00:00+02:00"
    checkout = AimoCheckout.model_validate(data)

    verdict = evaluate(policy, checkout, NOW, SIG_PASS)
    assert verdict.decision == "human"
    assert verdict.deadline == datetime.fromisoformat("2026-11-15T13:29:07+02:00")

    # Once `policy.valid_until` passes, autonomous open mandates are expired -> human must sign
    expired_policy = policy.model_copy(update={"valid_until": datetime.fromisoformat("2026-11-14T12:00:00+02:00")})
    act1 = AimoCheckout.model_validate(_example("checkout.act1.json"))
    verdict_exp_pol = evaluate(expired_policy, act1, NOW, SIG_PASS)
    assert verdict_exp_pol.decision == "human"
    spend_rule = next(r for r in verdict_exp_pol.rules if r.rule_id == "spend-limit")
    assert spend_rule.outcome == "human"
