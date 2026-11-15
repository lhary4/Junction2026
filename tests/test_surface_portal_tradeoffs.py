"""The substitution card of the kitchen order page says what changes on four sides: cost, the dish, the work in the
kitchen, storage and delivery.

tradeOffs() is cut out of portal.js with the page's own formatting helpers and run alone in Node, on the recorded
substitution and on copies of it with one fact changed."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "surface" / "static" / "portal.js"
RECORDED = ROOT / "contract" / "examples" / "demo-state.substitution.pending.json"

CASES = """
const fs = require("fs");
const ASSISTANT = "Aimo Personal Assistant";
%(code)s
const recorded = () => JSON.parse(fs.readFileSync("%(recorded)s", "utf8"));
const line = (state) => Object.values(state.quote.aimo.lines).find((entry) => entry.substitute_for);
const rows = (change) => {
  const state = recorded();
  if (change) change(state, line(state));
  return Object.fromEntries(tradeOffs(state).map((row) => [row.key, { tone: row.tone, text: row.text, label: row.label }]));
};
const drawn = {
  recorded: rows(),
  cheaper: rows((state, sub) => Object.assign(sub.substitute_for, { comparison_price_minor: 1286, comparison_unit: "KG" })),
  dearer: rows((state, sub) => Object.assign(sub.substitute_for, { comparison_price_minor: 900, comparison_unit: "KG" })),
  other_unit: rows((state, sub) => Object.assign(sub.substitute_for, { comparison_price_minor: 900, comparison_unit: "L" })),
  frozen: rows((state, sub) => { sub.temperature_condition = 7; }),
  no_storage: rows((state, sub) => { sub.temperature_condition = null; }),
  no_history: rows((state, sub) => { sub.delivery_reliability = { value: null, unit: "share_delivered", source: "none", certainty: "unknown" }; }),
  no_judge: rows((state) => { state.approval.judge.forEach((answer) => { answer.probability = null; }); }),
  no_substitute: (() => { const state = recorded(); delete line(state).substitute_for; return tradeOffs(state); })(),
};
console.log(JSON.stringify(drawn));
"""


@pytest.fixture(scope="module")
def drawn():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = PORTAL.read_text(encoding="utf-8")

    def cut(start: str, end: str) -> str:
        return script[script.index(start) : script.index(end)]

    code = "\n".join(
        [
            re.search(r"^const UNIT_WORDS = .*$", script, re.MULTILINE).group(0),
            cut("const round3 = ", "/*\n * The services write for the team"),
            cut("function stockText(claim) {", "function icon(name) {"),
            cut("const STORAGE_WORDS = ", "const TRADE_OFF_ICON = "),
        ]
    )
    harness = CASES % {"code": code, "recorded": RECORDED.as_posix()}
    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_the_four_sides_are_always_there_in_the_same_order(drawn):
    assert list(drawn["recorded"]) == ["cost", "dish", "work", "logistics"]
    assert [row["label"] for row in drawn["recorded"].values()] == [
        "Cost",
        "In the dish",
        "In the kitchen",
        "Storage, delivery",
    ]
    assert drawn["no_substitute"] == []


def test_cost_reads_two_signed_prices_side_by_side_and_never_works_one_out(drawn):
    cheaper, dearer = drawn["cheaper"]["cost"], drawn["dearer"]["cost"]

    assert cheaper["tone"] == "good"
    assert cheaper["text"].startswith("Cheaper: EUR 10.94 a kg, against EUR 12.86 a kg for the one you asked for.")
    assert dearer["tone"] == "ask" and dearer["text"].startswith(
        "More expensive: EUR 10.94 a kg, against EUR 9.00 a kg"
    )
    # The total is the approval's own, and no difference between the two prices is shown.
    assert "EUR 114.87 for the order." in cheaper["text"]
    assert "1.92" not in cheaper["text"] and "%" not in cheaper["text"]


def test_without_a_price_for_the_product_asked_the_card_says_so(drawn):
    for case in ("recorded", "other_unit"):  # no price in the quote, or a price in a unit that cannot be compared
        cost = drawn[case]["cost"]
        assert cost["tone"] == "note"
        assert "Valio's quote has no price for the one you asked for." in cost["text"]
        assert "Cheaper" not in cost["text"] and "More expensive" not in cost["text"]


def test_the_dish_is_the_assistants_two_answers_and_the_line_under_which_it_asks(drawn):
    dish = drawn["recorded"]["dish"]

    assert dish["tone"] == "ask"
    assert "93% sure it works the same way in the dish" in dish["text"]
    assert "64% sure it fits your kitchen's preferences" in dish["text"]
    assert dish["text"].endswith("Below 85%, it asks you.")
    # No answer from the judge is never shown as a score.
    assert drawn["no_judge"]["dish"] == {
        "tone": "ask",
        "label": "In the dish",
        "text": "Aimo Personal Assistant could not tell whether it works the same way in the dish, so it asks you.",
    }


def test_the_kitchen_side_is_the_pack_and_says_there_is_no_preparation_time(drawn):
    work = drawn["recorded"]["work"]

    assert work["tone"] == "note"
    assert work["text"] == (
        "21 pcs of 0.5 kg each. The one you asked for is sold by the kg. Valio's data gives no preparation time."
    )


def test_storage_and_delivery_come_from_the_signed_quote(drawn):
    logistics = drawn["recorded"]["logistics"]

    assert logistics["tone"] == "good"
    assert logistics["text"] == (
        "Chilled, like the one you asked for. Valio's stock: 100 pcs counted. Delivery Thu 19 Nov. "
        "In the past Valio delivered 100% of what was ordered of it."
    )


def test_a_change_of_storage_is_a_reason_to_ask_and_unknown_is_never_read_as_the_same(drawn):
    frozen, unknown = drawn["frozen"]["logistics"], drawn["no_storage"]["logistics"]

    assert frozen["tone"] == "ask"
    assert frozen["text"].startswith("Storage changes: frozen, where the one you asked for is chilled.")
    assert unknown["tone"] == "note"
    assert unknown["text"].startswith("Storage: unknown, and chilled for the one you asked for.")
    assert "Valio has no delivery history for it." in drawn["no_history"]["logistics"]["text"]
