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
/*
 * Where the services are. On a laptop each one has its own port. Hosted (README, "Hosted demo"), one address
 * serves everything: the page at the root and each service under its name, a prefix the reverse proxy cuts off
 * (deploy/Caddyfile.snippet). ?driver=, ?harness=, ?assistant= and ?gateway= still win over both.
 */
const ON_LAPTOP = ["localhost", "127.0.0.1", ""].includes(window.location.hostname); // "" is a page opened as a file
const serviceUrl = (name, port) => (query.get(name) || (ON_LAPTOP ? `http://localhost:${port}` : `/${name}`)).replace(/\/$/, "");
const DRIVER_URL = serviceUrl("driver", 8003);
const HARNESS_URL = serviceUrl("harness", 8002);
const ASSISTANT_URL = serviceUrl("assistant", 8004);
const GATEWAY_URL = serviceUrl("gateway", 8001);
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

const STEP_ACTORS = {
  open_mandate: { label: "Harness · Policy", tone: "harness" },
  signed_quote: { label: "Valio Gateway", tone: "gateway" },
  verdict: { label: "Harness Rules", tone: "harness" },
  closed_mandates: { label: "Harness / Chef", tone: "chef" },
  merchant_verifies: { label: "Valio Gateway", tone: "gateway" },
  sandbox_payment: { label: "Valio Gateway", tone: "gateway" },
  signed_receipt: { label: "Valio Gateway", tone: "gateway" },
  delivery: { label: "Valio Aimo", tone: "gateway" },
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
  "shelf-life-window": {
    pass: "Discounted lot shelf life fits your service window",
    human: "Short shelf life on a discounted item — check if you can use it in time",
    deny: "Shelf life is too short for delivery",
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
  detailsOpen: false, // the full comparison of a substitute
  recordOpen: query.has("record"), // both audit logs under the order; ?record=1 opens them from the start
  policy: null,
  busy: false,
  chatBusy: false,
  problem: null,
  // Valio's estimate of the order's carbon footprint, for the lines in `key`, and the offers the chef put off this week
  eco: { data: null, key: null, loading: false, dismissed: new Set() },
  trends: [], // sample food trends written for the demo (kitchen/trends.json), synthetic
  trendId: null,
  recommendation: null, // { trend, recipe, source, model }
  recBusy: false,
  recPortions: 50,
  recAdded: false,
  spotlightOpen: false,
  chatOpen: false,
  prospectOpen: false,
  prospectBusy: false,
  prospect: null,
  prospectQty: {},
  prospectAdded: new Set(),
};

const activeCustomer = () => app.state?.kitchen?.customer || "ravintola-demo";
const defaultProspectQty = (item) =>
  Math.min(item.available_base_quantity, item.base_unit === "KG" ? 5 : item.base_unit === "L" ? 4 : 2);

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
    check: '<path d="M4 10.500l4 4 8-9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    cross: '<path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
    wait: '<circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="M10 6v4.500l3 1.500" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    skip: '<path d="M5 10h10" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
    spark: '<path d="M9 2l1.700 4.600L15.300 8.300l-4.600 1.700L9 14.600 7.300 10 2.700 8.300l4.600-1.700z" fill="currentColor"/><path d="M15.500 12.500l.8 2.200 2.200.8-2.200.8-.8 2.200-.8-2.200-2.200-.8 2.200-.8z" fill="currentColor"/>',
    user: '<circle cx="10" cy="6.500" r="3.500" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M3 17.500c.6-3.400 3.400-5.500 7-5.500s6.400 2.100 7 5.500" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    arrow: '<path d="M4 10h11M11 5l5 5-5 5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    lock: '<rect x="4.500" y="9" width="11" height="8" rx="1.800" fill="currentColor"/><path d="M7 9V6.500a3 3 0 0 1 6 0V9" fill="none" stroke="currentColor" stroke-width="2"/>',
    shield: '<path d="M10 2l6.500 2.400v4.800c0 4-2.700 7.300-6.500 8.800-3.800-1.500-6.500-4.800-6.500-8.800V4.400z" fill="none" stroke="currentColor" stroke-width="1.800" stroke-linejoin="round"/><path d="M7 10l2.200 2.200L13.200 8" fill="none" stroke="currentColor" stroke-width="1.800" stroke-linecap="round" stroke-linejoin="round"/>',
    pen: '<path d="M3 17l1-4L14 3l3 3L7 16z" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linejoin="round"/><path d="M12 5l3 3" stroke="currentColor" stroke-width="1.700"/>',
    send: '<path d="M3 10l14-6.500-5 14-2.800-5.700z" fill="currentColor"/>',
    leaf: '<path d="M4 16.500C3.500 8.500 8 3.500 17 3.500c.5 8.500-4 13-11.500 13" fill="none" stroke="currentColor" stroke-width="1.800" stroke-linejoin="round"/><path d="M4 16.500l7.500-7.500" fill="none" stroke="currentColor" stroke-width="1.800" stroke-linecap="round"/>',
  };
  return `<svg class="icon" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">${paths[name]}</svg>`;
}

/* ---------- Sources ---------- */

const driver = {
  state: () => call(`${DRIVER_URL}/state`, {}, 1500),
  // The lines are what the chef confirmed in the stock table. A driver that only plays fixed scenarios ignores them.
  run: (id, body) => postJson(`${DRIVER_URL}/scenarios/${encodeURIComponent(id)}/run`, body ?? {}, 60000),
  reset: () => postJson(`${DRIVER_URL}/reset`, {}),
  // Valio's estimate of the carbon footprint of these lines, and its greener alternatives. Never signed.
  footprint: (lines) => postJson(`${DRIVER_URL}/footprint`, { lines }, 8000),
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
  chat: (turns, state) => postJson(`${ASSISTANT_URL}/chat`, { turns, state }, 30000),
  recommend: (payload) => postJson(`${ASSISTANT_URL}/recommend`, payload, 25000),
};

const gateway = {
  prospect: (customer) => call(`${GATEWAY_URL}/prospect?customer=${encodeURIComponent(customer)}`, {}, 8000),
};

// The page sits in surface/static/. Served by the harness, the same path reaches /contract/examples/.
const EXAMPLES_FOLDER = "../../contract/examples/";
const recorded = (name) => call(`${EXAMPLES_FOLDER}demo-state.${name}.json`);

const kitchenApi = {
  recipes: () => call("kitchen/recipes.json"),
  bookings: () => call("kitchen/bookings.json"),
  stock: (scenarioId) => call(`kitchen/stock.${STOCK_FILE[scenarioId] ?? "normal-order"}.json`),
  trends: () => call("kitchen/trends.json"),
};

/* ---------- What is on screen right now ---------- */

const status = () => app.state?.scenario?.status ?? "idle";
const hasRun = () => status() !== "idle";
const finished = () => ["done", "refused"].includes(status());
const missingLines = () => app.lines.filter((line) => line.to_order > 0);
const neededNow = (line) => round3(Math.max(0, line.need - line.in_stock));
const changedLines = () => app.lines.filter((line) => line.by.in_stock || line.by.to_order || line.swapped_from);

/* The lines the assistant will ask Valio for: what is short in the stock table. */
const orderLines = () =>
  missingLines().map((line) => ({
    product_id: line.product_id,
    name: line.name,
    amount: line.to_order,
    unit: line.unit,
    dish: line.dishes.join(", "),
    ...(line.claim_promo ? { claim_promo: true } : {}),
  }));

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
    unswap(line);
    line.in_stock = line.counted;
    line.to_order = neededNow(line);
    line.by = {};
  });
}

/* ---------- The carbon footprint and the weekly greener check ---------- */

/*
 * Valio's gateway estimates the footprint of the lines to order (weight x the average of the product group) and offers
 * at most two greener products for them, once a week. The page shows these figures as they come, marked as estimates,
 * and never works one out. Without the driver it reads the two estimates recorded for the normal order.
 */
const ECO_RECORDED = ["normal-order", "normal-order.greener"];
const ecoKey = () => linesKey(orderLines());
const ecoNow = () => (app.eco.key === ecoKey() ? app.eco.data : null);
const kgCo2 = (value) => `${Number(value).toLocaleString("en-GB", { maximumFractionDigits: 1 })} kg CO2e`;
const ecoOffer = (productId) => ecoNow()?.alternatives?.find((offer) => offer.product_id === productId) ?? null;
const swappedLines = () => app.lines.filter((line) => line.swapped_from);

async function recordedFootprint(key) {
  for (const name of ECO_RECORDED) {
    const found = await call(`${EXAMPLES_FOLDER}footprint.${name}.json`).catch(() => null);
    if (found && linesKey(found.lines) === key) return found;
  }
  return null;
}

/* Ask for the estimate of the lines on screen, once per set of lines. Called by draw(), so it follows every change. */
async function refreshEco() {
  const lines = orderLines();
  const asked = linesKey(lines);
  app.eco.loading = true;
  let data = null;
  try {
    if (lines.length && app.mode === "live") data = await driver.footprint(lines).catch(() => null);
    if (lines.length && !data) data = await recordedFootprint(asked);
  } finally {
    app.eco.loading = false;
    if (asked === ecoKey()) {
      app.eco.data = data;
      app.eco.key = asked;
    }
    draw();
  }
}

/* The chef (or the assistant, when the chef asks) takes Valio's greener product for one line. Returns what changed. */
function swapLine(productId, swapTo, by) {
  const offer = ecoOffer(productId);
  const line = app.lines.find((entry) => entry.product_id === productId);
  if (!canEdit() || !offer || !line || offer.alternative.id !== swapTo) return null;
  line.swapped_from = { product_id: line.product_id, name: line.name, offer, by };
  line.product_id = offer.alternative.id;
  line.name = offer.alternative.name;
  app.eco.dismissed.delete(productId);
  return { line, offer };
}

function unswap(line) {
  if (!line.swapped_from) return;
  line.product_id = line.swapped_from.product_id;
  line.name = line.swapped_from.name;
  delete line.swapped_from;
}

/* The kitchen's own name for the product of an offer, as in the stock table; Valio's name when the line is gone. */
const kitchenName = (offer) => app.lines.find((line) => line.product_id === offer.product_id)?.name ?? offer.name;
const swapText = (swap) => `${swap.line.swapped_from.name} → ${swap.offer.alternative.name}: ${kgCo2(swap.offer.saving_kg_co2e)} less`;
const savedByPercent = (offer) => `${Math.round(offer.saving_share * 100)}%`;

/* The little button on a line Valio has a greener product for, or the mark of a line already swapped. */
function ecoMarks(line) {
  if (line.swapped_from) {
    return ` <span class="tag tag--eco" title="${esc(`Swapped by ${line.swapped_from.by}`)}">Greener swap</span>
      <span class="muted">was ${esc(line.swapped_from.name)}</span>
      ${canEdit() ? `<button class="link" type="button" data-unswap="${esc(line.product_id)}">Undo</button>` : ""}`;
  }
  const offer = ecoOffer(line.product_id);
  if (!offer || !canEdit()) return "";
  return ` <button class="eco-btn" type="button" data-eco="${esc(line.product_id)}"
      title="${esc(`${offer.alternative.name}: ${savedByPercent(offer)} less CO2e`)}">${icon("leaf")}Greener option</button>`;
}

/* One line under the order: the estimated footprint, and what the greener swaps took off it. */
function footprintLine() {
  const data = ecoNow();
  if (!data) {
    if (app.eco.loading) return '<p class="eco-total">Estimating the carbon footprint…</p>';
    return orderLines().length ? '<p class="eco-total eco-total--off">Carbon footprint: no estimate for these quantities without Valio\'s gateway.</p>' : "";
  }
  // No line has a footprint: say so. A total of "0 kg CO2e" would read as no emissions, and unknown is never zero.
  if (data.lines.length && data.unknown.length === data.lines.length) {
    return `<p class="eco-total eco-total--off">Carbon footprint: no estimate, Valio has no footprint data for ${data.lines.length === 1 ? "this product" : "these products"}.</p>`;
  }
  const swaps = swappedLines();
  const saved = swaps.reduce((sum, line) => sum + line.swapped_from.offer.saving_kg_co2e, 0);
  const unknown = data.unknown.length ? `, ${data.unknown.length} ${data.unknown.length === 1 ? "line" : "lines"} without data left out` : "";
  return `<p class="eco-total" title="${esc(data.method)}">${icon("leaf")}Estimated carbon footprint <b>${esc(kgCo2(data.total_kg_co2e))}</b>
      ${saved ? `<span class="eco-total__saved">${esc(kgCo2(saved))} less with your greener ${swaps.length === 1 ? "swap" : "swaps"}</span>` : ""}
      <span class="muted">Product-group averages, an estimate${esc(unknown)}. Not part of the signed quote.</span></p>`;
}

/*
 * Under a quote, the estimate only shows when the quote was asked for the very lines it was estimated for.
 * The attack's quote carries its own quantities, twelve weeks at once: the estimate of the chef's table under it
 * would be a figure for another order, so nothing shows.
 */
const quoteFootprintLine = (quote) => (linesKey(quote.aimo.requested) === ecoKey() ? footprintLine() : "");

function offerFacts(offer) {
  return `<dl class="facts">
      <dt>Footprint</dt><dd>${esc(kgCo2(offer.kg_co2e_before))} → <b>${esc(kgCo2(offer.kg_co2e_after))}</b>, ${esc(savedByPercent(offer))} less</dd>
      <dt>Same amount</dt><dd>${esc(qty(offer.amount, offer.unit))}</dd>
      <dt>Allergens</dt><dd>${esc(allergenText(offer.alternative.allergens))}${offer.alternative.nutritional_claims.includes("FREE_FROM_LACTOSE") ? ", lactose free" : ""}</dd>
    </dl>
    <p class="card__note">${esc(offer.why)}</p>`;
}

/* The weekly greener check, beside the order before it is sent: one or two products, never more. */
function ecoCard() {
  const data = ecoNow();
  const offers = (data?.alternatives ?? []).filter((offer) => !app.eco.dismissed.has(offer.product_id));
  if (!offers.length || !canEdit()) return "";
  const items = offers
    .map(
      (offer) => `<div class="eco-offer">
        <p class="card__lead">${icon("leaf")}${esc(kitchenName(offer))} → ${esc(offer.alternative.name)}</p>
        ${offerFacts(offer)}
        <div class="eco-offer__actions">
          <button class="btn btn--go" type="button" data-eco-swap="${esc(offer.product_id)}">Switch</button>
          <button class="link" type="button" data-eco-dismiss="${esc(offer.product_id)}">Not this week</button>
        </div>
      </div>`
    )
    .join("");
  return `<section class="card card--eco">
      <p class="card__label">Weekly greener check · Valio Aimo</p>
      ${items}
      <p class="card__note muted">Checked every ${esc(data.review_every_days)} days on the products you order each week. Estimates from product-group averages.</p>
    </section>`;
}

function askSwap(productId) {
  const offer = ecoOffer(productId);
  if (!offer) return;
  openDialog({
    title: "Switch to the greener option?",
    body: `<p class="dialog__text"><b>${esc(kitchenName(offer))}</b> → <b>${esc(offer.alternative.name)}</b></p>${offerFacts(offer)}
      <p class="dialog__text">Valio's price comes with the signed quote, as for every line.</p>`,
    confirm: `${icon("leaf")}Switch`,
    onConfirm: () => {
      closeDialog();
      applySwap(productId, "you");
    },
  });
}

function applySwap(productId, by) {
  const swap = swapLine(productId, ecoOffer(productId)?.alternative.id, by);
  if (!swap) return;
  say("chef", `Switch the ${swap.line.swapped_from.name.toLowerCase()} to the greener option.`);
  const { offer } = swap;
  say("agent", `Done, same amount: ${kgCo2(offer.saving_kg_co2e)} less on this line, ${savedByPercent(offer)} less, by Valio's estimate. Valio prices it in the signed quote.`, {
    changes: [swapText(swap)],
  });
  toast(`Greener swap: ${kgCo2(swap.offer.saving_kg_co2e)} less`);
  draw();
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
  const name = app.state?.kitchen?.name ?? "";
  setHtml(
    el("account"),
    `<button class="account__btn" id="account-btn" aria-haspopup="true" aria-expanded="false" aria-controls="account-menu">
      ${icon("user")}${esc(name)}
      <svg class="account__chevron" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M2 5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
    <div class="account__menu" id="account-menu" hidden>
      <p class="account__who"><strong>${esc(name)}</strong>Customer ${esc(app.state?.kitchen?.customer)}</p>
      <button class="account__item" type="button" data-action="limit">Spending limit</button>
      <button class="account__item" type="button">Log out</button>
    </div>`
  );
}

function drawPlanning() {
  const services = app.kitchen.bookings?.services ?? [];
  if (!services.length) {
    setHtml(el("planning"), "");
    return;
  }
  const days = services
    .map(
      (service) => `<li class="day">
          <span class="day__date display">${esc(dayShort(service.date))}</span>
          <span class="day__covers"><b>${esc(service.booked)}</b> booked<br />${esc(service.projected)} projected</span>
        </li>`
    )
    .join("");
  setHtml(
    el("planning"),
    `<p class="needby"><span>Needed by</span><b class="display">${esc(dayLong(services[0].date))}</b></p>
    <ol class="days" aria-label="Covers per service: booked, and projected by the kitchen">${days}</ol>
    <p class="planning__src">${esc(titleCase(services[0].meal))} services<br />from bookings and planning</p>`
  );
}

/* ---------- Drawing: the chef's steps and the button ---------- */

function drawFlow() {
  const recipes = app.kitchen.recipes?.recipes ?? [];
  const missing = missingLines().length;
  const sent = orderOnScreen();
  const accepted = sent && status() === "done" && !app.busy && !revealing(); // not before the last step has lit up
  const items = [
    { n: 1, title: "Recipes", sub: app.confirmed.recipes ? `Confirmed at ${app.confirmed.recipes}` : `${recipes.length} on the menu`, done: Boolean(app.confirmed.recipes), open: true },
    { n: 2, title: "Stock", sub: app.confirmed.stock ? `Confirmed at ${app.confirmed.stock} · ${missing} to order` : `${missing} to order`, done: Boolean(app.confirmed.stock), open: Boolean(app.confirmed.recipes) || hasRun() },
    { n: 3, title: "Order", sub: accepted ? "Signed and accepted" : "then the signatures", done: accepted, open: Boolean(app.confirmed.stock) || hasRun() },
  ];
  setHtml(
    el("flow"),
    items
      .map(
        (item) => `<li>
          <button class="flow__step${item.done ? " is-done" : ""}" type="button" data-step="${item.n}"
            title="${esc(item.sub)}" ${app.step === item.n ? 'aria-current="step"' : ""} ${item.open ? "" : "disabled"}>
            <span class="flow__n">${item.done ? icon("check") : item.n}</span>
            <span class="flow__text"><b>${item.title}</b><span>${esc(item.sub)}</span></span>
          </button>
        </li>`
      )
      .join("")
  );

  let cta = "";
  if (inFlight()) {
    const waiting = status() === "waiting_for_human" && !app.busy && !revealing();
    cta = waiting
      ? `<p class="cta__status cta__status--waiting_for_human">${icon("pen")}Your signature is needed</p>
         <button class="btn btn--reject" type="button" data-action="reject">Reject</button>`
      : '<p class="cta__status">Your assistant is at work…</p>';
  } else if (app.step === 1) {
    cta = `<button class="btn" type="button" data-action="confirm-recipes">${app.confirmed.recipes ? "Go to the stock" : "Confirm recipes"} ${icon("arrow")}</button>`;
  } else if (app.step === 2) {
    cta = `<button class="btn" type="button" data-action="confirm-stock">${sent ? "Back to the order" : "Confirm stock"} ${icon("arrow")}</button>`;
  } else if (sent) {
    const done = status() === "done";
    cta = `<p class="cta__status cta__status--${done ? "done" : "refused"}">${done ? `${icon("check")}Order sent` : "No order placed"}</p>
      ${done ? "" : '<button class="btn" type="button" data-action="correct">Correct quantities</button>'}
      <button class="btn btn--quiet" type="button" data-action="reset">New order</button>`;
  } else {
    cta = `<button class="btn btn--go" type="button" data-action="run" ${missing ? "" : "disabled"}>${icon("spark")} Order with my assistant</button>`;
  }
  setHtml(el("cta"), cta);
}

/* ---------- Drawing: who signs ---------- */

function sealHtml() {
  if (!orderOnScreen() && !app.busy) return `<p class="seal">${icon("shield")}<span>No signature, no order.</span></p>`;
  if (app.busy || revealing()) return `<p class="seal seal--running">${icon("shield")}<span>Checking every signature…</span></p>`;
  if (status() === "waiting_for_human") return `<p class="seal seal--waiting">${icon("pen")}<span>Waiting for your signature.</span></p>`;
  if (status() === "refused") return `<p class="seal seal--refused">${icon("shield")}<span>Stopped: no valid signature, no order.</span></p>`;
  if (status() === "done") {
    // Who signed, read from the steps that are done.
    const names = { manager: "you", agent: "your assistant", merchant: "Valio" };
    const signers = [...new Set(trailSteps().filter((step) => step.status === "done" && names[step.signer]).map((step) => names[step.signer]))];
    return `<p class="seal seal--done">${icon("shield")}<span>Signed and checked at every step: ${esc(signers.join(", "))}.</span></p>`;
  }
  return `<p class="seal">${icon("shield")}<span>No signature, no order.</span></p>`;
}

function stepActor(step, on) {
  const base = STEP_ACTORS[step.key];
  if (!base) return "";
  let { label, tone } = base;
  if (step.key === "verdict" && on && app.state?.verdict?.judge?.length) {
    label = "Harness + Decision API";
    tone = "ai";
  } else if (step.key === "closed_mandates" && on) {
    if (step.signer === "agent") {
      label = "Harness · Agent";
      tone = "harness";
    } else if (step.signer === "human" || app.state?.approval) {
      label = "Surface · Chef";
      tone = "chef";
    }
  }
  return `<span class="step__actor step__actor--${tone}">${esc(label)}</span>`;
}

function stepBreakdown(step, on) {
  if (!on) return "";
  const lines = [];
  if (step.key === "signed_quote") {
    const alts = app.state?.quote?.aimo?.alternatives ?? [];
    if (alts.length) {
      lines.push({
        tone: "gateway",
        text: `Gateway ranked ${alts.length} catalog substitute${alts.length === 1 ? "" : "s"}`,
      });
    }
  } else if (step.key === "verdict" && app.state?.verdict) {
    const rules = app.state.verdict.rules ?? [];
    const judge = app.state.verdict.judge ?? [];
    const deterministic = judge.length ? rules.filter((r) => r.rule_id !== "substitution-within-preferences") : rules;
    if (deterministic.length) {
      const passed = deterministic.filter((r) => r.outcome === "pass").length;
      const allPass = passed === deterministic.length;
      lines.push({
        tone: allPass ? "pass" : "warn",
        text: `Harness: ${passed}/${deterministic.length} deterministic rules passed`,
      });
    }
    if (judge.length) {
      const scored = judge.map((j) => j.probability).filter((p) => typeof p === "number");
      const threshold = judge[0]?.auto_threshold ?? 0.85;
      if (!scored.length) {
        lines.push({ tone: "warn", text: "Decision API: unreachable → Human (fail-closed)" });
      } else {
        const minProb = Math.min(...scored);
        const auto = judge.every((j) => j.routed === "auto");
        lines.push({
          tone: auto ? "pass" : "ai",
          text: auto
            ? `Decision API: ${minProb.toFixed(2)} ≥ ${threshold.toFixed(2)} → Auto`
            : `Decision API: ${minProb.toFixed(2)} < ${threshold.toFixed(2)} → Human`,
        });
      }
    }
  }
  if (!lines.length) return "";
  return `<ul class="step__sub">${lines
    .map((line) => `<li class="step__sub-item step__sub-item--${line.tone}">${esc(line.text)}</li>`)
    .join("")}</ul>`;
}

function drawTrail() {
  const steps = trailSteps();
  const shown = lit();
  const items = steps
    .map((step, index) => {
      const on = index < shown;
      const state = on ? step.status : "pending";
      const mark = { done: icon("check"), refused: icon("cross"), waiting: icon("wait"), skipped: icon("skip") }[state] ?? index + 1;
      const signer = on && state !== "skipped" && SIGNER_WORDS[step.signer] ? `<span class="step__signer">${esc(SIGNER_WORDS[step.signer])}</span>` : "";
      const classes = [
        `step--${state}`,
        index === app.fresh && on ? "step--fresh" : "",
        index + 1 < shown ? "step--through" : "",
        index + 1 === app.fresh && index + 1 < shown ? "step--link" : "", // the line that has just reached the next step
      ].join(" ");
      return `<li class="step ${esc(classes)}">
          <span class="step__dot" aria-hidden="true">${mark}</span>
          <div class="step__body">
            <p class="step__title">${esc(STEP_WORDS[step.key] ?? step.title)}${signer}<span class="visually-hidden">, ${esc(state)}</span></p>
            <p class="step__term">${esc(step.title)}${stepActor(step, on)}${on && step.proof ? `<span class="step__proof mono" title="Signature: ${esc(step.proof)}">${icon("lock")}${esc(shortProof(step.proof))}</span>` : ""}</p>
            ${stepBreakdown(step, on)}
            ${on && step.detail ? `<p class="step__detail" title="${esc(plainDetail(step.detail))}">${esc(plainDetail(step.detail))}</p>` : ""}
          </div>
        </li>`;
    })
    .join("");
  // Three parts drawn apart: a part that did not change keeps its animation running.
  el("trail").classList.toggle("is-running", app.busy || revealing());
  setHtml(
    el("limit"),
    `<p class="limit__label">Your spending limit</p>
      <p class="limit__value display">${limitKnown() ? esc(limitText()) : "unknown"}<span> an order</span></p>
      <p class="limit__text">Above it, you sign every order yourself.</p>
      <button class="limit__btn" type="button" data-action="limit" ${canEdit() ? "" : "disabled"}>Change</button>`
  );
  setHtml(el("steps"), items);
  setHtml(el("seal"), sealHtml());
}

/* ---------- Drawing: step 1, recipes ---------- */

function recipesView() {
  const data = app.kitchen.recipes;
  const recipes = data?.recipes ?? [];
  const chosen = recipes.find((recipe) => recipe.id === app.recipeId) ?? recipes[0];
  const rows = recipes
    .map(
      (recipe) => `<tr class="pick${recipe === chosen ? " is-chosen" : ""}">
          <td><span class="tag">${esc(recipe.course)}</span></td>
          <td><button class="pick__btn" type="button" data-recipe="${esc(recipe.id)}" aria-pressed="${recipe === chosen}" title="${esc(recipe.with)}">
              <b>${esc(recipe.name)}</b>
            </button></td>
          <td class="num">${recipe.ingredients.length}</td>
        </tr>`
    )
    .join("");
  const ingredients = (chosen?.ingredients ?? [])
    .map(
      (item) => `<tr><td>${esc(item.name)}</td><td class="num">${esc(item.per_service)}</td><td class="muted num">${esc(item.product_id)}</td></tr>`
    )
    .join("");
  const activeTrend = (app.trends ?? []).find((t) => t.id === app.trendId) ?? (app.trends ?? [])[0];
  const spotlightBtn = activeTrend
    ? `<button class="spotlight-bubble${app.spotlightOpen ? " is-open" : ""}" type="button" data-action="toggle-spotlight" aria-expanded="${app.spotlightOpen}">
        <span class="spotlight-bubble__dot"></span>
        <span>Spotlight: Seasonal Dessert</span>
      </button>`
    : "";
  const prospectBtn = `<button class="spotlight-bubble${app.prospectOpen ? " is-open" : ""}" type="button" data-action="toggle-prospect" aria-expanded="${app.prospectOpen}">
      <span>Deals for your kitchen</span>
    </button>`;
  return `<div class="head head--with-spotlight">
      <div>
        <h2 class="display" title="Written for ${esc(data?.covers_per_service)} covers a service. Choose a recipe to see what goes into it.">Recipes on the menu</h2>
      </div>
      <div class="head__actions">${prospectBtn}${spotlightBtn}</div>
    </div>
    ${app.prospectOpen ? prospectView() : ""}
    ${app.spotlightOpen ? trendRecommendationView() : ""}
    <div class="split">
      <table class="tbl">
        <thead><tr><th>Course</th><th>Recipe</th><th class="num">Ingredients</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div class="panel">
        <h3 class="panel__title">${esc(chosen?.name)}</h3>
        <table class="tbl tbl--tight">
          <thead><tr><th>Ingredient</th><th class="num">For one service</th><th class="num">Product</th></tr></thead>
          <tbody>${ingredients}</tbody>
        </table>
      </div>
    </div>`;
}

function prospectView() {
  const data = app.prospect;
  const items = (data?.items ?? []).slice(0, 4);

  let body = "";
  if (app.prospectBusy) {
    body = `<p class="trend-card__loading">Loading deals for your kitchen…</p>`;
  } else if (!items.length) {
    body = `<p class="trend-card__prompt">No deals available right now.</p>`;
  } else {
    const rows = items
      .map((item) => {
        const added = app.prospectAdded.has(item.product.id);
        const urgent = item.shelf_life_days < 5;
        const tip = [
          `${qty(item.available_base_quantity, item.base_unit)} available`,
          item.portion_hint,
          ...(item.match_reasons ?? []),
        ].join(" · ");
        const chosenQty = app.prospectQty[item.product.id] ?? defaultProspectQty(item);
        return `<tr title="${esc(tip)}">
          <td><b>${esc(item.product.name)}</b></td>
          <td><span class="tag${urgent ? " tag--warn" : ""}">${esc(item.shelf_life_days)}d</span></td>
          <td class="num"><span class="prospect-price-old">${esc(money(item.contract_price_minor))}</span> <b>${esc(money(item.promo_price_minor))}</b> <span class="tag tag--eco">-${item.discount_pct}%</span></td>
          <td class="num"><span class="field">
            <input class="field__input" type="text" inputmode="decimal" autocomplete="off"
              data-prospect-qty="${esc(item.product.id)}" value="${esc(chosenQty)}"
              aria-label="${esc(`Quantity for ${item.product.name} in ${unitWord(item.base_unit)}`)}"
              ${canEdit() && !added ? "" : "disabled"} />
            <span class="field__unit">${esc(unitWord(item.base_unit, chosenQty))}</span>
          </span></td>
          <td class="num"><button class="btn btn--ghost" type="button" data-action="add-prospect" data-product-id="${esc(item.product.id)}" ${canEdit() && !added ? "" : "disabled"}>${added ? "Added" : "Add"}</button></td>
        </tr>`;
      })
      .join("");
    body = `<table class="tbl tbl--tight">
      <thead><tr><th>Product</th><th>Shelf life</th><th class="num">Price</th><th class="num">Qty</th><th class="num"></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  }

  return `<div class="panel trend-card prospect-card">
    <div class="trend-card__head">
      <h3 class="panel__title" title="Tailored to your kitchen profile and contract price. Hover a row for yield and match details.">Today for your kitchen</h3>
      <span class="trend-source-tiny">${esc(data ? `${data.customer_name} · ${data.customer_tier}` : activeCustomer())}</span>
    </div>
    ${body}
  </div>`;
}

function trendRecommendationView() {
  const trends = app.trends ?? [];
  if (!trends.length && !app.recommendation) return "";
  const activeTrend = trends.find((t) => t.id === app.trendId) ?? trends[0];
  const rec = app.recommendation;
  const portions = Math.max(1, Number(app.recPortions) || 50);

  const trendPills = trends
    .map((t) => {
      const selected = activeTrend && t.id === activeTrend.id;
      return `<button class="chip${selected ? " is-active" : ""}" type="button" data-action="select-trend" data-trend-id="${esc(t.id)}">${esc(t.title)}</button>`;
    })
    .join("");

  let body = "";
  if (app.recBusy) {
    body = `<p class="trend-card__loading">Generating recipe grounded in Valio Aimo catalog…</p>`;
  } else if (rec?.recipe) {
    const r = rec.recipe;
    const rows = (r.ingredients ?? [])
      .map((ing) => {
        const total = round3(Number(ing.amount_per_portion) * portions);
        const meta = [ing.origin ? `Origin ${ing.origin}` : null, ing.carbon_kg_per_kg != null ? `${num(ing.carbon_kg_per_kg)} kg CO2e/kg, group average` : null]
          .filter(Boolean)
          .join(" · ");
        return `<tr title="${esc(meta)}">
          <td><b>${esc(ing.name)}</b></td>
          <td class="num">${esc(qty(ing.amount_per_portion, ing.unit))}</td>
          <td class="num"><b>${esc(qty(total, ing.unit))}</b></td>
          <td class="muted num">#${esc(ing.product_id)}</td>
        </tr>`;
      })
      .join("");
    const sourceBadge = rec.source === "live_llm" ? `live · ${esc(rec.model)}` : "cached fallback";
    body = `
      <div class="trend-recipe">
        <div class="trend-recipe__head">
          <div>
            <span class="tag">${esc(r.course)}</span>
            <h4 class="trend-recipe__title" title="${esc(r.with_text)} — ${esc(r.trend_reason)}">${esc(r.name)}</h4>
          </div>
          <span class="trend-source-tiny">${sourceBadge}</span>
        </div>
        <table class="tbl tbl--tight">
          <thead><tr><th>Valio Ingredient</th><th class="num">Per portion</th><th class="num">For ${portions} portions</th><th class="num">Product</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <div class="trend-recipe__actions">
          <label class="trend-portions">
            <span>Portions</span>
            <input id="rec-portions" class="field__input" type="number" min="1" max="2000" value="${portions}" ${canEdit() ? "" : "disabled"} />
          </label>
          <button class="btn btn--primary" type="button" data-action="add-recommended" ${canEdit() && !app.recAdded ? "" : "disabled"}>
            ${app.recAdded ? "Added to menu & order" : `Add to menu & order (${portions} portions)`}
          </button>
        </div>
      </div>`;
  } else {
    body = `<p class="trend-card__prompt">Click <b>Generate recipe</b> to match this food trend against Valio Aimo's catalog.</p>`;
  }

  // The trends are sample lines written for the demo (kitchen/trends.json): the card says so, and names no news service.
  return `<div class="panel trend-card">
    <div class="trend-card__head">
      <div>
        <span class="tag">Valio Aimo Spotlight · sample trend</span>
        <h3 class="panel__title" title="${esc(activeTrend?.headline ?? "")} (${esc(activeTrend?.source ?? "Sample trend, synthetic")})">${esc(activeTrend?.title ?? "Seasonal Food Trend")}</h3>
        ${activeTrend?.headline ? `<p class="trend-card__headline">${esc(activeTrend.headline)} <span class="trend-source-tiny">(${esc(activeTrend.source ?? "Sample trend, synthetic")}${activeTrend.published_at ? ` · ${esc(activeTrend.published_at)}` : ""})</span></p>` : ""}
      </div>
    </div>
    ${trends.length > 1 ? `<div class="trend-card__pills">${trendPills}</div>` : ""}
    ${body}
  </div>`;
}

/* ---------- Drawing: step 2, stock ---------- */

function field(line, name, label) {
  const who = line.by[name];
  const title = who ? `Changed by ${who}` : "";
  return `<span class="field${who ? " is-changed" : ""}" title="${esc(title)}">
      <input class="field__input" type="text" inputmode="decimal" autocomplete="off" value="${esc(line[name])}"
        data-cell="${esc(line.product_id)}:${name}" aria-label="${esc(`${label}, ${line.name}, in ${unitWord(line.unit)}`)}" ${canEdit() ? "" : "disabled"} />
      <span class="field__unit">${esc(unitWord(line.unit, line[name]))}</span>
    </span>`;
}

function stockView() {
  const stock = app.kitchen.stock;
  const missing = missingLines();
  const shownLines = app.stockFilter === "missing" ? missing : [...missing, ...app.lines.filter((line) => line.to_order <= 0)];
  const rows = shownLines
    .map((line) => {
      const short = line.to_order > 0;
      const above = line.to_order > neededNow(line);
      return `<tr class="${short ? "is-short" : "is-covered"}">
          <td>${esc(line.name)}${above ? ' <span class="tag tag--warn" title="More than the recipes need, with what is in stock">above need</span>' : ""}${short ? ecoMarks(line) : ""}</td>
          <td class="muted">${esc(line.dishes.join(", "))}</td>
          <td class="num">${esc(qty(line.need, line.unit))}</td>
          <td class="num">${field(line, "in_stock", "In stock")}</td>
          <td class="num">${field(line, "to_order", "To order")}</td>
        </tr>`;
    })
    .join("");
  const chip = (id, label, count) =>
    `<button class="chip" type="button" data-filter="${id}" aria-pressed="${app.stockFilter === id}">${label} <span>${count}</span></button>`;
  const changed = changedLines().length;

  const stockHint = `Counted ${dayLong(stock.counted_at)}, ${stock.counted_by}. Need is for the ${stock.for_services} services. You can change any number.`;
  let note = "";
  if (!canEdit()) {
    note = `<p class="note">${icon("lock")}An order is open with these quantities. They are locked until it is signed or rejected.</p>`;
  } else if (app.correcting && !dirty()) {
    note = `<p class="note note--refused">The refused order asked for these quantities. Correct them, then order again.
        <button class="link" type="button" data-action="use-need">Use what the recipes need</button></p>`;
  } else if (dirty()) {
    note = '<p class="note">The quantities changed since the last order. Confirm the stock to prepare a new order.</p>';
  }
  return `<div class="head">
      <h2 class="display" title="${esc(stockHint)}">Stock check</h2>
      ${note}
      <div class="chips">
        ${changed && canEdit() ? `<button class="link" type="button" data-action="undo">Undo ${changed} ${changed === 1 ? "change" : "changes"}</button>` : ""}
        ${chip("all", "All", app.lines.length)}${chip("missing", "To order", missing.length)}
      </div>
    </div>
    <table class="tbl tbl--stock">
      <thead><tr><th>Ingredient</th><th>Used in</th><th class="num">Need</th><th class="num">In stock</th><th class="num">To order</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ---------- Drawing: step 3, the order ---------- */

function requestTable() {
  const lines = missingLines();
  const rows = lines
    .map(
      (line) => `<tr><td>${esc(line.name)}${ecoMarks(line)}</td><td class="muted">${esc(line.dishes.join(", "))}</td><td class="num"><b>${esc(qty(line.to_order, line.unit))}</b></td></tr>`
    )
    .join("");
  const empty = lines.length ? "" : '<p class="note">Everything is covered by the stock: there is nothing to order.</p>';
  return `<div class="head">
      <h2 class="display" title="What your assistant will ask Valio Aimo for. Prices and Valio's stock come with the signed quote.">Ready to order</h2>
    </div>
    ${empty}
    <table class="tbl">
      <thead><tr><th>Ingredient</th><th>Used in</th><th class="num">To order</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>${footprintLine()}`;
}

/* One sentence under the quote when Valio gave no stock count on some lines. It never blocks the order: unknown is shown, not hidden. */
function stockNote(quote) {
  const total = quote.line_items.length;
  const unconfirmed = quote.line_items.filter((item) => {
    const stock = quote.aimo.lines[item.id]?.stock;
    return !stock || stock.certainty === "unknown" || typeof stock.value !== "number";
  }).length;
  if (unconfirmed === 0) return "";
  return `<p class="stock-note">Stock not confirmed on ${unconfirmed} of ${total} ${total === 1 ? "line" : "lines"}: Valio gave no count. This does not stop the order.</p>`;
}

function quoteTable(state) {
  const quote = state.quote;
  const total = quote.totals.find((item) => item.type === "total");
  const rows = quote.line_items
    .map((item) => {
      const facts = quote.aimo.lines[item.id] ?? {};
      const lineTotal = item.totals.find((entry) => entry.type === "total");
      const replaces = facts.substitute_for ? `<span class="tag tag--warn">Substitute</span> <span class="muted">for ${esc(facts.substitute_for.name)}</span>` : "";
      const promoBadge = facts.promo_discount_pct ? `<span class="tag tag--eco">-${facts.promo_discount_pct}% deal · ${facts.shelf_life_days}d</span>` : "";
      const unitPrice = facts.base_unit_price_minor && facts.promo_discount_pct
        ? `<span class="prospect-price-old">${esc(money(facts.base_unit_price_minor, quote.currency))}</span> <b>${esc(money(item.item.price, quote.currency))}</b>`
        : esc(money(item.item.price, quote.currency));
      return `<tr>
          <td><b>${esc(item.item.title)}</b>${replaces ? `<br />${replaces}` : ""}${promoBadge ? ` ${promoBadge}` : ""}</td>
          <td class="num">${esc(qty(item.quantity, facts.sales_unit))}</td>
          <td class="num">${unitPrice}</td>
          <td class="num"><b>${esc(money(lineTotal.amount, quote.currency))}</b></td>
          <td>${esc(stockText(facts.stock))}</td>
        </tr>`;
    })
    .join("");
  const mismatch = app.mismatch
    ? `<p class="note note--refused">This quote is for the quantities of the recorded run, not for the ones you changed.
        ${app.mode === "live" ? "The demo driver does not take changed quantities yet." : "A quote for your own quantities needs the demo driver, which is not running."}</p>`
    : "";
  return `<div class="head">
      <h2 class="display">Quote signed by Valio Aimo</h2>
      <p class="head__meta">Delivery ${esc(dayLong(quote.aimo.delivery_date))}, valid until ${esc(clock(quote.expires_at))}. Prices before tax.</p>
    </div>
    ${mismatch}
    <table class="tbl tbl--quote">
      <thead><tr><th>Product</th><th class="num">Quantity</th><th class="num">Unit price</th><th class="num">Total</th><th>Valio's stock</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="3">Total before tax</td><td class="num"><b>${esc(money(total.amount, quote.currency))}</b></td><td></td></tr></tfoot>
    </table>${stockNote(quote)}${quoteFootprintLine(quote)}`;
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
  // When a check needs the chef, the ones that passed fold away: what matters is read first.
  const list = open.length
    ? `<ul class="checks">${open.map(row).join("")}</ul>
       <details class="passed"><summary>The ${passed.length} other checks passed</summary><ul class="checks">${passed.map(row).join("")}</ul></details>`
    : `<ul class="checks">${passed.map(row).join("")}</ul>`;
  return `<section class="card card--${esc(verdict.decision)}${arriving(3)}">
      <p class="card__label">Safety checks before anyone signs</p>
      <p class="card__lead"><span class="badge badge--${esc(verdict.decision)}">${esc(badge)}</span>${esc(lead)}</p>
      ${list}
    </section>`;
}

function productFacts(title, name, facts, extra = "") {
  const size = facts.size_per_sales_unit ? `${num(facts.size_per_sales_unit.value)} ${String(facts.size_per_sales_unit.unit).toLowerCase()} a unit` : "unknown";
  const claims = (facts.nutritional_claims ?? []).map(words).join(", ") || "none stated";
  const labels = (facts.labels ?? []).map(words).join(", ") || "none stated";
  return `<div class="versus__side">
      <p class="card__label">${title}</p>
      <p class="versus__name">${esc(name)}</p>
      <dl class="facts">
        <dt>Brand</dt><dd>${esc(facts.brand ?? "unknown")}</dd>
        <dt>Pack</dt><dd>${esc(size)}</dd>
        <dt>Storage</dt><dd>${esc(storageText(facts.temperature_condition))}</dd>
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

/* ---------- The trade-offs of a substitute ---------- */

// The storage classes of Valio's product file that we can name. Another class shows by its number, never guessed.
const STORAGE_WORDS = { 3: "chilled", 7: "frozen", 8: "ambient" };
const storageKnown = (code) => code !== null && code !== undefined;
const storageText = (code) => (storageKnown(code) ? (STORAGE_WORDS[code] ?? `storage class ${code}`) : "unknown");

/*
 * What changes for the kitchen with the substitute, on four sides: cost, the dish, the work in the kitchen,
 * storage and delivery. Every figure is read from the quote Valio signed or from the assistant's answers.
 * The page puts two signed prices side by side and says which is lower: it never works out a price, a saving
 * or a time. What the data does not say is said, not guessed.
 * tone: "good" nothing to weigh, "note" something changes, "ask" a reason the chef is asked.
 */
function tradeOffs(state) {
  const { quote, approval } = state;
  const item = quote.line_items.find((entry) => quote.aimo.lines[entry.id]?.substitute_for);
  if (!item) return [];
  const facts = quote.aimo.lines[item.id];
  const asked = facts.substitute_for;
  const perUnit = (minor, unit) => `${money(minor, quote.currency)} a ${String(unit).toLowerCase()}`;

  // Cost: Valio's price a kilo or a litre for both products, when the quote carries both.
  const ours = facts.comparison_price_minor;
  const theirs = asked.comparison_price_minor;
  const total = `${money(approval.total_minor, approval.currency)} for the order.`;
  let cost = { tone: "note", text: `${perUnit(ours, facts.comparison_unit)}, ${total} Valio's quote has no price for the one you asked for.` };
  if (Number.isFinite(theirs) && asked.comparison_unit === facts.comparison_unit) {
    const word = ours < theirs ? "Cheaper" : ours > theirs ? "More expensive" : "Same price";
    cost = { tone: ours > theirs ? "ask" : "good", text: `${word}: ${perUnit(ours, facts.comparison_unit)}, against ${perUnit(theirs, asked.comparison_unit)} for the one you asked for. ${total}` };
  }

  // The dish: the assistant's two answers, with the line under which it asks the chef.
  const answer = (key) => (approval.judge ?? []).find((entry) => entry.question_key === key && Number.isFinite(entry.probability));
  const percent = (entry) => `${Math.round(entry.probability * 100)}%`;
  const same = answer("same_use");
  const fits = answer("within_preferences");
  const sure = [same && `${percent(same)} sure it works the same way in the dish`, fits && `${percent(fits)} sure it fits your kitchen's preferences`].filter(Boolean);
  const unsure = [same, fits].filter((entry) => entry && entry.routed !== "auto");
  const dish = sure.length
    ? { tone: unsure.length ? "ask" : "good", text: `${ASSISTANT} is ${sure.join(", and ")}.${unsure.length ? ` Below ${Math.round(unsure[0].auto_threshold * 100)}%, it asks you.` : ""}` }
    : { tone: "ask", text: `${ASSISTANT} could not tell whether it works the same way in the dish, so it asks you.` };

  // The work in the kitchen: how the product comes. Valio's data has no preparation time, and the page says so.
  const size = facts.size_per_sales_unit;
  const askedSize = asked.size_per_sales_unit;
  const packs = size?.value ? `${qty(item.quantity, facts.sales_unit)} of ${qty(size.value, size.unit)} each` : qty(item.quantity, facts.sales_unit);
  const samePack = Boolean(size?.value && askedSize?.value && size.value === askedSize.value && size.unit === askedSize.unit && facts.sales_unit === asked.sales_unit);
  let before = "The pack size of the one you asked for is unknown.";
  if (samePack) before = "Same pack size as the one you asked for.";
  else if (askedSize?.value && asked.sales_unit === askedSize.unit) before = `The one you asked for is sold by the ${unitWord(askedSize.unit, 1)}.`;
  else if (askedSize?.value) before = `The one you asked for comes in packs of ${qty(askedSize.value, askedSize.unit)}.`;
  const work = { tone: samePack ? "good" : "note", text: `${packs}. ${before} Valio's data gives no preparation time.` };

  // Storage and delivery: the storage class of both, Valio's stock, the delivery day, and how reliably Valio delivered it.
  const here = facts.temperature_condition;
  const there = asked.temperature_condition;
  let storage = { tone: "note", text: `Storage: ${storageText(here)}, and ${storageText(there)} for the one you asked for.` };
  if (storageKnown(here) && here === there) storage = { tone: "good", text: `${titleCase(storageText(here))}, like the one you asked for.` };
  else if (storageKnown(here) && storageKnown(there)) storage = { tone: "ask", text: `Storage changes: ${storageText(here)}, where the one you asked for is ${storageText(there)}.` };
  const reliability = facts.delivery_reliability;
  const delivered =
    reliability && reliability.certainty !== "unknown" && Number.isFinite(reliability.value)
      ? `In the past Valio delivered ${Math.round(reliability.value * 100)}% of what was ordered of it.`
      : "Valio has no delivery history for it.";
  const logistics = { tone: storage.tone, text: `${storage.text} Valio's stock: ${stockText(facts.stock)}. Delivery ${dayLong(quote.aimo.delivery_date)}. ${delivered}` };

  return [
    { key: "cost", label: "Cost", ...cost },
    { key: "dish", label: "In the dish", ...dish },
    { key: "work", label: "In the kitchen", ...work },
    { key: "logistics", label: "Storage, delivery", ...logistics },
  ];
}

const TRADE_OFF_ICON = { good: "check", note: "arrow", ask: "pen" };
const tradeOffRows = (state) =>
  tradeOffs(state)
    .map(
      (row) => `<li class="tradeoff tradeoff--${esc(row.tone)}">
          <span class="tradeoff__side">${icon(TRADE_OFF_ICON[row.tone])}${esc(row.label)}</span>
          <span class="tradeoff__text">${esc(row.text)}</span>
        </li>`
    )
    .join("");

function approvalCard(state) {
  const approval = state.approval;
  const quote = state.quote;
  if (approval.status !== "pending") {
    const outcome = { approved: "Signed", rejected: "Rejected: nobody signed, no order", expired: "Expired: nobody signed in time" }[approval.status] ?? approval.status;
    const who = approval.decided_by ? ` by ${approval.decided_by}${approval.decided_at ? `, ${clock(approval.decided_at)}` : ""}` : "";
    return `<section class="card card--human">
        <p class="card__label">Your signature</p>
        <p class="sign__done sign__done--${esc(approval.status)}">${approval.status === "approved" ? icon("check") : icon("cross")}${esc(outcome + who)}</p>
      </section>`;
  }

  const item = quote.line_items.find((entry) => quote.aimo.lines[entry.id]?.substitute_for);
  let body = "";
  if (item) {
    const facts = quote.aimo.lines[item.id];
    const shortfall = (quote.aimo.shortfalls ?? []).find((entry) => entry.product_id === facts.substitute_for.product_id);
    const why = shortfall ? `Valio cannot deliver what you asked for: ${SHORTFALL_WORDS[shortfall.reason] ?? words(shortfall.reason)}.` : "Valio proposes another product than the one you asked for.";
    const candidates = (quote.aimo.alternatives ?? []).length;
    // Valio's gateway ranks substitutes in three tiers (good, better, best) and says why: the page repeats both.
    const chosen = (quote.aimo.alternatives ?? []).find((entry) => entry.chosen && entry.product_id === facts.product_id);
    const found = candidates === 1 ? " Valio found one substitute and proposes it" : candidates ? ` Valio ranked ${candidates} substitutes and proposes this one` : "";
    const ranked = found ? `${found}${chosen ? `, in its "${chosen.tier}" tier (${chosen.why})` : ""}.` : "";
    // What a chef looks at first: the same allergens or not (a check of the harness), then what changes on four sides.
    const allergens = state.verdict?.rules.find((rule) => rule.rule_id === "allergen-unchanged-on-substitution");
    const allergenFact = allergens ? checkLine(allergens) : null;
    const extra = `<dt>Price</dt><dd>${esc(money(facts.comparison_price_minor, quote.currency))} a ${esc(String(facts.comparison_unit).toLowerCase())}</dd>
      <dt>Valio's stock</dt><dd>${esc(stockText(facts.stock))}</dd>`;
    const askedMinor = facts.substitute_for.comparison_price_minor;
    const askedPrice = Number.isFinite(askedMinor) ? `${money(askedMinor, quote.currency)} a ${String(facts.substitute_for.comparison_unit).toLowerCase()}` : "not in the quote";
    body = `<p class="card__note">${esc(why)}${esc(ranked)}</p>
      <div class="swap">
        <p class="swap__from"><span class="card__label">You asked for</span>${esc(facts.substitute_for.name)}</p>
        <span class="swap__arrow" aria-hidden="true">${icon("arrow")}</span>
        <p class="swap__to"><span class="card__label">Valio proposes</span>${esc(item.item.title)}</p>
      </div>
      <ul class="keys">
        ${allergenFact ? `<li class="key key--${esc(allergenFact.outcome)}">${allergenFact.outcome === "pass" ? icon("check") : icon("pen")}${esc(allergenFact.label)}${allergenFact.value ? `: ${esc(allergenFact.value)}` : ""}</li>` : `<li class="key">Contains: ${esc(allergenText(facts.allergens))}</li>`}
      </ul>
      <p class="card__label card__label--gap">What changes if you take it</p>
      <ul class="tradeoffs">${tradeOffRows(state)}</ul>
      <button class="toggle" type="button" data-action="details" role="switch" aria-checked="${app.detailsOpen}">
        <span class="toggle__track" aria-hidden="true"><span class="toggle__knob"></span></span>All details of both products
      </button>
      ${
        app.detailsOpen
          ? `<div class="versus">
              ${productFacts("You asked for", facts.substitute_for.name, facts.substitute_for, `<dt>Price</dt><dd>${esc(askedPrice)}</dd>`)}
              ${productFacts("Valio proposes", item.item.title, facts, extra)}
            </div>
            <p class="card__label card__label--gap">How sure ${ASSISTANT} is</p>
            <ul class="judges">${confidenceBars(approval)}</ul>`
          : ""
      }`;
  } else {
    // No substitute: the reasons the harness gave for asking the chef.
    body = `<ul class="reasons">${approval.reasons.map((reason) => `<li>${esc(checkLine(reason).label)}</li>`).join("")}</ul>`;
  }
  return `<section class="card card--human card--sign${arriving(4)}">
      <p class="card__label">Your signature is needed</p>
      <p class="sign__deadline">${icon("wait")}Sign before <b>${esc(clock(approval.deadline))}</b>, Valio's order cut-off.</p>
      ${body}
      <button class="btn btn--go btn--wide" type="button" data-action="approve" ${app.busy ? "disabled" : ""}>
        ${icon("pen")}Approve and sign · ${esc(money(approval.total_minor, approval.currency))}
      </button>
    </section>`;
}

function receiptCard(state) {
  const order = state.order;
  const payment = state.steps.find((step) => step.key === "sandbox_payment");
  const receipt = state.steps.find((step) => step.key === "signed_receipt");
  return `<section class="card card--done${arriving(7)}">
      <p class="card__label">Receipt signed by Valio Aimo</p>
      <p class="card__lead">${icon("check")}Order ${esc(order.order_id)} accepted</p>
      <dl class="facts">
        <dt>Total</dt><dd>${esc(money(order.total_minor, order.currency))} before tax</dd>
        <dt>Delivery</dt><dd>${esc(dayLong(order.delivery_date))}</dd>
        <dt>Signed by</dt><dd>${esc(order.signed_by === "human" ? "you, on this page" : "your assistant, inside your limits")}</dd>
        <dt>Payment</dt><dd>${esc(payment?.detail ?? "unknown")}</dd>
        <dt>Receipt</dt><dd class="mono">${esc(shortProof(receipt?.proof) ?? "unknown")}</dd>
      </dl>
    </section>`;
}

function attacksCard(state) {
  const items = state.attacks
    .map((attack) => {
      // "accepted" would mean Valio let a bad mandate through: it is shown as a failure.
      const refused = attack.status === "refused";
      const label = { refused: "Refused by Valio", accepted: "ACCEPTED: this must not happen", pending: "Not sent yet" }[attack.status] ?? attack.status;
      const problems = attack.problems.map((problem) => `<li>${esc(problem)}</li>`).join("");
      return `<li class="attack attack--${esc(attack.status)}">
          <p class="attack__title">${refused ? icon("cross") : icon("wait")}${esc(lexicon(attack.title))}</p>
          <p class="attack__status">${esc(label)}</p>
          ${problems ? `<details class="attack__more"><summary>What Valio answered</summary><ul class="attack__problems">${problems}</ul></details>` : ""}
        </li>`;
    })
    .join("");
  return `<section class="card card--deny${arriving(5)}">
      <p class="card__label">Orders signed without you, sent straight to Valio</p>
      <ul class="attacks">${items}</ul>
    </section>`;
}

/* ---------- Drawing: what was recorded (both audit logs) ---------- */

const RECORD_WHO = { agent: "Your assistant", harness: "Safety checks", human: "You", merchant: "Valio Aimo" };
const timeOfDay = (isoTime) =>
  new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "Europe/Helsinki" }).format(new Date(isoTime));

/* One log as its owner wrote it: when, who, what and why, and the start of the line's hash. */
function recordLog(title, events, empty) {
  const lines = events
    .map((event) => {
      const why = event.why ? `<span class="record__why">${esc(lexicon(event.why))}</span>` : "";
      const chain = `Line ${event.seq}. Hash of this line: ${event.hash}. Hash of the line before: ${event.prev_hash ?? "none, it is the first line"}.`;
      const hash = event.hash ? `<span class="record__hash mono" title="${esc(chain)}">${esc(shortProof(event.hash))}</span>` : "";
      return `<li class="record__line${event.action === "order_refused" ? " record__line--refused" : ""}">
          <span class="record__time">${esc(timeOfDay(event.at))}</span>
          <span class="record__who">${esc(RECORD_WHO[event.actor] ?? words(event.actor))}</span>
          <span class="record__what">${esc(lexicon(event.what))}${why}</span>
          ${hash}
        </li>`;
    })
    .join("");
  return `<div class="record__log">
      <p class="card__label">${esc(title)} · ${events.length} ${events.length === 1 ? "line" : "lines"}</p>
      ${events.length ? `<ol class="record__lines">${lines}</ol>` : `<p class="record__empty">${esc(empty)}</p>`}
    </div>`;
}

/*
 * Both audit logs for the order on screen, side by side: the kitchen's own (kept by the safety checks) and Valio Aimo's.
 * The page shows the lines the demo state carries, as they were written. It does not check the chains itself.
 */
function recordPanel(state) {
  const buyer = state.audit?.buyer ?? [];
  const merchant = state.audit?.merchant ?? [];
  if (!buyer.length && !merchant.length) return "";
  // An order sent straight to Valio never reached the safety checks, so the kitchen's log has no line of it.
  const noBuyerLine = state.scenario?.id === "attack" ? "No line. This order was sent straight to Valio Aimo and never reached your safety checks." : "No line for this order.";
  const logs = app.recordOpen
    ? `<p class="record__note">Each side keeps its own log. Every line carries the hash of the line before it: change or remove a line and the hashes after it no longer match.</p>
      <div class="record__logs">
        ${recordLog("Your kitchen's log", buyer, noBuyerLine)}
        ${recordLog("Valio Aimo's log", merchant, "No line for this order.")}
      </div>`
    : "";
  return `<section class="record" aria-label="What was recorded">
      <button class="toggle" type="button" data-action="record" role="switch" aria-checked="${app.recordOpen}">
        <span class="toggle__track" aria-hidden="true"><span class="toggle__knob"></span></span>What was recorded: your log and Valio Aimo's log
      </button>
      ${logs}
    </section>`;
}

function orderView() {
  const state = app.state;
  if (!orderOnScreen() || app.shown < 2 || !state.quote) {
    const waiting = (hasRun() && !dirty()) || app.busy ? '<p class="working">Your assistant is asking Valio Aimo for a signed quote…</p>' : "";
    return `<div class="order"><div class="order__main">${requestTable()}${waiting}</div><div class="order__side">${waiting ? "" : ecoCard()}</div></div>`;
  }
  const pending = state.approval?.status === "pending";
  const side = [
    state.approval && pending && app.shown >= 4 ? approvalCard(state) : "",
    state.order && app.shown >= 7 ? receiptCard(state) : "",
    state.verdict && app.shown >= 3 ? checksCard(state) : "",
    state.attacks?.length && app.shown >= 5 ? attacksCard(state) : "",
    state.approval && !pending && app.shown >= 4 ? approvalCard(state) : "",
  ].join("");
  // The logs come once every step that happened is lit, so they never tell the end before the trail does.
  const record = app.shown >= reachable() ? recordPanel(state) : "";
  return `<div class="order"><div class="order__main">${quoteTable(state)}</div><div class="order__side">${side}</div></div>${record}`;
}

function drawMain() {
  const problem = app.problem ? `<p class="problem" role="alert"><strong>Something did not answer.</strong> ${esc(app.problem)}</p>` : "";
  const view = app.step === 3 ? orderView() : app.step === 2 ? stockView() : recipesView();
  setHtml(el("main"), problem + view);
}

/* ---------- Drawing: the side column ---------- */

/* The week's menu only goes with the recipes: on the stock and the order it would take room for nothing. */
function drawMenu() {
  const node = el("menu");
  node.hidden = app.step !== 1;
  const menu = app.state?.kitchen?.menu ?? [];
  const items = menu
    .map((item) => {
      const cut = item.dish.indexOf(",");
      return `<li><span class="menu__course">${esc(item.course)}</span>${esc(cut === -1 ? item.dish : item.dish.slice(0, cut))}</li>`;
    })
    .join("");
  setHtml(node, `<h2 class="side__title display">This week's menu</h2><ul class="menu__list">${items}</ul>`);
}

function drawTalk() {
  const lines = [...app.talk];
  if (revealing() || app.chatBusy) lines.push({ typing: true });
  const bubbles = lines
    .map((line) => {
      if (line.typing) return '<li class="say say--agent"><span class="say__dots" aria-label="working"><i></i><i></i><i></i></span></li>';
      const speaker = line.speaker ?? (line.who === "chef" ? "Chef" : ASSISTANT);
      const proof = line.proof ? `<span class="say__proof mono" title="${esc(line.proof)}">${esc(shortProof(line.proof))}</span>` : "";
      const changes = (line.changes ?? []).map((change) => `<span class="say__change">${icon("pen")}${esc(change)}</span>`).join("");
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

  setHtml(el("agent-title"), `${icon("spark")}${ASSISTANT}<span class="dot dot--${app.up.assistant ? "on" : "off"}" title="${app.up.assistant ? "Online" : "Offline"}"></span>`);
  el("ask-text").disabled = !app.up.assistant || app.chatBusy;
  el("ask-send").disabled = !app.up.assistant || app.chatBusy;
  setHtml(el("ask-send"), icon("send"));
  setHtml(el("ask-note"), app.up.assistant ? "It can change the stock table and take a greener product Valio offers. It never signs: you do, with the buttons." : `${ASSISTANT} is offline. You can still change the table by hand.`);
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
      ${light(app.up.assistant, "assistant", "live", "not started", "uv run uvicorn surface.assistant:app --port 8004")}
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
  drawTalk();
  drawDemo();
  // The lines to order changed: ask Valio for their footprint. Once per set of lines, never twice at once.
  if (app.kitchen.stock && app.eco.key !== ecoKey() && !app.eco.loading) refreshEco();
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
function openDialog({ title, body, confirm, tone = "go", onConfirm }) {
  const node = el("dialog");
  dialogConfirm = onConfirm;
  node.innerHTML = `<form class="dialog__box" method="dialog" id="dialog-form">
      <h2 class="dialog__title display" id="dialog-title">${esc(title)}</h2>
      <div class="dialog__body">${body}</div>
      <p class="dialog__error" id="dialog-error" role="alert" hidden></p>
      <div class="dialog__actions">
        <button class="btn btn--quiet" type="button" data-dialog="cancel">Cancel</button>
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
  app.detailsOpen = false;
  app.talk = [];
  app.eco.dismissed = new Set();
  app.prospect = null;
  app.prospectQty = {};
  app.prospectAdded = new Set();
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
  for (const name of [REPLAY_FILE["normal-order"], REPLAY_FILE.substitution, "normal-order.greener"]) {
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
  app.detailsOpen = false;
  app.mismatch = false;
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
  say("agent", "The quantities of the refused order are in the table. Correct them, confirm the stock, and I ask Valio for a new quote.");
  draw();
}

/* Valio's footprint estimate and greener alternatives, for the chat: it may only offer a swap listed here. */
function ecoFacts() {
  const data = ecoNow();
  const swapped = swappedLines().map((line) => `${line.swapped_from.name} → ${line.name}`);
  if (!data) return { estimate: "not known for these lines yet", alternatives: [], swapped };
  return {
    estimated_total_kg_co2e: data.total_kg_co2e,
    method: data.method,
    lines_without_data: data.unknown,
    lines: data.lines.map((line) => ({ product_id: line.product_id, name: line.name, kg_co2e: line.kg_co2e })),
    alternatives: data.alternatives.map((offer) => ({
      product_id: offer.product_id,
      name: offer.name,
      alternative_id: offer.alternative.id,
      alternative_name: offer.alternative.name,
      kg_co2e_before: offer.kg_co2e_before,
      kg_co2e_after: offer.kg_co2e_after,
      saving_kg_co2e: offer.saving_kg_co2e,
      saving_percent: Math.round(offer.saving_share * 100),
      why: offer.why,
      alternative_allergens: allergenText(offer.alternative.allergens),
    })),
    swapped,
    checked_every_days: data.review_every_days,
  };
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
    eco: ecoFacts(),
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
      signature: state.approval && {
        status: state.approval.status,
        sign_before: clock(state.approval.deadline),
        // What the card shows about the substitute, so the chat can explain the trade-off in the page's own words.
        what_changes_with_the_substitute: state.approval.status === "pending" ? tradeOffs(state).map((row) => `${row.label}: ${row.text}`) : [],
      },
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
    const answer = await assistant.chat(turns, pageFacts());
    // The page applies the changes itself and shows what really changed, whatever the reply says.
    const applied = (answer.stock_changes ?? []).map((change) => setStock(change.product_id, change.field, change.amount, ASSISTANT)).filter(Boolean);
    const swaps = (answer.swaps ?? []).map((swap) => swapLine(swap.product_id, swap.swap_to, ASSISTANT)).filter(Boolean);
    say("agent", answer.reply, { changes: [...applied.map(changeText), ...swaps.map(swapText)] });
    if (swaps.length) toast(`Greener swap: ${kgCo2(swaps.reduce((sum, swap) => sum + swap.offer.saving_kg_co2e, 0))} less`);
    else if (applied.length) toast(`${applied.length} ${applied.length === 1 ? "line" : "lines"} changed in the stock table`);
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
      }
    } catch {
      /* the next look may work */
    }
    watch();
  }, POLL_MS);
}

/*
 * Are the services there? The page looks again every few seconds, so a service started after the page shows up
 * without a reload. (Before, the page looked once when it loaded: a harness started later stayed "not reached".)
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
  app.up.driver = Boolean(state && Array.isArray(state.steps));
  // The driver arrived while nothing was running: from now on the page is live.
  if (app.up.driver && app.mode === "replay" && !hasRun() && !app.busy) {
    app.mode = "live";
    app.state = state;
  }
  draw();
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

  // The chef can always go back to the recipes and the stock, also once an order was sent.
  const stepButton = event.target.closest("[data-step]");
  if (stepButton) {
    app.step = Number(stepButton.dataset.step);
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

  // The greener check: the button on a line, the weekly card, and the undo of a swap.
  const ecoButton = event.target.closest("[data-eco]");
  if (ecoButton) {
    askSwap(ecoButton.dataset.eco);
    return;
  }
  const ecoSwap = event.target.closest("[data-eco-swap]");
  if (ecoSwap) {
    applySwap(ecoSwap.dataset.ecoSwap, "you");
    return;
  }
  const ecoDismiss = event.target.closest("[data-eco-dismiss]");
  if (ecoDismiss) {
    app.eco.dismissed.add(ecoDismiss.dataset.ecoDismiss);
    say("agent", "Noted: I will not offer it again before next week's check.");
    draw();
    return;
  }
  const unswapButton = event.target.closest("[data-unswap]");
  if (unswapButton) {
    const line = app.lines.find((entry) => entry.product_id === unswapButton.dataset.unswap);
    if (line && canEdit()) {
      unswap(line);
      toast("Back to the original product");
      draw();
    }
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
  } else if (action === "record") {
    app.recordOpen = !app.recordOpen;
    drawMain();
  } else if (action === "correct") {
    correctQuantities();
  } else if (action === "use-need") {
    useNeed();
    draw();
  } else if (action === "undo") {
    undoChanges();
    draw();
  } else if (action === "toggle-spotlight") {
    app.spotlightOpen = !app.spotlightOpen;
    drawMain();
    if (app.spotlightOpen && !app.recommendation && !app.recBusy) {
      fetchRecommendation();
    }
  } else if (action === "toggle-prospect") {
    app.prospectOpen = !app.prospectOpen;
    drawMain();
    const customer = activeCustomer();
    if (app.prospectOpen && (!app.prospect || app.prospect.customer !== customer) && !app.prospectBusy) {
      fetchProspect(customer);
    }
  } else if (action === "add-prospect") {
    const pid = event.target.closest("[data-product-id]")?.dataset.productId;
    if (pid) addProspectItem(pid);
  } else if (action === "toggle-chat") {
    app.chatOpen = !app.chatOpen;
    el("side")?.classList.toggle("is-open", app.chatOpen);
    el("chat-launcher")?.setAttribute("aria-expanded", String(app.chatOpen));
    if (app.chatOpen) setTimeout(() => el("ask-text")?.focus(), 0);
  } else if (action === "select-trend") {
    const tid = event.target.closest("[data-trend-id]")?.dataset.trendId;
    if (tid && tid !== app.trendId) {
      app.trendId = tid;
      app.recommendation = null;
      app.recAdded = false;
      fetchRecommendation();
    }
  } else if (action === "add-recommended") {
    addRecommendedDish();
  } else if (action === "reset") {
    chooseScenario(app.scenarioId === "attack" ? "normal-order" : app.scenarioId);
  }
});

async function fetchProspect(customer) {
  if (app.prospectBusy) return;
  app.prospectBusy = true;
  drawMain();
  try {
    app.prospect = await gateway.prospect(customer);
  } catch (error) {
    app.prospect = null;
    toast(`Could not load prospect: ${error.message}`, true);
  } finally {
    app.prospectBusy = false;
    drawMain();
  }
}

function parsePositiveQty(raw, max) {
  const typed = String(raw ?? "").trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(typed)) return null;
  const num = Number(typed);
  if (!(num > 0)) return null;
  return round3(Math.min(num, max));
}

function addProspectItem(productId) {
  const item = (app.prospect?.items ?? []).find((entry) => entry.product.id === productId);
  if (!item || !canEdit() || app.prospectAdded.has(productId)) return;
  const inputEl = document.querySelector(`[data-prospect-qty="${CSS.escape(productId)}"]`);
  const parsed = parsePositiveQty(inputEl?.value ?? app.prospectQty[productId], item.available_base_quantity);
  if (inputEl && parsed === null) {
    toast("Please enter a positive quantity.", true);
    inputEl.focus();
    return;
  }
  const addQty = parsed ?? defaultProspectQty(item);
  app.prospectQty[productId] = addQty;
  const existing = app.lines.find((line) => line.product_id === productId);
  if (existing) {
    existing.need = round3(existing.need + addQty);
    existing.to_order = neededNow(existing);
    existing.claim_promo = true;
    existing.by.to_order = "you";
    if (!existing.dishes.includes("Today's Deal")) existing.dishes.push("Today's Deal");
  } else {
    app.lines.push({
      product_id: productId,
      name: item.product.name,
      dishes: ["Today's Deal"],
      unit: item.base_unit,
      need: addQty,
      in_stock: 0,
      counted: 0,
      to_order: addQty,
      claim_promo: true,
      by: { to_order: "you" },
    });
  }
  app.prospectAdded.add(productId);
  if (app.confirmed.stock && !orderOnScreen()) app.confirmed.stock = null;
  say("chef", `Add ${qty(addQty, item.base_unit)} of ${item.product.name} (-${item.discount_pct}% deal).`);
  say("agent", `Added ${item.product.name} (${item.shelf_life_days}d shelf life) at ${money(item.promo_price_minor)} (${item.discount_pct}% off your contract price).`);
  toast(`Added ${item.product.name} (-${item.discount_pct}%)`);
  draw();
}

async function fetchRecommendation() {
  if (app.recBusy) return;
  app.recBusy = true;
  app.recAdded = false;
  drawMain();
  try {
    const existing = (app.kitchen.recipes?.recipes ?? []).map((r) => r.name);
    const data = await assistant.recommend({
      trend_id: app.trendId,
      portions: Math.max(1, Number(app.recPortions) || 50),
      existing_recipes: existing,
    });
    app.recommendation = data;
    toast(`Recipe ready (${data.source === "live_llm" ? "Gemini" : "cached"})`);
  } catch (error) {
    toast(`Could not load recommendation: ${error.message}`, true);
  } finally {
    app.recBusy = false;
    drawMain();
  }
}

function addRecommendedDish() {
  const rec = app.recommendation?.recipe;
  if (!rec || !canEdit() || app.recAdded) return;
  const portions = Math.max(1, Number(app.recPortions) || 50);
  const recipes = app.kitchen.recipes?.recipes ?? [];
  const newId = `trend-${app.trendId || "spotlight"}-${recipes.length + 1}`;
  recipes.push({
    id: newId,
    course: rec.course,
    name: rec.name,
    with: rec.with_text,
    ingredients: (rec.ingredients ?? []).map((ing) => ({
      product_id: ing.product_id,
      name: ing.name,
      per_service: `${round3(Number(ing.amount_per_portion) * portions)} ${ing.unit.toLowerCase()} (${portions} portions)`,
    })),
  });
  for (const ing of rec.ingredients ?? []) {
    const addNeed = round3(Number(ing.amount_per_portion) * portions);
    const existing = app.lines.find((line) => line.product_id === ing.product_id);
    if (existing) {
      existing.need = round3(existing.need + addNeed);
      existing.to_order = neededNow(existing);
      existing.by.to_order = "you";
      if (!existing.dishes.includes(rec.course)) existing.dishes.push(rec.course);
    } else {
      app.lines.push({
        product_id: ing.product_id,
        name: ing.name,
        dishes: [rec.course],
        unit: ing.unit,
        need: addNeed,
        in_stock: 0,
        counted: 0,
        to_order: addNeed,
        by: { to_order: "you" },
      });
    }
  }
  app.recipeId = newId;
  app.recAdded = true;
  if (app.confirmed.recipes) app.confirmed.recipes = null;
  if (app.confirmed.stock && !orderOnScreen()) app.confirmed.stock = null;
  say("chef", `Add "${rec.name}" for ${portions} portions.`);
  say("agent", `Added "${rec.name}" and scaled ${rec.ingredients.length} Valio ingredients for ${portions} portions into your stock ledger.`);
  toast(`Added "${rec.name}" (${portions} portions)`);
  draw();
}

document.addEventListener("input", (event) => {
  const qtyInput = event.target.closest("[data-prospect-qty]");
  if (!qtyInput) return;
  const pid = qtyInput.dataset.prospectQty;
  const item = (app.prospect?.items ?? []).find((entry) => entry.product.id === pid);
  if (!item) return;
  const parsed = parsePositiveQty(qtyInput.value, item.available_base_quantity);
  if (parsed !== null) app.prospectQty[pid] = parsed;
});

/* A number typed in the stock table. The field that has the focus keeps it when the table is drawn again. */
document.addEventListener("change", (event) => {
  if (event.target.id === "rec-portions") {
    const val = Math.max(1, Math.min(2000, Math.round(Number(event.target.value) || 50)));
    app.recPortions = val;
    drawMain();
    return;
  }
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

    const [recipes, bookings, stock, policy, trendsData] = await Promise.all([
      kitchenApi.recipes(),
      kitchenApi.bookings(),
      kitchenApi.stock(app.state.scenario.id ?? app.scenarioId),
      harness.policy().catch(() => null),
      kitchenApi.trends().catch(() => ({ trends: [] })),
    ]);
    app.kitchen = { recipes, bookings, stock };
    app.trends = trendsData?.trends ?? [];
    app.trendId = app.trends[0]?.id ?? null;
    app.recPortions = recipes?.covers_per_service ?? 50;
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
