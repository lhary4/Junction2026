"""The demo driver (scenarios/run.py) through the real gateway and the real harness, in replay mode.

The menu's products are not in the recorded answers yet (step A11), so the flow is tested on the recorded milk:
1,000 litres is under the EUR 1,500 limit (the agent signs), 2,000 litres is above it (a human signs).
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from contract.models import DemoState
from harness.app import create_app as create_harness
from merchant.app import app as gateway_app
from scenarios.run import KITCHEN, SCENARIOS, Driver, Scenario, create_app, request_of

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "contract" / "examples"
FROZEN = "2026-11-14T13:29:07+02:00"  # contract/fixtures/valio/frozen_now.txt
MONDAY = "2026-11-16"

MILK = (
    Scenario(
        "normal-order", "Normal order", "Under the limit.", "I need 1,000 litres.", (("464306", 1000, "L"),), MONDAY
    ),
    Scenario(
        "substitution", "Above the limit", "A human signs.", "Make it 2,000 litres.", (("464306", 2000, "L"),), MONDAY
    ),
    Scenario("other-day", "Not recorded", "Replay has no answer.", "For Tuesday.", (("464306", 1, "L"),), "2026-11-17"),
)


@pytest.fixture
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN)
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    with TestClient(gateway_app) as gateway:
        harness_app = create_harness(http_client=gateway, judge_fn=lambda *_a, **_kw: [])
        with TestClient(harness_app) as harness:
            yield Driver(MILK, gateway=gateway, harness=harness), harness


def steps_of(state: DemoState) -> dict:
    return {step.key: step for step in state.steps}


def test_nothing_has_run_after_a_reset(services):
    driver, _ = services
    state = driver.reset()
    assert (state.scenario.status, state.scenario.id, state.request, state.quote) == ("idle", None, None, None)
    assert {step.status for step in state.steps} == {"pending"}
    assert [scenario.id for scenario in state.scenarios] == ["normal-order", "substitution", "other-day"]


def test_an_order_inside_the_limit_is_signed_by_the_agent(services):
    driver, _ = services
    state = driver.run("normal-order")
    assert state.scenario.status == "done" and state.verdict.decision == "auto"
    assert (state.order.signed_by, state.order.total_minor) == ("agent", 101000)
    assert state.request.text == "I need 1,000 litres." and state.quote.id == state.order.checkout_id

    steps = steps_of(state)
    assert steps["open_mandate"].status == "done" and "EUR 1,500.00" in steps["open_mandate"].detail
    assert steps["signed_quote"].proof == state.order.checkout_hash
    assert (steps["closed_mandates"].signer, steps["closed_mandates"].proof) == ("agent", state.order.mandate_reference)
    assert steps["merchant_verifies"].status == "done" and "spend cap" in steps["merchant_verifies"].detail
    assert "EUR 1,010.00, within the EUR 1,500.00 cap" in steps["merchant_verifies"].detail
    assert steps["signed_receipt"].status == "done" and steps["signed_receipt"].proof
    # The charge is a sandbox, and the step says so in words the page shows as they are.
    payment = steps["sandbox_payment"]
    assert (payment.status, payment.proof, payment.at) == (
        "done",
        state.order.payment.payment_id,
        state.order.accepted_at,
    )
    assert payment.detail.startswith(
        "Sandbox payment: EUR 1,010.00 booked on invoice-account:demo-restaurant-helsinki."
    )
    assert payment.detail.endswith("No real money moves.")
    assert {step.status for step in state.steps} == {"done"}

    assert [event.action for event in state.audit.merchant] == [
        "quote_issued",
        "mandate_verified",
        "payment_captured",
        "order_accepted",
    ]
    assert state.audit.buyer and all(event.checkout_id == state.quote.id for event in state.audit.buyer)
    assert driver.state() == state  # asking again changes nothing


def test_an_order_above_the_limit_waits_for_the_chef_then_is_signed_by_the_chef(services):
    driver, harness = services
    state = driver.run("substitution")
    assert state.scenario.status == "waiting_for_human" and state.verdict.decision == "human"
    assert state.approval.status == "pending" and state.order is None
    steps = steps_of(state)
    assert (steps["closed_mandates"].signer, steps["closed_mandates"].status) == ("manager", "waiting")
    assert steps["merchant_verifies"].status == "pending"

    # The chef's decision goes from the page straight to the harness, never through the driver.
    decision = {"decision": "approve", "decided_by": "chef"}
    assert harness.post(f"/approvals/{state.approval.approval_id}/decision", json=decision).status_code == 200

    state = driver.state()
    assert state.scenario.status == "done" and state.order.signed_by == "human"
    steps = steps_of(state)
    assert (steps["closed_mandates"].signer, steps["closed_mandates"].status) == ("manager", "done")
    assert steps["closed_mandates"].proof == state.order.mandate_reference
    assert "EUR 2,020.00, no cap: the chef signed this exact order" in steps["merchant_verifies"].detail
    assert steps["sandbox_payment"].status == "done" and state.order.payment.amount_minor == 202000
    assert state.approval.status == "approved" and state.approval.decided_by == "chef"


def test_an_order_the_chef_rejects_ends_refused_with_nothing_sent_to_valio(services):
    driver, harness = services
    state = driver.run("substitution")
    decision = {"decision": "reject", "decided_by": "chef"}
    assert harness.post(f"/approvals/{state.approval.approval_id}/decision", json=decision).status_code == 200

    state = driver.state()
    assert state.scenario.status == "refused" and state.order is None
    steps = steps_of(state)
    assert steps["closed_mandates"].status == "refused" and "rejected" in steps["closed_mandates"].detail
    assert {steps[key].status for key in ("merchant_verifies", "sandbox_payment", "signed_receipt")} == {"skipped"}
    assert [event.action for event in state.audit.merchant] == ["quote_issued"]


def test_routes_run_state_reset_and_errors(services):
    driver, _ = services
    page = TestClient(create_app(driver))
    assert DemoState.model_validate(page.get("/state").json()).scenario.status == "idle"

    ran = page.post("/scenarios/normal-order/run", json={})
    assert ran.status_code == 200 and DemoState.model_validate(ran.json()).scenario.status == "done"
    assert page.get("/state").json() == ran.json()
    assert page.post("/reset", json={}).json()["scenario"] == {"id": None, "title": None, "status": "idle"}

    assert page.post("/scenarios/caviar/run", json={}).status_code == 404
    # The gateway cannot quote this one: the page gets its sentence, and the driver shows nothing half-done.
    failed = page.post("/scenarios/other-day/run", json={})
    assert failed.status_code == 502 and "only has answers for delivery on 2026-11-16" in failed.json()["detail"]
    assert page.get("/state").json()["scenario"]["status"] == "idle"

    answer = page.get("/state", headers={"Origin": "http://localhost:8002"})
    assert answer.headers["access-control-allow-origin"] == "http://localhost:8002"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.id)
def test_the_restaurant_scenarios_ask_what_the_recorded_examples_asked(scenario):
    """The page's stock files and its replay mode are built on the examples: the driver must ask for the same lines."""
    name = {"normal-order": "normal-order", "substitution": "substitution.pending"}[scenario.id]
    recorded = json.loads((EXAMPLES / f"demo-state.{name}.json").read_text(encoding="utf-8"))
    assert request_of(scenario) == recorded["request"]
    assert recorded["kitchen"] == KITCHEN
    assert {"id": scenario.id, "title": scenario.title, "hint": scenario.hint} in recorded["scenarios"]
