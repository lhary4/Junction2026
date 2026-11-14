"""Write one JSON Schema per contract model into contract/schemas/.

Run: uv run python scripts/export_schemas.py
The schemas are generated: edit contract/models.py, never the JSON files.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from contract import models

OUT = ROOT / "contract" / "schemas"
EXPORTED = [
    models.ProductCard,
    models.SearchResponse,
    models.OffersRequest,
    models.Offer,
    models.OffersResponse,
    models.QuoteRequest,
    models.FootprintRequest,
    models.FootprintResponse,
    models.AimoCheckout,
    models.CheckoutResponse,
    models.BuyerPolicy,
    models.Verdict,
    models.AuthorizeRequest,
    models.ApprovalRequest,
    models.ApprovalDecision,
    models.AuthorizationStatus,
    models.Authorization,
    models.Order,
    models.AuditEvent,
    models.DemoState,
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for model in EXPORTED:
        path = OUT / f"{model.__name__}.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
