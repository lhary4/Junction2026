"""The kitchen order page shows both audit logs under the order: the kitchen's own and Valio Aimo's.

The functions that draw them are cut out of portal.js and run alone in Node on the recorded demo states."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "surface" / "static" / "portal.js"
EXAMPLES = ROOT / "contract" / "examples"

# What the record functions of portal.js need around them, then one drawing per case.
RECORD_HARNESS = """
const fs = require("fs");
const app = { recordOpen: true };
const ASSISTANT = "Aimo Personal Assistant";
const esc = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const words = (code) => String(code ?? "").toLowerCase().replaceAll("_", " ");
const shortProof = (proof) => (proof && proof.length > 14 ? `${proof.slice(0, 12)}…` : proof);
%(lexicon)s
%(record)s
const state = (name) => JSON.parse(fs.readFileSync(`%(examples)s/demo-state.${name}.json`, "utf8"));
const drawn = {};
drawn.approved = recordPanel(state("substitution.approved"));
drawn.attack = recordPanel(state("attack"));
drawn.idle = recordPanel(state("idle"));
const tampered = state("normal-order");
tampered.audit.buyer[0].what = "<b>bold</b> <script>alert(1)</script>";
drawn.tampered = recordPanel(tampered);
app.recordOpen = false;
drawn.closed = recordPanel(state("normal-order"));
console.log(JSON.stringify(drawn));
"""


@pytest.fixture(scope="module")
def drawn():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    script = PORTAL.read_text(encoding="utf-8")
    harness = RECORD_HARNESS % {
        "lexicon": script[script.index("function lexicon(text) {") : script.index('/* "auto: all 7 rules pass"')],
        "record": script[script.index("const RECORD_WHO = ") : script.index("function orderView() {")],
        "examples": EXAMPLES.as_posix(),
    }
    result = subprocess.run([node, "-e", harness], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def load(name: str) -> dict:
    return json.loads((EXAMPLES / f"demo-state.{name}.json").read_text(encoding="utf-8"))


def test_both_logs_show_every_line_of_the_order(drawn):
    audit = load("substitution.approved")["audit"]
    html = drawn["approved"]

    assert f"Your kitchen's log · {len(audit['buyer'])} lines" in html
    assert f"Valio Aimo's log · {len(audit['merchant'])} lines" in html
    assert html.count('<li class="record__line') == len(audit["buyer"]) + len(audit["merchant"])
    # Who signed is in the kitchen's log, the sandbox payment and the receipt are in Valio's.
    assert "Mandate signed by human (chef)." in html
    assert "Sandbox payment" in html
    assert "receipt signed" in html


def test_the_lines_use_the_chefs_words_and_keep_the_facts(drawn):
    html = drawn["approved"]

    assert "Your assistant asked to order quote" in html
    assert "The agent asked" not in html
    # Amounts and identifiers are shown as the services wrote them.
    for event in load("substitution.approved")["audit"]["merchant"]:
        assert event["hash"][:12] in html


def test_an_attack_leaves_no_line_in_the_kitchens_log_and_three_refusals_in_valios(drawn):
    html = drawn["attack"]

    assert "never reached your safety checks" in html
    assert html.count("record__line--refused") == 3
    assert "above the EUR 1,500.00" in html


def test_text_from_the_logs_cannot_add_html_to_the_page(drawn):
    assert "<script>" not in drawn["tampered"]
    assert "&lt;script&gt;" in drawn["tampered"]


def test_closed_it_is_one_button_and_without_an_order_it_is_nothing(drawn):
    assert 'data-action="record"' in drawn["closed"]
    assert "record__line" not in drawn["closed"]
    assert drawn["idle"] == ""
