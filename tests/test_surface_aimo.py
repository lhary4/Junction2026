"""The clean portal (surface/static/aimo/): its files exist and point at files that exist, it needs no internet,
every rule and every step has its words, the sample history says it is a sample and adds up, the console is the
version that opens, and the approval screen says what changes with a substitute."""

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


# state.js is loaded as it is in Node, with the little of the browser it reads when it starts (the address).
LOADED = """
import fs from "node:fs";
globalThis.window = { location: { search: "%(search)s", hostname: "localhost", href: "http://localhost/" } };
const state = await import("%(module)s");
const recorded = () => JSON.parse(fs.readFileSync("%(recorded)s", "utf8"));
const line = (run) => Object.values(run.quote.aimo.lines).find((entry) => entry.substitute_for);
const rows = (change) => {
  const run = recorded();
  if (change) change(line(run));
  return Object.fromEntries(state.tradeOffs(run).map((row) => [row.key, { tone: row.tone, text: row.text }]));
};
console.log(JSON.stringify({
  main: state.MAIN_VARIANT,
  variant: state.app.variant,
  comparing: state.app.comparing,
  recorded: rows(),
  cheaper: rows((sub) => Object.assign(sub.substitute_for, { comparison_price_minor: 1286, comparison_unit: "KG" })),
  frozen: rows((sub) => { sub.temperature_condition = 7; }),
  idle: state.tradeOffs(null),
}));
"""


def loaded(search: str = "") -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = LOADED % {
        "search": search,
        "module": (AIMO / "state.js").as_uri(),
        "recorded": (EXAMPLES / "demo-state.substitution.pending.json").as_posix(),
    }
    result = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_console_is_the_version_that_opens_and_the_others_must_be_asked_for():
    alone, asked = loaded(), loaded("?v=c")

    assert alone["main"] == "b" and alone["variant"] == "b"
    assert alone["comparing"] is False, "the strip should not offer the other versions to someone who asked for none"
    assert asked["variant"] == "c" and asked["comparing"] is True
    # The body carries data-variant for the stylesheet: only a button may switch versions, or any click on plain
    # text would be read as a switch.
    assert ",[data-variant]," not in read("main.js") and "button[data-variant]" in read("main.js")


def test_the_approval_screen_says_what_changes_with_a_substitute_on_four_sides():
    """The same four lines as the first page (tests/test_surface_portal_tradeoffs.py), read from the signed quote."""
    drawn = loaded()
    recorded = drawn["recorded"]

    assert list(recorded) == ["cost", "dish", "work", "logistics"]
    # The recorded quote has no price for the product asked for: the page says so and compares nothing.
    assert recorded["cost"]["tone"] == "note"
    assert "Valio's quote has no price for the one you asked for." in recorded["cost"]["text"]
    assert recorded["dish"]["text"] == (
        "Aimo is 93% sure it works the same way in the dish, and 64% sure it fits your kitchen's preferences. "
        "Below 85%, it asks you."
    )
    assert "Valio's data gives no preparation time." in recorded["work"]["text"]
    assert recorded["logistics"]["text"].startswith("Chilled, like the one you asked for.")
    # Two signed prices are read side by side, and no difference between them is worked out.
    cheaper = drawn["cheaper"]["cost"]
    assert cheaper["tone"] == "good"
    assert cheaper["text"].startswith("Cheaper: EUR 10.94 a kg, against EUR 12.86 a kg for the one you asked for.")
    assert "1.92" not in cheaper["text"] and "%" not in cheaper["text"]
    # A change of storage is a reason to ask.
    assert drawn["frozen"]["logistics"]["tone"] == "ask"
    assert drawn["idle"] == []
