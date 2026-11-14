"""Write the signed fixtures other lanes test against, from contract/examples/.

Run: uv run python scripts/make_fixtures.py
Creates the demo keys if missing (never overwrites one), then writes into contract/fixtures/:
checkout.valid.jwt, checkout.tampered.jwt (price changed after signing), checkout.expired.jwt, open_mandates.json.
Signatures are randomised, so the files change on every run even when nothing else did.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ap2.sdk.utils import b64url_decode, b64url_encode

from contract.models import AimoCheckout, BuyerPolicy
from trust.checkout import sign_checkout
from trust.keys import private_key, public_jwk, write_demo_keys
from trust.mandates import issue_open_mandates

EXAMPLES = ROOT / "contract" / "examples"
OUT = ROOT / "contract" / "fixtures"
# Before the example's issued_at, so the quote is expired at any later clock.
EXPIRED_AT = datetime.fromisoformat("2026-11-14T12:00:00+02:00")
TAMPERED_PRICE = 71  # the example's 1.01 EUR becomes 0.71 EUR, signature unchanged


def load(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def tamper(checkout_jwt: str) -> str:
    header, body, signature = checkout_jwt.split(".")
    payload = json.loads(b64url_decode(body))
    payload["line_items"][0]["item"]["price"] = TAMPERED_PRICE
    return ".".join([header, b64url_encode(json.dumps(payload).encode("utf-8")), signature])


def write(name: str, text: str):
    path = OUT / name
    path.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


def main():
    created = write_demo_keys()
    if created:
        print(f"created demo keys: {', '.join(created)}")
    merchant = private_key("merchant")
    checkout = AimoCheckout.model_validate(load("checkout.act1.json"))
    valid = sign_checkout(checkout, merchant)
    expired = sign_checkout(checkout.model_copy(update={"expires_at": EXPIRED_AT}), merchant)
    open_mandates = issue_open_mandates(
        BuyerPolicy.model_validate(load("policy.demo.json")), private_key("manager"), public_jwk("agent")
    )
    write("checkout.valid.jwt", valid)
    write("checkout.tampered.jwt", tamper(valid))
    write("checkout.expired.jwt", expired)
    write("open_mandates.json", json.dumps(open_mandates.model_dump(), indent=2))


if __name__ == "__main__":
    main()
