"""The demo driver (scenarios/run.py) through the real gateway and the real harness, in replay mode.

The menu's products are not in the recorded answers yet (step A11), so the flow is tested on the recorded milk:
1,000 litres is under the EUR 1,500 limit (the agent signs), 2,000 litres is above it (a human signs, and an agent
that signs it anyway is refused by Valio).
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from contract.models import DemoState, Need
from harness.app import create_app as create_harness
from merchant import audit, payments, store
from merchant.app import app as gateway_app
from scenarios.run import INGREDIENTS, KITCHEN, SCENARIOS, Driver, DriverError, Scenario, create_app, request_of

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
    Scenario(
        "attack",
        "Attack",
        "Three bad mandates.",
        "Order 2,000 litres.",
        (("464306", 2000, "L"),),
        MONDAY,
        attack=True,
        other_needs=(("464306", 1000, "L"),),
    ),
    Scenario(
        "attack-under-the-cap",
        "No attack",
        "Valio would accept this one.",
        "Order 1,000 litres.",
        (("464306", 1000, "L"),),
        MONDAY,
        attack=True,
        other_needs=(("464306", 500, "L"),),
    ),
)


@pytest.fixture
def services(tmp_path, monkeypatch):
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN)
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    with TestClient(gateway_app) as gateway:
        quiet = lambda *_a, **_kw: None  # a test must never message the chef's phone
        harness_app = create_harness(http_client=gateway, judge_fn=lambda *_a, **_kw: [], notify_fn=quiet)
        with TestClient(harness_app) as harness:
            yield Driver(MILK, gateway=gateway, harness=harness), harness


@pytest.fixture
def restaurant(services):
    """The real scenarios of the demo, on the answers recorded for the restaurant's menu (delivery on 19/11)."""
    driver, harness = services
    return Driver(gateway=driver.gateway, harness=harness), harness


def steps_of(state: DemoState) -> dict:
    return {step.key: step for step in state.steps}


def test_nothing_has_run_after_a_reset(services):
    driver, _ = services
    state = driver.reset()
    assert (state.scenario.status, state.scenario.id, state.request, state.quote) == ("idle", None, None, None)
    assert {step.status for step in state.steps} == {"pending"}
    assert [scenario.id for scenario in state.scenarios] == [scenario.id for scenario in MILK]


def test_an_order_inside_the_limit_is_signed_by_the_agent(services):
    driver, harness = services
    state = driver.run("normal-order")
    assert state.scenario.status == "done" and state.verdict.decision == "auto"
    assert (state.order.signed_by, state.order.total_minor) == ("agent", 101000)
    assert state.request.text == "I need 1,000 litres." and state.quote.id == state.order.checkout_id

    steps = steps_of(state)
    assert steps["open_mandate"].status == "done" and "EUR 1,500.00" in steps["open_mandate"].detail
    # The fingerprint of the open payment mandate the harness holds, as the harness itself gives it.
    assert steps["open_mandate"].proof == harness.get("/mandates/open").json()["payment_hash"]
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


def test_three_bad_mandates_sent_straight_to_valio_are_all_refused(services):
    driver, _ = services
    state = driver.run("attack")
    assert state.scenario.status == "refused" and state.quote.total_minor() == 202000
    assert (state.verdict, state.authorization, state.approval, state.order) == (None, None, None, None)

    by_key = {attack.key: attack for attack in state.attacks}
    assert list(by_key) == ["above-cap", "changed-quote", "mandate-for-another-quote"]
    assert {attack.status for attack in state.attacks} == {"refused"}
    assert by_key["above-cap"].title == "The agent signs EUR 2,020.00 itself, above its EUR 1,500.00 cap"
    assert by_key["above-cap"].problems == [
        "The amount, EUR 2,020.00, is above the EUR 1,500.00 the agent may sign alone."
    ]
    assert "does not match the quote Valio Aimo signed" in by_key["changed-quote"].problems[0]
    assert "EUR 1,010.00" in by_key["mandate-for-another-quote"].title
    other_quote = by_key["mandate-for-another-quote"].problems  # the mandate itself is valid, for the other quote only
    assert len(other_quote) == 1 and other_quote[0].startswith("The mandate was signed for another quote (chk_")
    assert other_quote[0].endswith(f"not for this one ({state.quote.id}).")

    steps = steps_of(state)
    assert [steps[key].status for key in ("open_mandate", "signed_quote")] == ["done", "done"]
    assert steps["open_mandate"].proof and steps["open_mandate"].at  # the open mandates the leaked key came with
    assert steps["verdict"].status == "skipped" and "did not ask the harness" in steps["verdict"].detail
    assert (steps["closed_mandates"].signer, steps["closed_mandates"].status) == ("agent", "done")
    assert steps["merchant_verifies"].status == "refused" and "3 of 3 refused" in steps["merchant_verifies"].detail
    assert {steps[key].status for key in ("sandbox_payment", "signed_receipt")} == {"skipped"}

    # The harness never heard of it, Valio wrote one line per refusal, and nothing was ordered or booked.
    assert state.audit.buyer == []
    assert [event.action for event in state.audit.merchant] == ["quote_issued"] + ["order_refused"] * 3
    assert store.order_for_checkout(state.quote.id) is None
    assert payments.account(state.quote.aimo.customer).used_minor == 0
    assert driver.state() == state


def test_a_quote_under_the_cap_is_never_attacked(services):
    """Valio would accept an agent mandate for it: the driver stops before sending anything."""
    driver, _ = services
    with pytest.raises(DriverError, match="EUR 1,010.00 is within EUR 1,500.00, nothing sent") as stopped:
        driver.run("attack-under-the-cap")
    assert stopped.value.status_code == 500
    assert driver.state().scenario.status == "idle"
    assert [event.action for event in audit.events()] == ["quote_issued"]


# ---------- The demo itself, in replay mode: what the video is recorded on ----------


def test_replay_button_1_the_normal_order_is_signed_by_the_agent(restaurant):
    driver, _ = restaurant
    state = driver.run("normal-order")
    assert state.scenario.status == "done" and state.verdict.decision == "auto"
    assert (len(state.quote.line_items), state.order.total_minor, state.order.signed_by) == (10, 18689, "agent")
    assert state.quote.aimo.shortfalls == [] and state.order.payment.amount_minor == 18689
    # The answers keep the time Valio really gave them, later than the frozen clock of replay mode.
    assert state.quote.aimo.lines["li-1"].price.as_of.isoformat() == "2026-11-14T22:19:22+02:00"


def test_replay_button_2_the_squeaky_cheese_is_replaced_and_the_chef_signs(restaurant):
    driver, harness = restaurant
    state = driver.run("substitution")
    assert state.scenario.status == "waiting_for_human" and state.verdict.decision == "human"
    (shortfall,) = state.quote.aimo.shortfalls
    assert (shortfall.product_id, shortfall.reason) == ("474880", "late_delivery")
    # The gateway's own pick, with no cheddar cream before it: the closest name of the category.
    assert [(a.product_id, a.tier, a.chosen) for a in state.quote.aimo.alternatives] == [("475072", "best", True)]
    assert (state.quote.line_items[0].item.id, state.quote.total_minor()) == ("475072", 11487)

    decision = {"decision": "approve", "decided_by": "chef"}
    assert harness.post(f"/approvals/{state.approval.approval_id}/decision", json=decision).status_code == 200
    state = driver.state()
    assert state.scenario.status == "done" and state.order.signed_by == "human"
    assert {step.status for step in state.steps} == {"done"}


def test_replay_button_3_the_three_bad_mandates_are_refused(restaurant):
    driver, _ = restaurant
    state = driver.run("attack")
    assert state.scenario.status == "refused" and state.quote.total_minor() == 178315
    assert [attack.status for attack in state.attacks] == ["refused"] * 3
    assert state.attacks[0].problems == [
        "The amount, EUR 1,783.15, is above the EUR 1,500.00 the agent may sign alone."
    ]
    assert "EUR 186.89" in state.attacks[2].title


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
    name = {"normal-order": "normal-order", "substitution": "substitution.pending", "attack": "attack"}[scenario.id]
    recorded = json.loads((EXAMPLES / f"demo-state.{name}.json").read_text(encoding="utf-8"))
    assert request_of(scenario) == recorded["request"]
    assert recorded["kitchen"] == KITCHEN
    assert {"id": scenario.id, "title": scenario.title, "hint": scenario.hint} in recorded["scenarios"]


def test_an_outside_agent_order_shows_on_the_page_as_the_chat_order(services):
    """The MCP door: a quote and an authorization asked through the driver become the scenario on screen."""
    driver, _ = services
    page = TestClient(create_app(driver))
    needs = [{"product_id": "464306", "amount": 1000, "unit": "L"}]
    quoted = page.post("/agent/checkouts", json={"needs": needs, "delivery_date": MONDAY})
    assert quoted.status_code == 200 and "checkout_jwt" not in quoted.json()  # the agent never sees a token
    checkout_id = quoted.json()["checkout_id"]
    assert page.get("/state").json()["scenario"]["status"] == "idle"  # a quote alone puts nothing on screen

    sentence = "We need 1,000 litres of lactose-free milk for Monday."
    authorized = page.post("/agent/authorize", json={"checkout_id": checkout_id, "request_text": sentence})
    assert authorized.status_code == 200 and authorized.json()["status"] == "ordered"

    state = DemoState.model_validate(page.get("/state").json())
    assert (state.scenario.id, state.scenario.title, state.scenario.status) == ("chat-order", "Chat order", "done")
    assert "chat-order" in [s.id for s in state.scenarios] and state.request.text == sentence
    assert state.order.order_id == authorized.json()["order_id"] and state.order.signed_by == "agent"
    assert {step.status for step in state.steps} == {"done"}
    assert state.request.lines[0].name != "464306"  # the kitchen's name, or the quote's title: never a bare id

    unknown = page.post("/agent/authorize", json={"checkout_id": "chk_nobody", "request_text": sentence})
    assert unknown.status_code == 404


def test_a_product_off_the_menu_takes_its_name_from_the_quote(services):
    driver, _ = services
    assert "465039" not in INGREDIENTS  # a lactose-free milk the catalog lists as a substitute, not on the menu
    issued = driver.agent_quote([Need(product_id="465039", amount=10, unit="L")], MONDAY)
    chat = Scenario("chat-order", "Chat order", "", "Ten litres.", (("465039", 10, "L"),), MONDAY)
    claims = issued.checkout.aimo.lines[issued.checkout.line_items[0].id]
    named = claims.substitute_for.name if claims.substitute_for else issued.checkout.line_items[0].item.title
    line = request_of(chat, issued)["lines"][0]
    assert (line["name"], line["dish"]) == (named, "Asked in the chat")
