"""The MCP tools: get_kitchen reads the kitchen page's own files, the others call a service."""

from mcp.server.mcpserver.exceptions import ToolError

from agent_mcp import server
from agent_mcp.server import ServiceError, get_kitchen, lookup_offers
from contract.models import Need
from scenarios.run import DELIVERY_DATE, WEEK_OF_DAIRY_AND_DRY_GOODS


def test_get_kitchen_asks_what_button_1_asks():
    """'Order what is missing' in a chat and button 1 on the page must order the same lines, for the same day."""
    kitchen = get_kitchen()
    asked = [(need["product_id"], need["amount"], need["unit"]) for need in kitchen["order_needs"]]
    assert sorted(asked) == sorted(WEEK_OF_DAIRY_AND_DRY_GOODS)
    assert kitchen["needed_by"] == DELIVERY_DATE


def test_get_kitchen_order_needs_fit_request_quote():
    kitchen = get_kitchen()
    assert all(Need.model_validate(need) for need in kitchen["order_needs"])  # no extra key the gateway would refuse
    assert len(kitchen["recipes"]) == 3 and len(kitchen["services"]) == 3
    assert all(line["to_order"] == 0 for line in kitchen["stock"]["lines"] if line["in_stock"] >= line["need"])


def test_a_refusal_reaches_the_agent_in_plain_words():
    """The MCP SDK hides the message of any exception that is not a ToolError: 'out of stock' must get through."""
    assert issubclass(ServiceError, ToolError)


def test_lookup_offers_asks_the_gateway_once(monkeypatch):
    asked = []
    monkeypatch.setattr(server, "gateway", lambda method, path, **kwargs: asked.append((method, path, kwargs)) or {})
    lookup_offers("potato", "2026-11-19", amount=10, unit="KG", limit=99)
    lookup_offers("potato", "2026-11-19")
    assert asked[0] == (
        "GET",
        "/offers",
        {"params": {"q": "potato", "delivery_date": "2026-11-19", "limit": 50, "amount": 10, "unit": "KG"}},
    )
    assert asked[1][2]["params"] == {"q": "potato", "delivery_date": "2026-11-19", "limit": 5}
