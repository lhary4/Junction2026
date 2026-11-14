"""The kitchen order page (surface/static/portal.html): its files exist, it only replays examples that exist,
and the kitchen's stock files agree with what each recorded scenario orders."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "surface" / "static"
KITCHEN = STATIC / "kitchen"
EXAMPLES = ROOT / "contract" / "examples"

# The stock file of each scenario, and the recorded run that scenario replays (same pairs as in portal.js).
STOCK_AND_RUN = {"normal-order": "normal-order", "substitution": "substitution.pending"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_page_only_points_at_files_that_exist():
    html = (STATIC / "portal.html").read_text(encoding="utf-8")
    css = (STATIC / "portal.css").read_text(encoding="utf-8")
    linked = re.findall(r'(?:href|src)="([^"#]+)"', html) + re.findall(r'url\("([^"]+)"\)', css)
    local = [name for name in linked if not name.startswith(("http", "data:"))]
    assert local, "the page should link its stylesheet, script, fonts and logo"
    for name in local:
        assert (STATIC / name).is_file(), f"portal page points at a missing file: {name}"


def test_the_page_only_replays_examples_that_exist():
    script = (STATIC / "portal.js").read_text(encoding="utf-8")
    replayed = set(re.findall(r'recorded\("([^"]+)"\)', script))
    replay_table = re.search(r"const REPLAY_FILE = \{([^}]*)\}", script).group(1)
    replayed |= set(re.findall(r':\s*"([^"]+)"', replay_table))
    assert {"idle", "normal-order", "substitution.pending", "substitution.approved", "attack"} <= replayed
    for name in replayed:
        assert (EXAMPLES / f"demo-state.{name}.json").is_file(), f"no recorded run called {name}"


@pytest.mark.parametrize("scenario", sorted(STOCK_AND_RUN))
def test_what_is_missing_in_stock_is_what_the_scenario_orders(scenario):
    stock = load(KITCHEN / f"stock.{scenario}.json")
    asked = {
        line["product_id"]: line
        for line in load(EXAMPLES / f"demo-state.{STOCK_AND_RUN[scenario]}.json")["request"]["lines"]
    }
    missing = {line["product_id"]: line for line in stock["lines"] if line["to_order"] > 0}

    assert set(missing) == set(asked)
    for product_id, line in missing.items():
        assert line["to_order"] == pytest.approx(asked[product_id]["amount"])
        assert line["unit"] == asked[product_id]["unit"]


@pytest.mark.parametrize("scenario", sorted(STOCK_AND_RUN))
def test_to_order_is_the_need_minus_the_stock(scenario):
    for line in load(KITCHEN / f"stock.{scenario}.json")["lines"]:
        assert line["to_order"] == pytest.approx(max(0, line["need"] - line["in_stock"]))


def test_kitchen_files_say_they_are_synthetic():
    for path in KITCHEN.glob("*.json"):
        assert "Synthetic" in load(path)["_sample"], f"{path.name} must say it is synthetic sample data"


def test_recipes_and_bookings_match_the_demo_kitchen():
    kitchen = load(EXAMPLES / "demo-state.idle.json")["kitchen"]
    recipes = load(KITCHEN / "recipes.json")
    bookings = load(KITCHEN / "bookings.json")

    assert recipes["covers_per_service"] == kitchen["covers_per_service"]
    assert [recipe["course"] for recipe in recipes["recipes"]] == [item["course"] for item in kitchen["menu"]]
    assert [f"{service['date']} {service['meal']}" for service in bookings["services"]] == kitchen["services"]


def test_the_script_has_no_syntax_error():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    result = subprocess.run([node, "--check", str(STATIC / "portal.js")], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
