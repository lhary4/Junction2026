"""Second pass: signed payment chain (spend cap end to end) and the human-signed order (above the cap)."""
import json, time
from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.open_payment_mandate import AmountRange, OpenPaymentMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.mandate import MandateClient
from ap2.sdk.utils import compute_sha256_b64url
from jwcrypto.jwk import JWK

def key(kid):
    k = json.loads(JWK.generate(kty="EC", crv="P-256").export()); k["kid"] = kid
    return JWK.from_json(json.dumps(k))
pub = lambda k: JWK.from_json(k.export_public())
manager, agent, client = key("buyer-manager-1"), key("buyer-agent-1"), MandateClient()
VALIO = Merchant(id="valio-aimo", name="Valio Aimo")

open_pay = client.create(payloads=[OpenPaymentMandate(constraints=[AmountRange(currency="EUR", max=150000)],
    cnf={"jwk": json.loads(agent.export_public())}, exp=int(time.time()) + 86400)], issuer_key=manager)
for cents in (101000, 202000):
    tok = client.present(holder_key=agent, mandate_token=open_pay, aud="valio-aimo", nonce="quote-0001", payloads=[PaymentMandate(
        transaction_id="quote-0001", payee=VALIO, payment_amount=Amount(amount=cents, currency="EUR"),
        payment_instrument=PaymentInstrument(id="customer-account-demo", type="invoice"))])
    payloads = client.verify(token=tok, key_or_provider=lambda _t: pub(manager), expected_aud="valio-aimo", expected_nonce="quote-0001")
    print(f"signed payment chain, {cents / 100:.0f} EUR against a signed 1 500 EUR cap ->", PaymentMandateChain.parse(payloads).verify(expected_transaction_id="quote-0001") or "accept")

# Above the cap: the human signs the closed mandate directly (AP2 "human present"), no open mandate involved.
quote_jwt = "hdr.e30.sig"  # stand-in for the seller's signed quote, only its hash matters here
direct = client.create(payloads=[CheckoutMandate(checkout_jwt=quote_jwt, checkout_hash=compute_sha256_b64url(quote_jwt))], issuer_key=manager)
try:
    m = client.verify(token=direct, key_or_provider=pub(manager), payload_type=CheckoutMandate)
    print("human-signed closed mandate verifies with the manager's key ->", type(m).__name__, "| hash matches:", m.mandate_payload.checkout_hash == compute_sha256_b64url(quote_jwt))
except Exception as e:
    print("human-signed closed mandate FAILED ->", type(e).__name__, str(e)[:200])
try:
    client.verify(token=direct, key_or_provider=pub(agent), payload_type=CheckoutMandate)
    print("same token checked against the AGENT's key -> accepted (BAD)")
except Exception as e:
    print("same token checked against the agent's key -> refused:", type(e).__name__)
