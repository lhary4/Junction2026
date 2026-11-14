"""The approval page in mock mode: its files exist, it only reads examples that exist, and its drawing code
keeps the product rules (unknown is shown as unknown, text from the agent cannot add HTML, no signature check
means "not checked yet"). The drawing code is JavaScript, so those tests run it with Node and skip without it."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "surface" / "static"
EXAMPLES = ROOT / "contract" / "examples"

# Runs surface/static/app.js outside a browser and prints what the page would draw, as JSON.
NODE_SCRIPT = r"""
const fs = require("fs");
const path = require("path");
const [appPath, examplesDir] = process.argv.slice(1);
const app = require(appPath);

const files = {};
for (const name of fs.readdirSync(examplesDir)) {
  files[name] = JSON.parse(fs.readFileSync(path.join(examplesDir, name), "utf8"));
}
const data = app.buildMockData(files);
const quote = (key) => data.quotes.find((entry) => entry.key === key);
const rows = (key) =>
  app.comparisonRows(quote(key).checkout, data.products).map((row) => ({
    id: row.id,
    roleKind: row.roleKind,
    priceMinor: row.price ? row.price.minor : null,
    priceHasClaim: Boolean(row.price && row.price.claim),
  }));

const out = {
  money: app.money(202000, "EUR"),
  deadline: app.dayAndTime("2026-11-15T17:00:00+02:00"),
  countdown: app.countdownText(26 * 3600 * 1000 + 14 * 60 * 1000 + 3000),
  unknownClaim: app.claimValueText({ value: null, unit: "share_delivered", source: "none", certainty: "unknown" }),
  rowsAct1: rows("act1"),
  rowsAct3: rows("act3"),
  signatures: Object.fromEntries(data.quotes.map((entry) => [entry.key, app.signatureState(entry, data.audit).kind])),
  offersHtml: app.offersView(data),
  pairs: app.substitutionPairs(data.approvals[1].approval),
  chainOk: app.chainState(data.audit.buyer).ok,
  chainBroken: app.chainState(data.audit.buyer.map((event) => (event.seq === 3 ? { ...event, prev_hash: "ffff" } : event))),
  auditGroups: app.auditGroups(data.audit).map((group) => [group.id, group.buyer.length, group.merchant.length, group.hashes.length]),
  auditHtml: app.auditView(data),
  pendingHtml: app.approvalsView(data, null),
};

// The agent controls request_text. It must reach the page as text, never as HTML.
data.approvals[0].approval.request_text = '<script>alert(1)</script><button data-decision="approve">x</button>';
out.hostileHtml = app.approvalsView(data, null);

const states = {};
for (const state of ["approved", "rejected", "expired"]) {
  for (const entry of data.approvals) app.setMockState(entry, state, data.policy);
  states[state] = app.approvalsView(data, null);
}
out.states = states;
console.log(JSON.stringify(out));
"""


def test_the_three_files_of_the_page_exist_and_are_linked():
    index = (STATIC / "index.html").read_text()
    assert (STATIC / "app.js").exists() and (STATIC / "style.css").exists()
    assert 'src="app.js"' in index and 'href="style.css"' in index


def test_mock_mode_only_reads_examples_that_exist():
    names = set(re.findall(r'"([\w.\-]+\.json)"', (STATIC / "app.js").read_text()))
    assert names, "app.js should name the example files it reads"
    missing = sorted(name for name in names if not (EXAMPLES / name).exists())
    assert not missing, f"app.js reads example files that do not exist: {missing}"


def test_the_page_needs_no_internet():
    """It is projected on stage: no font, script or image may come from another site."""
    for name in ["index.html", "style.css"]:
        assert "http://" not in (STATIC / name).read_text() and "https://" not in (STATIC / name).read_text(), name


@pytest.fixture(scope="module")
def drawn():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed: the page's JavaScript cannot be run here")
    result = subprocess.run(
        [node, "-e", NODE_SCRIPT, str(STATIC / "app.js"), str(EXAMPLES)],
        capture_output=True,
        check=False,  # a failure is reported below, with what Node printed
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_money_dates_and_countdown_read_well(drawn):
    assert drawn["money"] == "EUR 2,020.00"
    assert drawn["deadline"] == "Sun 15 Nov, 17:00"  # Helsinki time, whatever the laptop's time zone
    assert drawn["countdown"] == "26 h 14 min 03 s"
    assert drawn["unknownClaim"] == "unknown"


def test_a_price_only_comes_from_the_signed_quote(drawn):
    by_id = {row["id"]: row for row in drawn["rowsAct1"]}
    assert drawn["rowsAct1"][0]["id"] == "464306" and by_id["464306"]["priceMinor"] == 101
    # The four other products are not in the act 1 quote: the page shows no price for them, it never guesses one.
    assert [row["priceMinor"] for row in drawn["rowsAct1"][1:]] == [None, None, None, None]


def test_act_3_lists_the_lines_then_the_alternatives_then_the_rest(drawn):
    assert [(row["id"], row["roleKind"]) for row in drawn["rowsAct3"]] == [
        ("469363", "quoted"),
        ("464201", "substitute"),
        ("463380", "alternative"),
        ("464320", "alternative"),
        ("464306", "other"),
    ]
    by_id = {row["id"]: row for row in drawn["rowsAct3"]}
    assert by_id["464320"]["priceMinor"] == 178 and not by_id["464320"]["priceHasClaim"]


def test_a_quote_is_only_called_verified_when_the_harness_said_so(drawn):
    assert drawn["signatures"] == {"act1": "ok", "act2": "ok", "act3": "wait", "act4": "bad"}
    assert "Signed by Valio Aimo, verified" in drawn["offersHtml"]


def test_no_cell_of_the_comparison_is_empty(drawn):
    assert not re.search(r"<td>\s*</td>", drawn["offersHtml"])
    assert "badge--unknown" in drawn["offersHtml"]  # the Arla reliability is unknown, and says so


def test_the_pending_cards_show_the_reason_the_countdown_and_both_buttons(drawn):
    html = drawn["pendingHtml"]
    assert "2020.00 EUR is above the 1500.00 EUR limit: a human must sign." in html
    assert "countdown__digits" in html and "2026-11-15T17:00:00+02:00" in html
    assert html.count('data-decision="approve"') == 2 and html.count('data-decision="reject"') == 2
    # The substitution card: both products, the allergens that differ, the judge's bar.
    assert drawn["pairs"] == [["469363", "464320"]]
    assert "chip--new" in html and "chip--gone" in html
    assert html.count("judge__marker") == 2


def test_text_from_the_agent_cannot_add_html_to_the_card(drawn):
    html = drawn["hostileHtml"]
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert html.count('data-decision="approve"') == 2  # still only the two real buttons


@pytest.mark.parametrize(
    ("state", "sentence"),
    [
        ("approved", "The signature covers this exact quote and no other."),
        ("rejected", "Nothing was signed, nothing was ordered."),
        ("expired", "No answer before the order cut-off"),
    ],
)
def test_a_decided_card_says_what_happened_and_has_no_button(drawn, state, sentence):
    html = drawn["states"][state]
    assert sentence in html
    assert "<button" not in html
    if state != "expired":
        assert "procurement.manager@demo-hotel.example" in html


def test_the_audit_lines_up_both_logs_by_quote(drawn):
    assert drawn["auditGroups"] == [["chk_act1_demo", 5, 3, 1]]
    assert "both logs name the same signed quote" in drawn["auditHtml"]
    assert drawn["chainOk"] is True
    assert drawn["chainBroken"] == {"ok": False, "brokenAt": 3}
