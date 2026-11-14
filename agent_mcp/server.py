"""MCP server for the external buying agent, on the real services.

Exposes the nine tools of docs/contract.md. `get_kitchen` reads the restaurant's own data, the files the
kitchen page reads (surface/static/kitchen/: recipes, bookings, stock count). Every other tool calls a running service,
so every fact comes from the gateway or the harness, never from this file:
- search, offers and orders: the Valio gateway (MERCHANT_URL, default http://localhost:8001)
- authorization status, pending approvals and the buyer's policy: the buyer's harness (HARNESS_URL, default
  http://localhost:8002)
- quotes and authorizations: the demo driver (DRIVER_URL, default http://localhost:8003), which forwards them to the
  gateway and the harness, and shows the order on the kitchen page as the "Chat order"

Start the services first: uv run python scripts/dev.py

Run:  uv run python agent_mcp/server.py                         stdio, for Claude Desktop
      uv run python agent_mcp/server.py --http                  HTTP on http://127.0.0.1:8005/mcp
      uv run python agent_mcp/server.py --http abc.trycloudflare.com   the same, reachable through that tunnel host

The agent never sees a token: quotes come back as a readable summary, orders without their receipt token.
Every tool answers twice: a short Markdown summary the agent can show as it is, then every field as JSON (sources,
certainties, timestamps), so nothing the summary leaves out is lost.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict
from zoneinfo import ZoneInfo

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, TextContent

KITCHEN_DIR = Path(__file__).resolve().parent.parent / "surface" / "static" / "kitchen"  # the page's kitchen data
HTTP_PORT = 8005
ANSWER_TIMEOUT_SECONDS = 60  # a quote asks Valio twice, an authorization may ask the judge
HELSINKI = ZoneInfo("Europe/Helsinki")  # the restaurant's time: cut-offs read in it

SERVER_INSTRUCTIONS = (
    "You are an external wholesale buying agent connected to Valio Aimo and the buyer's guardrail harness. "
    "The buyer is a 50-cover restaurant in Helsinki. Follow these rules strictly:\n"
    "1. Never invent or guess any fact: prices, stock, totals, delivery dates, allergens, reliability, and carbon "
    "footprint must come exclusively from tool outputs. Product search results have no prices. Prices from "
    "`lookup_offers` are indicative: say so, with their `as_of` time. A price or total only commits Valio once it is in "
    "the signed quote from `request_quote`. Report `unknown` certainty explicitly as unknown, never as safe or available.\n"
    "2. To compare products or find the cheapest, call `lookup_offers` once (one or two words of the product name, in "
    "English): it prices every match in one call, sorted orderable first, then cheapest per litre or kilo. Never call "
    "`request_quote` product by product to compare prices. Never pick an offer with `orderable: false`: say its "
    "`reason`. When the buyer says what they need, how much, and by when, complete the workflow without asking "
    "questions: `lookup_offers` with the amount and unit, `request_quote` for the first orderable offer that fits, then "
    "`authorize_checkout` so the buyer's harness decides whether the order is signed automatically or by a human. If a "
    "tool answers with an error, read its message and tell the buyer what it says.\n"
    "3. Always pass the buyer's exact original sentence verbatim as `request_text` when calling `authorize_checkout`.\n"
    "4. Human approvals never happen in chat. If `status` is `pending_approval`, state the reason, the `deadline` "
    "(order cut-off), and the `approval_url` where the approver must review and sign.\n"
    "5. For the menu, recipes, bookings, stock, or 'order what is missing', call `get_kitchen` first. Its "
    "`order_needs` is what to quote, exactly as given, with `needed_by` as the delivery date: no search is needed.\n"
    "6. 'Add X to the order' adds to the chat's last quote if it is not ordered yet: call `request_quote` with only the "
    "new items and `add_to` set to that quote's `checkout_id`, then `authorize_checkout` on the new quote. It has every "
    "line, and the earlier quote's pending approval is withdrawn: there is one order to sign, never two. If the earlier "
    "quote is already ordered, the tool says so: quote the new items alone and say it is a second order.\n"
    "7. For what the agent may do alone (spending limit, blocked allergens, substitutions, why the chef must sign), "
    "call `get_policy`. For what is waiting for the chef, call `list_pending_approvals`.\n"
    "8. Every tool answers with a Markdown summary first, then the full JSON. Build your answer from the summary and "
    "keep it short: a table of the lines (product, quantity, price per kg or litre, line total), then the total "
    "excluding tax, the delivery day, who signs (the agent within its mandate, or the chef), and for a pending approval "
    "the reasons, the cut-off and the approval link. Write dates with the weekday (Thu 19 Nov) and times in Helsinki "
    "time, as the summary does. Say 'indicative' for `lookup_offers` prices."
)

server = MCPServer("valio-aimo", instructions=SERVER_INSTRUCTIONS)


class NeedInput(TypedDict):
    """One item the buyer needs, expressed in buyer units (L, KG, or ST)."""

    product_id: str
    amount: float
    unit: Literal["L", "KG", "ST"]


class ServiceError(ToolError):
    """A service did not answer, or refused. The message is what the agent reads.

    It must be a ToolError: the MCP SDK hides the message of any other exception and the agent reads only
    "Error executing tool request_quote", with no way to tell "out of stock" from a crash.
    """


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


# ---------- Readable answers ----------


def _answer(markdown: str, data: Any) -> CallToolResult:
    """A tool's answer: the Markdown summary first, for the chat, then every field as JSON, for the facts."""
    return CallToolResult(content=[TextContent(text=markdown), TextContent(text=json.dumps(data, ensure_ascii=False))])


def _number(value: float | str | None) -> str:
    """2500, 0.205, 666,666,666: no float noise (0.20500000000000002), thousands separated. Words stay words."""
    if value is None:
        return "unknown"
    if isinstance(value, str):
        return value.replace("_", " ")
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.3f}".rstrip("0").rstrip(".")


def _eur(minor: int | None) -> str:
    return "unknown" if minor is None else f"{minor / 100:,.2f} EUR"


def _day(value: str | None) -> str:
    """'2026-11-19' -> 'Thu 19 Nov': the weekday makes a wrong date visible."""
    return date.fromisoformat(value[:10]).strftime("%a %d %b") if value else "unknown"


def _time(value: str | None) -> str:
    """Any ISO time, UTC or not -> 'Sun 15 Nov 17:00 (Helsinki)'."""
    if not value:
        return "unknown"
    return datetime.fromisoformat(value).astimezone(HELSINKI).strftime("%a %d %b %H:%M (Helsinki)")


def _cell(value: Any) -> str:
    return str(value).replace("|", "/").replace("\n", " ")


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return "\n".join(lines + ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows])


def _allergens(allergens: dict[str, Any]) -> str:
    """Missing data says so: unknown is never read as allergen-free."""
    if allergens.get("data") == "missing":
        return "unknown (no data)"
    found = ", ".join(allergens.get("contains") or []) or "none declared"
    return found if allergens.get("data") == "complete" else f"{found} ({allergens.get('data')} data)"


def _fact(fact: dict[str, Any] | None, scale: float = 1, suffix: str = "") -> str:
    """A sourced value with its certainty: '98.8% (measured)', or 'unknown'."""
    if not fact or fact.get("value") is None or fact.get("certainty") == "unknown":
        return "unknown"
    value = fact["value"]
    shown = _number(round(value * scale, 3)) if isinstance(value, (int, float)) else str(value)
    return f"{shown}{suffix} ({fact['certainty']})"


def _pack(card: dict[str, Any]) -> str:
    size = card.get("size_per_sales_unit") or {}
    if size.get("value") is None or (size["value"] == 1 and size["unit"] == card["sales_unit"]):
        return card["sales_unit"]
    return f"{_number(size['value'])} {size['unit']} per {card['sales_unit']}"


def _status_markdown(status: dict[str, Any]) -> str:
    """An AuthorizationStatus in words: what happened, who signs, and what the human must do."""
    checkout_id, state = status["checkout_id"], status["status"]
    reasons = "\n".join(f"- {reason}" for reason in status.get("reasons") or [])
    if state == "ordered":
        who = "by the agent, within its mandate" if status.get("signed_by") == "agent" else "by the chef"
        text = f"**Ordered**: order `{status['order_id']}` for quote `{checkout_id}`, signed {who}."
        return text + (f"\n\nWhy the chef signed:\n{reasons}" if status.get("signed_by") == "human" and reasons else "")
    if state == "pending_approval":
        return (
            f"**Waiting for the chef's signature**: quote `{checkout_id}`, nothing is ordered yet.\n\n"
            f"Why:\n{reasons}\n\n"
            f"- Sign before: {_time(status.get('deadline'))}\n"
            f"- Approve or reject on the page: {status.get('approval_url')}"
        )
    words = {
        "denied": "**Denied** by the buyer's rules: nothing is signed, nothing is ordered.",
        "rejected": "**Rejected by the chef**: nothing is ordered.",
        "expired": "**Expired**: no answer before the cut-off, nothing is ordered.",
    }
    return f"{words.get(state, f'**{state}**')} Quote `{checkout_id}`." + (f"\n\nWhy:\n{reasons}" if reasons else "")


def _quote_markdown(summary: dict[str, Any]) -> str:
    rows = []
    for line in summary["lines"]:
        name = f"{line['product_id']} {line['title']}"
        if line.get("substitute_for"):
            name += f" (substitute for {line['substitute_for']['product_id']})"
        quantity = f"{line['quantity_sales_units']} {line['sales_unit']}"
        if line["sales_unit"] != line["base_unit"]:
            quantity += f" ({_number(line['base_quantity'])} {line['base_unit']})"
        rows.append(
            [
                name,
                quantity,
                f"{line['comparison_price_eur']:.2f} EUR/{line['comparison_unit']}",
                f"{line['line_total_eur']:,.2f} EUR",
                _allergens(line["allergens"]),
            ]
        )
    parts = [
        f"**Quote `{summary['checkout_id']}`**, signed by {summary['merchant']['name']}, prices excluding tax",
        _table(["Product", "Quantity", "Price", "Line total", "Allergens"], rows),
        (
            f"**Total: {summary['total_eur']:,.2f} {summary['currency']} excl. tax** · delivery "
            f"{_day(summary['delivery_date'])} · order before {_time(summary['closing_time'])}"
        ),
    ]
    for short in summary["shortfalls"]:
        covers = [
            line["product_id"]
            for line in summary["lines"]
            if (line.get("substitute_for") or {}).get("product_id") == short["product_id"]
        ]
        parts.append(
            f"Short: {_number(short['missing_base_quantity'])} {short['base_unit']} of {short['product_id']} "
            f"({_number(short['reason'])}), "
            + (f"covered by {', '.join(covers)}." if covers else "not covered: nothing replaces it.")
        )
    parts.append("Nothing is ordered yet: `authorize_checkout` sends it to the buyer's rules.")
    return "\n\n".join(parts)


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
def get_kitchen() -> CallToolResult:
    """The restaurant's own kitchen data: the menu's recipes, the bookings of the coming services, and the stock count.

    Call it for any question about the menu, recipes, bookings, stock, or what the kitchen needs to order.
    `order_needs` lists what is short for the coming services (need minus stock, computed by the kitchen's system),
    ready to pass as `needs` to `request_quote`, with `needed_by` (the first service) as `delivery_date`.
    Never recompute or round these quantities yourself.
    """
    kitchen = _kitchen()
    stock = kitchen["stock"]
    services = "; ".join(
        f"{_day(s['date'])} {s['meal']}: {s['booked']} booked, {s['projected']} projected" for s in kitchen["services"]
    )
    short = [line for line in stock["lines"] if line["to_order"] > 0]
    parts = [
        f"**{kitchen['restaurant']}**, {kitchen['covers_per_service']} covers per service",
        f"Services: {services}",
        _table(["Course", "Dish"], [[r["course"], r["dish"]] for r in kitchen["recipes"]]),
        f"Stock counted on {_day(stock['counted_at'])} ({stock['counted_by']}), for {stock['for_services']} services.",
    ]
    if short:
        rows = [
            [
                f"{line['product_id']} {line['name']}",
                *(f"{_number(line[k])} {line['unit']}" for k in ("need", "in_stock", "to_order")),
            ]
            for line in short
        ]
        parts += [
            f"**To order for {_day(kitchen['needed_by'])}**:",
            _table(["Product", "Need", "In stock", "To order"], rows),
        ]
    else:
        parts.append("Nothing to order: the stock covers every service.")
    return _answer("\n\n".join(parts), kitchen)


def _kitchen() -> dict[str, Any]:
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
def search_products(query: str, limit: int = 5) -> CallToolResult:
    """Search the Valio Aimo catalog and return matching product cards without prices.

    Every word of `query` must be in the product name: use one or two words, in English (for example 'mozzarella',
    'whipping cream'). Product cards include pack sizes, allergens (`data='missing'` never means allergen-free),
    origin, historical delivery reliability, estimated carbon footprint, and sustainability labels, each with its
    source and certainty (`measured`, `declared`, `estimated`, or `unknown`).
    Prices and live stock are NOT in product cards: never guess or state a price before calling `request_quote`.
    """
    found = gateway("GET", "/products/search", params={"q": query, "limit": max(1, min(int(limit), 50))})
    rows = [
        [
            card["id"],
            card["name"],
            _pack(card),
            _allergens(card["allergens"]),
            _fact(card["origin"]),
            _fact(card["delivery_reliability"], 100, "%"),
            _fact(card["carbon_footprint"], 1, " kg"),
        ]
        for card in found["products"]
    ]
    header = f"**{found['count']} products for '{query}'**, no prices here: `lookup_offers` prices them."
    if not rows:
        return _answer(f"No product name has every word of '{query}': try one word, in English.", found)
    table = _table(["ID", "Product", "Pack", "Allergens", "Origin", "Delivered in full", "CO2e per kg"], rows)
    return _answer(f"{header}\n\n{table}", found)


@server.tool()
def lookup_offers(
    query: str,
    delivery_date: str,
    amount: float | None = None,
    unit: Literal["L", "KG", "ST"] | None = None,
    limit: int = 5,
) -> CallToolResult:
    """Compare products: price, stock, delivery date and cut-off of every product matching `query`, in one call.

    Args:
        query: One or two words of the product name, in English (for example 'potato', 'whipping cream').
        delivery_date: Requested delivery date in ISO format `YYYY-MM-DD`.
        amount: Optional quantity the buyer needs, with `unit` (`'L'`, `'KG'`, or `'ST'`). Both or neither.
        limit: How many offers to return (5 is enough for a chat, at most 50).

    Offers are sorted: orderable first, then enough counted stock for `amount`, then cheapest per litre or kilo
    (`comparison_price`, in euro cents). `orderable: false` comes with a `reason` (out of stock, too late, unit
    mismatch). Prices are indicative and not signed (`binding: false`): to order, call `request_quote` for the product
    picked. `matched` larger than `priced` means the words were too broad: only the closest names were priced.
    """
    params: dict[str, Any] = {"q": query, "delivery_date": delivery_date, "limit": max(1, min(int(limit), 50))}
    if amount is not None:
        params |= {"amount": amount, "unit": unit}
    found = gateway("GET", "/offers", params=params)
    return _answer(_offers_markdown(found), found)


def _offers_markdown(found: dict[str, Any]) -> str:
    wanted = f", for {_number(found['amount'])} {found['unit']}" if found.get("amount") is not None else ""
    header = (
        f"**Offers for '{found['query']}'**, delivery {_day(found['delivery_date'])}{wanted}. "
        f"Indicative prices at {_time(found['as_of'])}, not signed: only `request_quote` commits Valio."
    )
    if not found["offers"]:
        return f"{header}\n\nNo product name has every word of '{found['query']}': try one word, in English."
    rows, cut_offs = [], set()
    for offer in found["offers"]:
        card, price = offer["product"], offer.get("price") or {}
        comparison = (offer.get("comparison_price") or {}).get("value")
        stock = offer.get("stock") or {}
        to_order = offer.get("to_order")
        row = [
            card["id"],
            card["name"],
            f"{_eur(price.get('value'))} per {card['sales_unit']}" if price.get("value") is not None else "unknown",
            f"{_eur(comparison)}/{offer.get('comparison_unit')}" if comparison is not None else "unknown",
        ]
        if wanted:
            row.append(
                f"{to_order['quantity']} {card['sales_unit']} = {_eur(to_order['total_minor'])}" if to_order else "n/a"
            )
        stock_text = _number(stock.get("value"))  # 'not given' when Valio does not count it
        if isinstance(stock.get("value"), (int, float)):
            stock_text += f" {stock.get('unit')}"
        row += [
            stock_text,
            _day((offer.get("available_date") or {}).get("value")),
            "yes" if offer["orderable"] else f"no: {offer.get('reason')}",
        ]
        rows.append(row)
        if offer.get("closing_time"):
            cut_offs.add(_time(offer["closing_time"]["value"]))
    headers = [
        "ID",
        "Product",
        "Price",
        "Per kg or L",
        *(["To order"] if wanted else []),
        "Stock",
        "Ready",
        "Orderable",
    ]
    parts = [header, _table(headers, rows)]
    if cut_offs:
        parts.append("Order before: " + ", ".join(sorted(cut_offs)) + ".")
    if found["matched"] > found["priced"]:
        parts.append(f"{found['matched']} names matched, only the {found['priced']} closest were priced: add a word.")
    return "\n\n".join(parts)


@server.tool()
def request_quote(needs: list[NeedInput], delivery_date: str, add_to: str | None = None) -> CallToolResult:
    """Request a Valio Aimo ES256-signed quote for the buyer's product needs and target delivery date.

    Args:
        needs: List of `{product_id, amount, unit}` items (`unit` is `'L'`, `'KG'`, or `'ST'`).
        delivery_date: Requested delivery date in ISO format `YYYY-MM-DD` (for example `'2026-11-19'`).
        add_to: Optional `checkout_id` of an earlier quote in this chat that is not ordered yet. The new quote then has
            the earlier lines plus `needs` (amounts of the same product add up) and replaces it once authorized.

    Returns `checkout_id` and a readable summary of the signed quote (unit and per-litre/kg prices,
    total in EUR excluding tax, stock and certainty, delivery date, order cut-off `closing_time`,
    shortfalls, and ranked alternatives). Never state any price that did not come from this tool.
    After obtaining the best quote for the buyer's request, call `authorize_checkout` with `checkout_id`.
    """
    if not needs:
        raise ToolError("needs must contain at least one item")
    body: dict[str, Any] = {"needs": needs, "delivery_date": delivery_date}
    if add_to:
        body["add_to"] = add_to
    issued = driver("POST", "/agent/checkouts", json=body)
    summary = _summarize_checkout(issued["checkout_id"], issued["checkout"])
    return _answer(_quote_markdown(summary), summary)


@server.tool()
def authorize_checkout(checkout_id: str, request_text: str) -> CallToolResult:
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
        raise ToolError("request_text must contain the human's original request sentence")
    status = driver("POST", "/agent/authorize", json={"checkout_id": checkout_id, "request_text": request_text})
    return _answer(_status_markdown(status), status)


@server.tool()
def get_authorization_status(checkout_id: str) -> CallToolResult:
    """Check the current authorization and approval status of a `checkout_id` on the buyer's harness.

    Returns `ordered`, `pending_approval` (with `approval_url` and `deadline`), `denied`, `rejected`, or `expired`.
    If `pending_approval`, remind the human of the `deadline` and `approval_url` where approval must happen.
    """
    status = harness("GET", f"/authorizations/{checkout_id}")
    return _answer(_status_markdown(status), status)


@server.tool()
def list_pending_approvals() -> CallToolResult:
    """List every quote waiting for the chef's signature: why, the cut-off, and where to approve.

    Call it for 'what is waiting for the chef?' or 'what still needs approval?'. Approvals happen on the page at
    `approval_url`, never in the chat.
    """
    pending = [s for s in harness("GET", "/authorizations") if s["status"] == "pending_approval"]
    if not pending:
        return _answer("Nothing is waiting for the chef.", pending)
    rows = [
        [f"`{s['checkout_id']}`", " ".join(s.get("reasons") or []), _time(s.get("deadline")), s.get("approval_url")]
        for s in pending
    ]
    text = f"**{len(pending)} waiting for the chef's signature**\n\n" + _table(
        ["Quote", "Why", "Sign before", "Approve on"], rows
    )
    return _answer(text, pending)


@server.tool()
def get_policy() -> CallToolResult:
    """The buyer's rules the harness applies to every order: what the agent may sign alone, and when the chef signs.

    Call it for 'how much can you spend alone?', 'why does the chef have to sign?', 'which allergens are blocked?',
    or 'which substitutes do you accept?'. It is the rule itself, from the harness, not a summary of it.
    """
    policy = harness("GET", "/policy")
    words = {"human": "the chef signs", "deny": "refused", "auto": "the agent signs"}
    substitution = policy["substitution"]
    pre_accepted = {
        "same_category_and_same_allergens": "accepted when they have the same category and the same allergens",
        "none": "none is accepted without a check",
    }.get(substitution["pre_accepted"], substitution["pre_accepted"])
    lines = [
        f"**The buyer's rules** (policy `{policy['policy_id']}`, valid until {_time(policy['valid_until'])})",
        (
            f"- The agent signs alone up to **{_eur(policy['autonomous_limit_minor'])}** an order. Above, the chef "
            f"({policy['approver']}) signs on the page."
        ),
        f"- Suppliers allowed: {', '.join(m['name'] for m in policy['allowed_merchants'])}.",
        f"- Blocked allergens, always refused: {', '.join(policy['blocked_allergens']) or 'none'}.",
        (
            f"- Allergen data missing: {words.get(policy['unknown_allergen_data'])}. A substitute with other allergens: "
            f"{words.get(policy['allergen_change_on_substitution'])}. A late delivery: "
            f"{words.get(policy['late_delivery'])}."
        ),
    ]
    if substitution["allowed"]:
        lines.append(
            f"- Substitutes: {pre_accepted}. The others are judged against the buyer's written preferences "
            "(`substitution.preferences_text` in the JSON)."
        )
    else:
        lines.append("- Substitutes: the chef signs every one.")
    return _answer("\n".join(lines), policy)


@server.tool()
def get_order(order_id: str) -> CallToolResult:
    """Fetch a confirmed Valio Aimo order by `order_id` (without exposing raw cryptographic receipt tokens)."""
    order: dict[str, Any] = gateway("GET", f"/orders/{order_id}")
    order.pop("receipt_jwt", None)
    payment = order.get("payment") or {}
    signer = "the agent, within its mandate" if order.get("signed_by") == "agent" else "the chef"
    text = (
        f"**Order `{order['order_id']}`: {order['status']}** by Valio Aimo, for quote `{order['checkout_id']}`\n\n"
        f"Total {_eur(order.get('total_minor'))} excl. tax · delivery {_day(order.get('delivery_date'))} · "
        f"signed by {signer} · placed {_time(order.get('created_at'))}"
    )
    if payment:
        text += f"\n\nPayment: {payment.get('terms')}, {payment.get('status')}."
    return _answer(text, order)


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
