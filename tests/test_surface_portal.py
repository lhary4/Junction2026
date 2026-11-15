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


def test_every_rule_of_the_harness_has_a_plain_sentence():
    """A chef reads the checks: each rule the harness can report needs its words in portal.js (CHECK_WORDS)."""
    harness = (ROOT / "harness" / "rules.py").read_text(encoding="utf-8") + (ROOT / "harness" / "app.py").read_text(
        encoding="utf-8"
    )
    rule_ids = set(re.findall(r'rule_id="([a-z-]+)"', harness))
    script = (STATIC / "portal.js").read_text(encoding="utf-8")
    table = script[script.index("const CHECK_WORDS = {") : script.index("const OUTCOME_WORDS")]
    worded = set(re.findall(r'^  "([a-z-]+)": \{', table, flags=re.MULTILINE))

    assert rule_ids, "no rule found in the harness: has the code moved?"
    assert rule_ids <= worded, f"rules without plain words on the page: {sorted(rule_ids - worded)}"
    for rule_id in worded:
        entry = table[table.index(f'"{rule_id}"') :]
        entry = entry[: entry.index("\n  },")]
        for outcome in ("pass", "human", "deny"):
            assert f"{outcome}: " in entry, f"{rule_id} has no sentence for {outcome}"


def test_every_step_of_the_trail_has_the_chefs_words():
    from typing import get_args

    from contract.models import StepKey

    script = (STATIC / "portal.js").read_text(encoding="utf-8")
    table = script[script.index("const STEP_WORDS = {") : script.index("};", script.index("const STEP_WORDS = {"))]
    worded = set(re.findall(r"^  ([a-z_]+): ", table, flags=re.MULTILINE))

    # The seven steps of the contract, and the eighth the page reads from the accepted order.
    assert worded == set(get_args(StepKey)) | {"delivery"}


def test_the_page_calls_the_ai_by_one_name():
    """The buying agent and the judge are both shown as Aimo Personal Assistant."""
    html = (STATIC / "portal.html").read_text(encoding="utf-8")
    script = (STATIC / "portal.js").read_text(encoding="utf-8")

    assert "Aimo Personal Assistant" in html
    assert 'const ASSISTANT = "Aimo Personal Assistant";' in script
    for old_name in ("Buying agent", "The judge, threshold", "Agent order"):
        assert old_name not in html + script


def test_bookings_show_booked_and_projected_covers():
    for service in load(KITCHEN / "bookings.json")["services"]:
        assert {"booked", "projected"} <= set(service)
        assert "planned" not in service


def test_the_script_has_no_syntax_error():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    result = subprocess.run([node, "--check", str(STATIC / "portal.js")], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


# What the two footprint functions of portal.js need around them to run alone in Node, and three cases to draw.
FOOTPRINT_HARNESS = """
const app = { eco: { loading: false } };
let data = null;
let table = [];
const ecoNow = () => data;
const orderLines = () => table;
const swappedLines = () => [];
const icon = () => "";
const esc = (text) => String(text);
const kgCo2 = (value) => `${value} kg CO2e`;
const linesKey = (lines) => (lines ?? []).map((line) => `${line.product_id}:${line.amount}`).sort().join("|");
const ecoKey = () => linesKey(orderLines());
%s
const drawn = {};
table = [{ product_id: "475072", amount: 21 }];
data = { method: "m", total_kg_co2e: 0, unknown: ["475072"], lines: [{ product_id: "475072" }] };
drawn.no_data = footprintLine();
table = [{ product_id: "463437", amount: 6.45 }];
data = { method: "m", total_kg_co2e: 42.8, unknown: [], lines: [{ product_id: "463437" }] };
drawn.same_lines = quoteFootprintLine({ aimo: { requested: [{ product_id: "463437", amount: 6.45 }] } });
drawn.other_quantities = quoteFootprintLine({ aimo: { requested: [{ product_id: "463437", amount: 77.4 }] } });
console.log(JSON.stringify(drawn));
"""


def test_the_footprint_line_never_shows_a_wrong_figure():
    """No data is never drawn as 0 kg CO2e, and a quote for other quantities gets no estimate under it."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = (STATIC / "portal.js").read_text(encoding="utf-8")
    functions = script[script.index("function footprintLine() {") : script.index("function offerFacts(")]
    result = subprocess.run([node, "-e", FOOTPRINT_HARNESS % functions], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    drawn = json.loads(result.stdout)

    assert "no estimate" in drawn["no_data"]
    assert "0 kg" not in drawn["no_data"]
    assert "42.8 kg CO2e" in drawn["same_lines"]
    assert drawn["other_quantities"] == ""
