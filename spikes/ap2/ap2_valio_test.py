"""One-hour test: can the official AP2 SDK carry the Valio Aimo guardrails? Real numbers from the 14/11 API call."""
import json, time
from ap2.sdk.checkout_mandate_chain import CheckoutMandateChain
from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from ap2.sdk.constraints import MandateContext
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.open_checkout_mandate import AllowedMerchants, LineItemRequirements, LineItems, OpenCheckoutMandate
from ap2.sdk.generated.open_checkout_mandate import Item as MandateItem
from ap2.sdk.generated.open_payment_mandate import AmountRange, Budget, OpenPaymentMandate
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
from ap2.sdk.utils import b64url_decode, b64url_encode, compute_sha256_b64url
from jwcrypto.jwk import JWK

def key(kid):
    k = json.loads(JWK.generate(kty="EC", crv="P-256").export()); k["kid"] = kid
    return JWK.from_json(json.dumps(k))
def pub(k): return JWK.from_json(k.export_public())
def cnf(k): return {"jwk": json.loads(k.export_public())}

manager, agent, merchant_key, attacker = key("buyer-manager-1"), key("buyer-agent-1"), key("valio-aimo-gateway-1"), key("attacker-1")
VALIO = Merchant(id="valio-aimo", name="Valio Aimo")
client, results, timings = MandateClient(), [], {}

def quote(sku, title, qty, unit_cents, merchant=VALIO, **extra):
    """The seller's signed quote: a UCP Checkout object in a merchant-signed ES256 JWT."""
    total = qty * unit_cents
    checkout = Checkout(id="quote-0001", merchant=merchant, status=Status.ready_for_complete, currency="EUR",
        line_items=[LineItem(id="li-1", item=Item(id=sku, title=title, price=unit_cents), quantity=qty,
                             totals=[Total(type="subtotal", amount=total), Total(type="total", amount=total)])],
        totals=[Total(type="subtotal", amount=total), Total(type="total", amount=total)],
        links=[Link(type="terms_of_service", url="https://example.com/tos")], **extra)
    return create_jwt({"alg": "ES256", "typ": "JWT", "kid": "valio-aimo-gateway-1"},
                      checkout.model_dump(mode="json", exclude_none=True), merchant_key)

def open_checkout(signer=manager, holder=agent, exp=None, qty=1000):
    return client.create(payloads=[OpenCheckoutMandate(
        constraints=[AllowedMerchants(allowed=[VALIO]),
                     LineItems(items=[LineItemRequirements(id="lactose-free-milk", quantity=qty, acceptable_items=[
                         MandateItem(id="464306", title="Valio Arki Eila semi skimmed lactose free 1 l"),
                         MandateItem(id="464401", title="Valio Arki Eila skimmed lactose free 1 l")])])],
        cnf=cnf(holder), exp=exp or int(time.time()) + 86400)], issuer_key=signer)

def order(open_tok, checkout_jwt, holder=agent, aud="valio-aimo", nonce="quote-0001"):
    return client.present(holder_key=holder, mandate_token=open_tok, aud=aud, nonce=nonce,
        payloads=[CheckoutMandate(checkout_jwt=checkout_jwt, checkout_hash=compute_sha256_b64url(checkout_jwt))])

def seller_checks(chain_tok, issued_jwt, received_jwt=None, aud="valio-aimo", nonce="quote-0001", trusted=None):
    """What the Valio Aimo gateway runs before accepting an order. Returns the list of problems (empty = accept)."""
    received_jwt = received_jwt or issued_jwt
    problems = []
    try:
        verify_jwt(received_jwt, pub(merchant_key))
    except Exception as e:
        problems.append(f"quote signature invalid ({type(e).__name__})")
    try:
        payloads = client.verify(token=chain_tok, key_or_provider=lambda _t: pub(trusted or manager), expected_aud=aud, expected_nonce=nonce)
    except Exception as e:
        return problems + [f"mandate chain rejected: {type(e).__name__}: {str(e)[:110]}"]
    return problems + CheckoutMandateChain.parse(payloads).verify(expected_checkout_hash=compute_sha256_b64url(issued_jwt), checkout_jwt=received_jwt)

def case(name, expect_ok, problems):
    ok = (not problems) == expect_ok
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} | {name} | expected {'accept' if expect_ok else 'refuse'} | got: {problems or 'accept'}")

# 1. Happy path, with our own claims riding in the signed quote (the Checkout model allows extra fields).
t = time.perf_counter(); q = quote("464306", "Valio Arki Eila semi skimmed lactose free 1 l", 1000, 101, expires_at="2026-11-15T17:00:00+02:00",
    valio_claims={"464306": {"stock_basis": "counted", "available_date": "2026-11-16", "order_cutoff": "2026-11-15T17:00:00+02:00",
                             "delivery_reliability": 1.0, "country_of_origin": "FI", "allergens_declared": ["AM"]}}); timings["seller signs quote"] = time.perf_counter() - t
t = time.perf_counter(); o = open_checkout(); timings["manager signs open mandate"] = time.perf_counter() - t
t = time.perf_counter(); c = order(o, q); timings["agent signs closed mandate"] = time.perf_counter() - t
t = time.perf_counter(); p = seller_checks(c, q); timings["seller verifies everything"] = time.perf_counter() - t
case("1 000 L of 464306 at 1.01 EUR, inside the mandate", True, p)
kept = json.loads(b64url_decode(q.split(".")[1]))
print(f"     extra claims survive in the signed quote: {'valio_claims' in kept and 'expires_at' in kept} | sizes: quote {len(q)} chars, open mandate {len(o)}, order token {len(c)}")

# 2. Attacks and exceptions from the demo script.
h, body, sig = q.split("."); forged = json.loads(b64url_decode(body)); forged["line_items"][0]["item"]["price"] = 71
tampered = f"{h}.{b64url_encode(json.dumps(forged).encode())}.{sig}"
case("tampered quote: price 1.01 -> 0.71", False, seller_checks(order(o, tampered), q, received_jwt=tampered))
oat = quote("464320", "Oatly iKaffe Oat drink 1L", 1000, 178)
case("substitute outside the accepted list (Oatly 464320)", False, seller_checks(order(o, oat), oat))
big = quote("464306", "Valio Arki Eila semi skimmed lactose free 1 l", 2000, 101)
case("quantity 2 000 instead of the mandated 1 000", False, seller_checks(order(o, big), big))
other = quote("464306", "Valio Arki Eila semi skimmed lactose free 1 l", 1000, 101, merchant=Merchant(id="fake-wholesaler", name="Fake Wholesaler"))
case("quote from a merchant not in the mandate", False, seller_checks(order(o, other), other))
case("open mandate forged by someone who is not the manager", False, seller_checks(order(open_checkout(signer=attacker), q), q))
case("another agent uses the mandate bound to our agent's key", False, seller_checks(order(o, q, holder=attacker), q))
case("replay: order token presented with another quote id (nonce)", False, seller_checks(c, q, nonce="quote-0002"))
case("replay: order token presented to another seller (aud)", False, seller_checks(c, q, aud="other-wholesaler"))
case("expired open mandate (expired 1 h ago)", False, seller_checks(order(open_checkout(exp=int(time.time()) - 3600), q), q))

# 3. Spend cap: it lives in the PAYMENT mandate, not in the checkout mandate.
def pay(amount_cents, constraints, context=None):
    chain = PaymentMandateChain(open_mandate=OpenPaymentMandate(constraints=constraints, cnf=cnf(agent)),
        closed_mandate=PaymentMandate(transaction_id="tx-1", payee=VALIO, payment_amount=Amount(amount=amount_cents, currency="EUR"),
                                      payment_instrument=PaymentInstrument(id="customer-account-demo", type="invoice")))
    return chain.verify(mandate_context=context)
cap = [AmountRange(currency="EUR", max=150000)]
case("spend cap 1 500 EUR, order of 1 010 EUR", True, pay(101000, cap))
case("spend cap 1 500 EUR, order of 2 020 EUR", False, pay(202000, cap))
budget = [Budget(max=1500, currency="EUR")]
case("budget 1 500 EUR, second order of 1 010 EUR after 1 010 EUR already spent (split orders)", False, pay(101000, budget, MandateContext(total_amount=101000, total_uses=1)))

print(f"\n{sum(results)}/{len(results)} cases behave as expected")
print("timings (ms): " + ", ".join(f"{k} {v * 1000:.1f}" for k, v in timings.items()))
