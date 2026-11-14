"""Ground the demo beats on real data: lactose-free milk candidates, substitutes, labels, allergens, reliability, carbon, live price and availability."""
import csv, io, json, sys, urllib.request
from collections import Counter
from pathlib import Path

catalog, env_file, out_dir, date = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
API = "https://junction26.valioaimo.fi/api"
key = dict(l.split("=", 1) for l in env_file.read_text().splitlines() if "=" in l and not l.startswith("#"))["VALIO_AIMO_API_KEY"].strip()

def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, headers={"X-API-Key": key, "Content-Type": "application/json", "User-Agent": "junction2026-team-demo-check/0.1"},
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()

def table(name, path):
    f = out_dir / name
    if not f.exists():
        f.write_bytes(call("GET", path))
    rows = list(csv.reader(io.StringIO(f.read_text(encoding="utf-8-sig"))))
    return {r[0]: float(r[1]) for r in rows[1:] if len(r) > 1 and r[1]}

reliability = table("delivery-reliability.csv", "/delivery-reliability/download")
carbon = table("carbon-footprint.csv", "/carbon-footprint/download")
products = json.loads(catalog.read_bytes())

def names(p):
    return {n["language"]: n["value"] for n in ((p.get("synkkaData") or {}).get("names") or [])}
def classes(p):
    out = {}
    for c in (p.get("synkkaData") or {}).get("classifications") or []:
        out[c["name"]] = c.get("values") or []
    return out
def has(p, *terms_sets):
    n = " | ".join(names(p).values()).lower()
    return any(all(t in n for t in terms) for terms in terms_sets)

live = [p for p in products if str(p.get("deleted")) != "True"]
milk = [p for p in live if has(p, ("lactose free", "milk"), ("laktoositon", "maito"))]
cats = Counter(p["category"] for p in milk)
top = cats.most_common(1)[0][0]
milk_top = [p for p in milk if p["category"] == top]
subs = [p for p in live if has(p, ("oat drink",), ("kaurajuoma",), ("soy drink",), ("soijajuoma",), ("almond drink",))][:14]

sample = milk_top[0]
print("RAW classifications of", sample["id"], names(sample).get("en"))
for k, v in classes(sample).items():
    print("  ", k, "->", json.dumps(v, ensure_ascii=False)[:260])
print("  ingredients origins:", json.dumps([(i.get("origins")) for i in (sample["synkkaData"].get("ingredients") or [])])[:200])

ids = [p["id"] for p in milk_top + subs]
body = {"customer": "demo", "requestedDate": date, "products": ids}
avail = {a["productId"]: a for a in json.loads(call("POST", "/availability", body))["products"]}
price = {a["productId"]: a for a in json.loads(call("POST", "/price", body))["products"]}

def row(p):
    c, a, pr = classes(p), avail.get(p["id"]) or {}, price.get(p["id"]) or {}
    line = (a.get("scheduleLines") or [{}])[0]
    def codes(vals, level):
        got = []
        for v in vals:
            s = json.dumps(v, ensure_ascii=False)
            if level in s:
                got.append((v.get("id") or v.get("code") or v.get("value") or "?") if isinstance(v, dict) else str(v))
        return got
    al = c.get("allergen", []) + c.get("nonAllergen", [])
    labels = [(v.get("id") or v.get("value") or json.dumps(v)) if isinstance(v, dict) else str(v) for v in c.get("packagingMarkedLabel", [])]
    return {
        "id": p["id"], "name": names(p).get("en", names(p).get("fi", ""))[:58], "vendor": p.get("vendorName", "")[:18], "origin": p.get("countryOfOrigin"),
        "unit": p["salesUnit"], "model": a.get("logisticModel"), "amount": line.get("availableAmount"), "avail": line.get("availableDate"),
        "closing": (a.get("closingTime") or "")[:16], "block": a.get("salesBlock"),
        "price": (pr.get("catalogPrice") or {}).get("value"), "per": (pr.get("comparisonPrice") or {}).get("value"), "perUnit": pr.get("comparisonUnit"),
        "rel": reliability.get(p["id"]), "co2": carbon.get(p["id"]),
        "contains": codes(al, "CONTAINS"), "free": codes(al, "FREE_FROM"), "allergenData": bool(al), "labels": labels,
    }

def show(title, plist):
    print(f"\n== {title} ({len(plist)})")
    for r in sorted((row(p) for p in plist), key=lambda r: (r["per"] is None, r["per"] or 0)):
        print(f'{r["id"]} {r["name"]:58} | {r["vendor"]:18} {r["origin"]} | {r["unit"]:3} {str(r["model"]):8} amt={r["amount"]} on {r["avail"]} cut={r["closing"]} blk={r["block"]}'
              f' | {r["price"]} EUR, {r["per"]}/{r["perUnit"]} | rel={r["rel"]} co2={r["co2"]} | CONTAINS={r["contains"]} FREE={r["free"]} data={r["allergenData"]} | labels={r["labels"]}')

print("\ncategories of lactose-free milk names:", dict(cats.most_common()))
show(f"lactose-free milk, category {top}, requested {date}", milk_top)
show("plant-based drinks (substitutes outside preferences)", subs)
cov = lambda d, pl: sum(1 for p in pl if p["id"] in d)
print(f"\ncoverage in milk set: reliability {cov(reliability, milk_top)}/{len(milk_top)}, carbon {cov(carbon, milk_top)}/{len(milk_top)}, allergen data {sum(1 for p in milk_top if row(p)['allergenData'])}/{len(milk_top)}")
