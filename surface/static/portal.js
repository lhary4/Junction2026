"use strict";

/*
 * The kitchen order page: the chef goes through the recipes, the stock, then lets the agent order.
 *
 * The page draws what it is given and never works out a fact of Valio's:
 * prices, Valio's stock, totals, verdicts and signatures all come from the demo state.
 *
 * Where the data comes from (see "Sources" below):
 * - the demo driver   GET /state, POST /scenarios/{id}/run, POST /reset      docs/contract.md, "The demo state"
 * - the harness       GET /policy, POST /approvals/{id}/decision              the chef's signature goes straight there
 * - the kitchen       kitchen/recipes.json, stock.<scenario>.json, bookings.json   synthetic, stands in for the restaurant's system
 *
 * When the demo driver does not answer, the page replays the runs recorded in contract/examples/ (real runs of 14/11).
 */

const query = new URLSearchParams(window.location.search);
const DRIVER_URL = (query.get("driver") || "http://localhost:8003").replace(/\/$/, "");
const HARNESS_URL = (query.get("harness") || "http://localhost:8002").replace(/\/$/, "");
const REVEAL_MS = 450; // time between two steps lighting up, so a viewer can follow
const POLL_MS = 1000;

// Which recorded run each scenario replays, and which stock count goes with it.
const REPLAY_FILE = { "normal-order": "normal-order", substitution: "substitution.pending", attack: "attack" };
const STOCK_FILE = { "normal-order": "normal-order", substitution: "substitution", attack: "normal-order" };

const UNIT_WORDS = { ST: ["pc", "pcs"], KG: ["kg", "kg"], L: ["l", "l"], PAK: ["pack", "packs"], BAG: ["bag", "bags"] };
const ALLERGEN_WORDS = { AM: "milk", AW: "gluten", GO: "oats", NR: "rye", AF: "fish", AS: "sesame", ML: "lactose", AP: "peanuts", AN: "tree nuts" };
const SIGNER_WORDS = { manager: "chef", agent: "agent", merchant: "Valio", none: "" };
const SPEAKER_WORDS = { manager: "Chef", agent: "Agent", merchant: "Valio Aimo", none: "Harness" };
const SHORTFALL_WORDS = { late_delivery: "its order cut-off has passed", out_of_stock: "Valio cannot deliver it", not_found: "Valio has no price for it" };
const JUDGE_WORDS = { within_preferences: "Within the kitchen's preferences", same_use: "Same use in the dish" };

const el = (id) => document.getElementById(id);

const app = {
  mode: "replay", // "live" when the demo driver answers
  harnessUp: false,
  scenarioId: query.get("scenario") === "substitution" ? "substitution" : "normal-order",
  step: 1, // 1 recipes, 2 stock, 3 order
  confirmed: { recipes: false, stock: false },
  recipeId: null,
  stockFilter: "all",
  state: null, // the demo state
  shown: 0, // how many of the seven steps are lit
  talk: [], // what the chef and the agent said before the order
  kitchen: { recipes: null, bookings: null, stock: null },
  policy: null,
  busy: false,
  problem: null,
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

async function call(url, options = {}, timeoutMs = 4000) {
  const stop = new AbortController();
  const timer = setTimeout(() => stop.abort(), timeoutMs);
  try {
    const answer = await fetch(url, { ...options, signal: stop.signal });
    if (!answer.ok) {
      const body = await answer.text().catch(() => "");
      throw new Error(`${answer.status} ${body.slice(0, 200)}`.trim());
    }
    return await answer.json();
  } finally {
    clearTimeout(timer);
  }
}

const postJson = (url, body, timeoutMs) =>
  call(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) }, timeoutMs);

function num(value) {
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function qty(amount, unit) {
  const words = UNIT_WORDS[unit];
  if (!words) return `${num(amount)} ${String(unit ?? "").toLowerCase()}`.trim();
  return `${num(amount)} ${Number(amount) === 1 ? words[0] : words[1]}`;
}

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

const words = (code) => String(code ?? "").toLowerCase().replaceAll("_", " ");
const shortProof = (proof) => (proof && proof.length > 14 ? `${proof.slice(0, 12)}…` : proof);
const titleCase = (text) => String(text ?? "").charAt(0).toUpperCase() + String(text ?? "").slice(1);

function allergenText(allergens) {
  if (!allergens || allergens.data !== "complete") return "unknown";
  const list = (allergens.contains ?? []).map((code) => ALLERGEN_WORDS[code] ?? code);
  return list.length ? list.join(", ") : "none declared";
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
  };
  return `<svg class="icon" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">${paths[name]}</svg>`;
}

/* ---------- Sources ---------- */

const driver = {
  state: () => call(`${DRIVER_URL}/state`, {}, 1500),
  run: (id) => postJson(`${DRIVER_URL}/scenarios/${encodeURIComponent(id)}/run`, {}, 60000),
  reset: () => postJson(`${DRIVER_URL}/reset`, {}),
};

const harness = {
  policy: () => call(`${HARNESS_URL}/policy`, {}, 1200),
  decide: (approvalId, decision) =>
    postJson(`${HARNESS_URL}/approvals/${encodeURIComponent(approvalId)}/decision`, { decision, decided_by: "chef" }, 30000),
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
const missingLines = () => (app.kitchen.stock?.lines ?? []).filter((line) => line.to_order > 0);

/* The steps that have happened are lit one after the other: this is how many may be lit. */
function reachable() {
  const steps = app.state?.steps ?? [];
  let last = 0;
  steps.forEach((step, index) => {
    if (step.status !== "pending") last = index + 1;
  });
  return hasRun() ? last : 0;
}

let revealTimer = null;
function reveal() {
  clearTimeout(revealTimer);
  if (app.shown >= reachable()) {
    draw();
    return;
  }
  app.shown += 1;
  draw();
  revealTimer = setTimeout(reveal, REVEAL_MS);
}

function say(who, text) {
  app.talk.push({ who, text });
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
  return `${missing} of ${stock.lines.length} ingredients are short for the ${stock.for_services} services, from the count of ${dayLong(stock.counted_at)}. Have a look at the fridge, then confirm.`;
}

function orderLine() {
  const missing = missingLines().length;
  const limit = app.policy && Number.isFinite(app.policy.autonomous_limit_minor)
    ? ` I may sign alone up to ${money(app.policy.autonomous_limit_minor, app.policy.currency)} an order. Above that, or if a product changes, you sign here.`
    : "";
  return `I will ask Valio Aimo for a signed quote for ${missing === 1 ? "this ingredient" : `these ${missing} ingredients`}.${limit}`;
}

/* ---------- Drawing: header ---------- */

function drawAccount() {
  const name = app.state?.kitchen?.name ?? "";
  el("account").innerHTML = `
    <button class="account__btn" id="account-btn" aria-haspopup="true" aria-expanded="false" aria-controls="account-menu">
      ${icon("user")}${esc(name)}
      <svg class="account__chevron" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M2 5l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
    <div class="account__menu" id="account-menu" hidden>
      <p class="account__who"><strong>${esc(name)}</strong>Customer ${esc(app.state?.kitchen?.customer)}</p>
      <button class="account__item" type="button">Kitchen preferences</button>
      <button class="account__item" type="button">Log out</button>
    </div>`;
}

function drawPlanning() {
  const services = app.kitchen.bookings?.services ?? [];
  if (!services.length) {
    el("planning").innerHTML = "";
    return;
  }
  const days = services
    .map(
      (service) => `<li class="day">
          <span class="day__date display">${esc(dayShort(service.date))}</span>
          <span class="day__covers"><b>${esc(service.booked)}</b> booked<br />${esc(service.planned)} planned</span>
        </li>`
    )
    .join("");
  el("planning").innerHTML = `
    <p class="needby"><span>Needed by</span><b class="display">${esc(dayLong(services[0].date))}</b></p>
    <ol class="days" aria-label="Covers per service, from bookings and planning">${days}</ol>
    <p class="planning__src">${esc(titleCase(services[0].meal))} services<br />from bookings and planning</p>`;
}

/* ---------- Drawing: the chef's steps and the button ---------- */

function drawFlow() {
  const recipes = app.kitchen.recipes?.recipes ?? [];
  const missing = missingLines().length;
  const items = [
    { n: 1, title: "Recipes", sub: `${recipes.length} on the menu`, done: app.confirmed.recipes, open: !hasRun() },
    { n: 2, title: "Stock", sub: `${missing} to order`, done: app.confirmed.stock, open: !hasRun() && app.confirmed.recipes },
    { n: 3, title: "Order", sub: "the agent, then the signatures", done: status() === "done", open: hasRun() || app.confirmed.stock },
  ];
  el("flow").innerHTML = items
    .map(
      (item) => `<li>
          <button class="flow__step${item.done ? " is-done" : ""}" type="button" data-step="${item.n}"
            ${app.step === item.n ? 'aria-current="step"' : ""} ${item.open ? "" : "disabled"}>
            <span class="flow__n">${item.done ? icon("check") : item.n}</span>
            <span class="flow__text"><b>${item.title}</b><span>${esc(item.sub)}</span></span>
          </button>
        </li>`
    )
    .join("");

  let cta = "";
  if (hasRun() || app.busy) {
    const now = app.busy || app.shown < reachable() ? "running" : status();
    const label = {
      running: "The agent is at work…",
      waiting_for_human: "Your signature is needed",
      done: "Order sent",
      refused: "No order was placed",
      idle: "The agent is at work…",
    }[now];
    const finished = now === "done" || now === "refused";
    cta = `<p class="cta__status cta__status--${esc(now)}">${now === "done" ? icon("check") : ""}${label}</p>
      ${finished ? '<button class="btn btn--quiet" type="button" data-action="reset">New order</button>' : ""}`;
  } else if (app.step === 1) {
    cta = `<button class="btn" type="button" data-action="confirm-recipes">Confirm recipes ${icon("arrow")}</button>`;
  } else if (app.step === 2) {
    cta = `<button class="btn" type="button" data-action="confirm-stock">Confirm stock ${icon("arrow")}</button>`;
  } else {
    cta = `<button class="btn btn--go" type="button" data-action="run">${icon("spark")} Agent order</button>`;
  }
  el("cta").innerHTML = cta;
}

/* ---------- Drawing: who signs ---------- */

function drawTrail() {
  const steps = app.state?.steps ?? [];
  const items = steps
    .map((step, index) => {
      const lit = index < app.shown;
      const state = lit ? step.status : "pending";
      const mark = { done: icon("check"), refused: icon("cross"), waiting: icon("wait"), skipped: icon("skip") }[state] ?? index + 1;
      const signer = lit && state !== "skipped" && SIGNER_WORDS[step.signer] ? `<span class="step__signer">${esc(SIGNER_WORDS[step.signer])}</span>` : "";
      return `<li class="step step--${esc(state)}" ${lit && step.detail ? `title="${esc(step.detail)}"` : ""}>
          <span class="step__dot" aria-hidden="true">${mark}</span>
          <span class="step__title">${esc(step.title)}${lit ? `<span class="visually-hidden">, ${esc(state)}</span>` : ""}</span>
          ${signer}
        </li>`;
    })
    .join("");
  el("trail").innerHTML = `<h2 class="trail__title display">Who signs</h2><ol class="steps">${items}</ol>`;
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
          <td><button class="pick__btn" type="button" data-recipe="${esc(recipe.id)}" aria-pressed="${recipe === chosen}">
              <b>${esc(recipe.name)}</b><span>${esc(recipe.with)}</span>
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
  return `<div class="head">
      <h2 class="display">Recipes on the menu</h2>
      <p class="head__meta">Written for ${esc(data?.covers_per_service)} covers a service. Choose a recipe to see what goes into it.</p>
    </div>
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

/* ---------- Drawing: step 2, stock ---------- */

function stockView() {
  const stock = app.kitchen.stock;
  const all = stock?.lines ?? [];
  const missing = missingLines();
  const shownLines = app.stockFilter === "missing" ? missing : [...missing, ...all.filter((line) => line.to_order <= 0)];
  const rows = shownLines
    .map((line) => {
      const short = line.to_order > 0;
      return `<tr class="${short ? "is-short" : "is-covered"}">
          <td>${esc(line.name)}</td>
          <td class="muted">${esc(line.dishes.join(", "))}</td>
          <td class="num">${esc(qty(line.need, line.unit))}</td>
          <td class="num">${esc(qty(line.in_stock, line.unit))}</td>
          <td class="num">${short ? `<b class="short">${esc(qty(line.to_order, line.unit))}</b>` : '<span class="covered">covered</span>'}</td>
        </tr>`;
    })
    .join("");
  const chip = (id, label, count) =>
    `<button class="chip" type="button" data-filter="${id}" aria-pressed="${app.stockFilter === id}">${label} <span>${count}</span></button>`;
  return `<div class="head">
      <h2 class="display">Stock check</h2>
      <p class="head__meta">Counted on ${esc(dayLong(stock.counted_at))}, ${esc(stock.counted_by)}. Need is for the ${esc(stock.for_services)} services.</p>
      <div class="chips">${chip("all", "All", all.length)}${chip("missing", "To order", missing.length)}</div>
    </div>
    <table class="tbl tbl--stock">
      <thead><tr><th>Ingredient</th><th>Used in</th><th class="num">Need</th><th class="num">In stock</th><th class="num">To order</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/* ---------- Drawing: step 3, the order ---------- */

function requestTable() {
  const rows = missingLines()
    .map(
      (line) => `<tr><td>${esc(line.name)}</td><td class="muted">${esc(line.dishes.join(", "))}</td><td class="num"><b>${esc(qty(line.to_order, line.unit))}</b></td></tr>`
    )
    .join("");
  return `<div class="head">
      <h2 class="display">Ready to order</h2>
      <p class="head__meta">What the agent will ask Valio Aimo for. Prices and Valio's stock come with the signed quote.</p>
    </div>
    <table class="tbl">
      <thead><tr><th>Ingredient</th><th>Used in</th><th class="num">To order</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function quoteTable(state) {
  const quote = state.quote;
  const total = quote.totals.find((item) => item.type === "total");
  const rows = quote.line_items
    .map((item) => {
      const facts = quote.aimo.lines[item.id] ?? {};
      const lineTotal = item.totals.find((entry) => entry.type === "total");
      const replaces = facts.substitute_for ? `<span class="tag tag--warn">Substitute</span> <span class="muted">for ${esc(facts.substitute_for.name)}</span>` : "";
      return `<tr>
          <td><b>${esc(item.item.title)}</b>${replaces ? `<br />${replaces}` : ""}</td>
          <td class="num">${esc(qty(item.quantity, facts.sales_unit))}</td>
          <td class="num">${esc(money(item.item.price, quote.currency))}</td>
          <td class="num"><b>${esc(money(lineTotal.amount, quote.currency))}</b></td>
          <td>${esc(stockText(facts.stock))}</td>
        </tr>`;
    })
    .join("");
  return `<div class="head">
      <h2 class="display">Quote signed by Valio Aimo</h2>
      <p class="head__meta">Delivery ${esc(dayLong(quote.aimo.delivery_date))}, valid until ${esc(clock(quote.expires_at))}. Prices before tax.</p>
    </div>
    <table class="tbl tbl--quote">
      <thead><tr><th>Product</th><th class="num">Quantity</th><th class="num">Unit price</th><th class="num">Total</th><th>Valio's stock</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="3">Total before tax</td><td class="num"><b>${esc(money(total.amount, quote.currency))}</b></td><td></td></tr></tfoot>
    </table>`;
}

function verdictCard(state) {
  const verdict = state.verdict;
  const sentence = state.steps[2]?.detail ?? "";
  const rules = verdict.rules
    .map((rule) => `<li class="rule rule--${esc(rule.outcome)}">${rule.outcome === "pass" ? icon("check") : icon("wait")}${esc(rule.message)}</li>`)
    .join("");
  return `<section class="card card--${esc(verdict.decision)}">
      <p class="card__label">Verdict</p>
      <p class="card__lead"><span class="badge badge--${esc(verdict.decision)}">${esc(verdict.decision)}</span>${esc(sentence.replace(/^\w+:\s*/, ""))}</p>
      <details class="rules"><summary>The ${verdict.rules.length} rules</summary><ul>${rules}</ul></details>
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
        <dt>Contains</dt><dd>${esc(allergenText(facts.allergens))}</dd>
        <dt>Claims</dt><dd>${esc(claims)}</dd>
        <dt>Labels</dt><dd>${esc(labels)}</dd>
        ${extra}
      </dl>
    </div>`;
}

function approvalCard(state) {
  const approval = state.approval;
  const quote = state.quote;
  const item = quote.line_items.find((entry) => quote.aimo.lines[entry.id]?.substitute_for);
  let versus = "";
  if (item) {
    const facts = quote.aimo.lines[item.id];
    const shortfall = (quote.aimo.shortfalls ?? []).find((entry) => entry.product_id === facts.substitute_for.product_id);
    const why = shortfall ? `Valio cannot deliver the product asked for: ${SHORTFALL_WORDS[shortfall.reason] ?? shortfall.reason}.` : "";
    const candidates = (quote.aimo.alternatives ?? []).length;
    const extra = `<dt>Price</dt><dd>${esc(money(facts.comparison_price_minor, quote.currency))} a ${esc(String(facts.comparison_unit).toLowerCase())}</dd>
      <dt>Valio's stock</dt><dd>${esc(stockText(facts.stock))}</dd>`;
    versus = `<p class="card__note">${esc(why)} ${candidates ? `Valio ranked ${candidates} substitutes and proposes this one.` : ""}</p>
      <div class="versus">
        ${productFacts("Asked for", facts.substitute_for.name, facts.substitute_for)}
        ${productFacts("Proposed by Valio", item.item.title, facts, extra)}
      </div>`;
  }
  const judge = (approval.judge ?? [])
    .map((answer) => {
      const percent = Math.round(answer.probability * 100);
      return `<li class="judge">
          <span class="judge__q">${esc(JUDGE_WORDS[answer.question_key] ?? words(answer.question_key))}</span>
          <span class="judge__bar" role="img" aria-label="${percent} percent, threshold ${Math.round(answer.auto_threshold * 100)} percent">
            <span class="judge__fill judge__fill--${esc(answer.routed)}" style="width:${percent}%"></span>
            <span class="judge__mark" style="left:${Math.round(answer.auto_threshold * 100)}%"></span>
          </span>
          <span class="judge__p">${percent}%</span>
        </li>`;
    })
    .join("");
  // The reason is the verdict's sentence, shown in the card above. It is only repeated here if there is no verdict.
  const reasons = state.verdict ? "" : approval.reasons.map((reason) => `<li>${esc(reason.message)}</li>`).join("");
  const open = approval.status === "pending";

  let foot = "";
  if (approval.status === "pending") {
    foot = `<div class="sign">
        <p class="sign__deadline">${icon("wait")} Sign before <b>${esc(clock(approval.deadline))}</b>, Valio's order cut-off.</p>
        <button class="btn btn--quiet" type="button" data-action="reject" ${app.busy ? "disabled" : ""}>Reject</button>
        <button class="btn btn--go" type="button" data-action="approve" ${app.busy ? "disabled" : ""}>Approve and sign</button>
      </div>`;
  } else {
    const outcome = { approved: "Signed", rejected: "Rejected", expired: "Expired: nobody signed in time" }[approval.status] ?? approval.status;
    const who = approval.decided_by ? ` by ${approval.decided_by}, ${clock(approval.decided_at)}` : "";
    foot = `<p class="sign__done sign__done--${esc(approval.status)}">${approval.status === "approved" ? icon("check") : icon("cross")}${esc(outcome + who)}</p>`;
  }
  return `<section class="card card--human">
      <p class="card__label">Your signature</p>
      ${reasons ? `<ul class="reasons">${reasons}</ul>` : ""}
      ${open ? versus : ""}
      ${open && judge ? `<p class="card__label card__label--gap">The judge, threshold ${Math.round((approval.judge[0].auto_threshold ?? 0) * 100)}%</p><ul class="judges">${judge}</ul>` : ""}
      ${foot}
    </section>`;
}

function receiptCard(state) {
  const order = state.order;
  const payment = state.steps[5];
  const receipt = state.steps[6];
  return `<section class="card card--done">
      <p class="card__label">Receipt signed by Valio Aimo</p>
      <p class="card__lead">${icon("check")}Order ${esc(order.order_id)} accepted</p>
      <dl class="facts">
        <dt>Total</dt><dd>${esc(money(order.total_minor, order.currency))} before tax</dd>
        <dt>Delivery</dt><dd>${esc(dayLong(order.delivery_date))}</dd>
        <dt>Signed by</dt><dd>${esc(order.signed_by === "human" ? "the chef, on this page" : "the agent, inside the chef's limits")}</dd>
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
          <p class="attack__title">${refused ? icon("cross") : icon("wait")}${esc(attack.title)}</p>
          <p class="attack__status">${esc(label)}</p>
          ${problems ? `<ul class="attack__problems">${problems}</ul>` : ""}
        </li>`;
    })
    .join("");
  return `<section class="card card--deny">
      <p class="card__label">Bad mandates sent straight to Valio</p>
      <ul class="attacks">${items}</ul>
    </section>`;
}

function orderView() {
  const state = app.state;
  if (!hasRun() || app.shown < 2 || !state.quote) {
    const waiting = hasRun() || app.busy ? '<p class="working">The agent is asking Valio Aimo for a signed quote…</p>' : "";
    return `<div class="order"><div class="order__main">${requestTable()}${waiting}</div><div class="order__side"></div></div>`;
  }
  const side = [
    state.verdict && app.shown >= 3 ? verdictCard(state) : "",
    state.attacks?.length && app.shown >= 5 ? attacksCard(state) : "",
    state.approval && app.shown >= 4 ? approvalCard(state) : "",
    state.order && app.shown >= 7 ? receiptCard(state) : "",
  ].join("");
  return `<div class="order"><div class="order__main">${quoteTable(state)}</div><div class="order__side">${side}</div></div>`;
}

function drawMain() {
  const problem = app.problem ? `<p class="problem" role="alert"><strong>Something did not answer.</strong> ${esc(app.problem)}</p>` : "";
  const view = hasRun() || app.step === 3 ? orderView() : app.step === 2 ? stockView() : recipesView();
  el("main").innerHTML = problem + view;
}

/* ---------- Drawing: the side column ---------- */

function drawMenu() {
  const menu = app.state?.kitchen?.menu ?? [];
  const items = menu
    .map((item) => {
      const cut = item.dish.indexOf(",");
      return `<li><span class="menu__course">${esc(item.course)}</span>${esc(cut === -1 ? item.dish : item.dish.slice(0, cut))}</li>`;
    })
    .join("");
  el("menu").innerHTML = `<h2 class="side__title display">This week's menu</h2><ul class="menu__list">${items}</ul>`;
}

function drawAgent() {
  const lines = app.talk.map((line) => ({ ...line }));
  if (hasRun() && app.state.request) {
    lines.push({ who: "chef", text: app.state.request.text });
    app.state.steps.slice(0, app.shown).forEach((step) => {
      if (!step.detail) return;
      const asks = step.status === "waiting";
      const byChef = step.signer === "manager" && !asks;
      lines.push({ who: byChef ? "chef" : "other", speaker: asks ? "Agent" : SPEAKER_WORDS[step.signer], text: step.detail, proof: step.proof, status: byChef ? null : step.status });
    });
  }
  if (hasRun() && app.shown < reachable()) lines.push({ who: "agent", typing: true });

  const bubbles = lines
    .map((line) => {
      if (line.typing) return '<li class="say say--agent"><span class="say__dots" aria-label="working"><i></i><i></i><i></i></span></li>';
      const speaker = line.speaker ?? (line.who === "chef" ? "Chef" : "Agent");
      const proof = line.proof ? `<span class="say__proof mono" title="${esc(line.proof)}">${esc(shortProof(line.proof))}</span>` : "";
      return `<li class="say say--${line.who === "chef" ? "chef" : "agent"}${line.status ? ` say--${esc(line.status)}` : ""}">
          <span class="say__who">${esc(speaker)}</span>
          <span class="say__text">${esc(line.text)}</span>${proof}
        </li>`;
    })
    .join("");
  el("agent").innerHTML = `<h2 class="side__title display">${icon("spark")}Buying agent</h2><ol class="talk" id="talk">${bubbles}</ol>`;
  const talk = el("talk");
  talk.scrollTop = talk.scrollHeight;
}

/* ---------- Drawing: the demo strip (for the team, not for the customer) ---------- */

function drawDemo() {
  const scenarios = app.state?.scenarios ?? [];
  const current = hasRun() ? app.state.scenario.id : app.scenarioId;
  const buttons = scenarios
    .map(
      (scenario, index) => `<button class="demo__btn" type="button" data-scenario="${esc(scenario.id)}" aria-pressed="${scenario.id === current}"
          title="${esc(scenario.hint)}">${index + 1} ${esc(scenario.title)}</button>`
    )
    .join("");
  const source = app.mode === "live" ? `driver live (${esc(DRIVER_URL)})` : "driver: replay of the runs recorded on 14/11";
  el("demo").innerHTML = `
    <span class="demo__label">Demo controls</span>
    ${buttons}
    <button class="demo__btn" type="button" data-action="reset">Reset</button>
    <span class="demo__src">${source} · harness ${app.harnessUp ? "live" : "not reached"} · kitchen data: synthetic</span>
    <span class="demo__note">Concept mock-up, Junction 2026, synthetic data. Not a Valio Aimo service.</span>`;
}

function draw() {
  drawFlow();
  drawTrail();
  drawMain();
  drawAgent();
  drawDemo();
}

function drawAll() {
  drawAccount();
  drawPlanning();
  drawMenu();
  draw();
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
  app.step = 1;
  app.confirmed = { recipes: false, stock: false };
  app.stockFilter = "all";
  app.shown = 0;
  app.talk = [];
  say("agent", openingLine());
}

async function chooseScenario(id) {
  clearTimeout(revealTimer);
  await guarded(async () => {
    app.state = app.mode === "live" ? await driver.reset() : await recorded("idle");
    if (id === "attack") {
      // The attack is not something the chef does: it runs at once.
      app.scenarioId = "attack";
      app.kitchen.stock = await kitchenApi.stock(id);
      startOver();
      app.step = 3;
      await runScenario();
      return;
    }
    app.scenarioId = id;
    app.kitchen.stock = await kitchenApi.stock(id);
    startOver();
  });
}

async function runScenario() {
  app.step = 3;
  app.shown = 0;
  draw();
  app.state = app.mode === "live" ? await driver.run(app.scenarioId) : await recorded(REPLAY_FILE[app.scenarioId]);
  reveal();
  watch();
}

async function decide(decision) {
  const approval = app.state.approval;
  await guarded(async () => {
    if (app.mode === "live") {
      await harness.decide(approval.approval_id, decision);
      app.state = await driver.state();
    } else if (decision === "approve") {
      app.state = await recorded("substitution.approved");
    } else {
      throw new Error("No run was recorded for a rejection. Start the services to try it live.");
    }
    reveal();
    watch();
  });
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

  const stepButton = event.target.closest("[data-step]");
  if (stepButton && !hasRun()) {
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

  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "confirm-recipes") {
    app.confirmed.recipes = true;
    app.step = 2;
    say("chef", "The recipes are right.");
    say("agent", stockLine());
    draw();
  } else if (action === "confirm-stock") {
    app.confirmed.stock = true;
    app.step = 3;
    say("chef", "The stock is checked.");
    say("agent", orderLine());
    draw();
  } else if (action === "run") {
    guarded(runScenario);
  } else if (action === "approve" || action === "reject") {
    decide(action);
  } else if (action === "reset") {
    chooseScenario(app.scenarioId === "attack" ? "normal-order" : app.scenarioId);
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
    app.state = app.mode === "live" ? state : await recorded("idle");

    const [recipes, bookings, stock, policy] = await Promise.all([
      kitchenApi.recipes(),
      kitchenApi.bookings(),
      kitchenApi.stock(app.state.scenario.id ?? app.scenarioId),
      harness.policy().catch(() => null),
    ]);
    app.kitchen = { recipes, bookings, stock };
    app.harnessUp = Boolean(policy);
    // Without the harness, the limit is read from the policy file the harness loads.
    app.policy = policy ?? (await call("../../scenarios/policy.demo.json").catch(() => null));

    startOver();
    if (hasRun()) {
      // The driver was already in the middle of a scenario: show it where it is.
      app.scenarioId = app.state.scenario.id;
      app.step = 3;
      app.shown = reachable();
      watch();
    }
    drawAll();
  } catch (error) {
    el("main").innerHTML = `<p class="problem"><strong>The page could not load its data.</strong>
      Serve the repo from its root (<code>python3 -m http.server 8003</code>) and open
      <code>http://localhost:8003/surface/static/portal.html</code>. Detail: ${esc(error.message)}</p>`;
  }
})();
