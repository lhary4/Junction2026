"""The Valio Aimo gateway, port 8001: search, signed quotes, orders with a signed receipt, public keys, audit log.

Run: uv run uvicorn merchant.app:app --port 8001   (or both services at once: uv run python scripts/dev.py)
VALIO_MODE=replay (default) serves the answers recorded on 14/11, VALIO_MODE=live calls the Valio APIs.
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from contract.models import AuditEvent, Authorization, CheckoutResponse, Order, QuoteRequest, SearchResponse
from merchant import audit, catalog, orders, store
from merchant.quotes import QuoteError, build_quote, summary
from trust.checkout import checkout_hash, sign_checkout
from trust.keys import private_key, public_jwks

app = FastAPI(title="Valio Aimo gateway", version="0.2")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/products/search")
def search_products(q: str = Query(min_length=2), limit: int = Query(10, ge=1, le=50)) -> SearchResponse:
    products = catalog.load().search(q, limit)
    return SearchResponse(query=q, count=len(products), products=products)


@app.post("/checkouts")
def create_checkout(request: QuoteRequest) -> CheckoutResponse:
    try:
        checkout = build_quote(request)
    except QuoteError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    response = CheckoutResponse(
        checkout_id=checkout.id, checkout_jwt=sign_checkout(checkout, private_key("merchant")), checkout=checkout
    )
    store.save_checkout(response)
    audit.record(
        "quote_issued",
        f"Quote for {summary(checkout)}.",
        f"Asked by {checkout.aimo.customer} for delivery on {checkout.aimo.requested_delivery_date}, "
        f"valid until {checkout.expires_at:%Y-%m-%d %H:%M}.",
        checkout.id,
        checkout_hash(response.checkout_jwt),
    )
    return response


@app.get("/checkouts/{checkout_id}")
def get_checkout(checkout_id: str) -> CheckoutResponse:
    response = store.load_checkout(checkout_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"no quote {checkout_id}")
    return response


@app.post("/checkouts/{checkout_id}/complete", responses={403: {"model": orders.Refusal}})
def complete_checkout(checkout_id: str, authorization: Authorization) -> Order:
    try:
        return orders.complete(checkout_id, authorization)
    except orders.UnknownQuote as e:
        raise HTTPException(status_code=404, detail=f"no quote {checkout_id}") from e


@app.exception_handler(orders.OrderRefused)
def refuse_order(_request: Request, refusal: orders.OrderRefused) -> JSONResponse:
    return JSONResponse(status_code=403, content=orders.Refusal(problems=refusal.problems).model_dump())


@app.get("/orders/{order_id}")
def get_order(order_id: str) -> Order:
    order = store.load_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"no order {order_id}")
    return order


@app.get("/audit")
def get_audit() -> list[AuditEvent]:
    return audit.events()


@app.get("/.well-known/jwks.json")
def jwks() -> dict:
    return public_jwks()
