"""MCP server for the external buying agent (Step C1: example-backed mode).

Exposes the five tools defined in docs/contract.md over stdio using MCPServer (mcp >= 2.3).
Reads contract/examples/ relative to this file's location so it works regardless of the
working directory used by Claude Desktop or Antigravity when launching the process.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, TypedDict

from mcp.server.mcpserver import MCPServer

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "contract" / "examples"

SERVER_INSTRUCTIONS = (
    "You are an external wholesale buying agent connected to Valio Aimo and the buyer's guardrail harness. "
    "Follow these rules strictly:\n"
    "1. Never invent or guess any fact: prices, stock, totals, delivery dates, allergens, reliability, and carbon "
    "footprint must come exclusively from tool outputs. Product search results have no prices; call `request_quote` "
    "before stating any price or total. Report `unknown` certainty explicitly as unknown, never as safe or available.\n"
    "2. When the buyer specifies what they need, how much, and by when, complete the workflow without asking "
    "unnecessary questions: call `search_products`, call `request_quote` for the best matching option, and call "
    "`authorize_checkout` so the buyer's harness applies policy and decides whether to auto-order or route to a human.\n"
    "3. Always pass the buyer's exact original sentence verbatim as `request_text` when calling `authorize_checkout`.\n"
    "4. Human approvals never happen in chat. If `status` is `pending_approval`, state the reason, the `deadline` "
    "(order cut-off), and the `approval_url` where the approver must review and sign."
)

server = MCPServer(
    "valio-aimo",
    instructions=SERVER_INSTRUCTIONS,
)


class NeedInput(TypedDict):
    """One item the buyer needs, expressed in buyer units (L, KG, or ST)."""

    product_id: str
    amount: float
    unit: Literal["L", "KG", "ST"]


def _load_json(filename: str) -> Any:
    path = EXAMPLES_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_tokens(text: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return [tok for tok in cleaned.split() if tok]


def _product_haystack(card: dict[str, Any]) -> str:
    parts: list[str] = [
        str(card.get("id", "")),
        str(card.get("name", "")),
        str(card.get("brand") or ""),
        str(card.get("vendor") or ""),
        str(card.get("category", "")),
        " ".join(card.get("nutritional_claims", [])),
        " ".join(card.get("labels", [])),
    ]
    return re.sub(r"[^a-z0-9]+", " ", " ".join(parts).lower())


def _select_checkout_file(needs: list[NeedInput]) -> str:
    product_ids = [str(item.get("product_id", "")) for item in needs]
    if "469363" in product_ids and "464306" not in product_ids:
        return "checkout.act3.json"
    total_amount = sum(float(item.get("amount", 0)) for item in needs)
    if total_amount >= 1500:
        return "checkout.act2.json"
    return "checkout.act1.json"


def _summarize_checkout(checkout: dict[str, Any]) -> dict[str, Any]:
    """Build a readable, token-free summary of a signed AimoCheckout."""
    aimo = checkout["aimo"]
    total_minor = next(t["amount"] for t in checkout["totals"] if t["type"] == "total")
    currency = checkout["currency"]

    lines_summary: list[dict[str, Any]] = []
    line_sentences: list[str] = []
    for item in checkout["line_items"]:
        line_id = item["id"]
        claims = aimo["lines"][line_id]
        line_total_minor = next(t["amount"] for t in item["totals"] if t["type"] == "total")
        unit_price_eur = item["item"]["price"] / 100
        comp_price_eur = claims["comparison_price_minor"] / 100
        line_total_eur = line_total_minor / 100

        lines_summary.append(
            {
                "line_id": line_id,
                "product_id": claims["product_id"],
                "title": item["item"]["title"],
                "quantity_sales_units": item["quantity"],
                "sales_unit": claims["sales_unit"],
                "base_quantity": claims["base_quantity"],
                "base_unit": claims["base_unit"],
                "unit_price_eur": round(unit_price_eur, 2),
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
        sub_note = (
            f" (substitute for {claims['substitute_for']['product_id']})"
            if claims.get("substitute_for")
            else ""
        )
        line_sentences.append(
            f"{item['quantity']} {claims['sales_unit']} ({claims['base_quantity']:g} {claims['base_unit']}) "
            f"x {claims['product_id']} {item['item']['title']}{sub_note} "
            f"at {comp_price_eur:.2f} EUR/{claims['comparison_unit']} = {line_total_eur:.2f} {currency}"
        )

    total_eur = total_minor / 100
    summary_text = (
        f"Quote {checkout['id']} signed by {checkout['merchant']['name']}: "
        + "; ".join(line_sentences)
        + f". Total (excl. tax): {total_eur:.2f} {currency}. "
        f"Delivery: {aimo['delivery_date']}. Order cut-off / quote expires: {checkout['expires_at']}."
    )
    if aimo.get("shortfalls"):
        summary_text += f" Shortfalls: {len(aimo['shortfalls'])}."

    return {
        "checkout_id": checkout["id"],
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


def _lookup_authorization_status(checkout_id: str) -> dict[str, Any]:
    statuses: dict[str, dict[str, Any]] = _load_json("authorization-status.json")
    if checkout_id == "chk_act1_demo":
        return statuses["ordered"]
    if checkout_id == "chk_act2_demo":
        return statuses["pending_approval"]
    if checkout_id == "chk_act3_demo":
        result = dict(statuses["ordered"])
        result["checkout_id"] = "chk_act3_demo"
        return result
    if checkout_id in ("chk_denied_demo", "denied"):
        return statuses["denied"]
    if checkout_id in ("chk_rejected_demo", "rejected"):
        return statuses["rejected"]
    if checkout_id in ("chk_expired_demo", "expired"):
        return statuses["expired"]
    raise ValueError(f"Unknown checkout_id: {checkout_id}")


@server.tool()
def search_products(query: str, limit: int = 5) -> dict[str, Any]:
    """Search the Valio Aimo catalog and return matching product cards without prices.

    Product cards include pack sizes, allergens (`data='missing'` never means allergen-free),
    origin, historical delivery reliability, estimated carbon footprint, and sustainability labels,
    each with its source and certainty (`measured`, `declared`, `estimated`, or `unknown`).
    Prices and live stock are NOT in product cards: never guess or state a price before calling `request_quote`.
    """
    cards: list[dict[str, Any]] = _load_json("product-cards.json")
    tokens = _normalize_tokens(query)
    capped_limit = max(1, min(int(limit), 50))

    if not tokens:
        matched = cards[:capped_limit]
    else:
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for idx, card in enumerate(cards):
            haystack = _product_haystack(card)
            score = sum(1 for tok in tokens if tok in haystack)
            if score > 0:
                scored.append((score, -idx, card))
        scored.sort(reverse=True)
        matched = [card for _, _, card in scored[:capped_limit]] if scored else cards[:capped_limit]

    return {
        "query": query,
        "count": len(matched),
        "products": matched,
    }


@server.tool()
def request_quote(needs: list[NeedInput], delivery_date: str) -> dict[str, Any]:
    """Request a Valio Aimo ES256-signed quote for the buyer's product needs and target delivery date.

    Args:
        needs: List of `{product_id, amount, unit}` items (`unit` is `'L'`, `'KG'`, or `'ST'`).
        delivery_date: Requested delivery date in ISO format `YYYY-MM-DD` (for example `'2026-11-16'`).

    Returns `checkout_id` and a readable summary of the signed quote (unit and per-litre/kg prices,
    total in EUR excluding tax, stock and certainty, delivery date, order cut-off `closing_time`,
    shortfalls, and ranked alternatives). Never state any price that did not come from this tool.
    After obtaining the best quote for the buyer's request, call `authorize_checkout` with `checkout_id`.
    """
    if not needs:
        raise ValueError("needs must contain at least one item")
    filename = _select_checkout_file(needs)
    checkout = _load_json(filename)
    return _summarize_checkout(checkout)


@server.tool()
def authorize_checkout(checkout_id: str, request_text: str) -> dict[str, Any]:
    """Submit a `checkout_id` to the buyer's guardrail harness for policy evaluation and signing.

    Args:
        checkout_id: Short quote identifier returned by `request_quote` (e.g. `'chk_act1_demo'`).
        request_text: Always pass the human buyer's exact original sentence verbatim, unedited.

    The harness verifies Valio Aimo's signature and rules (`auto`, `human`, or `deny`):
    - `status == 'ordered'`: within policy, auto-signed by the agent mandate and accepted (`order_id` returned).
    - `status == 'pending_approval'`: requires a human signature before `deadline`. Tell the human clearly
      why approval is needed (`reasons`), the exact cut-off `deadline`, and the `approval_url` where they
      must review and sign (never ask for approval in the chat).
    - `status == 'denied'`: blocked by policy or signature check; nothing is signed or ordered.
    """
    if not request_text or not request_text.strip():
        raise ValueError("request_text must contain the human's original request sentence")
    return _lookup_authorization_status(checkout_id)


@server.tool()
def get_authorization_status(checkout_id: str) -> dict[str, Any]:
    """Check the current authorization and approval status of a `checkout_id` on the buyer's harness.

    Returns `ordered`, `pending_approval` (with `approval_url` and `deadline`), `denied`, `rejected`, or `expired`.
    If `pending_approval`, remind the human of the `deadline` and `approval_url` where approval must happen.
    """
    return _lookup_authorization_status(checkout_id)


@server.tool()
def get_order(order_id: str) -> dict[str, Any]:
    """Fetch a confirmed Valio Aimo order by `order_id` (without exposing raw cryptographic receipt tokens)."""
    order: dict[str, Any] = _load_json("order.json")
    order.pop("receipt_jwt", None)

    if order_id == order["order_id"]:
        return order
    if order_id == "ord_91f3c7de":
        updated = dict(order)
        updated["order_id"] = "ord_91f3c7de"
        updated["checkout_id"] = "chk_act2_demo"
        updated["signed_by"] = "human"
        updated["total_minor"] = 202000
        if isinstance(updated.get("receipt"), dict):
            updated["receipt"] = {**updated["receipt"], "order_id": "ord_91f3c7de"}
        return updated
    raise ValueError(f"Unknown order_id: {order_id}")


if __name__ == "__main__":
    server.run("stdio")
