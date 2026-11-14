"""The live Valio Aimo mock APIs, called with the key from .env. Read-only: price, availability, file downloads.

The API answers HTTP 403 to Python's default urllib user agent, so this uses requests.
Docs: https://junction26.valioaimo.fi/docs. Only call price and availability on a shortlist, never the whole catalog.
Every failure (no key, no network, too slow, an HTTP error, an answer that is not JSON) raises ValioUnavailable.
"""

import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://junction26.valioaimo.fi/api"
ANSWER_TIMEOUT_SECONDS = 30  # price and availability: a quote that waits longer is lost anyway
DOWNLOAD_TIMEOUT_SECONDS = 120  # the product file is 86 MB
MAX_PRODUCTS_PER_CALL = 1000  # more is HTTP 422


class ValioUnavailable(RuntimeError):
    """The Valio API gave no usable answer. The message names the call and the cause, never the key."""


def api_key() -> str:
    key = os.environ.get("VALIO_AIMO_API_KEY") or _from_env_file("VALIO_AIMO_API_KEY")
    if not key:
        raise ValioUnavailable(
            "VALIO_AIMO_API_KEY is not set: copy .env.example to .env and fill it from the team chat"
        )
    return key


def data_dir() -> Path:
    return Path(os.environ.get("AIMO_DATA_DIR") or _from_env_file("AIMO_DATA_DIR") or ROOT / "data")


def ping() -> dict:
    return _json("GET", "/ping")


def availability(product_ids: list[str], requested_date: str, customer: str = "demo") -> dict:
    return _json("POST", "/availability", _body(product_ids, requested_date, customer))


def price(product_ids: list[str], requested_date: str, customer: str = "demo") -> dict:
    return _json("POST", "/price", _body(product_ids, requested_date, customer))


def download(path: str) -> bytes:
    return _call("GET", path, timeout=DOWNLOAD_TIMEOUT_SECONDS).content


def _body(product_ids, requested_date, customer):
    if not 1 <= len(product_ids) <= MAX_PRODUCTS_PER_CALL:
        raise ValueError(f"1 to {MAX_PRODUCTS_PER_CALL} products per call, got {len(product_ids)}")
    return {"customer": customer, "requestedDate": requested_date, "products": product_ids}


def _json(method: str, path: str, body: dict | None = None) -> dict:
    response = _call(method, path, body)
    try:
        return response.json()
    except ValueError as e:  # requests raises a ValueError subclass for a body that is not JSON
        raise ValioUnavailable(f"Valio API {method} {path}: the answer is not JSON") from e


def _call(method: str, path: str, body: dict | None = None, timeout: int = ANSWER_TIMEOUT_SECONDS) -> requests.Response:
    try:
        response = requests.request(method, API + path, json=body, headers={"X-API-Key": api_key()}, timeout=timeout)
        response.raise_for_status()
    except requests.Timeout as e:
        raise ValioUnavailable(f"Valio API {method} {path}: no answer within {timeout} seconds") from e
    except requests.HTTPError as e:
        raise ValioUnavailable(f"Valio API {method} {path}: HTTP {e.response.status_code}") from e
    except requests.RequestException as e:
        raise ValioUnavailable(f"Valio API {method} {path}: not reachable ({type(e).__name__})") from e
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
