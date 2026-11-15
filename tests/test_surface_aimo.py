"""The clean portal (surface/static/aimo/): its files exist and point at files that exist, it needs no internet,
every rule and every step has its words, and the sample history says it is a sample and adds up."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import get_args

import pytest

from contract.models import RuleId, StepKey

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "surface" / "static"
AIMO = STATIC / "aimo"
EXAMPLES = ROOT / "contract" / "examples"
MODULES = ("core.js", "state.js", "ui.js", "pages.js", "main.js")
LONG_DASHES = (chr(0x2014), chr(0x2013))  # written as numbers so this file holds none either


def read(name: str) -> str:
    return (AIMO / name).read_text(encoding="utf-8")


def test_the_page_only_points_at_files_that_exist():
    html = read("index.html")
    css = read("app.css")
    linked = re.findall(r'(?:href|src)="([^"#]+)"', html) + re.findall(r'url\("([^"]+)"\)', css)
    assert linked, "the page should link its stylesheet, script and fonts"
    for name in linked:
        assert (AIMO / name).resolve().exists(), f"{name} is linked and does not exist"
    for module in MODULES:
        for imported in re.findall(r'from "\./([a-z]+\.js)"', read(module)):
            assert (AIMO / imported).exists(), f"{module} imports {imported}, which does not exist"
    assert (STATIC / "img" / "valio-aimo-logo-petrol.svg").exists()


def test_the_page_needs_no_internet():
    """Fonts, scripts and styles are local. The only addresses in the code are the services on the laptop."""
    for name in ("index.html", "app.css", *MODULES):
        for address in re.findall(r'https?://[^\s"\'`)]+', read(name)):
            assert address.startswith("http://localhost"), f"{name} points at {address}"


def test_the_replay_reads_files_that_exist():
    core = read("core.js")
    replayed = core[core.index("const REPLAY_FILE = {") : core.index("const STOCK_FILE")]
    counted = core[core.index("const STOCK_FILE = {") : core.index("/* ---------- Words")]
    runs = set(re.findall(r': "([a-z.-]+)"', replayed)) | {"idle", "substitution.approved", "normal-order.greener"}
    for name in runs:
        assert (EXAMPLES / f"demo-state.{name}.json").exists(), f"demo-state.{name}.json is replayed and does not exist"
    stocks = set(re.findall(r': "([a-z.-]+)"', counted))
    assert stocks, "no stock file found in core.js: has the table moved?"
    for name in stocks:
        assert (STATIC / "kitchen" / f"stock.{name}.json").exists(), f"stock.{name}.json is read and does not exist"


def test_every_rule_of_the_harness_has_a_plain_sentence():
    """A chef reads the checks: each rule the harness can report needs its name and a sentence for each outcome."""
    core = read("core.js")
    table = core[core.index("export const CHECK_WORDS = {") : core.index("export const OUTCOME_WORDS")]
    worded = set(re.findall(r'^  "([a-z-]+)": \{', table, flags=re.MULTILINE))
    rule_ids = set(get_args(RuleId))

    assert rule_ids <= worded, f"rules without plain words on the page: {sorted(rule_ids - worded)}"
    for rule_id in worded:
        entry = table[table.index(f'"{rule_id}"') :]
        entry = entry[: entry.index("\n  },")]
        for key in ("name", "pass", "human", "deny"):
            assert f"{key}: " in entry, f"{rule_id} has no {key}"


def test_every_step_of_the_trail_has_its_term_and_its_headline():
    core = read("core.js")
    terms = core[core.index("export const STEP_TERMS = {") : core.index("/* One plain sentence for each rule")]
    state = read("state.js")
    headlines = state[state.index("function stepHead(") : state.index("/* The verdict line carries")]
    for key in get_args(StepKey):
        assert f"{key}:" in terms, f"step {key} has no protocol term"
        assert f'case "{key}":' in headlines, f"step {key} has no headline in the chef's words"


def test_the_sample_history_says_it_is_a_sample_and_adds_up():
    history = json.loads(read("history.sample.json"))
    assert "Sample history" in history["_sample"] and "Not Valio data" in history["_sample"]
    assert history["orders"], "the orders screen needs a few past orders"
    for order in history["orders"]:
        assert order["sample"] is True
        assert order["total_minor"] == sum(line["total_minor"] for line in order["lines"])
        for line in order["lines"]:
            assert line["total_minor"] == line["quantity"] * line["unit_price_minor"]
        # No signature, no order: a request nobody signed has no order id, no mandate and no receipt.
        signed = order["signed_by"] in ("agent", "human")
        assert bool(order["order_id"]) is signed
        assert bool(order["mandate_reference"]) is signed and bool(order["receipt_hash"]) is signed
        # An order above the demo limit is never shown as signed by the agent alone.
        if order["signed_by"] == "agent":
            assert order["total_minor"] <= 150000


def test_the_sample_history_uses_prices_of_the_recorded_quote():
    quote = json.loads((EXAMPLES / "demo-state.normal-order.json").read_text(encoding="utf-8"))["quote"]
    recorded = {item["item"]["id"]: item["item"]["price"] for item in quote["line_items"]}
    history = json.loads(read("history.sample.json"))
    for order in history["orders"]:
        for line in order["lines"]:
            if line["product_id"] in recorded:
                assert line["unit_price_minor"] == recorded[line["product_id"]], f"{line['title']}: not the recorded price"


def test_text_from_the_data_goes_through_esc():
    """The drawing modules build HTML as text: a value from the data must not reach it raw."""
    names = "state|order|quote|approval|event|entry|row|line|attack|step|seal|check"
    for module in ("ui.js", "pages.js"):
        for line in read(module).splitlines():
            for raw in re.findall(rf"\$\{{((?:{names})\.[A-Za-z_.?]+)\}}", line):
                pytest.fail(f"{module} writes {raw} into the page without esc(): {line.strip()[:120]}")


def test_no_long_dash_in_the_page():
    for name in ("index.html", "app.css", "history.sample.json", *MODULES):
        text = read(name)
        assert not any(dash in text for dash in LONG_DASHES), f"{name} has a long dash"


@pytest.mark.parametrize("module", MODULES)
def test_the_modules_are_valid_javascript(module):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    result = subprocess.run([node, "--check", str(AIMO / module)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
