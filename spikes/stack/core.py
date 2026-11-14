"""Stack test core: plain functions, no transport. AP2 mandates for the proof, files for the shared state.

The MCP server process and the web server process both import this module and meet through STATE (a folder).
"""
import json
import os
import time
import uuid
from pathlib import Path

from ap2.sdk.checkout_mandate_chain import CheckoutMandateChain
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.open_checkout_mandate import AllowedMerchants, OpenCheckoutMandate
from ap2.sdk.generated.open_payment_mandate import AmountRange, OpenPaymentMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.checkout import Checkout, Status
from ap2.sdk.generated.types.item import Item
from ap2.sdk.generated.types.line_item import LineItem
from ap2.sdk.generated.types.link import Link
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.generated.types.total import Total
from ap2.sdk.jwt_helper import create_jwt, verify_jwt
from ap2.sdk.mandate import MandateClient
from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from ap2.sdk.utils import b64url_decode, compute_sha256_b64url
from jwcrypto.jwk import JWK

STATE = Path(os.environ["STACK_TEST_STATE"])
CAP_CENTS = 150000  # the agent may spend up to 1 500 EUR alone
PRICES = {"464306": ("Valio Arki Eila semi skimmed lactose free 1 l", 101), "464320": ("Oatly iKaffe Oat drink 1L", 178)}
VALIO = Merchant(id="valio-aimo", name="Valio Aimo")
client = MandateClient()


def setup():
    """Create the three keys and the two open mandates once. Run before any server starts."""
    STATE.mkdir(parents=True, exist_ok=True)
    keys = {}
    for kid in ("manager", "agent", "merchant"):
        jwk = json.loads(JWK.generate(kty="EC", crv="P-256").export())
        jwk["kid"] = kid
        keys[kid] = jwk
    (STATE / "keys.json").write_text(json.dumps(keys))
    cnf = {"jwk": json.loads(_key("agent").export_public())}
    exp = int(time.time()) + 86400
    mandates = {
        "checkout": client.create(payloads=[OpenCheckoutMandate(constraints=[AllowedMerchants(allowed=[VALIO])], cnf=cnf, exp=exp)], issuer_key=_key("manager")),
        "payment": client.create(payloads=[OpenPaymentMandate(constraints=[AmountRange(currency="EUR", max=CAP_CENTS)], cnf=cnf, exp=exp)], issuer_key=_key("manager")),
    }
    (STATE / "open_mandates.json").write_text(json.dumps(mandates))


def _key(kid):
    return JWK.from_json(json.dumps(json.loads((STATE / "keys.json").read_text())[kid]))


def _pub(kid):
    return JWK.from_json(_key(kid).export_public())


def audit(event, **fields):
    """One JSON line per decision, appended by whichever process made it."""
    line = {"at": time.strftime("%H:%M:%S"), "pid": os.getpid(), "event": event, **fields}
    with open(STATE / "audit.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps(line) + "\n")
    return line


def read_audit():
    path = STATE / "audit.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def get_quote(sku: str, quantity: int) -> dict:
    """Seller side: a signed quote. The chat only gets an id and readable fields, never the token."""
    title, cents = PRICES[sku]
    total, quote_id = quantity * cents, "quote-" + uuid.uuid4().hex[:8]
    totals = [Total(type="subtotal", amount=total), Total(type="total", amount=total)]
    checkout = Checkout(id=quote_id, merchant=VALIO, status=Status.ready_for_complete, currency="EUR", totals=totals,
                        line_items=[LineItem(id="li-1", item=Item(id=sku, title=title, price=cents), quantity=quantity, totals=totals)],
                        links=[Link(type="terms_of_service", url="https://example.com/tos")])
    jwt = create_jwt({"alg": "ES256", "typ": "JWT", "kid": "merchant"}, checkout.model_dump(mode="json", exclude_none=True), _key("merchant"))
    (STATE / f"{quote_id}.jwt").write_text(jwt)
    return {"quote_id": quote_id, "sku": sku, "title": title, "quantity": quantity, "total_eur": total / 100}


def _load_quote(quote_id):
    jwt = (STATE / f"{quote_id}.jwt").read_text()
    verify_jwt(jwt, _pub("merchant"))  # the buyer side checks the seller's signature before anything else
    return jwt, Checkout.model_validate(json.loads(b64url_decode(jwt.split(".")[1])))


def place_order(quote_id: str) -> dict:
    """Buyer harness decides, AP2 proves, seller verifies."""
    jwt, checkout = _load_quote(quote_id)
    total = next(t.amount for t in checkout.totals if t.type == "total")
    if total > CAP_CENTS:
        audit("needs_human", quote_id=quote_id, total_eur=total / 100, rule="spend-cap")
        return {"status": "needs_human", "quote_id": quote_id, "reason": f"{total / 100:.2f} EUR is above the {CAP_CENTS / 100:.0f} EUR cap"}
    open_mandates, agent = json.loads((STATE / "open_mandates.json").read_text()), _key("agent")
    order_token = client.present(holder_key=agent, mandate_token=open_mandates["checkout"], aud=VALIO.id, nonce=quote_id,
                                 payloads=[CheckoutMandate(checkout_jwt=jwt, checkout_hash=compute_sha256_b64url(jwt))])
    payment_token = client.present(holder_key=agent, mandate_token=open_mandates["payment"], aud=VALIO.id, nonce=quote_id, payloads=[PaymentMandate(
        transaction_id=quote_id, payee=VALIO, payment_amount=Amount(amount=total, currency="EUR"),
        payment_instrument=PaymentInstrument(id="customer-account-demo", type="invoice"))])
    # Seller side: verify both chains against the manager's public key, then the constraints.
    provider = lambda _token: _pub("manager")
    problems = CheckoutMandateChain.parse(client.verify(token=order_token, key_or_provider=provider, expected_aud=VALIO.id, expected_nonce=quote_id)).verify(
        expected_checkout_hash=compute_sha256_b64url(jwt), checkout_jwt=jwt)
    problems += PaymentMandateChain.parse(client.verify(token=payment_token, key_or_provider=provider, expected_aud=VALIO.id, expected_nonce=quote_id)).verify(
        expected_transaction_id=quote_id)
    status = "refused" if problems else "accepted"
    audit(status, quote_id=quote_id, total_eur=total / 100, rule="within-mandate", signed_by="agent", problems=problems)
    return {"status": status, "quote_id": quote_id, "problems": problems}


def approve(quote_id: str) -> dict:
    """Above the cap: the human signs this exact order with the manager's key (AP2 human present)."""
    jwt, checkout = _load_quote(quote_id)
    token = client.create(payloads=[CheckoutMandate(checkout_jwt=jwt, checkout_hash=compute_sha256_b64url(jwt))], issuer_key=_key("manager"))
    mandate = client.verify(token=token, key_or_provider=_pub("manager"), payload_type=CheckoutMandate)
    ok = mandate.mandate_payload.checkout_hash == compute_sha256_b64url(jwt)
    total = next(t.amount for t in checkout.totals if t.type == "total")
    audit("accepted" if ok else "refused", quote_id=quote_id, total_eur=total / 100, rule="human-approval", signed_by="manager")
    return {"status": "accepted" if ok else "refused", "quote_id": quote_id}
