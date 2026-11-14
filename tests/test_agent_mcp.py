"""The MCP tools that read no service: get_kitchen reads the kitchen page's own files."""

from agent_mcp.server import get_kitchen
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
