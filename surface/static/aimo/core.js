/*
 * The clean portal: what every screen shares. Where the data comes from, the words, the small helpers.
 *
 * Same rule as the first page (portal.js): the page draws what it is given and never works out a fact of Valio's.
 * Prices, Valio's stock, totals, verdicts and signatures come from the demo state. The only arithmetic here is the
 * kitchen's own: to order = need - in stock.
 *
 * Sources:
 * - the demo driver   GET /state, POST /scenarios/{id}/run, POST /reset, POST /footprint
 * - the harness       GET /policy, PUT /policy, GET /approvals, GET /authorizations, GET /audit, POST /approvals/{id}/decision
 * - the gateway       GET /audit, GET /orders/{id}
 * - the assistant     GET /health, POST /chat
 * - the kitchen       ../kitchen/*.json (synthetic, stands in for the restaurant's own system)
 * When the demo driver does not answer, the page replays the runs recorded in contract/examples/.
 */

const query = new URLSearchParams(window.location.search);
/*
 * Where the services are. On a laptop each one has its own port. Hosted, one address serves everything: the page,
 * and each service under its name (the reverse proxy cuts the prefix off). ?driver=, ?harness=, ?assistant= and
 * ?merchant= win over both. The gateway is not published when hosted: the page then shows Valio's log lines
 * that came with the order on screen.
 */
const ON_LAPTOP = ["localhost", "127.0.0.1", ""].includes(window.location.hostname);
const base = (name, port) => (query.get(name) || (ON_LAPTOP ? `http://localhost:${port}` : `/${name}`)).replace(/\/$/, "");

export const URLS = {
  driver: base("driver", 8003),
  harness: base("harness", 8002),
  assistant: base("assistant", 8004),
  merchant: base("merchant", 8001),
};
export const QUERY = query;
export const ASSISTANT = "Aimo";
export const REVEAL_MS = 520; // time between two lines of the assistant's work: seven steps take under four seconds
export const POLL_MS = 1000;
export const SERVICES_MS = 5000;

const EXAMPLES = "/contract/examples/";
const KITCHEN = "../kitchen/";
const REPLAY_FILE = { "normal-order": "normal-order", substitution: "substitution.pending", attack: "attack" };
const STOCK_FILE = { "normal-order": "normal-order", substitution: "substitution", attack: "normal-order" };

/* ---------- Words ---------- */

export const UNIT_WORDS = { ST: ["pc", "pcs"], KG: ["kg", "kg"], L: ["l", "l"], PAK: ["pack", "packs"], BAG: ["bag", "bags"] };
export const ALLERGEN_WORDS = { AM: "milk", AW: "gluten", GO: "oats", NR: "rye", AF: "fish", AS: "sesame", ML: "lactose", AP: "peanuts", AN: "tree nuts", AE: "eggs", AY: "soy", AC: "crustaceans", BM: "mustard", BC: "celery" };
export const SHORTFALL_WORDS = { late_delivery: "its order cut-off has passed", out_of_stock: "Valio cannot deliver it", not_found: "Valio has no price for it" };
export const JUDGE_WORDS = { within_preferences: "Fits your kitchen's preferences", same_use: "Works the same way in the dish" };
export const WHO = { manager: "You", agent: ASSISTANT, merchant: "Valio", none: "Checks", human: "You", harness: "Checks" };

/* The seven steps of the AP2 trail. `term` is the protocol's word, shown small for the people who know it. */
export const STEP_TERMS = {
  open_mandate: "Open mandate",
  signed_quote: "Signed quote",
  verdict: "Verdict",
  closed_mandates: "Closed mandates",
  merchant_verifies: "Valio verifies",
  sandbox_payment: "Sandbox payment",
  signed_receipt: "Signed receipt",
};

/* One plain sentence for each rule of the harness (harness/rules.py), by outcome. A test checks none is missing. */
export const CHECK_WORDS = {
  "quote-signature": {
    name: "Prices signed by Valio",
    pass: "The prices really come from Valio Aimo",
    human: "We could not confirm the prices come from Valio Aimo",
    deny: "The prices were changed after Valio signed them",
  },
  "quote-not-expired": {
    name: "Prices still valid",
    pass: "The prices are still valid",
    human: "The prices are about to expire",
    deny: "The prices have expired",
    value: (e) => (e.expires_at ? `until ${clock(e.expires_at)}` : ""),
  },
  "merchant-allowed": {
    name: "Allowed supplier",
    pass: "Valio Aimo is a supplier you allow",
    human: "This supplier is not on your list",
    deny: "This supplier is not on your list",
  },
  "allergen-not-blocked": {
    name: "Banned allergens",
    pass: "None of the allergens you ban",
    human: "An allergen you ban may be in the order",
    deny: "The order contains an allergen you ban",
    value: (e) => (e.blocked?.length ? `you ban ${allergenNames(e.blocked)}` : ""),
  },
  "allergen-data-known": {
    name: "Allergen information",
    pass: "Allergen information is complete for every product",
    human: "Allergen information is missing for a product",
    deny: "Allergen information is missing for a product",
  },
  "allergen-unchanged-on-substitution": {
    name: "Substitute's allergens",
    pass: "The substitute has the same allergens",
    human: "The substitute does not have the same allergens",
    deny: "The substitute does not have the same allergens",
    value: (e) => (e.contains?.length ? `contains ${allergenNames(e.contains)}` : ""),
  },
  "delivery-on-time": {
    name: "Delivery date",
    pass: "It arrives in time for your service",
    human: "It arrives later than you asked",
    deny: "It arrives too late for your service",
    value: (e) => (e.promised && e.requested ? `arrives ${dayLong(e.promised)}, needed ${dayLong(e.requested)}` : ""),
  },
  "spend-limit": {
    name: "Spending limit",
    pass: "The total is within your spending limit",
    human: "The total is above your spending limit",
    deny: "The total is above your spending limit",
    value: (e) => (Number.isFinite(e.total_minor) && Number.isFinite(e.limit_minor) ? `${money(e.total_minor)} of ${money(e.limit_minor)}` : ""),
  },
  "substitution-within-preferences": {
    name: "Substitute fits your kitchen",
    pass: "The substitute fits your kitchen's preferences",
    human: "Not sure enough that the substitute fits your kitchen",
    deny: "The substitute does not fit your kitchen's preferences",
  },
  "shelf-life-window": {
    name: "Shelf-life window",
    pass: "Discounted lot shelf life fits your service window",
    human: "Short shelf life on a discounted item: check if you can use it in time",
    deny: "Shelf life is too short for delivery",
  },
};
export const OUTCOME_WORDS = { pass: "OK", human: "You decide", deny: "Blocked" };

/* What each line of the audit logs is, in a chef's words. An action that is not listed shows its own name. */
export const ACTION_WORDS = {
  authorization_requested: "Asked to order",
  quote_verified: "Quote checked",
  verdict: "Checks decided",
  mandate_signed: "Order signed",
  order_confirmed: "Order confirmed",
  approval_requested: "Asked for your signature",
  approval_decided: "You decided",
  approval_approved: "You signed",
  approval_rejected: "You rejected",
  approval_expired: "Signature not given in time",
  policy_changed: "Rules changed",
  policy_reset: "Rules reset",
  quote_issued: "Quote signed",
  quote_rejected: "Quote refused",
  mandate_verified: "Signature checked",
  payment_captured: "Payment booked (test)",
  order_accepted: "Order accepted",
  order_refused: "Order refused",
};

/* ---------- Small helpers ---------- */

export const el = (id) => document.getElementById(id);

/* Text from the data is only text: everything goes through esc() before it reaches the page. */
export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/* Only touch the page when something changed: a running animation, a focused field and typed text survive. */
export function setHtml(node, html) {
  if (!node || node.dataset.drawn === html) return;
  node.dataset.drawn = html;
  node.innerHTML = html;
}

export async function call(url, options = {}, timeoutMs = 4000) {
  const stop = new AbortController();
  const timer = setTimeout(() => stop.abort(), timeoutMs);
  try {
    const answer = await fetch(url, { ...options, signal: stop.signal });
    if (!answer.ok) {
      let body = await answer.text().catch(() => "");
      try {
        const detail = JSON.parse(body).detail; // our services explain a refusal in `detail`: a sentence, or a list of field errors
        if (typeof detail === "string") body = detail;
        else if (Array.isArray(detail)) body = detail.map((item) => `${(item.loc ?? []).slice(1).join(".")}: ${item.msg}`).join("; ");
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

export const round3 = (value) => Math.round(Number(value) * 1000) / 1000;
export const num = (value) => Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
export const unitWord = (unit, amount = 2) => (UNIT_WORDS[unit] ? UNIT_WORDS[unit][Number(amount) === 1 ? 0 : 1] : String(unit ?? "").toLowerCase());
export const qty = (amount, unit) => `${num(amount)} ${unitWord(unit, amount)}`.trim();

export function money(minor, currency = "EUR") {
  return `${currency} ${(minor / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function dayOf(isoDate, options) {
  const [y, m, d] = String(isoDate).slice(0, 10).split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", ...options }).format(new Date(Date.UTC(y, m - 1, d)));
}
export const dayShort = (isoDate) => dayOf(isoDate, { weekday: "short", day: "numeric" }); // Thu 19
export const dayLong = (isoDate) => dayOf(isoDate, { weekday: "short", day: "numeric", month: "short" }); // Thu 19 Nov

const HELSINKI = "Europe/Helsinki";
export function clock(isoTime) {
  if (!isoTime) return "";
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: HELSINKI }).format(new Date(isoTime));
}
export function timeOf(isoTime) {
  if (!isoTime) return "";
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: HELSINKI }).format(new Date(isoTime));
}
export function dateTime(isoTime) {
  if (!isoTime) return "";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: HELSINKI }).format(new Date(isoTime));
}

export const words = (code) => String(code ?? "").toLowerCase().replaceAll("_", " ");
export const shortProof = (proof, keep = 10) => (proof && proof.length > keep + 2 ? `${proof.slice(0, keep)}…` : proof ?? "");
export const titleCase = (text) => String(text ?? "").charAt(0).toUpperCase() + String(text ?? "").slice(1);
export const allergenNames = (codes) => codes.map((code) => ALLERGEN_WORDS[code] ?? code).join(", ");
export const plural = (count, one, many) => `${count} ${count === 1 ? one : many}`;

/*
 * The services write for the team ("the agent", "the judge", "the harness"). The chef reads one name: Aimo.
 * Only the words change, never a number or a fact.
 */
export function lexicon(text) {
  return String(text ?? "")
    .replace(/\b[Tt]he judge\b/g, ASSISTANT)
    .replace(/\b[Tt]he (buying )?agent's\b/g, `${ASSISTANT}'s`)
    .replace(/\b[Tt]he (buying )?agent\b/g, ASSISTANT)
    .replace(/\bThe harness\b/g, "The safety checks")
    .replace(/\bthe harness\b/g, "the safety checks")
    .replace(/\bThe (chef|manager)'s\b/g, "Your")
    .replace(/\bthe (chef|manager)'s\b/g, "your")
    .replace(/\bby the (chef|manager)\b/g, "by you")
    .replace(/\bthe (chef|manager)\b/g, "you");
}

/* "auto: all 7 rules pass" -> "All 7 rules pass": the code word in front is for the team. */
export const plainDetail = (detail) => titleCase(lexicon(String(detail ?? "").replace(/^(auto|human|deny):\s*/, "")));
export const firstSentence = (text) => {
  const match = String(text ?? "").match(/^.*?[.!?](?=\s|$)/);
  return match ? match[0] : String(text ?? "");
};

export function allergenText(allergens) {
  if (!allergens || allergens.data !== "complete") return "unknown";
  const list = allergens.contains ?? [];
  return list.length ? allergenNames(list) : "none declared";
}

/* Valio's stock claim, in words. Unknown is never shown as available. */
export function stockText(claim) {
  if (!claim || claim.value === null || claim.certainty === "unknown") return "unknown";
  if (claim.value === "not_given") return "available, count not given";
  return `${qty(claim.value, claim.unit)} counted`;
}

export const kgCo2 = (value) => `${Number(value).toLocaleString("en-GB", { maximumFractionDigits: 1 })} kg CO2e`;

const ICONS = {
  check: '<path d="M4 10.5l4 4 8-9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
  cross: '<path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
  wait: '<circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M10 6v4.5l3 1.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  skip: '<path d="M5 10h10" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
  dot: '<circle cx="10" cy="10" r="3" fill="currentColor"/>',
  spark: '<path d="M9 2l1.7 4.6 4.6 1.7-4.6 1.7L9 14.6 7.3 10 2.7 8.3l4.6-1.7z" fill="currentColor"/><path d="M15.5 12.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" fill="currentColor"/>',
  arrow: '<path d="M4 10h11M11 5l5 5-5 5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  pen: '<path d="M3 17l1-4L14 3l3 3L7 16z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M12 5l3 3" stroke="currentColor" stroke-width="1.7"/>',
  shield: '<path d="M10 2l6.5 2.4v4.8c0 4-2.7 7.3-6.5 8.800-3.800-1.500-6.500-4.800-6.500-8.800V4.400z" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linejoin="round"/><path d="M7 10l2.200 2.200L13.200 8" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linecap="round" stroke-linejoin="round"/>',
  leaf: '<path d="M4 16.5C3.5 8.5 8 3.5 17 3.5c.5 8.5-4 13-11.5 13" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linejoin="round"/><path d="M4 16.500l7.500-7.500" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linecap="round"/>',
  send: '<path d="M3 10l14-6.5-5 14-2.8-5.7z" fill="currentColor"/>',
  home: '<path d="M3 9.500L10 3.500l7 6V17h-4.500v-4.500h-5V17H3z" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linejoin="round"/>',
  box: '<path d="M3 6.500L10 3l7 3.500v7L10 17l-7-3.500z" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linejoin="round"/><path d="M3 6.500L10 10l7-3.500M10 10v7" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linejoin="round"/>',
  sliders: '<path d="M3 6h8M15 6h2M3 14h2M9 14h8" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linecap="round"/><circle cx="13" cy="6" r="2" fill="none" stroke="currentColor" stroke-width="1.700"/><circle cx="7" cy="14" r="2" fill="none" stroke="currentColor" stroke-width="1.700"/>',
  list: '<path d="M7 5.500h10M7 10h10M7 14.500h10" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linecap="round"/><circle cx="3.500" cy="5.500" r="1" fill="currentColor"/><circle cx="3.500" cy="10" r="1" fill="currentColor"/><circle cx="3.500" cy="14.500" r="1" fill="currentColor"/>',
  truck: '<path d="M2 5.500h9.500v8H2zM11.500 8.500h3.500l3 3v2h-6.500z" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linejoin="round"/><circle cx="6" cy="14.500" r="1.700" fill="#fff" stroke="currentColor" stroke-width="1.700"/><circle cx="14.500" cy="14.500" r="1.700" fill="#fff" stroke="currentColor" stroke-width="1.700"/>',
  down: '<path d="M10 3.500v9M6 9l4 4 4-4M4 16.500h12" fill="none" stroke="currentColor" stroke-width="1.800" stroke-linecap="round" stroke-linejoin="round"/>',
  close: '<path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" stroke-width="1.800" stroke-linecap="round"/>',
  chevron: '<path d="M7.500 4.500L13 10l-5.500 5.500" fill="none" stroke="currentColor" stroke-width="1.800" stroke-linecap="round" stroke-linejoin="round"/>',
  lock: '<rect x="4.500" y="9" width="11" height="8" rx="1.800" fill="none" stroke="currentColor" stroke-width="1.700"/><path d="M7 9V6.500a3 3 0 0 1 6 0V9" fill="none" stroke="currentColor" stroke-width="1.700"/>',
};
export const icon = (name, size = 18) =>
  `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 20 20" aria-hidden="true">${ICONS[name] ?? ICONS.dot}</svg>`;

/* ---------- Sources ---------- */

export const driver = {
  state: () => call(`${URLS.driver}/state`, {}, 1500),
  run: (id, body) => sendJson("POST", `${URLS.driver}/scenarios/${encodeURIComponent(id)}/run`, body ?? {}, 60000),
  reset: () => sendJson("POST", `${URLS.driver}/reset`, {}),
  footprint: (lines) => sendJson("POST", `${URLS.driver}/footprint`, { lines }, 8000),
};

/* The demo policy as a file, for when the harness is not running: the rules can be read, not changed. */
export const policyFile = () => call("/scenarios/policy.demo.json").catch(() => call(`${EXAMPLES}policy.demo.json`));

export const harness = {
  policy: () => call(`${URLS.harness}/policy`, {}, 1200),
  // The chef's rules live in the harness, where they are enforced. The page never keeps a rule of its own.
  changePolicy: (change) => sendJson("PUT", `${URLS.harness}/policy`, { ...change, decided_by: "chef" }, 8000),
  resetPolicy: () => sendJson("POST", `${URLS.harness}/policy/reset`, {}, 8000),
  decide: (approvalId, decision) =>
    sendJson("POST", `${URLS.harness}/approvals/${encodeURIComponent(approvalId)}/decision`, { decision, decided_by: "chef" }, 30000),
  approvals: () => call(`${URLS.harness}/approvals`, {}, 2500),
  authorizations: () => call(`${URLS.harness}/authorizations`, {}, 2500),
  verdict: (checkoutId) => call(`${URLS.harness}/verdicts/${encodeURIComponent(checkoutId)}`, {}, 2500),
  audit: () => call(`${URLS.harness}/audit`, {}, 2500),
  openMandate: () => call(`${URLS.harness}/mandates/open`, {}, 2500),
};

export const merchant = {
  audit: () => call(`${URLS.merchant}/audit`, {}, 2500),
  order: (orderId) => call(`${URLS.merchant}/orders/${encodeURIComponent(orderId)}`, {}, 2500),
  checkout: (checkoutId) => call(`${URLS.merchant}/checkouts/${encodeURIComponent(checkoutId)}`, {}, 2500),
};

export const assistant = {
  health: () => call(`${URLS.assistant}/health`, {}, 1200),
  chat: (turns, state) => sendJson("POST", `${URLS.assistant}/chat`, { turns, state }, 30000),
  // Spotlight: a dish for a food trend, made of products of Valio's catalog. Gemini writes it, or a kept answer.
  recommend: (payload) => sendJson("POST", `${URLS.assistant}/recommend`, payload, 25000),
};

export const recorded = (name) => call(`${EXAMPLES}demo-state.${name}.json`);
export const recordedFootprintFile = (name) => call(`${EXAMPLES}footprint.${name}.json`);
export const replayFile = (scenarioId) => REPLAY_FILE[scenarioId];

export const kitchenApi = {
  recipes: () => call(`${KITCHEN}recipes.json`),
  bookings: () => call(`${KITCHEN}bookings.json`),
  stock: (scenarioId) => call(`${KITCHEN}stock.${STOCK_FILE[scenarioId] ?? "normal-order"}.json`),
  history: () => call("history.sample.json"),
  trends: () => call(`${KITCHEN}trends.json`),
};

/* ---------- The audit chain, recomputed in the browser ---------- */

/* Python writes its canonical JSON with every non-ASCII character escaped: do the same, or the digest differs. */
function asciiJson(value) {
  return JSON.stringify(value).replace(/[\u007f-￿]/g, (char) => `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`);
}

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${asciiJson(key)}:${canonical(value[key])}`)
      .join(",")}}`;
  }
  return asciiJson(value);
}

/* The fingerprint of one audit line, as common/audit.py computes it: SHA-256 of its canonical JSON without `hash`. */
export async function digest(event) {
  const { hash: _hash, ...body } = event;
  const bytes = new TextEncoder().encode(canonical(body));
  const sum = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(sum)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/*
 * Check one log: every line's fingerprint is recomputed, and every line must point at the one before it.
 * Returns the lines that fail, by seq. A log cut at its start (the page holds only one order's lines) is not a break:
 * the first line on screen is only checked against itself.
 */
export async function verifyChain(events) {
  const broken = [];
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    const own = (await digest(event)) === event.hash;
    const previous = events[index - 1];
    const linked = !previous || previous.seq !== event.seq - 1 || event.prev_hash === previous.hash;
    if (!own || !linked) broken.push(event.seq);
  }
  return broken;
}

export function download(name, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}
