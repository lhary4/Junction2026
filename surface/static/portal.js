"use strict";

/*
 * The kitchen order page: the chef goes through the recipes, the stock, then lets the assistant order.
 *
 * The page draws what it is given and never works out a fact of Valio's:
 * prices, Valio's stock, totals, verdicts and signatures all come from the demo state.
 * What the page does work out is the kitchen's own arithmetic: to order = need - in stock.
 *
 * Where the data comes from (see "Sources" below):
 * - the demo driver   GET /state, POST /scenarios/{id}/run, POST /reset      docs/contract.md, "The demo state"
 * - the harness       GET /policy, POST /approvals/{id}/decision              the chef's signature goes straight there
 * - the assistant     GET /health, POST /chat                                  surface/assistant.py, the chat (Gemini)
 * - the kitchen       kitchen/recipes.json, stock.<scenario>.json, bookings.json   synthetic, stands in for the restaurant's system
 *
 * When the demo driver does not answer, the page replays the runs recorded in contract/examples/ (real runs of 14/11).
 *
 * Words. The buyer is a chef, not an engineer: the buying agent and the judge are both shown as
 * "Aimo Personal Assistant", and each rule of the harness has a plain sentence (see CHECK_WORDS).
 */

const query = new URLSearchParams(window.location.search);
const DRIVER_URL = (query.get("driver") || "http://localhost:8003").replace(/\/$/, "");
const HARNESS_URL = (query.get("harness") || "http://localhost:8002").replace(/\/$/, "");
const ASSISTANT_URL = (query.get("assistant") || "http://localhost:8004").replace(/\/$/, "");
const REVEAL_MS = 420; // time between two steps lighting up: eight steps take under four seconds
const POLL_MS = 1000;
const SERVICES_MS = 5000; // how often the page looks whether the services are there
const ASSISTANT = "Aimo Personal Assistant";

// Which recorded run each scenario replays, and which stock count goes with it.
const REPLAY_FILE = { "normal-order": "normal-order", substitution: "substitution.pending", attack: "attack" };
const STOCK_FILE = { "normal-order": "normal-order", substitution: "substitution", attack: "normal-order" };

const UNIT_WORDS = { ST: ["pc", "pcs"], KG: ["kg", "kg"], L: ["l", "l"], PAK: ["pack", "packs"], BAG: ["bag", "bags"] };
const ALLERGEN_WORDS = { AM: "milk", AW: "gluten", GO: "oats", NR: "rye", AF: "fish", AS: "sesame", ML: "lactose", AP: "peanuts", AN: "tree nuts" };
const SIGNER_WORDS = { manager: "you", agent: "assistant", merchant: "Valio", none: "" };
const SPEAKER_WORDS = { manager: "Chef", agent: ASSISTANT, merchant: "Valio Aimo", none: "Safety checks" };
const SHORTFALL_WORDS = { late_delivery: "its order cut-off has passed", out_of_stock: "Valio cannot deliver it", not_found: "Valio has no price for it" };
const JUDGE_WORDS = { within_preferences: "It fits your kitchen's preferences", same_use: "It works the same way in the dish" };

// The steps of the trail, in a chef's words. The second word is the term of the AP2 protocol, shown small.
const STEP_WORDS = {
  open_mandate: "Your standing permission",
  signed_quote: "Valio's prices, signed",
  verdict: "Safety checks",
  closed_mandates: "Signature for this order",
  merchant_verifies: "Valio checks the signature",
  sandbox_payment: "Payment, in test mode",
  signed_receipt: "Valio's signed receipt",
  delivery: "Delivery scheduled",
};

/*
 * One plain sentence for each rule of the harness (harness/rules.py), by outcome.
 * `pass` reads as a reassurance, `human` as the reason the chef is asked, `deny` as the reason it is blocked.
 * `value` shows the numbers the harness sent with the rule. A rule that is not listed shows the harness's own sentence.
 */
const CHECK_WORDS = {
  "quote-signature": {
    pass: "The prices really come from Valio Aimo",
    human: "We could not confirm the prices come from Valio Aimo",
    deny: "The prices were changed after Valio signed them",
  },
  "quote-not-expired": {
    pass: "The prices are still valid",
    human: "The prices are about to expire",
    deny: "The prices have expired",
    value: (e) => (e.expires_at ? `until ${clock(e.expires_at)}` : ""),
  },
  "merchant-allowed": {
    pass: "Valio Aimo is a supplier you allow",
    human: "This supplier is not on your list",
    deny: "This supplier is not on your list",
  },
  "allergen-not-blocked": {
    pass: "None of the allergens you ban",
    human: "An allergen you ban may be in the order",
    deny: "The order contains an allergen you ban",
    value: (e) => (e.blocked?.length ? `you ban ${allergenNames(e.blocked)}` : ""),
  },
  "allergen-data-known": {
    pass: "Allergen information is complete for every product",
    human: "Allergen information is missing for a product",
    deny: "Allergen information is missing for a product",
  },
  "allergen-unchanged-on-substitution": {
    pass: "The substitute has the same allergens",
    human: "The substitute does not have the same allergens",
    deny: "The substitute does not have the same allergens",
    value: (e) => (e.contains?.length ? `contains ${allergenNames(e.contains)}` : ""),
  },
  "delivery-on-time": {
    pass: "It arrives in time for your service",
    human: "It arrives later than you asked",
    deny: "It arrives too late for your service",
    value: (e) => (e.promised && e.requested ? `arrives ${dayLong(e.promised)}, needed ${dayLong(e.requested)}` : ""),
  },
  "spend-limit": {
    pass: "The total is within your spending limit",
    human: "The total is above your spending limit",
    deny: "The total is above your spending limit",
    value: (e) => (Number.isFinite(e.total_minor) && Number.isFinite(e.limit_minor) ? `${money(e.total_minor)} of ${money(e.limit_minor)}` : ""),
  },
  "substitution-within-preferences": {
    pass: "The substitute fits your kitchen's preferences",
    human: "Not sure enough that the substitute fits your kitchen",
    deny: "The substitute does not fit your kitchen's preferences",
  },
};
const OUTCOME_WORDS = { pass: "OK", human: "You decide", deny: "Blocked" };

const el = (id) => document.getElementById(id);

const app = {
  mode: "replay", // "live" when the demo driver answers
  up: { driver: false, harness: false, assistant: false },
  scenarioId: query.get("scenario") === "substitution" ? "substitution" : "normal-order",
  step: 1, // 1 recipes, 2 stock, 3 order
  confirmed: { recipes: null, stock: null }, // the time the chef confirmed each step
  recipeId: null,
  stockFilter: "all",
  state: null, // the demo state
  shown: 0, // how many steps of the trail are lit
  fresh: null, // the step that has just lit up, for the animation
  told: {}, // which steps the assistant has already told in the conversation
  talk: [], // the conversation, in order
  kitchen: { recipes: null, bookings: null, stock: null },
  lines: [], // the stock table the chef works on: the count, with the chef's and the assistant's changes
  sentKey: null, // the quantities of the order on screen
  correcting: false, // the chef is correcting the quantities of a refused order
  mismatch: false, // the quote is not for the quantities the chef asked
  detailsOpen: true, // the full comparison of a substitute
  policy: null,
  busy: false,
  chatBusy: false,
  problem: null,
  interactionId: null, // Gemini Interactions API server-side stateful chain id
  assistantModel: "",
  decisionModel: "gemini-decision-1",
  followUps: [], // contextual follow-up chips suggested by Gemini
  focusedProductId: null, // ingredient or product highlighted by Gemini
  pulseOnline: false,
  pulseBusy: false,
  pulseData: null, // calibrated readiness metrics from gemini-decision-1
  pulseKey: "",
};

/* ---------- Small helpers ---------- */

/* Text from the data is only text: everything goes through esc() before it reaches the page. */
function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/* Only touch the page when something changed: a running animation, a focused field and typed text survive. */
function setHtml(node, html) {
  if (node.dataset.drawn === html) return;
  node.dataset.drawn = html;
  node.innerHTML = html;
}

async function call(url, options = {}, timeoutMs = 4000) {
  const stop = new AbortController();
  const timer = setTimeout(() => stop.abort(), timeoutMs);
  try {
    const answer = await fetch(url, { ...options, signal: stop.signal });
    if (!answer.ok) {
      let body = await answer.text().catch(() => "");
      try {
        const detail = JSON.parse(body).detail; // our services explain a refusal in `detail`
        if (typeof detail === "string") body = detail;
      } catch {
        /* not JSON: keep the text */
      }
      const error = new Error(`${answer.status} ${body.slice(0, 200)}`.trim());
      error.status = answer.status;
      throw error;
    }
    return await answer.json();
  } finally {
    clearTimeout(timer);
  }
}

const sendJson = (method, url, body, timeoutMs) =>
  call(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) }, timeoutMs);
const postJson = (url, body, timeoutMs) => sendJson("POST", url, body, timeoutMs);

const round3 = (value) => Math.round(Number(value) * 1000) / 1000;

function num(value) {
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
}

const unitWord = (unit, amount = 2) => (UNIT_WORDS[unit] ? UNIT_WORDS[unit][Number(amount) === 1 ? 0 : 1] : String(unit ?? "").toLowerCase());
const qty = (amount, unit) => `${num(amount)} ${unitWord(unit, amount)}`.trim();

function money(minor, currency = "EUR") {
  return `${currency} ${(minor / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function dayOf(isoDate, options) {
  const [y, m, d] = String(isoDate).slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", ...options }).format(new Date(Date.UTC(y, m - 1, d)));
}

const dayShort = (isoDate) => dayOf(isoDate, { weekday: "short", day: "numeric" }); // Thu 19
const dayLong = (isoDate) => dayOf(isoDate, { weekday: "short", day: "numeric", month: "short" }); // Thu 19 Nov

function clock(isoTime) {
  if (!isoTime) return "";
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Helsinki" }).format(new Date(isoTime));
}

const timeNow = () => new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" }).format(new Date());
const words = (code) => String(code ?? "").toLowerCase().replaceAll("_", " ");
const shortProof = (proof) => (proof && proof.length > 14 ? `${proof.slice(0, 12)}…` : proof);
const titleCase = (text) => String(text ?? "").charAt(0).toUpperCase() + String(text ?? "").slice(1);
const allergenNames = (codes) => codes.map((code) => ALLERGEN_WORDS[code] ?? code).join(", ");

/*
 * The services write for the team ("the agent", "the judge", "the harness"). The chef reads one name:
 * Aimo Personal Assistant. Only the words change, never a number or a fact.
 */
function lexicon(text) {
  return String(text ?? "")
    .replace(/\b[Tt]he judge\b/g, ASSISTANT)
    .replace(/\bThe (buying )?agent\b/g, "Your assistant")
    .replace(/\bthe (buying )?agent\b/g, "your assistant")
    .replace(/\bThe harness\b/g, "The safety checks")
    .replace(/\bthe harness\b/g, "the safety checks")
    .replace(/\bthe manager's\b/g, "the chef's")
    .replace(/\bthe manager\b/g, "the chef");
}

/* "auto: all 7 rules pass" -> "All 7 rules pass": the code word in front is for the team. */
const plainDetail = (detail) => titleCase(lexicon(String(detail ?? "").replace(/^(auto|human|deny):\s*/, "")));

function allergenText(allergens) {
  if (!allergens || allergens.data !== "complete") return "unknown";
  const list = allergens.contains ?? [];
  return list.length ? allergenNames(list) : "none declared";
}

/* Valio's stock claim, in words. Unknown is never shown as available. */
function stockText(claim) {
  if (!claim || claim.value === null || claim.certainty === "unknown") return "unknown";
  if (claim.value === "not_given") return "available, count not given";
  return `${qty(claim.value, claim.unit)} counted`;
}

function icon(name) {
  const paths = {
    check: '<path d="M4 10.500l4 4 8-9" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>',
    cross: '<path d="M5.5 5.5l9 9M14.5 5.5l-9 9" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/>',
    wait: '<circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" stroke-width="1.9"/><path d="M10 6v4.4l2.8 1.6" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>',
    skip: '<path d="M5.5 10h9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    dispatch: '<path d="M4 3.5h8.5L16 7v9.5H4z" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/><path d="M12 3.5V7h4M7 11.5h6M10.5 9l2.5 2.5-2.5 2.5" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
    terminal: '<rect x="2.75" y="3.75" width="14.5" height="12.5" rx="1.75" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M6.25 8l2.5 2-2.5 2M10.25 12h3.25" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
    gauge: '<path d="M3.5 13.5a6.5 6.5 0 1 1 13 0" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M10 13l3.2-4.2" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="10" cy="13" r="1.4" fill="currentColor"/>',
    user: '<circle cx="10" cy="6.500" r="3.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3.5 17c.6-3.1 3.2-5 6.5-5s5.9 1.9 6.5 5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    arrow: '<path d="M4 10h11M11 5.5L15.5 10 11 14.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    lock: '<rect x="4.75" y="9" width="10.5" height="7.75" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M7.2 9V6.6a2.8 2.8 0 0 1 5.6 0V9" fill="none" stroke="currentColor" stroke-width="1.7"/>',
    shield: '<path d="M10 2.2l6.3 2.3v4.7c0 3.9-2.6 7.1-6.3 8.6-3.7-1.5-6.3-4.7-6.3-8.6V4.5z" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linejoin="round"/><path d="M7.1 10.1l2.1 2.1 3.9-4.1" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>',
    pen: '<path d="M3.5 16.5l.9-3.7L13.7 3.5l2.8 2.8-9.3 9.3z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M11.8 5.4l2.8 2.8" stroke="currentColor" stroke-width="1.7"/>',
    send: '<path d="M4 10h11.5M11 5.5L15.5 10 11 14.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    pulse: '<path d="M2.5 10.5h3l2.1-5 3.2 9.5 2.4-6.2 1.6 1.7h2.7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  };
  return `<svg class="icon" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">${paths[name]}</svg>`;
}

/* ---------- Sources ---------- */

const driver = {
  state: () => call(`${DRIVER_URL}/state`, {}, 1500),
  // The lines are what the chef confirmed in the stock table. A driver that only plays fixed scenarios ignores them.
  run: (id, body) => postJson(`${DRIVER_URL}/scenarios/${encodeURIComponent(id)}/run`, body ?? {}, 60000),
  reset: () => postJson(`${DRIVER_URL}/reset`, {}),
};

const harness = {
  policy: () => call(`${HARNESS_URL}/policy`, {}, 1200),
  decide: (approvalId, decision) =>
    postJson(`${HARNESS_URL}/approvals/${encodeURIComponent(approvalId)}/decision`, { decision, decided_by: "chef" }, 30000),
  // Asked of the harness, not there yet (team/colette/notes.md): the chef signs a new spending limit.
  setLimit: (minor) => sendJson("PUT", `${HARNESS_URL}/policy/autonomous-limit`, { autonomous_limit_minor: minor, decided_by: "chef" }, 8000),
};

const assistant = {
  health: () => call(`${ASSISTANT_URL}/health`, {}, 1200),
  chat: (turns, state, previous_interaction_id) =>
    postJson(`${ASSISTANT_URL}/chat`, { turns, state, previous_interaction_id }, 30000),
  pulse: (state) => postJson(`${ASSISTANT_URL}/pulse`, { state }, 8000),
};

// The page sits in surface/static/. Served by the harness, the same path reaches /contract/examples/.
const EXAMPLES_FOLDER = "../../contract/examples/";
const recorded = (name) => call(`${EXAMPLES_FOLDER}demo-state.${name}.json`);

const kitchenApi = {
  recipes: () => call("kitchen/recipes.json"),
  bookings: () => call("kitchen/bookings.json"),
  stock: (scenarioId) => call(`kitchen/stock.${STOCK_FILE[scenarioId] ?? "normal-order"}.json`),
};

/* ---------- What is on screen right now ---------- */

const status = () => app.state?.scenario?.status ?? "idle";
const hasRun = () => status() !== "idle";
const finished = () => ["done", "refused"].includes(status());
const missingLines = () => app.lines.filter((line) => line.to_order > 0);
const neededNow = (line) => round3(Math.max(0, line.need - line.in_stock));
const changedLines = () => app.lines.filter((line) => line.by.in_stock || line.by.to_order);

/* The lines the assistant will ask Valio for: what is short in the stock table. */
const orderLines = () =>
  missingLines().map((line) => ({ product_id: line.product_id, name: line.name, amount: line.to_order, unit: line.unit, dish: line.dishes.join(", ") }));

const linesKey = (lines) =>
  (lines ?? [])
    .map((line) => `${line.product_id}:${round3(line.amount)}`)
    .sort()
    .join("|");

/* The chef changed the quantities after an order finished: what is on screen is a new order, not sent yet. */
function dirty() {
  if (!hasRun() || !finished() || app.sentKey === null) return false;
  // The attack is not the chef's order: its quantities only reach the table when the chef corrects them.
  if (app.state.scenario.id === "attack" && !app.correcting) return false;
  return linesKey(orderLines()) !== app.sentKey;
}

/* Is there an order on screen that matches the table? */
const orderOnScreen = () => hasRun() && !dirty();

/* The trail: the seven steps of the demo state, and an eighth the page reads from the order Valio accepted. */
function trailSteps() {
  const steps = (app.state?.steps ?? []).map((step) => ({ ...step }));
  if (!steps.length) return steps;
  const receipt = steps.find((step) => step.key === "signed_receipt");
  const order = app.state.order;
  const delivery = { key: "delivery", title: "Delivery", signer: "merchant", status: "pending", detail: null, proof: null };
  if (receipt?.status === "done" && order) {
    delivery.status = "done";
    delivery.detail = `Valio Aimo delivers on ${dayLong(order.delivery_date)}. Order ${order.order_id} is ${words(order.status)}.`;
  } else if (receipt && ["skipped", "refused"].includes(receipt.status)) {
    delivery.status = "skipped";
    delivery.detail = "No order, so nothing is delivered.";
  }
  return [...steps, delivery];
}

/* The steps that have happened are lit one after the other: this is how many may be lit. */
function reachable() {
  if (!hasRun()) return 0;
  let last = 0;
  trailSteps().forEach((step, index) => {
    if (step.status !== "pending") last = index + 1;
  });
  return last;
}

const lit = () => (orderOnScreen() ? app.shown : 0);
const revealing = () => hasRun() && app.shown < reachable();
/* The assistant is at work, or an order waits for a signature: the quantities cannot change. */
const inFlight = () => app.busy || revealing() || ["running", "waiting_for_human"].includes(status());
const canEdit = () => !inFlight();

let freshTimer = null;
let revealTimer = null;
function reveal() {
  clearTimeout(revealTimer);
  clearTimeout(freshTimer);
  if (app.shown >= reachable()) {
    // Leave the last step its animation, then draw it at rest.
    freshTimer = setTimeout(() => {
      app.fresh = null;
      draw();
    }, 900);
    draw();
    schedulePulse();
    return;
  }
  app.shown += 1;
  app.fresh = app.shown - 1;
  tell();
  draw();
  revealTimer = setTimeout(reveal, REVEAL_MS);
}

/* ---------- The conversation ---------- */

function say(who, text, more = {}) {
  app.talk.push({ who, text, ...more });
}

/* Each step that lights up is told once in the conversation, in the words of who did it. */
function tell() {
  trailSteps()
    .slice(0, app.shown)
    .forEach((step, index) => {
      if (!step.detail || app.told[index] === step.status) return;
      app.told[index] = step.status;
      const asks = step.status === "waiting";
      const byChef = step.signer === "manager" && !asks;
      say(byChef ? "chef" : "agent", plainDetail(step.detail), {
        speaker: asks ? ASSISTANT : SPEAKER_WORDS[step.signer],
        proof: step.proof,
        status: byChef ? null : step.status,
      });
    });
}

function openingLine() {
  const recipes = app.kitchen.recipes?.recipes ?? [];
  const services = app.kitchen.bookings?.services ?? [];
  const days = services.length ? `${dayShort(services[0].date)} to ${dayLong(services.at(-1).date)}` : "the coming services";
  return `These are the ${recipes.length} recipes on the menu for ${days}. Confirm them and I check them against the stock.`;
}

function stockLine() {
  const stock = app.kitchen.stock;
  const missing = missingLines().length;
  return `${missing} of ${app.lines.length} ingredients are short for the ${stock.for_services} services, from the count of ${dayLong(stock.counted_at)}. Correct a count in the table or tell me what changed, then confirm.`;
}

const limitKnown = () => app.policy && Number.isFinite(app.policy.autonomous_limit_minor);
const limitText = () => (limitKnown() ? money(app.policy.autonomous_limit_minor, app.policy.currency) : null);

function orderLine() {
  const missing = missingLines().length;
  const limit = limitKnown() ? ` Up to ${limitText()} an order I may sign alone. Above that, or if a product changes, you sign here.` : "";
  return `I will ask Valio Aimo for a signed quote for ${missing === 1 ? "this ingredient" : `these ${missing} ingredients`}.${limit}`;
}

/* ---------- The stock table: the chef's and the assistant's changes ---------- */

function loadLines(stock) {
  app.lines = (stock?.lines ?? []).map((line) => ({ ...line, counted: line.in_stock, by: {} }));
}

/* Change one cell. `by` is who changed it: "you", the assistant, or the refused order. Returns what changed, or null. */
function setStock(productId, field, amount, by) {
  const line = app.lines.find((entry) => entry.product_id === productId);
  if (!line || !["in_stock", "to_order"].includes(field) || !Number.isFinite(amount) || amount < 0 || !canEdit()) return null;
  const before = line[field];
  const value = round3(amount);
  if (value === before) return null;
  if (field === "in_stock") {
    line.in_stock = value;
    line.to_order = neededNow(line); // the kitchen's own arithmetic
    line.by.in_stock = value === line.counted ? null : by;
    line.by.to_order = null;
  } else {
    line.to_order = value;
    line.by.to_order = value === neededNow(line) ? null : by;
  }
  return { line, field, before, after: value };
}

const changeText = (change) =>
  `${change.line.name}: ${change.field === "in_stock" ? "in stock" : "to order"} ${qty(change.before, change.line.unit)} → ${qty(change.after, change.line.unit)}`;

function undoChanges() {
  if (!canEdit()) return;
  app.lines.forEach((line) => {
    line.in_stock = line.counted;
    line.to_order = neededNow(line);
    line.by = {};
  });
}

/* Every line back to what the kitchen needs, with the stock counts as they are. */
function useNeed() {
  if (!canEdit()) return;
  app.lines.forEach((line) => {
    line.to_order = neededNow(line);
    line.by.to_order = null;
  });
}

/* ---------- Drawing: header ---------- */

function drawAccount() {
  const name = app.state?.kitchen?.name ?? "Ravintola Demo";
  const city = app.state?.kitchen?.city ? ` · ${app.state.kitchen.city}` : "";
  setHtml(
    el("account"),
    `<button class="account__btn" id="account-btn" type="button" aria-haspopup="true" aria-expanded="false" aria-controls="account-menu">
      ${icon("user")}<span>${esc(name)}${esc(city)}</span>
      <svg class="account__chevron" width="13" height="13" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M2 5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
    <div class="account__menu" id="account-menu" hidden>
      <p class="account__who"><strong>${esc(name)}</strong>Customer ${esc(app.state?.kitchen?.customer ?? "unknown")}</p>
      <button class="account__item" type="button" data-action="limit">Autonomous mandate limit</button>
      <button class="account__item" type="button" data-action="reset">Reset order desk</button>
    </div>`
  );
}

function drawPlanning() {
  const services = app.kitchen.bookings?.services ?? [];
  if (!services.length) {
    setHtml(el("planning"), "");
    return;
  }
  const capacity = app.kitchen.recipes?.covers_per_service || app.state?.kitchen?.covers_per_service || 50;
  const days = services
    .map((service, idx) => {
      const pct = Math.min(100, Math.round((Number(service.booked) / capacity) * 100));
      const target = idx === 0;
      return `<li class="day${target ? " day--target" : ""}">
          <div class="day__top">
            <span class="day__name">${esc(dayShort(service.date))}</span>
            ${target ? '<span class="day__tag">Delivery</span>' : `<span class="day__pct mono">${pct}%</span>`}
          </div>
          <p class="day__nums"><b>${esc(service.booked)}</b> booked <span class="day__sep">·</span> <span>${esc(service.projected)} proj.</span></p>
          <div class="day__meter" aria-hidden="true"><span style="width:${pct}%"></span></div>
        </li>`;
    })
    .join("");
  setHtml(
    el("planning"),
    `<ol class="days" aria-label="Covers per service: booked, and projected by the kitchen">${days}</ol>`
  );
}

/* ---------- Drawing: the chef's steps and the button ---------- */

function drawFlow() {
  const recipes = app.kitchen.recipes?.recipes ?? [];
  const missing = missingLines().length;
  const sent = orderOnScreen();
  const accepted = sent && status() === "done" && !app.busy && !revealing(); // not before the last step has lit up
  const items = [
    { n: 1, title: "Recipes", sub: app.confirmed.recipes ? `Confirmed ${app.confirmed.recipes}` : `${recipes.length} courses on menu`, done: Boolean(app.confirmed.recipes), open: true },
    { n: 2, title: "Stock", sub: app.confirmed.stock ? `Confirmed ${app.confirmed.stock} · ${missing} short` : `${missing} lines to order`, done: Boolean(app.confirmed.stock), open: Boolean(app.confirmed.recipes) || hasRun() },
    { n: 3, title: "Order", sub: accepted ? "Signed & accepted" : "Quote & signatures", done: accepted, open: Boolean(app.confirmed.stock) || hasRun() },
  ];
  setHtml(
    el("flow"),
    items
      .map(
        (item) => `<button class="flow__step${item.done ? " flow__step--done" : ""}" type="button" data-step="${item.n}"
            ${app.step === item.n ? 'aria-current="step"' : ""} ${item.open ? "" : "disabled"}>
            <span class="flow__num">${item.done ? icon("check") : String(item.n).padStart(2, "0")}</span>
            <span class="flow__text"><b>${item.title}</b><span>${esc(item.sub)}</span></span>
          </button>`
      )
      .join("")
  );

  let cta = "";
  if (inFlight()) {
    const waiting = status() === "waiting_for_human" && !app.busy && !revealing();
    cta = waiting
      ? `<p class="cta__status cta__status--waiting_for_human">${icon("pen")}<span>Your signature is needed</span></p>
         <button class="btn btn--reject-outline" type="button" data-action="reject">Reject</button>`
      : `<p class="cta__status">${icon("wait")}<span>Your assistant is at work…</span></p>`;
  } else if (app.step === 1) {
    cta = `<button class="btn btn--primary" type="button" data-action="confirm-recipes">${app.confirmed.recipes ? "Go to stock ledger" : "Confirm recipes"} ${icon("arrow")}</button>`;
  } else if (app.step === 2) {
    cta = `<button class="btn btn--primary" type="button" data-action="confirm-stock">${sent ? "Back to the order" : "Confirm stock"} ${icon("arrow")}</button>`;
  } else if (sent) {
    const done = status() === "done";
    cta = `<p class="cta__status cta__status--${done ? "done" : "refused"}">${done ? `${icon("check")}<span>Order sent</span>` : `${icon("cross")}<span>No order placed</span>`}</p>
      ${done ? "" : '<button class="btn btn--primary" type="button" data-action="correct">Correct quantities</button>'}
      <button class="btn btn--ghost" type="button" data-action="reset">New order</button>`;
  } else {
    cta = `<button class="btn btn--primary" type="button" data-action="run" ${missing ? "" : "disabled"}>${icon("dispatch")} Order with my assistant</button>`;
  }
  setHtml(el("cta"), cta);
}

/* ---------- Drawing: who signs (AP2 Cryptographic Vault) ---------- */

function sealHtml() {
  if (!orderOnScreen() && !app.busy) return `${icon("shield")}<span>No signature, no order.</span>`;
  if (app.busy || revealing()) return `${icon("shield")}<span>Verifying mandate chain…</span>`;
  if (status() === "waiting_for_human") return `${icon("pen")}<span>Waiting for your signature.</span>`;
  if (status() === "refused") return `${icon("shield")}<span>Stopped: no valid signature, no order.</span>`;
  if (status() === "done") {
    const names = { manager: "you", agent: "your assistant", merchant: "Valio" };
    const signers = [...new Set(trailSteps().filter((step) => step.status === "done" && names[step.signer]).map((step) => names[step.signer]))];
    return `${icon("shield")}<span>Signed &amp; verified: ${esc(signers.join(", "))}.</span>`;
  }
  return `${icon("shield")}<span>No signature, no order.</span>`;
}

function drawTrail() {
  const steps = trailSteps();
  const shown = lit();
  const items = steps
    .map((step, index) => {
      const on = index < shown;
      const state = on ? step.status : "pending";
      const numStr = String(index + 1).padStart(2, "0");
      const mark = { done: icon("check"), refused: icon("cross"), waiting: icon("wait"), skipped: icon("skip") }[state] ?? numStr;
      const signer = on && state !== "skipped" && SIGNER_WORDS[step.signer] ? `<span class="step__signer">${esc(SIGNER_WORDS[step.signer])}</span>` : "";
      const classes = [
        `step--${state}`,
        index === app.fresh && on ? "step--fresh" : "",
      ]
        .filter(Boolean)
        .join(" ");
      return `<li class="step ${esc(classes)}">
          <span class="step__dot" aria-hidden="true">${mark}</span>
          <div class="step__body">
            <div class="step__top">
              <span class="step__index mono">${numStr}</span>
              <span class="step__name">${esc(STEP_WORDS[step.key] ?? step.title)}</span>${signer}<span class="visually-hidden">, ${esc(state)}</span>
            </div>
            <p class="step__sub">${esc(step.title)}${on && step.proof ? ` <span class="step__proof mono" title="Signature: ${esc(step.proof)}">${icon("lock")}${esc(shortProof(step.proof))}</span>` : ""}</p>
            ${on && step.detail ? `<p class="step__sub step__sub--detail" title="${esc(plainDetail(step.detail))}">${esc(plainDetail(step.detail))}</p>` : ""}
          </div>
        </li>`;
    })
    .join("");
  const trailNode = el("trail");
  trailNode.classList.toggle("is-running", app.busy || revealing());
  trailNode.classList.toggle("trail--sealed", orderOnScreen() && status() === "done" && !app.busy && !revealing());
  setHtml(
    el("limit"),
    `<div>
        <p class="limit__label">Autonomous Mandate Cap</p>
        <p class="limit__value">${limitKnown() ? esc(limitText()) : "unknown"} <span class="limit__per">/ order</span></p>
      </div>
      <button class="limit__edit" type="button" data-action="limit" ${canEdit() ? "" : "disabled"}>Change</button>`
  );
  setHtml(el("steps"), items);
  setHtml(el("seal"), sealHtml());
}

/* ---------- Drawing: step 1, recipes ---------- */

function recipesView() {
  const data = app.kitchen.recipes;
  const recipes = data?.recipes ?? [];
  const chosen = recipes.find((recipe) => recipe.id === app.recipeId) ?? recipes[0];
  const services = app.kitchen.bookings?.services ?? [];
  const totalBooked = services.reduce((sum, s) => sum + Number(s.booked || 0), 0);
  const totalProjected = services.reduce((sum, s) => sum + Number(s.projected || 0), 0);

  const cards = recipes
    .map((recipe, idx) => {
      const active = recipe === chosen;
      return `<button class="course-card${active ? " is-chosen" : ""}" type="button" data-recipe="${esc(recipe.id)}" aria-pressed="${active}">
          <div class="course-card__top">
            <span class="tag">${esc(recipe.course)}</span>
            <span class="course-card__idx mono">${String(idx + 1).padStart(2, "0")}</span>
          </div>
          <p class="course-card__title">${esc(recipe.name)}</p>
          <p class="course-card__meta"><span>${esc(recipe.with)}</span> <span>·</span> <span class="mono">${recipe.ingredients.length} SKUs</span></p>
        </button>`;
    })
    .join("");

  const ingredients = (chosen?.ingredients ?? [])
    .map((item) => {
      const stockEntry = app.lines.find((line) => line.product_id === item.product_id);
      const totalNeed = stockEntry ? qty(stockEntry.need, stockEntry.unit) : "—";
      const focused = app.focusedProductId === item.product_id;
      return `<tr data-row-id="${esc(item.product_id)}" class="${focused ? "is-focused" : ""}">
          <td><span class="ing-name">${esc(item.name)}</span></td>
          <td class="num">${esc(item.per_service)}</td>
          <td class="num"><b>${esc(totalNeed)}</b></td>
          <td class="num"><span class="ing-sku mono">#${esc(item.product_id)}</span></td>
        </tr>`;
    })
    .join("");

  return `<div class="stage-head">
      <div>
        <p class="stage-head__kicker">01 · Culinary Menu &amp; Mise-en-Place</p>
        <h2 class="work__title">Recipes on the menu</h2>
        <p class="work__lead">Scaled for ${esc(data?.covers_per_service)} covers per service. Inspect each course's mise-en-place before checking walk-in stock.</p>
      </div>
    </div>
    <div class="kpi-strip">
      <div class="kpi"><span class="kpi__label">Menu Courses</span><span class="kpi__val">${recipes.length} Dishes</span></div>
      <div class="kpi"><span class="kpi__label">Service Scale</span><span class="kpi__val">${esc(data?.covers_per_service ?? 50)} Covers / Svc</span></div>
      <div class="kpi"><span class="kpi__label">3-Day Bookings</span><span class="kpi__val">${totalBooked} Booked · ${totalProjected} Proj</span></div>
      <div class="kpi kpi--accent"><span class="kpi__label">Tracked Valio SKUs</span><span class="kpi__val">${app.lines.length} Ingredients</span></div>
    </div>
    <div class="split">
      <div class="course-stack">${cards}</div>
      <div class="panel">
        <div class="panel__head">
          <div>
            <span class="tag">${esc(chosen?.course)}</span>
            <h3 class="panel__title">${esc(chosen?.name)}</h3>
          </div>
          <span class="panel__stamp mono">${esc(data?.covers_per_service ?? 50)} covers / service</span>
        </div>
        <table class="tbl tbl--tight">
          <thead><tr><th>Ingredient</th><th class="num">Per service</th><th class="num">3-Svc Need</th><th class="num">Valio SKU</th></tr></thead>
          <tbody>${ingredients}</tbody>
        </table>
      </div>
    </div>`;
}

/* ---------- Drawing: step 2, stock ---------- */

function field(line, name, label, highlightShort = false) {
  const who = line.by[name];
  const title = who ? `Changed by ${who}` : "";
  return `<span class="field${who ? " is-changed" : ""}${highlightShort ? " field--short" : ""}" title="${esc(title)}">
      <input class="field__input" type="text" inputmode="decimal" autocomplete="off" value="${esc(line[name])}"
        data-cell="${esc(line.product_id)}:${name}" aria-label="${esc(`${label}, ${line.name}, in ${unitWord(line.unit)}`)}" ${canEdit() ? "" : "disabled"} />
      <span class="field__unit">${esc(unitWord(line.unit, line[name]))}</span>
    </span>`;
}

function stockView() {
  const stock = app.kitchen.stock;
  const missing = missingLines();
  const coveredCount = app.lines.length - missing.length;
  const shownLines = app.stockFilter === "missing" ? missing : [...missing, ...app.lines.filter((line) => line.to_order <= 0)];
  const rows = shownLines
    .map((line) => {
      const short = line.to_order > 0;
      const above = line.to_order > neededNow(line);
      const focused = app.focusedProductId === line.product_id;
      const editedBy = line.by.in_stock || line.by.to_order;
      const coverPct = line.need > 0 ? Math.min(100, Math.round((line.in_stock / line.need) * 100)) : 100;
      return `<tr data-row-id="${esc(line.product_id)}" class="${short ? "is-short" : "is-covered"}${focused ? " is-focused" : ""}">
          <td>
            <span class="ing-name">${esc(line.name)}</span>
            <span class="ing-sku mono"> #${esc(line.product_id)}</span>
            ${above ? ' <span class="tag tag--warn" title="More than the recipes need, with what is in stock">above need</span>' : ""}
            ${editedBy ? `<span class="row-note">Edited by ${esc(editedBy)}</span>` : ""}
          </td>
          <td class="muted">${esc(line.dishes.join(", "))}</td>
          <td class="num">
            <span class="need-cell">
              <span>${esc(qty(line.need, line.unit))}</span>
              <span class="need-bar" title="${coverPct}% covered by walk-in stock"><i style="width:${coverPct}%"></i></span>
            </span>
          </td>
          <td class="num">${field(line, "in_stock", "In stock")}</td>
          <td class="num">${field(line, "to_order", "To order", short)}</td>
        </tr>`;
    })
    .join("");

  const tab = (id, label, count) =>
    `<button class="filter-tab${app.stockFilter === id ? " is-active" : ""}" type="button" data-filter="${id}" aria-pressed="${app.stockFilter === id}">${label} <span>${count}</span></button>`;
  const changed = changedLines().length;

  let note = `<p class="work__lead">Counted ${esc(dayLong(stock.counted_at))} by ${esc(stock.counted_by)}. Need covers ${esc(stock.for_services)} services — edit any count directly or tell ${ASSISTANT}.</p>`;
  if (!canEdit()) {
    note = `<p class="note">${icon("lock")}<span>An order is open with these quantities. They are locked until it is signed or rejected.</span></p>`;
  } else if (app.correcting && !dirty()) {
    note = `<p class="note note--refused"><span>The refused order asked for these quantities. Correct them, then order again.</span>
        <button class="link" type="button" data-action="use-need">Reset to recipe need</button></p>`;
  } else if (dirty()) {
    note = '<p class="note"><span>Quantities changed since the last order. Confirm stock to prepare a fresh order.</span></p>';
  }

  return `<div class="stage-head">
      <div>
        <p class="stage-head__kicker">02 · Walk-In Cold Room &amp; Dry Store Ledger</p>
        <h2 class="work__title">Stock check</h2>
        ${note}
      </div>
      <div class="stock-toolbar">
        ${changed && canEdit() ? `<button class="link" type="button" data-action="undo">Undo ${changed} ${changed === 1 ? "change" : "changes"}</button>` : ""}
        <div class="filter-tabs" role="group" aria-label="Filter stock lines">
          ${tab("all", "All SKUs", app.lines.length)}${tab("missing", "To order", missing.length)}
        </div>
      </div>
    </div>
    <div class="kpi-strip kpi-strip--3">
      <div class="kpi"><span class="kpi__label">Last Walk-In Count</span><span class="kpi__val">${esc(dayShort(stock.counted_at))} · ${esc(stock.for_services)} Services</span></div>
      <div class="kpi"><span class="kpi__label">Covered In House</span><span class="kpi__val">${coveredCount} of ${app.lines.length} Lines</span></div>
      <div class="kpi kpi--accent"><span class="kpi__label">Shortfall To Order</span><span class="kpi__val">${missing.length} ${missing.length === 1 ? "Ingredient" : "Ingredients"}</span></div>
    </div>
    <div class="sheet-wrap">
      <table class="tbl tbl--stock">
        <thead><tr><th>Ingredient</th><th>Used in</th><th class="num">Need</th><th class="num">In stock</th><th class="num">To order</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

/* ---------- Drawing: step 3, the order ---------- */

function requestTable() {
  const lines = missingLines();
  const rows = lines
    .map(
      (line) => `<tr data-row-id="${esc(line.product_id)}" class="${app.focusedProductId === line.product_id ? "is-focused" : ""}">
          <td><span class="ing-name">${esc(line.name)}</span> <span class="ing-sku mono">#${esc(line.product_id)}</span></td>
          <td class="muted">${esc(line.dishes.join(", "))}</td>
          <td class="num"><span class="short">${esc(qty(line.to_order, line.unit))}</span></td>
        </tr>`
    )
    .join("");
  const empty = lines.length ? "" : '<p class="note"><span>Everything is covered by walk-in stock: there is nothing to order.</span></p>';
  return `<div class="stage-head">
      <div>
        <p class="stage-head__kicker">03 · Outbound AP2 Mandate Dispatch</p>
        <h2 class="work__title">Ready to order</h2>
        <p class="work__lead">What your assistant will ask Valio Aimo to quote. Prices, availability, and allergens arrive inside Valio's signed quote.</p>
      </div>
    </div>
    ${empty}
    <div class="sheet-wrap">
      <table class="tbl">
        <thead><tr><th>Ingredient</th><th>Used in</th><th class="num">To order</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

/* One sentence under the quote when Valio gave no stock count on some lines. It never blocks the order: unknown is shown, not hidden. */
function stockNote(quote) {
  const total = quote.line_items.length;
  const unconfirmed = quote.line_items.filter((item) => {
    const stock = quote.aimo.lines[item.id]?.stock;
    return !stock || stock.certainty === "unknown" || typeof stock.value !== "number";
  }).length;
  if (unconfirmed === 0) return "";
  return `<p class="stock-note">Stock not confirmed on ${unconfirmed} of ${total} ${total === 1 ? "line" : "lines"}: Valio gave no count. Unknown stays unknown — this does not block the order.</p>`;
}

function quoteTable(state) {
  const quote = state.quote;
  const total = quote.totals.find((item) => item.type === "total");
  const quoteStep = (state.steps ?? []).find((step) => step.key === "signed_quote");
  const rows = quote.line_items
    .map((item) => {
      const facts = quote.aimo.lines[item.id] ?? {};
      const lineTotal = item.totals.find((entry) => entry.type === "total");
      const focused = app.focusedProductId === item.item.id || app.focusedProductId === facts.substitute_for?.product_id;
      const replaces = facts.substitute_for
        ? `<span class="sub-note"><span class="tag tag--warn">Substitute</span> replaces ${esc(facts.substitute_for.name)}</span>`
        : "";
      return `<tr data-row-id="${esc(item.item.id)}" class="${focused ? "is-focused" : ""}">
          <td>
            <span class="ing-name">${esc(item.item.title)}</span> <span class="ing-sku mono">#${esc(item.item.id)}</span>
            ${replaces ? `<br />${replaces}` : ""}
          </td>
          <td class="num">${esc(qty(item.quantity, facts.sales_unit))}</td>
          <td class="num">${esc(money(item.item.price, quote.currency))}</td>
          <td class="num"><b>${esc(money(lineTotal.amount, quote.currency))}</b></td>
          <td class="muted">${esc(stockText(facts.stock))}</td>
        </tr>`;
    })
    .join("");
  const mismatch = app.mismatch
    ? `<p class="mismatch">This quote is for the quantities of the recorded run, not for the ones you changed.
        ${app.mode === "live" ? "The demo driver does not take changed quantities yet." : "A quote for your own quantities needs the demo driver, which is not running."}</p>`
    : "";
  return `<div class="invoice-head">
      <div>
        <p class="stage-head__kicker">03 · Verified Wholesale Quote · Valio Aimo</p>
        <h2 class="work__title">Quote signed by Valio Aimo</h2>
        <p class="work__lead">Delivery ${esc(dayLong(quote.aimo.delivery_date))}, valid until ${esc(clock(quote.expires_at))}. Prices before tax.</p>
      </div>
      <div class="sig-pill">
        ${icon("shield")}
        <div>
          <b>ES256 Signature Verified</b>
          <span class="mono">${esc(shortProof(quoteStep?.proof) || quote.id)} · ${quote.line_items.length} lines</span>
        </div>
      </div>
    </div>
    ${mismatch}
    <div class="sheet-wrap">
      <table class="tbl tbl--quote">
        <thead><tr><th>Product</th><th class="num">Quantity</th><th class="num">Unit price</th><th class="num">Total</th><th>Valio's stock</th></tr></thead>
        <tbody>${rows}</tbody>
        <tfoot><tr><td colspan="3">Total before tax</td><td class="num">${esc(money(total.amount, quote.currency))}</td><td></td></tr></tfoot>
      </table>
    </div>${stockNote(quote)}`;
}

/* A card moves in once, when the step it belongs to lights up. */
const arriving = (stepNumber) => (app.fresh !== null && app.shown === stepNumber ? " card--fresh" : "");

/* One rule of the harness, as a line a chef can read. */
function checkLine(rule) {
  const wordsFor = CHECK_WORDS[rule.rule_id];
  const label = wordsFor?.[rule.outcome] ?? lexicon(rule.message);
  let value = "";
  try {
    value = wordsFor?.value?.(rule.evidence ?? {}) ?? "";
  } catch {
    value = "";
  }
  return { label, value, outcome: rule.outcome, title: lexicon(rule.message) };
}

function checksCard(state) {
  const verdict = state.verdict;
  const checks = verdict.rules.map(checkLine);
  const open = checks.filter((check) => check.outcome !== "pass");
  const lead = {
    auto: `All ${checks.length} checks passed. Your assistant may sign this order for you.`,
    human: `${open.length === 1 ? "One check needs" : `${open.length} checks need`} you. You sign this order, or nobody does.`,
    deny: "Blocked. Nobody may sign this order.",
  }[verdict.decision];
  const badge = { auto: "Assistant signs", human: "You sign", deny: "Blocked" }[verdict.decision];
  const row = (check) => `<li class="check check--${esc(check.outcome)}" title="${esc(check.title)}">
      ${check.outcome === "pass" ? icon("check") : check.outcome === "deny" ? icon("cross") : icon("pen")}
      <span class="check__label">${esc(check.label)}${check.value ? `<span class="check__value">${esc(check.value)}</span>` : ""}</span>
      <span class="check__out">${esc(OUTCOME_WORDS[check.outcome] ?? check.outcome)}</span>
    </li>`;
  const passed = checks.filter((check) => check.outcome === "pass");
  const list = open.length
    ? `<ul class="checks">${open.map(row).join("")}</ul>
       <details class="passed"><summary>The ${passed.length} other checks passed</summary><ul class="checks">${passed.map(row).join("")}</ul></details>`
    : `<ul class="checks">${passed.map(row).join("")}</ul>`;
  const cardTone = verdict.decision === "auto" ? "done" : verdict.decision;
  return `<section class="card card--${esc(cardTone)}${arriving(3)}">
      <p class="card__label">Safety checks before anyone signs</p>
      <p class="card__lead"><span class="badge badge--${esc(verdict.decision)}">${esc(badge)}</span><span>${esc(lead)}</span></p>
      ${list}
    </section>`;
}

function productFacts(title, name, facts, extra = "", proposed = false) {
  const size = facts.size_per_sales_unit ? `${num(facts.size_per_sales_unit.value)} ${String(facts.size_per_sales_unit.unit).toLowerCase()} a unit` : "unknown";
  const claims = (facts.nutritional_claims ?? []).map(words).join(", ") || "none stated";
  const labels = (facts.labels ?? []).map(words).join(", ") || "none stated";
  return `<div class="versus__side${proposed ? " versus__side--prop" : ""}">
      <p class="card__label">${title}</p>
      <p class="versus__name">${esc(name)}</p>
      <dl class="facts">
        <dt>Brand</dt><dd>${esc(facts.brand ?? "unknown")}</dd>
        <dt>Pack</dt><dd>${esc(size)}</dd>
        <dt>Contains</dt><dd>${esc(allergenText(facts.allergens))}</dd>
        <dt>Claims</dt><dd>${esc(claims)}</dd>
        <dt>Labels</dt><dd>${esc(labels)}</dd>
        ${extra}
      </dl>
    </div>`;
}

/* The assistant's two answers about a substitute, as bars with the line above which it would sign alone. */
function confidenceBars(approval) {
  return (approval.judge ?? [])
    .map((answer) => {
      if (!Number.isFinite(answer.probability)) return `<li class="judge"><span class="judge__q">${esc(JUDGE_WORDS[answer.question_key] ?? words(answer.question_key))}</span><span class="judge__p">unknown</span></li>`;
      const percent = Math.round(answer.probability * 100);
      const threshold = Math.round(answer.auto_threshold * 100);
      return `<li class="judge">
          <span class="judge__q">${esc(JUDGE_WORDS[answer.question_key] ?? words(answer.question_key))}</span>
          <span class="judge__bar" role="img" aria-label="${percent} percent sure, asks you below ${threshold} percent">
            <span class="judge__fill judge__fill--${esc(answer.routed)}" style="width:${percent}%"></span>
            <span class="judge__mark" style="left:${threshold}%"></span>
          </span>
          <span class="judge__p">${percent}%</span>
        </li>`;
    })
    .join("");
}

function approvalCard(state) {
  const approval = state.approval;
  const quote = state.quote;
  if (approval.status !== "pending") {
    const outcome = { approved: "Signed", rejected: "Rejected: nobody signed, no order", expired: "Expired: nobody signed in time" }[approval.status] ?? approval.status;
    const who = approval.decided_by ? ` by ${approval.decided_by}${approval.decided_at ? `, ${clock(approval.decided_at)}` : ""}` : "";
    const tone = approval.status === "approved" ? "done" : "deny";
    return `<section class="card card--${tone}">
        <p class="card__label">Your signature</p>
        <p class="sign__done sign__done--${esc(approval.status)}">${approval.status === "approved" ? icon("check") : icon("cross")}<span>${esc(outcome + who)}</span></p>
      </section>`;
  }

  const item = quote.line_items.find((entry) => quote.aimo.lines[entry.id]?.substitute_for);
  let body = "";
  if (item) {
    const facts = quote.aimo.lines[item.id];
    const shortfall = (quote.aimo.shortfalls ?? []).find((entry) => entry.product_id === facts.substitute_for.product_id);
    const why = shortfall ? `Valio cannot deliver what you asked for: ${SHORTFALL_WORDS[shortfall.reason] ?? words(shortfall.reason)}.` : "Valio proposes another product than the one you asked for.";
    const candidates = (quote.aimo.alternatives ?? []).length;
    const allergens = state.verdict?.rules.find((rule) => rule.rule_id === "allergen-unchanged-on-substitution");
    const allergenFact = allergens ? checkLine(allergens) : null;
    const fits = (approval.judge ?? []).find((answer) => answer.question_key === "within_preferences");
    const sure = fits && Number.isFinite(fits.probability)
      ? `${ASSISTANT} is ${Math.round(fits.probability * 100)}% sure it fits your kitchen's preferences (auto threshold ${Math.round(fits.auto_threshold * 100)}%).`
      : `${ASSISTANT} could not tell whether it fits your kitchen's preferences, so it asks you.`;
    const extra = `<dt>Price</dt><dd>${esc(money(facts.comparison_price_minor, quote.currency))} a ${esc(String(facts.comparison_unit).toLowerCase())}</dd>
      <dt>Valio's stock</dt><dd>${esc(stockText(facts.stock))}</dd>`;
    body = `<p class="card__note">${esc(why)}${candidates === 1 ? " Valio found one substitute and proposes it." : candidates ? ` Valio ranked ${candidates} substitutes and proposes this one.` : ""}</p>
      <div class="swap">
        <p class="swap__from"><span class="card__label">You asked for</span>${esc(facts.substitute_for.name)}</p>
        <span class="swap__arrow" aria-hidden="true">${icon("arrow")}</span>
        <p class="swap__to"><span class="card__label">Valio proposes</span>${esc(item.item.title)}</p>
      </div>
      <ul class="keys">
        ${allergenFact ? `<li class="key key--${esc(allergenFact.outcome)}">${allergenFact.outcome === "pass" ? icon("check") : icon("pen")}<span>${esc(allergenFact.label)}${allergenFact.value ? `: ${esc(allergenFact.value)}` : ""}</span></li>` : `<li class="key"><span>Contains: ${esc(allergenText(facts.allergens))}</span></li>`}
        <li class="key">${icon("shield")}<span>${esc(money(facts.comparison_price_minor, quote.currency))} / ${esc(String(facts.comparison_unit).toLowerCase())} · ${esc(money(approval.total_minor, approval.currency))} total</span></li>
        <li class="key key--human">${icon("gauge")}<span>${esc(sure)}</span></li>
      </ul>
      <button class="toggle" type="button" data-action="details" role="switch" aria-checked="${app.detailsOpen}">
        <span class="toggle__track" aria-hidden="true"><span class="toggle__knob"></span></span>All details of both products
      </button>
      ${
        app.detailsOpen
          ? `<div class="versus">
              ${productFacts("You asked for", facts.substitute_for.name, facts.substitute_for)}
              ${productFacts("Valio proposes", item.item.title, facts, extra, true)}
            </div>
            <p class="card__label card__label--gap">Calibrated confidence · ${ASSISTANT}</p>
            <ul class="judges">${confidenceBars(approval)}</ul>`
          : ""
      }`;
  } else {
    body = `<ul class="reasons">${approval.reasons.map((reason) => `<li>${esc(checkLine(reason).label)}</li>`).join("")}</ul>`;
  }
  return `<section class="card card--human card--sign${arriving(4)}">
      <p class="card__label">Your signature is needed</p>
      <p class="sign__deadline">${icon("wait")} Sign before <b>${esc(clock(approval.deadline))}</b>, Valio's order cut-off.</p>
      ${body}
      <div class="sign">
        <button class="btn btn--approve btn--wide" type="button" data-action="approve" ${app.busy ? "disabled" : ""}>
          ${icon("pen")} Approve and sign · ${esc(money(approval.total_minor, approval.currency))}
        </button>
      </div>
    </section>`;
}

function receiptCard(state) {
  const order = state.order;
  const payment = state.steps.find((step) => step.key === "sandbox_payment");
  const receipt = state.steps.find((step) => step.key === "signed_receipt");
  return `<section class="card card--done${arriving(7)}">
      <p class="card__label">Receipt signed by Valio Aimo</p>
      <p class="card__lead">${icon("check")}<span>Order ${esc(order.order_id)} accepted</span></p>
      <dl class="facts">
        <dt>Total</dt><dd><b>${esc(money(order.total_minor, order.currency))}</b> before tax</dd>
        <dt>Delivery</dt><dd>${esc(dayLong(order.delivery_date))}</dd>
        <dt>Signed by</dt><dd>${esc(order.signed_by === "human" ? "you, on this page" : "your assistant, inside your limits")}</dd>
        <dt>Payment</dt><dd>${esc(payment?.detail ?? "unknown")}</dd>
        <dt>Receipt</dt><dd class="mono">${esc(shortProof(receipt?.proof) ?? "unknown")}</dd>
      </dl>
    </section>`;
}

function attacksCard(state) {
  const items = state.attacks
    .map((attack, idx) => {
      const refused = attack.status === "refused";
      const label = { refused: "Refused by Valio", accepted: "ACCEPTED: must not happen", pending: "Not sent yet" }[attack.status] ?? attack.status;
      const problems = attack.problems.map((problem) => `<li>${esc(problem)}</li>`).join("");
      return `<li class="attack__item">
          <div class="attack__head">
            <span class="attack__idx mono">${String(idx + 1).padStart(2, "0")}</span>
            <span class="attack__title">${esc(lexicon(attack.title))}</span>
            <span class="badge badge--${refused ? "deny" : "human"}">${esc(label)}</span>
          </div>
          ${problems ? `<ul class="attack__problems">${problems}</ul>` : ""}
        </li>`;
    })
    .join("");
  return `<section class="card card--deny${arriving(5)}">
      <p class="card__label">Zero-trust verification · Forged mandates sent straight to Valio</p>
      <ul class="attack__list">${items}</ul>
    </section>`;
}

function orderView() {
  const state = app.state;
  if (!orderOnScreen() || app.shown < 2 || !state.quote) {
    const waiting = (hasRun() && !dirty()) || app.busy ? '<p class="working">Your assistant is asking Valio Aimo for a signed quote…</p>' : "";
    return `<div class="order"><div class="order__main">${requestTable()}${waiting}</div><div class="order__side"></div></div>`;
  }
  const pending = state.approval?.status === "pending";
  const side = [
    state.approval && pending && app.shown >= 4 ? approvalCard(state) : "",
    state.order && app.shown >= 7 ? receiptCard(state) : "",
    state.verdict && app.shown >= 3 ? checksCard(state) : "",
    state.attacks?.length && app.shown >= 5 ? attacksCard(state) : "",
    state.approval && !pending && app.shown >= 4 ? approvalCard(state) : "",
  ].join("");
  return `<div class="order"><div class="order__main">${quoteTable(state)}</div><div class="order__side">${side}</div></div>`;
}

function drawMain() {
  const problem = app.problem ? `<p class="problem" role="alert"><strong>Something did not answer.</strong> ${esc(app.problem)}</p>` : "";
  const view = app.step === 3 ? orderView() : app.step === 2 ? stockView() : recipesView();
  setHtml(el("main"), problem + view);
}

/* ---------- Drawing: the side column ---------- */

function drawMenu() {
  const node = el("menu");
  node.hidden = app.step !== 1;
  const menu = app.state?.kitchen?.menu ?? [];
  const items = menu
    .map((item) => {
      const cut = item.dish.indexOf(",");
      return `<li><span class="menu__course">${esc(item.course)}</span><span>${esc(cut === -1 ? item.dish : item.dish.slice(0, cut))}</span></li>`;
    })
    .join("");
  setHtml(node, `<p class="menu__kicker">Service Tasting Sheet</p><h2 class="side__title">This week's menu</h2><ul class="menu__list">${items}</ul>`);
}

const PULSE_LABELS = {
  menu_covered: "Menu coverage",
  dietary_intact: "Safety & origin",
  ready_without_escalation: "Mandate fit",
};

function drawPulse() {
  const node = el("pulse");
  if (!node) return;
  const metricsByKey = Object.fromEntries((app.pulseData?.metrics ?? []).map((m) => [m.key, m]));
  const cells = ["menu_covered", "dietary_intact", "ready_without_escalation"]
    .map((key) => {
      const m = metricsByKey[key];
      const hasProb = m && Number.isFinite(m.probability);
      const pct = hasProb ? Math.round(m.probability * 100) : null;
      const conf = m && Number.isFinite(m.confidence) ? Math.round(m.confidence * 100) : null;
      const tone = pct === null ? "" : pct >= 80 ? " pulse__cell--ok" : pct >= 45 ? " pulse__cell--warn" : " pulse__cell--bad";
      const tip = hasProb
        ? `${PULSE_LABELS[key]}: ${pct}% calibrated probability${conf !== null ? ` (confidence ${conf}%)` : ""} · 0 output tokens`
        : "Calibrated probability not yet evaluated";
      return `<div class="pulse__cell${tone}" title="${esc(tip)}">
          <span class="pulse__label">${esc(PULSE_LABELS[key])}</span>
          <span class="pulse__val mono">${app.pulseBusy && !hasProb ? "…" : pct !== null ? `${pct}%` : "—"}</span>
          <span class="pulse__bar" aria-hidden="true"><i style="width:${pct ?? 0}%"></i></span>
        </div>`;
    })
    .join("");

  const statusTag = !app.pulseOnline
    ? '<span class="pulse__tag mono">offline</span>'
    : `<button class="pulse__btn" type="button" data-action="pulse" ${app.pulseBusy ? "disabled" : ""} title="Run zero-output-token calibrated check via ${esc(app.decisionModel)}">${app.pulseBusy ? "Scoring…" : "0-tok check"}</button>`;

  setHtml(
    node,
    `<div class="pulse__head">
        <span class="pulse__title">${icon("pulse")}<span>Calibrated Readiness · ${esc(app.decisionModel)}</span></span>
        ${statusTag}
      </div>
      <div class="pulse__grid">${cells}</div>`
  );
}

function defaultPrompts() {
  if (app.step === 1) {
    return [
      "Which dishes need dairy deliveries?",
      "Summarize the 3-day cover forecast",
    ];
  }
  if (app.step === 2) {
    return canEdit()
      ? [
          "We found 2 L more cooking cream in walk-in",
          "Which ingredients are short right now?",
        ]
      : ["Why are the stock quantities locked?"];
  }
  if (status() === "waiting_for_human") {
    return [
      "Compare the substitute allergens and price",
      "Why does this order need my signature?",
    ];
  }
  if (status() === "refused") {
    return [
      "Why was this order blocked?",
      "Which checks or signatures failed?",
    ];
  }
  if (orderOnScreen()) {
    return [
      "Summarize the signed quote and delivery",
      "Are any Valio stock counts unconfirmed?",
    ];
  }
  return [
    "What will you ask Valio Aimo to quote?",
    "Is this within my spending limit?",
  ];
}

function drawPrompts() {
  const node = el("prompts");
  if (!node) return;
  const items = (app.followUps.length ? app.followUps : defaultPrompts()).slice(0, 3);
  const chips = items
    .map(
      (prompt) =>
        `<button class="prompt-chip" type="button" data-prompt="${esc(prompt)}" ${!app.up.assistant || app.chatBusy ? "disabled" : ""}>${esc(prompt)}</button>`
    )
    .join("");
  setHtml(node, chips);
}

function drawTalk() {
  const lines = [...app.talk];
  if (revealing() || app.chatBusy) lines.push({ typing: true });
  const bubbles = lines
    .map((line) => {
      if (line.typing) return '<li class="say say--agent"><span class="say__dots" aria-label="working"><i></i><i></i><i></i></span></li>';
      const speaker = line.speaker ?? (line.who === "chef" ? "Chef" : ASSISTANT);
      const proof = line.proof ? `<span class="say__proof mono" title="${esc(line.proof)}">${esc(shortProof(line.proof))}</span>` : "";
      const changes = (line.changes ?? [])
        .map((change) => {
          if (typeof change === "string") return `<span class="say__change">${icon("pen")}<span>${esc(change)}</span></span>`;
          return `<button class="say__change" type="button" data-jump="${esc(change.productId)}" title="Highlight in stock table">${icon("pen")}<span>${esc(change.text)}</span></button>`;
        })
        .join("");
      return `<li class="say say--${line.who === "chef" ? "chef" : "agent"}${line.status ? ` say--${esc(line.status)}` : ""}">
          <span class="say__who">${esc(speaker)}</span>
          <span class="say__text">${esc(line.text)}</span>${changes}${proof}
        </li>`;
    })
    .join("");
  const talk = el("talk");
  const before = talk.dataset.drawn;
  setHtml(talk, bubbles);
  if (before !== bubbles) talk.scrollTop = talk.scrollHeight;

  setHtml(
    el("agent-title"),
    `${icon("terminal")}<span>${ASSISTANT}</span><span class="agent__state"><i class="dot dot--${app.up.assistant ? "on" : "off"}"></i>${app.up.assistant ? "Live" : "Log only"}</span>`
  );
  const subNode = el("agent-sub");
  if (subNode) {
    const modelTag = app.assistantModel || "gemini-3.5-flash-lite";
    const chainTag = app.interactionId ? " · Stateful chain" : "";
    setHtml(
      subNode,
      app.up.assistant
        ? `Interactions API (${esc(modelTag)})${chainTag} · Grounded on signed state`
        : "Gemini Interactions API · Grounded exclusively on signed page state"
    );
  }
  el("ask-text").disabled = !app.up.assistant || app.chatBusy;
  el("ask-send").disabled = !app.up.assistant || app.chatBusy;
  setHtml(el("ask-send"), `<span>Send</span>${icon("send")}`);
  setHtml(el("ask-note"), app.up.assistant ? "Edits walk-in stock on command. Never signs mandates — only you sign with the buttons." : `${ASSISTANT} is offline. You can still edit the stock table directly.`);
}

/* ---------- Drawing: the demo strip (for the team, not for the customer) ---------- */

function drawDemo() {
  const scenarios = app.state?.scenarios ?? [];
  const current = hasRun() && !app.correcting ? app.state.scenario.id : app.scenarioId;
  const buttons = scenarios
    .map(
      (scenario, index) => `<button class="demo__btn" type="button" data-scenario="${esc(scenario.id)}" aria-pressed="${scenario.id === current}"
          title="${esc(scenario.hint)}">${index + 1} ${esc(scenario.title)}</button>`
    )
    .join("");
  const light = (up, name, on, off, how) => `<span class="demo__light demo__light--${up ? "on" : "off"}" title="${esc(how)}">${name}: ${up ? on : off}</span>`;
  setHtml(
    el("demo"),
    `<span class="demo__label">Demo controls</span>
    ${buttons}
    <button class="demo__btn" type="button" data-action="reset">Reset</button>
    <span class="demo__src">
      ${light(app.mode === "live", "driver", `live (${DRIVER_URL})`, app.up.driver ? "could not run, replaying a recorded run" : "not started, replaying the runs recorded on 14/11", "scenarios/run.py on port 8003, started by scripts/dev.py. It needs VALIO_MODE=live.")}
      ${light(app.up.harness, "harness", "live", "not started", "uv run python scripts/dev.py starts the gateway (8001), the harness (8002) and the driver (8003)")}
      ${light(app.up.assistant, "assistant", app.pulseOnline ? "live (interactions + decisions)" : "live", "not started", "uv run uvicorn surface.assistant:app --port 8004")}
      <span>kitchen data: synthetic</span>
    </span>
    <span class="demo__note">Concept mock-up, Junction 2026, synthetic data. Not a Valio Aimo service.</span>`
  );
}

function draw() {
  drawFlow();
  drawTrail();
  drawMain();
  drawMenu();
  drawPulse();
  drawPrompts();
  drawTalk();
  drawDemo();
}

function drawAll() {
  drawAccount();
  drawPlanning();
  draw();
}

/* ---------- A short confirmation, and the window that asks before a signature ---------- */

let toastTimer = null;
function toast(text) {
  const node = el("toast");
  node.innerHTML = `${icon("check")}${esc(text)}`;
  node.classList.add("is-on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("is-on"), 2600);
}

let dialogConfirm = null;
function openDialog({ title, body, confirm, tone = "primary", onConfirm }) {
  const node = el("dialog");
  dialogConfirm = onConfirm;
  node.innerHTML = `<form class="dialog__box" method="dialog" id="dialog-form">
      <h2 class="dialog__title" id="dialog-title">${esc(title)}</h2>
      <div class="dialog__body">${body}</div>
      <p class="dialog__error" id="dialog-error" role="alert" hidden></p>
      <div class="dialog__actions">
        <button class="btn btn--ghost" type="button" data-dialog="cancel">Cancel</button>
        <button class="btn btn--${esc(tone)}" type="submit" id="dialog-ok">${confirm}</button>
      </div>
    </form>`;
  node.showModal();
}

function closeDialog() {
  dialogConfirm = null;
  el("dialog").close();
}

function dialogError(text) {
  const node = el("dialog-error");
  node.textContent = text;
  node.hidden = false;
}

/* The last look before a signature: exactly what is signed, in the quote's own numbers. */
function askSignature() {
  const { quote, approval } = app.state;
  const lines = quote.line_items
    .map((item) => `<li><span>${esc(item.item.title)}</span><b>${esc(qty(item.quantity, quote.aimo.lines[item.id]?.sales_unit))}</b></li>`)
    .join("");
  openDialog({
    title: "Sign this order?",
    tone: "approve",
    body: `<ul class="dialog__lines">${lines}</ul>
      <dl class="facts dialog__facts">
        <dt>Total</dt><dd><b>${esc(money(approval.total_minor, approval.currency))}</b> before tax</dd>
        <dt>Delivery</dt><dd>${esc(dayLong(quote.aimo.delivery_date))}</dd>
        <dt>Quote</dt><dd class="mono">${esc(shortProof(approval.checkout_hash))}</dd>
      </dl>
      <p class="dialog__text">Your signature is for this exact quote and nothing else. Valio checks it before it accepts the order.</p>`,
    confirm: `${icon("pen")}Sign the order`,
    onConfirm: async () => {
      closeDialog();
      await decide("approve");
    },
  });
}

function askRejection() {
  openDialog({
    title: "Reject this order?",
    body: '<p class="dialog__text">Nobody signs, so nothing is ordered. You can then correct the quantities and order again.</p>',
    confirm: "Reject the order",
    tone: "reject",
    onConfirm: async () => {
      closeDialog();
      await decide("reject");
    },
  });
}

function askLimit() {
  if (!canEdit()) return;
  const current = limitKnown() ? app.policy.autonomous_limit_minor / 100 : "";
  openDialog({
    title: "Your spending limit",
    body: `<p class="dialog__text">Up to this amount an order, ${ASSISTANT} may sign alone when every safety check passes. Above it, the order waits for your signature on this page.</p>
      <label class="dialog__field">New limit, in ${esc(app.policy?.currency ?? "EUR")} an order
        <input id="limit-input" type="number" min="1" step="1" inputmode="numeric" value="${esc(current)}" required />
      </label>
      <p class="dialog__text muted">Now: ${limitKnown() ? esc(limitText()) : "unknown"}. A new limit is signed by you, like an order.</p>`,
    confirm: `${icon("pen")}Sign the new limit`,
    onConfirm: async () => {
      const amount = Number(el("limit-input").value);
      if (!Number.isFinite(amount) || amount < 1) {
        dialogError("Give an amount of 1 or more.");
        return;
      }
      el("dialog-ok").disabled = true;
      try {
        app.policy = await harness.setLimit(Math.round(amount * 100));
        app.up.harness = true;
        closeDialog();
        toast(`New limit signed: ${limitText()} an order`);
        say("chef", `My spending limit is now ${limitText()} an order.`);
        draw();
        schedulePulse();
      } catch (error) {
        el("dialog-ok").disabled = false;
        // The limit lives in the harness, which enforces it. The page never keeps a limit of its own.
        if (error.status === 404 || error.status === 405) dialogError("The safety service cannot take a new limit yet: this is asked of the harness. The limit has not changed.");
        else if (error.status) dialogError(`The safety service refused: ${error.message}. The limit has not changed.`);
        else dialogError("The safety service (harness) is not running, and only it can change the limit. The limit has not changed.");
      }
    },
  });
  el("limit-input").select();
}

/* ---------- Focus highlight & calibrated pulse ---------- */

let focusTimer = null;
function focusRow(productId) {
  if (!productId) return;
  app.focusedProductId = productId;
  drawMain();
  requestAnimationFrame(() => {
    const row = document.querySelector(`[data-row-id="${CSS.escape(productId)}"]`);
    row?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  clearTimeout(focusTimer);
  focusTimer = setTimeout(() => {
    app.focusedProductId = null;
    drawMain();
  }, 2400);
}

function pulseFingerprint() {
  const stockPart = app.lines.map((l) => `${l.product_id}:${l.in_stock}:${l.to_order}`).join(",");
  return `${app.scenarioId}|${status()}|${app.state?.approval?.status ?? ""}|${limitText() ?? ""}|${stockPart}`;
}

let pulseTimer = null;
function schedulePulse(force = false) {
  if (!app.pulseOnline || revealing()) return;
  const key = pulseFingerprint();
  if (!force && key === app.pulseKey) return;
  clearTimeout(pulseTimer);
  pulseTimer = setTimeout(async () => {
    if (!app.pulseOnline || app.pulseBusy) return;
    const nextKey = pulseFingerprint();
    if (!force && nextKey === app.pulseKey) return;
    app.pulseBusy = true;
    drawPulse();
    try {
      app.pulseData = await assistant.pulse(pageFacts());
      app.pulseKey = nextKey;
    } catch {
      /* fail closed: leave unknown rather than guessing */
    } finally {
      app.pulseBusy = false;
      drawPulse();
    }
  }, force ? 20 : 280);
}

/* ---------- Actions ---------- */

async function guarded(work) {
  app.problem = null;
  app.busy = true;
  draw();
  try {
    await work();
  } catch (error) {
    app.problem = error.name === "AbortError" ? "No answer in time." : error.message;
  } finally {
    app.busy = false;
    draw();
    schedulePulse();
  }
}

function startOver() {
  clearTimeout(revealTimer);
  app.step = 1;
  app.confirmed = { recipes: null, stock: null };
  app.stockFilter = "all";
  app.shown = 0;
  app.fresh = null;
  app.told = {};
  app.sentKey = null;
  app.correcting = false;
  app.mismatch = false;
  app.detailsOpen = true;
  app.talk = [];
  app.interactionId = null;
  app.followUps = [];
  app.focusedProductId = null;
  app.pulseData = null;
  app.pulseKey = "";
  loadLines(app.kitchen.stock);
  say("agent", openingLine());
}

const idleState = () => (app.mode === "live" ? driver.reset() : recorded("idle"));

/*
 * The driver is there but could not run the scenario (for example the gateway is in replay mode, which has no
 * answers for the menu's products). The page shows the recorded run instead, and says so.
 */
async function liveOrRecorded(run, replay) {
  if (app.mode !== "live") return replay();
  try {
    return await run();
  } catch (error) {
    app.mode = "replay";
    app.problem = `The demo driver could not run this: ${error.name === "AbortError" ? "no answer in time" : error.message}. What you see is the recorded run.`;
    return replay();
  }
}

async function chooseScenario(id) {
  await guarded(async () => {
    app.state = await idleState();
    app.scenarioId = id;
    app.kitchen.stock = await kitchenApi.stock(id);
    startOver();
    if (id === "attack") {
      // The attack is not something the chef does: it runs at once.
      app.step = 3;
      draw();
      app.state = await liveOrRecorded(
        () => driver.run("attack"),
        () => recorded("attack")
      );
      app.sentKey = linesKey(app.state.request?.lines);
      reveal();
      watch();
    }
  });
}

/* In replay mode, the recorded run that asked for exactly these quantities, or else the run of the scenario. */
async function replayRun(lines) {
  for (const name of [REPLAY_FILE["normal-order"], REPLAY_FILE.substitution]) {
    const run = await recorded(name);
    if (linesKey(run.request?.lines) === linesKey(lines)) return run;
  }
  return recorded(REPLAY_FILE[app.scenarioId]);
}

async function runScenario() {
  const lines = orderLines();
  const deliveryDate = app.kitchen.bookings?.services?.[0]?.date ?? null;
  clearTimeout(revealTimer);
  if (hasRun()) app.state = await idleState(); // a new order starts from a clean trail
  app.step = 3;
  app.shown = 0;
  app.fresh = null;
  app.told = {};
  app.correcting = false;
  app.detailsOpen = true;
  app.mismatch = false;
  app.followUps = [];
  draw();
  app.state = await liveOrRecorded(
    () => driver.run(app.scenarioId, { lines, delivery_date: deliveryDate }),
    () => replayRun(lines)
  );
  app.sentKey = linesKey(lines);
  app.mismatch = linesKey(app.state.request?.lines) !== app.sentKey;
  reveal();
  watch();
}

/* No run was recorded for a rejection: in replay mode the page draws what a rejection does (nobody signs, no order). */
function rejectedReplay(state) {
  const copy = structuredClone(state);
  copy.scenario.status = "refused";
  copy.approval.status = "rejected";
  copy.approval.decided_by = "chef";
  copy.steps.forEach((step) => {
    if (step.key === "closed_mandates") Object.assign(step, { status: "refused", detail: "Rejected by the chef on this page. Nobody signed: no order." });
    else if (step.status === "pending") Object.assign(step, { status: "skipped", detail: step.key === "signed_receipt" ? "No order, no receipt." : "Nothing happens: nobody signed." });
  });
  return copy;
}

async function decide(decision) {
  const approval = app.state.approval;
  if (!approval || approval.status !== "pending") return;
  await guarded(async () => {
    if (app.mode === "live") {
      await harness.decide(approval.approval_id, decision);
      app.state = await driver.state();
    } else {
      app.state = decision === "approve" ? await recorded("substitution.approved") : rejectedReplay(app.state);
    }
    app.followUps = [];
    say("chef", decision === "approve" ? "I approve and sign this order." : "I reject this order.");
    toast(decision === "approve" ? "Signed" : "Rejected: nothing is ordered");
    app.shown = Math.min(app.shown, 3); // the signature step lights up again, signed this time
    reveal();
    watch();
  });
}

/* The refused order's quantities go into the table, where the chef corrects them. */
function correctQuantities() {
  if (!finished()) return;
  if (app.state.scenario.id === "attack" && !app.correcting) {
    (app.state.request?.lines ?? []).forEach((asked) => {
      const line = app.lines.find((entry) => entry.product_id === asked.product_id);
      if (!line) return;
      line.to_order = round3(asked.amount);
      line.by.to_order = line.to_order === neededNow(line) ? null : "the refused order";
    });
    app.sentKey = linesKey(orderLines());
    app.scenarioId = "normal-order";
  }
  app.correcting = true;
  app.confirmed.stock = null;
  app.step = 2;
  app.followUps = [];
  say("agent", "The quantities of the refused order are in the table. Correct them, confirm the stock, and I ask Valio for a new quote.");
  draw();
  schedulePulse();
}

/* What the page shows, for the assistant's chat: it may only repeat what is here. */
function pageFacts() {
  const state = app.state;
  const facts = {
    step: ["recipes", "stock", "order"][app.step - 1],
    can_edit: canEdit(),
    kitchen: { name: state?.kitchen?.name, covers_per_service: state?.kitchen?.covers_per_service },
    services: (app.kitchen.bookings?.services ?? []).map((service) => ({ date: dayLong(service.date), meal: service.meal, booked: service.booked, projected: service.projected })),
    recipes: (app.kitchen.recipes?.recipes ?? []).map((recipe) => ({
      course: recipe.course,
      name: recipe.name,
      ingredients: recipe.ingredients.map((item) => `${item.name}: ${item.per_service} a service`),
    })),
    stock_counted_on: app.kitchen.stock?.counted_at ? dayLong(app.kitchen.stock.counted_at) : null,
    stock: app.lines.map((line) => ({ product_id: line.product_id, name: line.name, unit: line.unit, need: line.need, in_stock: line.in_stock, to_order: line.to_order, used_in: line.dishes })),
    spending_limit: limitText(),
    order: null,
  };
  if (orderOnScreen() && !revealing()) {
    const quote = state.quote;
    facts.order = {
      status: status(),
      asked: state.request?.text,
      quote: quote && {
        total_before_tax: money(quote.totals.find((item) => item.type === "total").amount, quote.currency),
        delivery: dayLong(quote.aimo.delivery_date),
        valid_until: clock(quote.expires_at),
        lines: quote.line_items.map((item) => {
          const line = quote.aimo.lines[item.id] ?? {};
          return {
            product_id: item.item.id,
            product: item.item.title,
            quantity: qty(item.quantity, line.sales_unit),
            unit_price: money(item.item.price, quote.currency),
            valio_stock: stockText(line.stock),
            contains: allergenText(line.allergens),
            substitute_for: line.substitute_for?.name ?? null,
          };
        }),
      },
      safety_checks: (state.verdict?.rules ?? []).map((rule) => {
        const check = checkLine(rule);
        return `${OUTCOME_WORDS[check.outcome] ?? check.outcome}: ${check.label}${check.value ? ` (${check.value})` : ""}`;
      }),
      signature: state.approval && { status: state.approval.status, sign_before: clock(state.approval.deadline) },
      receipt: state.order && { order_id: state.order.order_id, total: money(state.order.total_minor, state.order.currency), delivery: dayLong(state.order.delivery_date), signed_by: state.order.signed_by },
      refused_attempts: (state.attacks ?? []).map((attack) => `${lexicon(attack.title)}: ${attack.status}`),
    };
  }
  return facts;
}

async function sendChat(text) {
  if (!text || app.chatBusy) return;
  say("chef", text);
  app.chatBusy = true;
  draw();
  try {
    const turns = app.talk.slice(-12).map((line) => ({ who: line.who === "chef" ? "chef" : "assistant", text: String(line.text).slice(0, 2000) }));
    const answer = await assistant.chat(turns, pageFacts(), app.interactionId);
    if (answer.interaction_id) app.interactionId = answer.interaction_id;
    if (answer.model) app.assistantModel = answer.model;
    if (Array.isArray(answer.follow_ups)) app.followUps = answer.follow_ups;

    // The page applies the changes itself and shows what really changed, whatever the reply says.
    const applied = (answer.stock_changes ?? []).map((change) => setStock(change.product_id, change.field, change.amount, ASSISTANT)).filter(Boolean);
    if (applied.length && app.confirmed.stock && !orderOnScreen()) app.confirmed.stock = null;
    say("agent", answer.reply, {
      changes: applied.map((change) => ({ productId: change.line.product_id, text: changeText(change) })),
    });
    if (applied.length) {
      if (app.step === 1) app.step = 2;
      toast(`${applied.length} ${applied.length === 1 ? "line" : "lines"} updated in stock ledger`);
      schedulePulse();
    }
    const targetId = answer.focus_product_id || applied[0]?.line.product_id || null;
    if (targetId) setTimeout(() => focusRow(targetId), 40);
  } catch (error) {
    app.up.assistant = Boolean(error.status) && error.status !== 503;
    say("agent", "I could not answer just now. Nothing was changed. You can still change the table by hand.", { status: "refused" });
  } finally {
    app.chatBusy = false;
    draw();
    el("ask-text").focus();
  }
}

/* In live mode the state can move without the page asking: look again every second while something is open. */
let watchTimer = null;
function watch() {
  clearTimeout(watchTimer);
  if (app.mode !== "live" || !["running", "waiting_for_human"].includes(status())) return;
  watchTimer = setTimeout(async () => {
    try {
      const fresh = await driver.state();
      if (JSON.stringify(fresh.steps) !== JSON.stringify(app.state.steps) || fresh.scenario.status !== status()) {
        app.state = fresh;
        reveal();
        schedulePulse();
      }
    } catch {
      /* the next look may work */
    }
    watch();
  }, POLL_MS);
}

/*
 * Are the services there? The page looks again every few seconds, so a service started after the page shows up
 * without a reload.
 */
async function checkServices() {
  const [policy, health, state] = await Promise.all([
    harness.policy().catch(() => null),
    assistant.health().catch(() => null),
    query.has("replay") ? null : driver.state().catch(() => null),
  ]);
  app.up.harness = Boolean(policy);
  if (policy) app.policy = policy;
  app.up.assistant = Boolean(health?.chat);
  app.pulseOnline = Boolean(health?.pulse);
  if (health?.model) app.assistantModel = health.model;
  if (health?.decision_model) app.decisionModel = health.decision_model;
  app.up.driver = Boolean(state && Array.isArray(state.steps));
  // The driver arrived while nothing was running: from now on the page is live.
  if (app.up.driver && app.mode === "replay" && !hasRun() && !app.busy) {
    app.mode = "live";
    app.state = state;
  }
  draw();
  schedulePulse();
  setTimeout(checkServices, SERVICES_MS);
}

function closeAccountMenu() {
  const button = el("account-btn");
  const menu = el("account-menu");
  if (button && menu) {
    button.setAttribute("aria-expanded", "false");
    menu.hidden = true;
  }
}

document.addEventListener("click", (event) => {
  const accountButton = event.target.closest("#account-btn");
  if (accountButton) {
    const open = accountButton.getAttribute("aria-expanded") === "true";
    accountButton.setAttribute("aria-expanded", String(!open));
    el("account-menu").hidden = open;
    return;
  }
  if (!event.target.closest("#account-menu")) closeAccountMenu();

  if (event.target.closest('[data-dialog="cancel"]')) {
    closeDialog();
    return;
  }

  const promptChip = event.target.closest("[data-prompt]");
  if (promptChip && !promptChip.disabled) {
    sendChat(promptChip.dataset.prompt);
    return;
  }

  const jumpBtn = event.target.closest("[data-jump]");
  if (jumpBtn) {
    if (app.step !== 2) app.step = 2;
    draw();
    focusRow(jumpBtn.dataset.jump);
    return;
  }

  // The chef can always go back to the recipes and the stock, also once an order was sent.
  const stepButton = event.target.closest("[data-step]");
  if (stepButton) {
    app.step = Number(stepButton.dataset.step);
    app.followUps = [];
    draw();
    return;
  }

  const recipe = event.target.closest("[data-recipe]");
  if (recipe) {
    app.recipeId = recipe.dataset.recipe;
    drawMain();
    return;
  }

  const filter = event.target.closest("[data-filter]");
  if (filter) {
    app.stockFilter = filter.dataset.filter;
    drawMain();
    return;
  }

  const scenario = event.target.closest("[data-scenario]");
  if (scenario) {
    chooseScenario(scenario.dataset.scenario);
    return;
  }

  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "confirm-recipes") {
    if (!app.confirmed.recipes) {
      app.confirmed.recipes = timeNow();
      say("chef", "The recipes are right.");
      say("agent", stockLine());
      toast("Recipes confirmed");
    }
    app.step = 2;
    app.followUps = [];
    draw();
  } else if (action === "confirm-stock") {
    if (!orderOnScreen()) {
      const missing = missingLines().length;
      app.confirmed.stock = timeNow();
      say("chef", "The stock is checked.");
      say("agent", missing ? orderLine() : "Everything is covered by the stock: there is nothing to order.");
      toast(`Stock confirmed: ${missing} ${missing === 1 ? "ingredient" : "ingredients"} to order`);
    }
    app.step = 3;
    app.followUps = [];
    draw();
  } else if (action === "run") {
    toast("Order handed to your assistant");
    guarded(runScenario);
  } else if (action === "approve") {
    askSignature();
  } else if (action === "reject") {
    askRejection();
  } else if (action === "limit") {
    closeAccountMenu();
    askLimit();
  } else if (action === "details") {
    app.detailsOpen = !app.detailsOpen;
    drawMain();
  } else if (action === "correct") {
    correctQuantities();
  } else if (action === "use-need") {
    useNeed();
    draw();
    schedulePulse();
  } else if (action === "undo") {
    undoChanges();
    draw();
    schedulePulse();
  } else if (action === "pulse") {
    schedulePulse(true);
  } else if (action === "reset") {
    chooseScenario(app.scenarioId === "attack" ? "normal-order" : app.scenarioId);
  }
});

/* A number typed in the stock table. The field that has the focus keeps it when the table is drawn again. */
document.addEventListener("change", (event) => {
  const cell = event.target.closest("[data-cell]");
  if (!cell) return;
  const [productId, name] = cell.dataset.cell.split(":");
  const typed = cell.value.trim().replace(",", "."); // 4,5 and 4.5 are both read as four and a half
  const amount = /^\d+(\.\d+)?$/.test(typed) ? Number(typed) : NaN;
  const changed = setStock(productId, name, amount, "you");
  if (!changed) cell.value = app.lines.find((line) => line.product_id === productId)?.[name] ?? "";
  if (changed && app.confirmed.stock && !orderOnScreen()) app.confirmed.stock = null; // a changed table is confirmed again
  setTimeout(() => {
    const focused = document.activeElement?.dataset?.cell;
    draw();
    schedulePulse();
    if (focused) document.querySelector(`[data-cell="${CSS.escape(focused)}"]`)?.focus();
  }, 0);
});

document.addEventListener("submit", (event) => {
  event.preventDefault();
  if (event.target.id === "ask") {
    const input = el("ask-text");
    const text = input.value.trim();
    input.value = "";
    sendChat(text);
  } else if (event.target.id === "dialog-form" && dialogConfirm) {
    dialogConfirm();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeAccountMenu();
});

/* ---------- Start ---------- */

(async function start() {
  try {
    // Is the demo driver there? If not, replay the recorded runs.
    let state = null;
    if (!query.has("replay")) {
      state = await driver.state().catch(() => null);
    }
    app.mode = state && Array.isArray(state.steps) ? "live" : "replay";
    app.up.driver = app.mode === "live";
    app.state = app.mode === "live" ? state : await recorded("idle");

    const [recipes, bookings, stock, policy] = await Promise.all([
      kitchenApi.recipes(),
      kitchenApi.bookings(),
      kitchenApi.stock(app.state.scenario.id ?? app.scenarioId),
      harness.policy().catch(() => null),
    ]);
    app.kitchen = { recipes, bookings, stock };
    app.up.harness = Boolean(policy);
    // Without the harness, the limit is read from the policy file the harness loads.
    app.policy = policy ?? (await call("../../scenarios/policy.demo.json").catch(() => null));

    startOver();
    if (hasRun()) {
      // The driver was already in the middle of a scenario: show it where it is.
      app.scenarioId = app.state.scenario.id;
      app.step = 3;
      app.shown = reachable();
      app.sentKey = app.scenarioId === "attack" ? linesKey(app.state.request?.lines) : linesKey(orderLines());
      tell();
      watch();
    }
    drawAll();
    checkServices();
  } catch (error) {
    el("main").innerHTML = `<p class="problem"><strong>The page could not load its data.</strong>
      Start the page's service from the root of the repo (<code>uv run uvicorn surface.assistant:app --port 8004</code>)
      and open <code>http://localhost:8004/</code>. Detail: ${esc(error.message)}</p>`;
  }
})();
