# Junction2026

## Tiny V1 (Valio Aimo)

`v1.py` runs one purchase request end to end on the real mock data: local search in the product file, one call each to price and availability, litres to sales units, cheapest option that arrives in time (split across two products when stock is short), a 500 EUR approval rule, an order file and an audit log.

Setup, once (Python 3.9 or later):

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then paste the API key from the team chat
```

Run:

```sh
source .venv/bin/activate
python v1.py "lactose free milk" 1000 L 2026-11-17
```

The first run downloads the product file (87 MB) into `data/` and reuses it after that. Orders go to `orders/<id>.json`, one line per decision to `orders/audit.log`. Both folders are git-ignored.
