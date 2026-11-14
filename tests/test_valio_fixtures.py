"""The recorded Valio answers in contract/fixtures/valio/ are complete and still support the demo script."""

import json
from datetime import datetime
from pathlib import Path

from scripts.record_fixtures import DEMO_PRODUCTS, MAX_BYTES, demo_problems

VALIO = Path(__file__).resolve().parent.parent / "contract" / "fixtures" / "valio"


def load(name):
    return json.loads((VALIO / name).read_text(encoding="utf-8"))


def test_folder_stays_under_one_megabyte():
    assert sum(f.stat().st_size for f in VALIO.iterdir()) <= MAX_BYTES


def test_every_requested_product_has_a_record_a_price_and_an_availability():
    requested = set(load("request.json")["products"])
    assert set(DEMO_PRODUCTS) <= requested
    assert {p["id"] for p in load("products.json")} == requested
    assert {p["productId"] for p in load("price.json")["products"]} == requested
    assert {p["productId"] for p in load("availability.json")["products"]} == requested


def test_demo_facts_hold_on_the_recorded_answers():
    assert demo_problems(load("availability.json")) == []


def test_frozen_now_is_an_aware_time():
    assert datetime.fromisoformat((VALIO / "frozen_now.txt").read_text(encoding="utf-8").strip()).tzinfo is not None
