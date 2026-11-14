"""The Valio Aimo gateway, port 8001: search, signed quotes, public keys. Orders come in A5.

Run: uv run uvicorn merchant.app:app --port 8001
VALIO_MODE=replay (default) serves the answers recorded on 14/11, VALIO_MODE=live calls the Valio APIs.
"""

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from contract.models import CheckoutResponse, OffersRequest, OffersResponse, QuoteRequest, SearchResponse
from merchant import catalog, store
from merchant.offers import OffersError, find_offers
from merchant.quotes import QuoteError, build_quote
from trust.checkout import sign_checkout
from trust.keys import private_key, public_jwks

app = FastAPI(title="Valio Aimo gateway", version="0.1")
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


@app.get("/offers")
def lookup_offers(request: Annotated[OffersRequest, Query()]) -> OffersResponse:
    """Products, prices and availability for a query. Informative: only POST /checkouts returns a signed quote."""
    try:
        return find_offers(request)
    except OffersError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


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
    return response


@app.get("/checkouts/{checkout_id}")
def get_checkout(checkout_id: str) -> CheckoutResponse:
    response = store.load_checkout(checkout_id)
    if response is None:
        raise HTTPException(status_code=404, detail=f"no quote {checkout_id}")
    return response


@app.get("/.well-known/jwks.json")
def jwks() -> dict:
    return public_jwks()
