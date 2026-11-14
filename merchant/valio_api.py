"""The live Valio Aimo mock APIs, called with the key from .env. Read-only: price, availability, file downloads.

The API answers HTTP 403 to Python's default urllib user agent, so this uses requests.
Docs: https://junction26.valioaimo.fi/docs. Only call price and availability on a shortlist, never the whole catalog.
"""

import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://junction26.valioaimo.fi/api"
TIMEOUT_SECONDS = 120
MAX_PRODUCTS_PER_CALL = 1000  # more is HTTP 422


def api_key() -> str:
    key = os.environ.get("VALIO_AIMO_API_KEY") or _from_env_file("VALIO_AIMO_API_KEY")
    if not key:
        raise RuntimeError("VALIO_AIMO_API_KEY is not set: copy .env.example to .env and fill it from the team chat")
    return key


def data_dir() -> Path:
    return Path(os.environ.get("AIMO_DATA_DIR") or _from_env_file("AIMO_DATA_DIR") or ROOT / "data")


def ping() -> dict:
    return _call("GET", "/ping").json()


def availability(product_ids: list[str], requested_date: str, customer: str = "demo") -> dict:
    return _call("POST", "/availability", _body(product_ids, requested_date, customer)).json()


def price(product_ids: list[str], requested_date: str, customer: str = "demo") -> dict:
    return _call("POST", "/price", _body(product_ids, requested_date, customer)).json()


def download(path: str) -> bytes:
    return _call("GET", path).content


def _body(product_ids, requested_date, customer):
    if not 1 <= len(product_ids) <= MAX_PRODUCTS_PER_CALL:
        raise ValueError(f"1 to {MAX_PRODUCTS_PER_CALL} products per call, got {len(product_ids)}")
    return {"customer": customer, "requestedDate": requested_date, "products": product_ids}


def _call(method: str, path: str, body: dict | None = None) -> requests.Response:
    response = requests.request(
        method, API + path, json=body, headers={"X-API-Key": api_key()}, timeout=TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response


def _from_env_file(name: str) -> str | None:
    """Read one variable from the repo's .env without exporting anything."""
    env = ROOT / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name and not key.lstrip().startswith("#"):
            return value.strip() or None
    return None
