"""MCP server for the external buying agent, on the real services.

Exposes the tools of docs/contract.md, plus `get_kitchen`. `get_kitchen` reads the restaurant's own data, the files the
kitchen page reads (surface/static/kitchen/: recipes, bookings, stock count). Every other tool calls a running service,
so every fact comes from the gateway or the harness, never from this file:
- search and orders: the Valio gateway (MERCHANT_URL, default http://localhost:8001)
- authorization status: the buyer's harness (HARNESS_URL, default http://localhost:8002)
- quotes and authorizations: the demo driver (DRIVER_URL, default http://localhost:8003), which forwards them to the
  gateway and the harness, and shows the order on the kitchen page as the "Chat order"

Start the services first: uv run python scripts/dev.py

Run:  uv run python agent_mcp/server.py                         stdio, for Claude Desktop
      uv run python agent_mcp/server.py --http                  HTTP on http://127.0.0.1:8005/mcp
      uv run python agent_mcp/server.py --http abc.trycloudflare.com   the same, reachable through that tunnel host

The agent never sees a token: quotes come back as a readable summary, orders without their receipt token.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Literal, TypedDict

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

KITCHEN_DIR = Path(__file__).resolve().parent.parent / "surface" / "static" / "kitchen"  # the page's kitchen data
HTTP_PORT = 8005
ANSWER_TIMEOUT_SECONDS = 60  # a quote asks Valio twice, an authorization may ask the judge

SERVER_INSTRUCTIONS = (
    "You are an external wholesale buying agent connected to Valio Aimo and the buyer's guardrail harness. "
    "The buyer is a 50-cover restaurant in Helsinki. Follow these rules strictly:\n"
    "1. Never invent or guess any fact: prices, stock, totals, delivery dates, allergens, reliability, and carbon "
    "footprint must come exclusively from tool outputs. Product search results have no prices; call `request_quote` "
    "before stating any price or total. Report `unknown` certainty explicitly as unknown, never as safe or available.\n"
    "2. When the buyer says what they need, how much, and by when, complete the workflow without asking questions: "
    "`search_products` (one or two words of the product name, in English), then `request_quote` for the best match, "
    "then `authorize_checkout` so the buyer's harness decides whether the order is signed automatically or by a human.\n"
    "3. Always pass the buyer's exact original sentence verbatim as `request_text` when calling `authorize_checkout`.\n"
    "4. Human approvals never happen in chat. If `status` is `pending_approval`, state the reason, the `deadline` "
    "(order cut-off), and the `approval_url` where the approver must review and sign.\n"
    "5. For the menu, recipes, bookings, stock, or 'order what is missing', call `get_kitchen` first. Its "
    "`order_needs` is what to quote, exactly as given, with `needed_by` as the delivery date: no search is needed.\n"
    "6. Keep answers short: what was ordered, the total, who signed, the order id."
)

server = MCPServer("valio-aimo", instructions=SERVER_INSTRUCTIONS)


class NeedInput(TypedDict):
    """One item the buyer needs, expressed in buyer units (L, KG, or ST)."""

    product_id: str
    amount: float
    unit: Literal["L", "KG", "ST"]


class ServiceError(RuntimeError):
    """A service did not answer, or refused. The message is what the agent reads."""


def _url(name: str, default: str) -> str:
    return (os.environ.get(name) or default).rstrip("/")


def _call(method: str, base: str, path: str, **kwargs: Any) -> Any:
    service = base.split("://")[-1]
    try:
        response = httpx.request(method, base + path, timeout=ANSWER_TIMEOUT_SECONDS, **kwargs)
    except httpx.HTTPError as e:
        raise ServiceError(f"{service} does not answer on {path} (is scripts/dev.py running?): {e}") from e
    if response.status_code != 200:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise ServiceError(f"{service} answered HTTP {response.status_code} on {path}: {detail}")
    return response.json()


def gateway(method: str, path: str, **kwargs: Any) -> Any:
    return _call(method, _url("MERCHANT_URL", "http://localhost:8001"), path, **kwargs)


def harness(method: str, path: str, **kwargs: Any) -> Any:
    return _call(method, _url("HARNESS_URL", "http://localhost:8002"), path, **kwargs)


def driver(method: str, path: str, **kwargs: Any) -> Any:
    return _call(method, _url("DRIVER_URL", "http://localhost:8003"), path, **kwargs)


def _summarize_checkout(checkout_id: str, checkout: dict[str, Any]) -> dict[str, Any]:
    """Build a readable, token-free summary of a signed AimoCheckout."""
    aimo = checkout["aimo"]
    total_minor = next(t["amount"] for t in checkout["totals"] if t["type"] == "total")
    currency = checkout["currency"]

    lines_summary: list[dict[str, Any]] = []
    line_sentences: list[str] = []
    for item in checkout["line_items"]:
        claims = aimo["lines"][item["id"]]
        line_total_minor = next(t["amount"] for t in item["totals"] if t["type"] == "total")
        comp_price_eur = claims["comparison_price_minor"] / 100
        line_total_eur = line_total_minor / 100

        lines_summary.append(
            {
                "line_id": item["id"],
                "product_id": claims["product_id"],
                "title": item["item"]["title"],
                "quantity_sales_units": item["quantity"],
                "sales_unit": claims["sales_unit"],
                "base_quantity": claims["base_quantity"],
                "base_unit": claims["base_unit"],
                "unit_price_eur": round(item["item"]["price"] / 100, 2),
                "comparison_price_eur": round(comp_price_eur, 2),
                "comparison_unit": claims["comparison_unit"],
                "line_total_eur": round(line_total_eur, 2),
                "available_date": claims["available_date"],
                "closing_time": claims["closing_time"],
                "logistic_model": claims["logistic_model"],
                "substitute_for": claims["substitute_for"],
                "stock": claims["stock"],
                "price": claims["price"],
                "origin": claims["origin"],
                "allergens": claims["allergens"],
                "delivery_reliability": claims["delivery_reliability"],
                "carbon_footprint": claims["carbon_footprint"],
                "labels": claims["labels"],
            }
        )
        sub_note = f" (substitute for {claims['substitute_for']['product_id']})" if claims.get("substitute_for") else ""
        line_sentences.append(
            f"{item['quantity']} {claims['sales_unit']} ({claims['base_quantity']:g} {claims['base_unit']}) "
            f"x {claims['product_id']} {item['item']['title']}{sub_note} "
            f"at {comp_price_eur:.2f} EUR/{claims['comparison_unit']} = {line_total_eur:.2f} {currency}"
        )

    total_eur = total_minor / 100
    summary_text = (
        f"Quote {checkout_id} signed by {checkout['merchant']['name']}: "
        + "; ".join(line_sentences)
        + f". Total (excl. tax): {total_eur:.2f} {currency}. "
        f"Delivery: {aimo['delivery_date']}. Order cut-off / quote expires: {checkout['expires_at']}."
    )
    if aimo.get("shortfalls"):
        summary_text += f" Shortfalls: {len(aimo['shortfalls'])}."

    return {
        "checkout_id": checkout_id,
        "merchant": checkout["merchant"],
        "signed_by_merchant": True,
        "currency": currency,
        "total_minor": total_minor,
        "total_eur": round(total_eur, 2),
        "totals_exclude_tax": aimo["totals_exclude_tax"],
        "requested_delivery_date": aimo["requested_delivery_date"],
        "delivery_date": aimo["delivery_date"],
        "closing_time": aimo["closing_time"],
        "expires_at": checkout["expires_at"],
        "summary": summary_text,
        "lines": lines_summary,
        "shortfalls": aimo.get("shortfalls", []),
        "alternatives": aimo.get("alternatives", []),
    }


def _kitchen_file(name: str) -> dict[str, Any]:
    return json.loads((KITCHEN_DIR / name).read_text(encoding="utf-8"))


@server.tool()
def get_kitchen() -> dict[str, Any]:
    """The restaurant's own kitchen data: the menu's recipes, the bookings of the coming services, and the stock count.

    Call it for any question about the menu, recipes, bookings, stock, or what the kitchen needs to order.
    `order_needs` lists what is short for the coming services (need minus stock, computed by the kitchen's system),
    ready to pass as `needs` to `request_quote`, with `needed_by` (the first service) as `delivery_date`.
    Never recompute or round these quantities yourself.
    """
    recipes = _kitchen_file("recipes.json")
    bookings = _kitchen_file("bookings.json")
    stock = _kitchen_file("stock.normal-order.json")
    services = bookings["services"]
    short = [line for line in stock["lines"] if line["to_order"] > 0]
    return {
        "restaurant": "Demo Restaurant Helsinki (synthetic sample data, not Valio data)",
        "covers_per_service": recipes["covers_per_service"],
        "recipes": [
            {
                "course": recipe["course"],
                "dish": f"{recipe['name']}, {recipe['with']}",
                "ingredients": [
                    {"product_id": i["product_id"], "name": i["name"], "per_service": i["per_service"]}
                    for i in recipe["ingredients"]
                ],
            }
            for recipe in recipes["recipes"]
        ],
        "services": [
            {"date": s["date"], "meal": s["meal"], "booked": s["booked"], "projected": s["projected"]} for s in services
        ],
        "stock": {
            "counted_at": stock["counted_at"],
            "counted_by": stock["counted_by"],
            "for_services": stock["for_services"],
            "lines": [
                {key: line[key] for key in ("product_id", "name", "unit", "need", "in_stock", "to_order", "dishes")}
                for line in stock["lines"]
            ],
        },
        "needed_by": services[0]["date"],
        "order_needs": [
            {"product_id": line["product_id"], "amount": line["to_order"], "unit": line["unit"]} for line in short
        ],
    }


@server.tool()
def search_products(query: str, limit: int = 5) -> dict[str, Any]:
    """Search the Valio Aimo catalog and return matching product cards without prices.

    Every word of `query` must be in the product name: use one or two words, in English (for example 'mozzarella',
    'whipping cream'). Product cards include pack sizes, allergens (`data='missing'` never means allergen-free),
    origin, historical delivery reliability, estimated carbon footprint, and sustainability labels, each with its
    source and certainty (`measured`, `declared`, `estimated`, or `unknown`).
    Prices and live stock are NOT in product cards: never guess or state a price before calling `request_quote`.
    """
    return gateway("GET", "/products/search", params={"q": query, "limit": max(1, min(int(limit), 50))})


@server.tool()
def request_quote(needs: list[NeedInput], delivery_date: str) -> dict[str, Any]:
    """Request a Valio Aimo ES256-signed quote for the buyer's product needs and target delivery date.

    Args:
        needs: List of `{product_id, amount, unit}` items (`unit` is `'L'`, `'KG'`, or `'ST'`).
        delivery_date: Requested delivery date in ISO format `YYYY-MM-DD` (for example `'2026-11-19'`).

    Returns `checkout_id` and a readable summary of the signed quote (unit and per-litre/kg prices,
    total in EUR excluding tax, stock and certainty, delivery date, order cut-off `closing_time`,
    shortfalls, and ranked alternatives). Never state any price that did not come from this tool.
    After obtaining the best quote for the buyer's request, call `authorize_checkout` with `checkout_id`.
    """
    if not needs:
        raise ValueError("needs must contain at least one item")
    issued = driver("POST", "/agent/checkouts", json={"needs": needs, "delivery_date": delivery_date})
    return _summarize_checkout(issued["checkout_id"], issued["checkout"])


@server.tool()
def authorize_checkout(checkout_id: str, request_text: str) -> dict[str, Any]:
    """Submit a `checkout_id` to the buyer's guardrail harness for policy evaluation and signing.

    Args:
        checkout_id: Short quote identifier returned by `request_quote`.
        request_text: Always pass the human buyer's exact original sentence verbatim, unedited.

    The harness verifies Valio Aimo's signature and rules (`auto`, `human`, or `deny`):
    - `status == 'ordered'`: within policy, auto-signed by the agent mandate and accepted (`order_id` returned).
    - `status == 'pending_approval'`: requires a human signature before `deadline`. Tell the human clearly
      why approval is needed (`reasons`), the exact cut-off `deadline`, and the `approval_url` where they
      must review and sign (never ask for approval in the chat).
    - `status == 'denied'`: blocked by policy or signature check; nothing is signed or ordered.
    The order shows on the restaurant's kitchen page at the same time.
    """
    if not request_text or not request_text.strip():
        raise ValueError("request_text must contain the human's original request sentence")
    return driver("POST", "/agent/authorize", json={"checkout_id": checkout_id, "request_text": request_text})


@server.tool()
def get_authorization_status(checkout_id: str) -> dict[str, Any]:
    """Check the current authorization and approval status of a `checkout_id` on the buyer's harness.

    Returns `ordered`, `pending_approval` (with `approval_url` and `deadline`), `denied`, `rejected`, or `expired`.
    If `pending_approval`, remind the human of the `deadline` and `approval_url` where approval must happen.
    """
    return harness("GET", f"/authorizations/{checkout_id}")


@server.tool()
def get_order(order_id: str) -> dict[str, Any]:
    """Fetch a confirmed Valio Aimo order by `order_id` (without exposing raw cryptographic receipt tokens)."""
    order: dict[str, Any] = gateway("GET", f"/orders/{order_id}")
    order.pop("receipt_jwt", None)
    return order


def main(argv: list[str]) -> None:
    if not argv:
        server.run("stdio")
        return
    if argv[0] != "--http" or len(argv) > 2:
        sys.exit("usage: python agent_mcp/server.py [--http [tunnel-host]]")
    # The protection against DNS rebinding only lets local Host headers in: a tunnel host must be named to pass.
    hosts = [f"127.0.0.1:{HTTP_PORT}", f"localhost:{HTTP_PORT}", *argv[1:]]
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts)
    server.run("streamable-http", host="127.0.0.1", port=HTTP_PORT, transport_security=security)


if __name__ == "__main__":
    main(sys.argv[1:])
