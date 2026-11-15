"""The chef changes the buyer policy from the settings page: PUT /policy, PUT /policy/autonomous-limit, POST /policy/reset.

Run against the real gateway in replay mode, so the tests also prove that Valio accepts the open
mandate the harness signs again after a change.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from common.audit import AuditLog, default_log_path
from contract.models import AuditEvent, AuthorizationStatus, BuyerPolicy, Order, Verdict
from harness.app import create_app
from harness.policy import load_policy
from merchant.app import app as real_merchant_app
from scripts import dev

FROZEN_NOW = "2026-11-14T13:20:00+02:00"
FILE_LIMIT_MINOR = 150000  # the limit of the policy file: EUR 1,500.00


@pytest.fixture
def services(tmp_path, monkeypatch):
    """The real gateway in replay mode, and a harness that keeps its state in a temp folder."""
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN_NOW)
    with TestClient(real_merchant_app) as gateway:
        harness_app = create_app(http_client=gateway, judge_fn=lambda *_a, **_kw: [])
        with TestClient(harness_app) as harness:
            yield harness, gateway, tmp_path


def order_milk(harness: TestClient, gateway: TestClient, litres: int) -> AuthorizationStatus:
    """Ask Valio for a fresh quote of lactose-free milk (EUR 1.01 a litre) and ask the harness to order it."""
    quote = gateway.post(
        "/checkouts",
        json={
            "customer": "demo-restaurant-helsinki",
            "delivery_date": "2026-11-16",
            "needs": [{"product_id": "464306", "amount": litres, "unit": "L"}],
        },
    ).json()
    answer = harness.post(
        "/authorize",
        json={"checkout_id": quote["checkout_id"], "request_text": f"{litres} litres of lactose-free milk."},
    )
    assert answer.status_code == 200
    return AuthorizationStatus.model_validate(answer.json())


def audit_lines(harness: TestClient, *actions: str) -> list[AuditEvent]:
    events = [AuditEvent.model_validate(event) for event in harness.get("/audit").json()]
    return [event for event in events if event.action in actions]


def test_put_policy_changes_what_get_policy_returns_and_reset_restores_the_file(services):
    harness, _, tmp_path = services
    from_file = load_policy()
    assert BuyerPolicy.model_validate(harness.get("/policy").json()) == from_file
    assert from_file.autonomous_limit_minor == FILE_LIMIT_MINOR

    answer = harness.put(
        "/policy",
        json={
            "decided_by": "chef",
            "autonomous_limit_minor": 80000,
            "blocked_allergens": ["AP", "AN", "AM", "AP"],
            "late_delivery": "deny",
            "substitution": {"allowed": False, "judge_auto_threshold": 0.9},
        },
    )
    assert answer.status_code == 200
    changed = BuyerPolicy.model_validate(answer.json())
    assert changed.autonomous_limit_minor == 80000
    assert changed.blocked_allergens == ["AP", "AN", "AM"]  # the repeated code is dropped, the order is kept
    assert changed.late_delivery == "deny"
    assert changed.substitution.allowed is False
    assert changed.substitution.judge_auto_threshold == 0.9
    # What the body did not name stays as it was.
    assert changed.unknown_allergen_data == from_file.unknown_allergen_data
    assert changed.substitution.judge_floor == from_file.substitution.judge_floor
    assert changed.substitution.preferences_text == from_file.substitution.preferences_text
    assert changed.policy_id == from_file.policy_id and changed.valid_until == from_file.valid_until
    assert BuyerPolicy.model_validate(harness.get("/policy").json()) == changed

    # The change lives in the buyer's state folder, and the file of the repo is not written.
    assert (tmp_path / "buyer" / "policy.json").exists()
    assert load_policy() == from_file

    reset = harness.post("/policy/reset", json={"decided_by": "chef"})
    assert reset.status_code == 200
    assert BuyerPolicy.model_validate(reset.json()) == from_file
    assert BuyerPolicy.model_validate(harness.get("/policy").json()) == from_file
    assert not (tmp_path / "buyer" / "policy.json").exists()


def test_fresh_start_goes_back_to_the_policy_file(services):
    harness, _, tmp_path = services
    assert harness.put("/policy", json={"decided_by": "chef", "autonomous_limit_minor": 80000}).status_code == 200

    dev.empty_state({"AIMO_STATE_DIR": str(tmp_path)})  # what `scripts/dev.py --fresh` does

    assert BuyerPolicy.model_validate(harness.get("/policy").json()) == load_policy()


def test_same_order_is_auto_before_and_human_after_the_limit_is_lowered(services):
    harness, gateway, _ = services

    before = order_milk(harness, gateway, 1000)  # EUR 1,010.00, under the EUR 1,500.00 of the file
    assert before.status == "ordered" and before.decision == "auto" and before.signed_by == "agent"

    assert harness.put("/policy", json={"decided_by": "chef", "autonomous_limit_minor": 100000}).status_code == 200

    after = order_milk(harness, gateway, 1000)  # the same order, now above the EUR 1,000.00 limit
    assert after.status == "pending_approval" and after.decision == "human"
    assert after.signed_by is None and after.order_id is None

    verdict = Verdict.model_validate(harness.get(f"/verdicts/{after.checkout_id}").json())
    spend = next(rule for rule in verdict.rules if rule.rule_id == "spend-limit")
    assert spend.outcome == "human"
    assert spend.evidence == {"total_minor": 101000, "limit_minor": 100000}


def test_open_mandate_is_signed_again_with_the_new_cap_and_valio_accepts_it(services):
    harness, gateway, _ = services

    proofs = harness.get("/mandates/open").json()
    assert harness.get("/mandates/open").json() == proofs  # no change, no new signature

    assert harness.put("/policy", json={"decided_by": "chef", "autonomous_limit_minor": 250000}).status_code == 200

    new_proofs = harness.get("/mandates/open").json()
    assert new_proofs["policy_id"] == proofs["policy_id"]
    assert new_proofs["payment_hash"] != proofs["payment_hash"]  # the payment mandate carries the cap
    assert harness.get("/mandates/open").json() == new_proofs

    # EUR 2,020.00 was above the file's limit. Under the new one the agent signs, and Valio reads the new cap.
    status = order_milk(harness, gateway, 2000)
    assert status.status == "ordered" and status.signed_by == "agent" and status.order_id is not None
    order = Order.model_validate(gateway.get(f"/orders/{status.order_id}").json())
    assert order.mandate is not None and order.mandate.cap_minor == 250000

    # Back to the file: the same order waits for the chef again.
    assert harness.post("/policy/reset").status_code == 200
    assert order_milk(harness, gateway, 2000).status == "pending_approval"
    assert harness.get("/mandates/open").json()["payment_hash"] != new_proofs["payment_hash"]


@pytest.mark.parametrize(
    "body",
    [
        {"decided_by": "chef", "autonomous_limit_minor": 0},
        {"decided_by": "chef", "autonomous_limit_minor": -50000},
        {"decided_by": "chef", "autonomous_limit_minor": 1500.5},
        {"decided_by": "chef", "autonomous_limit_minor": "1500"},
        {"decided_by": "chef", "autonomous_limit_minor": True},
        {"decided_by": "chef", "currency": "USD"},  # a field this route cannot change
        {"decided_by": "chef", "autonomous_limit_minor": 50000, "approver": "someone@else.example"},
        {"decided_by": "chef", "substitution": {"surprise": 1}},
        {"decided_by": "chef", "substitution": {"judge_floor": 0.9}},  # above the 0.85 threshold in force
        {"decided_by": "chef", "substitution": {"judge_auto_threshold": 0.1}},  # under the 0.15 floor in force
        {"decided_by": "chef", "substitution": {"judge_floor": 0.6, "judge_auto_threshold": 0.5}},
        {"decided_by": "chef", "substitution": {"judge_auto_threshold": 1.5}},
        {"decided_by": "chef", "blocked_allergens": ["AP", " "]},
        {"decided_by": "chef", "late_delivery": "auto"},
        {"decided_by": "chef"},  # no editable field
        {"decided_by": "chef", "substitution": {}},
        {"decided_by": "chef", "autonomous_limit_minor": None},
        {"autonomous_limit_minor": 50000},  # nobody decided it
        {"decided_by": "", "autonomous_limit_minor": 50000},
    ],
)
def test_refused_change_answers_422_and_leaves_the_policy_as_it_was(services, body):
    harness, _, tmp_path = services
    before = harness.get("/policy").json()

    answer = harness.put("/policy", json=body)

    assert answer.status_code == 422
    assert harness.get("/policy").json() == before
    assert not (tmp_path / "buyer" / "policy.json").exists()
    assert harness.get("/audit").json() == []


def test_put_autonomous_limit_changes_the_limit_alone(services):
    harness, _, _ = services
    from_file = load_policy()

    answer = harness.put("/policy/autonomous-limit", json={"autonomous_limit_minor": 90000, "decided_by": "chef"})
    assert answer.status_code == 200
    changed = BuyerPolicy.model_validate(answer.json())
    assert changed == from_file.model_copy(update={"autonomous_limit_minor": 90000})
    assert BuyerPolicy.model_validate(harness.get("/policy").json()) == changed

    for refused in (
        {"autonomous_limit_minor": 0, "decided_by": "chef"},
        {"autonomous_limit_minor": 12.5, "decided_by": "chef"},
        {"autonomous_limit_minor": 50000},
        {"decided_by": "chef"},
        {"autonomous_limit_minor": 50000, "decided_by": "chef", "late_delivery": "deny"},
    ):
        assert harness.put("/policy/autonomous-limit", json=refused).status_code == 422
    assert BuyerPolicy.model_validate(harness.get("/policy").json()) == changed


def test_each_change_writes_one_line_in_the_buyer_audit_log(services):
    harness, _, _ = services

    limit = {"decided_by": "chef", "autonomous_limit_minor": 90000}
    assert harness.put("/policy", json=limit).status_code == 200
    (first,) = audit_lines(harness, "policy_changed")
    assert (first.side, first.actor) == ("buyer", "human")
    assert first.what == "Buyer rules changed: spending limit from 1500.00 EUR to 900.00 EUR."
    assert first.why == "Decided by chef."

    # The same values again: the answer is the policy in force, and nothing new is logged.
    again = harness.put("/policy", json=limit)
    assert again.status_code == 200 and again.json()["autonomous_limit_minor"] == 90000
    assert len(audit_lines(harness, "policy_changed")) == 1

    rules = {
        "decided_by": "Colette",
        "blocked_allergens": ["AP"],
        "unknown_allergen_data": "deny",
        "substitution": {"judge_floor": 0.2},
    }
    assert harness.put("/policy", json=rules).status_code == 200
    _, second = audit_lines(harness, "policy_changed")
    assert second.what == (
        "Buyer rules changed: blocked allergens from AP, AN to AP; "
        "missing allergen data from 'a human signs' to 'refused'; judge floor from 0.15 to 0.2."
    )
    assert second.why == "Decided by Colette."

    limit_alone = {"autonomous_limit_minor": 70000, "decided_by": "chef"}
    assert harness.put("/policy/autonomous-limit", json=limit_alone).status_code == 200
    assert len(audit_lines(harness, "policy_changed")) == 3

    assert harness.post("/policy/reset", json={"decided_by": "chef"}).status_code == 200
    (reset,) = audit_lines(harness, "policy_reset")
    assert reset.actor == "human"
    assert reset.what.startswith(
        "Buyer rules reset to the policy file: spending limit from 700.00 EUR to 1500.00 EUR; "
    )
    assert reset.why == "Decided by chef."

    # Nothing saved any more: a second reset has nothing to undo and logs nothing.
    assert harness.post("/policy/reset").status_code == 200
    assert len(audit_lines(harness, "policy_changed", "policy_reset")) == 4
    assert len(harness.get("/audit").json()) == 4
    assert AuditLog(default_log_path("buyer")).verify() is None


def test_pending_approval_keeps_its_verdict_when_the_limit_is_raised(services):
    harness, gateway, _ = services

    pending = order_milk(harness, gateway, 2000)  # EUR 2,020.00, above the EUR 1,500.00 of the file
    assert pending.status == "pending_approval" and pending.approval_id is not None
    verdict = harness.get(f"/verdicts/{pending.checkout_id}").json()
    approval = harness.get(f"/approvals/{pending.approval_id}").json()

    assert harness.put("/policy", json={"decided_by": "chef", "autonomous_limit_minor": 300000}).status_code == 200

    # The order would be `auto` under the new limit, but the card stays on the chef's page as it was.
    assert AuthorizationStatus.model_validate(harness.get(f"/authorizations/{pending.checkout_id}").json()) == pending
    assert harness.get(f"/verdicts/{pending.checkout_id}").json() == verdict
    assert harness.get(f"/approvals/{pending.approval_id}").json() == approval
    asked_again = harness.post(
        "/authorize", json={"checkout_id": pending.checkout_id, "request_text": "2000 litres of lactose-free milk."}
    )
    assert AuthorizationStatus.model_validate(asked_again.json()) == pending

    decided = harness.post(
        f"/approvals/{pending.approval_id}/decision",
        json={"decision": "approve", "decided_by": "chef@demo-restaurant.example"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "ordered" and decided.json()["signed_by"] == "human"


@pytest.mark.parametrize("path", ["/policy", "/policy/autonomous-limit"])
def test_put_is_allowed_from_a_page_on_another_localhost_port(services, path):
    harness, _, _ = services
    page = "http://localhost:8005"

    preflight = harness.options(
        path,
        headers={
            "Origin": page,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == page
    assert "PUT" in preflight.headers["access-control-allow-methods"]
    assert "content-type" in preflight.headers["access-control-allow-headers"].lower()

    answer = harness.put(path, json={"decided_by": "chef", "autonomous_limit_minor": 90000}, headers={"Origin": page})
    assert answer.status_code == 200
    assert answer.headers["access-control-allow-origin"] == page

    outside = harness.options(path, headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "PUT"})
    assert outside.status_code == 400


def test_saved_policy_file_can_be_set_for_tests_and_an_unreadable_one_falls_back_to_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN_NOW)
    saved = tmp_path / "elsewhere" / "policy.json"

    with TestClient(create_app(saved_policy_file=saved, judge_fn=lambda *_a, **_kw: [])) as harness:
        assert harness.put("/policy", json={"decided_by": "chef", "autonomous_limit_minor": 90000}).status_code == 200
        assert BuyerPolicy.model_validate_json(saved.read_text(encoding="utf-8")).autonomous_limit_minor == 90000
        assert not (tmp_path / "state" / "buyer" / "policy.json").exists()

        saved.write_text("{not json", encoding="utf-8")
        assert BuyerPolicy.model_validate(harness.get("/policy").json()) == load_policy()
