"""The MCP tools: get_kitchen reads the kitchen page's own files, the others call a service."""

import json
from pathlib import Path

from mcp.server.mcpserver.exceptions import ToolError

from agent_mcp import server
from agent_mcp.server import ServiceError, get_kitchen, lookup_offers
from contract.models import Need
from scenarios.run import DELIVERY_DATE, WEEK_OF_DAIRY_AND_DRY_GOODS

EXAMPLES = Path(__file__).resolve().parent.parent / "contract" / "examples"


def example(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def answer(result):
    """A tool's two answers: the Markdown summary, and every field as JSON."""
    markdown, data = result.content
    return markdown.text, json.loads(data.text)


def test_get_kitchen_asks_what_button_1_asks():
    """'Order what is missing' in a chat and button 1 on the page must order the same lines, for the same day."""
    _, kitchen = answer(get_kitchen())
    asked = [(need["product_id"], need["amount"], need["unit"]) for need in kitchen["order_needs"]]
    assert sorted(asked) == sorted(WEEK_OF_DAIRY_AND_DRY_GOODS)
    assert kitchen["needed_by"] == DELIVERY_DATE


def test_get_kitchen_order_needs_fit_request_quote():
    markdown, kitchen = answer(get_kitchen())
    assert "**To order for Thu 19 Nov**" in markdown and "| 464306 Lactose-free semi-skimmed milk | 7.5 L |" in markdown
    assert all(Need.model_validate(need) for need in kitchen["order_needs"])  # no extra key the gateway would refuse
    assert len(kitchen["recipes"]) == 3 and len(kitchen["services"]) == 3
    assert all(line["to_order"] == 0 for line in kitchen["stock"]["lines"] if line["in_stock"] >= line["need"])


def test_a_refusal_reaches_the_agent_in_plain_words():
    """The MCP SDK hides the message of any exception that is not a ToolError: 'out of stock' must get through."""
    assert issubclass(ServiceError, ToolError)


def test_lookup_offers_asks_the_gateway_once(monkeypatch):
    asked = []
    offers = example("offers.act1.json")
    monkeypatch.setattr(
        server, "gateway", lambda method, path, **kwargs: asked.append((method, path, kwargs)) or offers
    )
    lookup_offers("potato", "2026-11-19", amount=10, unit="KG", limit=99)
    lookup_offers("potato", "2026-11-19")
    assert asked[0] == (
        "GET",
        "/offers",
        {"params": {"q": "potato", "delivery_date": "2026-11-19", "limit": 50, "amount": 10, "unit": "KG"}},
    )
    assert asked[1][2]["params"] == {"q": "potato", "delivery_date": "2026-11-19", "limit": 5}


# ---------- Readable answers ----------


def test_numbers_and_times_read_like_a_person_writes_them():
    assert server._number(0.20500000000000002) == "0.205" and server._number(2500.0) == "2,500"
    assert server._number("not_given") == "not given" and server._number(None) == "unknown"
    assert server._time("2026-11-14T22:49:24Z") == "Sun 15 Nov 00:49 (Helsinki)"
    assert server._day("2026-11-19") == "Thu 19 Nov"
    assert server._allergens({"contains": [], "free_from": [], "data": "missing"}) == "unknown (no data)"


def test_offers_are_a_table_with_indicative_prices(monkeypatch):
    monkeypatch.setattr(server, "gateway", lambda *args, **kwargs: example("offers.act1.json"))
    markdown, offers = answer(lookup_offers("milk", "2026-11-16", amount=1000, unit="L"))
    assert offers == example("offers.act1.json")  # every field still there, as JSON
    assert "Indicative prices" in markdown and "| ID | Product | Price | Per kg or L | To order |" in markdown
    assert markdown.count("\n| ") == 1 + len(offers["offers"])  # the header row, then one row per offer


def test_a_quote_says_what_covers_a_shortfall(monkeypatch):
    checkout = example("checkout.act3.json")
    monkeypatch.setattr(server, "driver", lambda *args, **kwargs: {"checkout_id": checkout["id"], "checkout": checkout})
    markdown, summary = answer(
        server.request_quote([{"product_id": "469363", "amount": 600, "unit": "L"}], "2026-11-16")
    )
    assert summary["checkout_id"] == "chk_act3_demo" and len(summary["lines"]) == 2
    assert "(substitute for 469363)" in markdown and "covered by" in markdown
    assert f"**Total: {summary['total_eur']:,.2f} EUR excl. tax** · delivery Mon 16 Nov" in markdown


def test_every_authorization_status_says_what_happens_next(monkeypatch):
    for state, status in example("authorization-status.json").items():
        monkeypatch.setattr(server, "harness", lambda *args, status=status, **kwargs: status)
        markdown, data = answer(server.get_authorization_status(status["checkout_id"]))
        assert data == status and status["checkout_id"] in markdown
        if state == "pending_approval":
            assert status["approval_url"] in markdown and "Sun 15 Nov 17:00 (Helsinki)" in markdown
        if status["order_id"]:
            assert status["order_id"] in markdown


def test_pending_approvals_list_only_what_waits_for_the_chef(monkeypatch):
    every_status = list(example("authorization-status.json").values())
    monkeypatch.setattr(server, "harness", lambda *args, **kwargs: every_status)
    markdown, pending = answer(server.list_pending_approvals())
    assert [s["checkout_id"] for s in pending] == ["chk_act2_demo"]
    assert markdown.startswith("**1 waiting for the chef's signature**") and "apr_7c1e0b52" in markdown
    monkeypatch.setattr(server, "harness", lambda *args, **kwargs: [])
    assert answer(server.list_pending_approvals()) == ("Nothing is waiting for the chef.", [])


def test_the_policy_reads_as_the_agent_s_mandate(monkeypatch):
    asked = []
    monkeypatch.setattr(server, "harness", lambda *args, **kwargs: asked.append(args) or example("policy.demo.json"))
    markdown, policy = answer(server.get_policy())
    assert asked == [("GET", "/policy")] and policy == example("policy.demo.json")
    assert "up to **1,500.00 EUR** an order" in markdown and "AP, AN" in markdown


def test_an_order_keeps_its_receipt_token_out(monkeypatch):
    monkeypatch.setattr(server, "gateway", lambda *args, **kwargs: example("order.json"))
    markdown, order = answer(server.get_order("ord_4b9d2a10"))
    assert "receipt_jwt" not in order and "ord_4b9d2a10" in markdown and "1,010.00 EUR" in markdown
