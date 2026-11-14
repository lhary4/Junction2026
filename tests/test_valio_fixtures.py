"""The recorded Valio answers in contract/fixtures/valio/ are complete and still support the demo script.

Two recordings: the milk case for delivery on 16/11, in the folder itself, and the restaurant's menu for delivery on
19/11, in a sub-folder named after that date. What the demo does on the second one is checked in
tests/test_scenarios_run.py, through the gateway, the harness and the driver.
"""

import json
from datetime import datetime
from pathlib import Path

from merchant.catalog import recorded_for, recordings
from scripts.record_fixtures import DEMO_PRODUCTS, MAX_BYTES, SUBSTITUTED, demo_problems

ROOT = Path(__file__).resolve().parent.parent
VALIO = ROOT / "contract" / "fixtures" / "valio"
RESTAURANT = VALIO / "2026-11-19"


def load(name, folder=VALIO):
    return json.loads((folder / name).read_text(encoding="utf-8"))


def test_all_recordings_together_stay_under_one_megabyte():
    assert sum(f.stat().st_size for f in VALIO.rglob("*") if f.is_file()) <= MAX_BYTES


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


# ---------- The second recording: the restaurant's menu ----------


def test_the_first_recording_was_not_recorded_again():
    """Tests and the frozen clock of replay mode stand on it: 157 products, asked on 14/11 at 13:29:07."""
    assert len(load("request.json")["products"]) == 157 and load("request.json")["requestedDate"] == "2026-11-16"
    assert (VALIO / "frozen_now.txt").read_text(encoding="utf-8").strip() == "2026-11-14T13:29:07+02:00"


def test_replay_mode_reads_two_recordings_for_two_delivery_dates():
    assert recordings() == [VALIO, RESTAURANT]
    assert [recorded_for(folder) for folder in recordings()] == ["2026-11-16", "2026-11-19"]


def test_the_restaurant_recording_is_complete():
    requested = set(load("request.json", RESTAURANT)["products"])
    assert {p["id"] for p in load("products.json", RESTAURANT)} == requested
    assert {p["productId"] for p in load("price.json", RESTAURANT)["products"]} == requested
    assert {p["productId"] for p in load("availability.json", RESTAURANT)["products"]} == requested
    recorded_at = datetime.fromisoformat((RESTAURANT / "recorded_at.txt").read_text(encoding="utf-8").strip())
    assert recorded_at.tzinfo is not None


def test_the_restaurant_recording_holds_the_menu_and_the_candidates_of_the_replaced_product():
    case = json.loads((ROOT / "scenarios" / "restaurant-case" / "order.json").read_text(encoding="utf-8"))
    records = {p["id"]: p for p in load("products.json", RESTAURANT)}
    assert {line["product"]["product_id"] for line in case["lines"]} <= set(records)
    for replaced in SUBSTITUTED:
        same_category = [p for p in records.values() if p["category"] == records[replaced]["category"]]
        assert len(same_category) > 10  # the whole category, so that replay ranks what live ranked
