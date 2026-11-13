"""Tiny V1 for the Valio Aimo challenge: one purchase request, end to end, on real data (steps 1 to 7 in main()).
Usage: python v1.py "lactose free milk" 1000 L 2026-11-17. The mock has no order API: orders/<id>.json is the order."""
import json, math, re, sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
API = "https://junction26.valioaimo.fi/api"
CATALOG, ORDERS = ROOT / "data" / "products.json", ROOT / "orders"
SHORTLIST_MAX = 20        # products sent to the APIs: never the whole catalog
MAX_LINES = 2             # an order is split across two products at most
APPROVAL_LIMIT_EUR = 500  # above this total (excl. tax), a human must approve
NAME_SIZES = {"L": {"ml": 0.001, "cl": 0.01, "dl": 0.1, "l": 1.0}, "KG": {"g": 0.001, "kg": 1.0}}  # "5 dl" in names
DECISIONS = []            # (time, what, why, rule), written to orders/audit.log at the end

def decide(what, why, rule):
    DECISIONS.append((datetime.now().astimezone(), what, why, rule))

def api_key():
    """Read VALIO_AIMO_API_KEY from .env (git-ignored, the value is in the team chat)."""
    env = ROOT / ".env"
    pairs = [line.split("=", 1) for line in env.read_text().splitlines() if "=" in line] if env.exists() else []
    return dict(pairs).get("VALIO_AIMO_API_KEY", "").strip() or sys.exit("Fill in VALIO_AIMO_API_KEY in .env")

def api(method, path, key, **kwargs):
    """One call to the mock API. Any network, HTTP or JSON error stops the script with a clear message."""
    try:
        response = requests.request(method, API + path, headers={"X-API-Key": key}, timeout=120, **kwargs)
        response.raise_for_status()
        return response.content, response.json()
    except (requests.RequestException, ValueError) as error:
        sys.exit(f"API call {method} {path} failed: {error}")

def names(product):
    """English and Finnish names from the GS1 Synkka data, e.g. {"en": "...", "fi": "..."}."""
    found = (product.get("synkkaData") or {}).get("names") or []
    return {n["language"]: n["value"] for n in found if n["language"] in ("en", "fi")}

def size_per_sales_unit(product, price, unit):
    """Litres (or kg) in one sales unit, from two independent sources. Returns (size, explanation).
    by price: catalogPrice / comparisonPrice, e.g. 31.31 EUR / 1.57 EUR/L = 19.94 L (prices are rounded)
    by name:  pack size in the name x units[].sizeInBaseUnits, e.g. "10 l" x 2 ST per KI = 20 L
    The name wins when both agree within 2 %, otherwise we trust the price.
    """
    unit_price, per_unit = price["catalogPrice"]["value"], price["comparisonPrice"]["value"]
    by_price, sizes = unit_price / per_unit, NAME_SIZES[unit]
    text = f"price {unit_price:.2f} / {per_unit:.2f} = {by_price:.3f} {unit}"
    base_units = {u["unitId"]: u["sizeInBaseUnits"] for u in product.get("units", [])}.get(product["salesUnit"])
    match = re.search(rf"(\d+(?:[.,]\d+)?)\s*({'|'.join(sizes)})\b", names(product).get("en", ""), re.IGNORECASE)
    if not (match and base_units):
        return by_price, text + " | no pack size in the name: use price"
    by_name = float(match.group(1).replace(",", ".")) * sizes[match.group(2).lower()] * base_units
    text += f' | name "{match.group(0)}" x {base_units:g} {product["baseUnit"]} = {by_name:.3f} {unit}'
    if abs(by_name - by_price) <= 0.02 * by_price:
        return by_name, text + " | agree: use name"
    return by_price, text + " | disagree: use price"

def delivery_problem(availability, date, now):
    """Why a product cannot arrive by `date` if ordered now, or None if it can."""
    lines = (availability or {}).get("scheduleLines") or []
    if availability is None or availability.get("salesBlock") or any(line.get("salesBlock") for line in lines):
        return "no availability answer or sales block"
    if not lines or lines[0]["availableAmount"] <= 0:
        return "not available on any date"
    if lines[0]["availableDate"] > date:
        return f"earliest delivery {lines[0]['availableDate']}"
    # closingTime: order before it to be delivered on availableDate, e.g. "2026-11-15T17:00:00+0200"
    cutoff = datetime.strptime(availability.get("closingTime") or "9999-12-31T00:00:00+0000", "%Y-%m-%dT%H:%M:%S%z")
    return f"order cut-off passed on {cutoff:%d/%m %H:%M}" if cutoff < now else None

def write_audit(order_id):
    """Append one readable line per decision to orders/audit.log: when | order | what | why | rule."""
    with open(ORDERS / "audit.log", "a", encoding="utf-8") as log:
        for when, what, why, rule in DECISIONS:
            log.write(f"{when:%Y-%m-%d %H:%M:%S} | order {order_id} | {what} | why: {why} | rule: {rule}\n")
            print(f"   - {what}\n     why: {why} (rule: {rule})")
    print(f"   {len(DECISIONS)} decision(s) appended to orders/audit.log")

def main():
    args = sys.argv[1:]
    if len(args) != 4 or not re.fullmatch(r"\d+(\.\d+)?", args[1]) or float(args[1]) <= 0 \
            or args[2].upper() not in NAME_SIZES or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args[3]):
        sys.exit('Usage: python v1.py "lactose free milk" 1000 L 2026-11-17  (unit L or KG, date YYYY-MM-DD)')
    query, wanted, unit, date = args[0], float(args[1]), args[2].upper(), args[3]
    key, now = api_key(), datetime.now().astimezone()

    print("\n1. Product file")
    if not CATALOG.exists():  # api() checks the answer is valid JSON before we save it
        print("   Not here yet: downloading it once through /api/products/download (87 MB, about 20 s)")
        CATALOG.parent.mkdir(exist_ok=True)
        CATALOG.write_bytes(api("GET", "/products/download", key)[0])
    products = json.loads(CATALOG.read_bytes())
    print(f"   {len(products)} products read from {CATALOG.relative_to(ROOT)}")

    print(f'\n2. Search "{query}" in English and Finnish names')
    terms, matches = query.lower().split(), []  # matches: (extra words, id, product), fewer extra words = closer
    for product in products:
        hits = [n.lower() for n in names(product).values() if all(t in n.lower() for t in terms)]
        if hits and not product.get("deleted"):
            extra = min(sum(not any(t in word for t in terms) for word in hit.split()) for hit in hits)
            matches.append((extra, product["id"], product))
    categories = Counter(product["category"] for _, _, product in matches)
    if not matches:
        sys.exit(f"   No product name contains all of {terms}.")
    top = categories.most_common(1)[0][0]  # the most common category is taken as the product type asked for
    ranked = sorted((m for m in matches if m[2]["category"] == top), key=lambda m: m[:2])
    shortlist = [product for _, _, product in ranked[:SHORTLIST_MAX]]
    not_priced = ", ".join(m[1] for m in ranked[SHORTLIST_MAX:]) or "none"
    print(f"   {len(matches)} names match, by category: {dict(categories.most_common())}")
    print(f"   Keeping category {top}, its {len(shortlist)} closest names. Not priced (cap {SHORTLIST_MAX}): {not_priced}")

    print(f"\n3. Availability and price for the {len(shortlist)} shortlisted products, one call each")
    body = {"customer": "demo", "requestedDate": date, "products": [p["id"] for p in shortlist]}
    availability = {a["productId"]: a for a in api("POST", "/availability", key, json=body)[1]["products"]}
    prices = {p["productId"]: p for p in api("POST", "/price", key, json=body)[1]["products"]}
    print(f"   {len(availability)} availability answers, {len(prices)} prices, for delivery by {date}")
    ORDERS.mkdir(exist_ok=True)

    print(f"\n4. Convert {wanted:g} {unit} into sales units")
    options = []
    for product in shortlist:
        price, name, sales_unit = prices.get(product["id"]) or {}, names(product).get("en", ""), product["salesUnit"]
        per_unit = (price.get("comparisonPrice") or {}).get("value")
        if price.get("error", True) or price.get("comparisonUnit") != unit or not per_unit:
            print(f"   {product['id']} skipped, no price per {unit}: {name[:60]}")
            continue
        size, explanation = size_per_sales_unit(product, price, unit)
        print(f"   {product['id']} {name[:60]}\n          1 {sales_unit}: {explanation}"
              f" -> {wanted:g} / {size:.3f} = {math.ceil(wanted / size - 1e-9)} {sales_unit}")
        options.append({"product": product, "name": name, "price": price["catalogPrice"]["value"], "size": size,
                        "per_unit": per_unit, "availability": availability.get(product["id"])})

    print(f"\n5. Cheapest per {unit} that arrives by {date} if ordered now")
    usable = []
    for option in sorted(options, key=lambda o: o["per_unit"]):
        product, a = option["product"], option["availability"] or {}
        problem, line = delivery_problem(option["availability"], date, now), (a.get("scheduleLines") or [{}])[0]
        print(f"   {product['id']} {option['per_unit']:5.2f} EUR/{unit}  {a.get('logisticModel', '-'):8} "
              f"{line.get('availableAmount', 0):>12.0f} {product['salesUnit']:3} on {line.get('availableDate', '-')}"
              f"  {problem or 'OK'}")
        if problem is None:
            usable.append(option)
    lines, missing = [], wanted
    for option in usable:
        product, a = option["product"], option["availability"]
        # Terminal products always report 999999: the supplier's stock is unknown, we assume it is enough.
        stock = math.inf if a["logisticModel"] == "Terminal" else a["scheduleLines"][0]["availableAmount"]
        if len(lines) == MAX_LINES or missing <= 1e-9:
            break
        if lines and stock * option["size"] < missing:
            continue  # the second product must cover everything still missing
        quantity = int(min(math.ceil(missing / option["size"] - 1e-9), stock))
        print(f"   -> {quantity} {product['salesUnit']} of {product['id']} = {quantity * option['size']:.1f} {unit},"
              f" {quantity} x {option['price']:.2f} = {quantity * option['price']:.2f} EUR excl. tax")
        why = (f"{lines[0]['productId']} has only {lines[0]['quantity']} {lines[0]['salesUnit']} in stock: cheapest"
               f" product covering the remaining {missing:.1f} {unit}") if lines else \
            f"cheapest per {unit} ({option['per_unit']:.2f} EUR) that arrives by {date}"
        decide(f"{'add' if lines else 'pick'} {quantity} {product['salesUnit']} of {product['id']} {option['name']}",
               why, "split-when-stock-short" if lines else "cheapest-deliverable")
        lines.append({"productId": product["id"], "name": option["name"], "quantity": quantity,
                      "salesUnit": product["salesUnit"], unit: round(quantity * option["size"], 3),
                      "unitPriceExclTax": option["price"], "lineTotalExclTax": round(quantity * option["price"], 2),
                      "availableDate": a["scheduleLines"][0]["availableDate"], "orderCutoff": a.get("closingTime")})
        missing -= quantity * option["size"]
    order_id = now.strftime("%Y%m%d-%H%M%S")
    if missing > 1e-9:
        print(f"   Cannot cover {wanted:g} {unit} with {MAX_LINES} products: {missing:.1f} {unit} missing. No order.\n")
        decide("no order", f"no {MAX_LINES} products that arrive in time cover {wanted:g} {unit}", "max-2-products")
        write_audit(order_id)
        sys.exit(1)

    print(f"\n6. Rule: a total above {APPROVAL_LIMIT_EUR} EUR excl. tax needs a human")
    total, rule = round(sum(line["lineTotalExclTax"] for line in lines), 2), f"spend-limit-{APPROVAL_LIMIT_EUR}"
    print(f"   Total {total:.2f} EUR excl. tax")
    if total > APPROVAL_LIMIT_EUR:
        cutoff = min((line["orderCutoff"] for line in lines if line["orderCutoff"]), default="the order cut-off")
        print(f"   Above the limit. Approve before {cutoff} or the delivery date is lost.")
        approved = input("   Approve? y/n ").strip().lower() == "y"  # anything but "y" is a no
        approver, verdict = "a human in the terminal", "approved" if approved else "rejected"
        decide(f"{verdict} {total:.2f} EUR", f"above {APPROVAL_LIMIT_EUR} EUR excl. tax, {verdict} by {approver}", rule)
    else:
        approved, approver = True, "the agent"
        decide(f"auto-approved {total:.2f} EUR", f"within the agent's {APPROVAL_LIMIT_EUR} EUR limit", rule)

    print("\n7. Order and audit log")
    if approved:
        order = {"id": order_id, "createdAt": now.isoformat(timespec="seconds"), "status": "approved",
                 "request": {"query": query, "quantity": wanted, "unit": unit, "deliveryBy": date},
                 "currency": "EUR", "totalExclTax": total, "lines": lines,
                 "approval": {"rule": rule, "required": total > APPROVAL_LIMIT_EUR, "approvedBy": approver}}
        (ORDERS / f"{order_id}.json").write_text(json.dumps(order, indent=2, ensure_ascii=False) + "\n")
    print(f"   Order written to orders/{order_id}.json" if approved else "   Not approved: no order written")
    write_audit(order_id)

if __name__ == "__main__":
    main()
