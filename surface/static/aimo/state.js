/*
 * What is on screen right now, and what can be read from it. No drawing here, no network call.
 */

import {
  QUERY,
  ASSISTANT,
  STEP_TERMS,
  CHECK_WORDS,
  round3,
  money,
  qty,
  dayShort,
  dayLong,
  clock,
  lexicon,
  plainDetail,
  firstSentence,
  allergenText,
  stockText,
  plural,
} from "./core.js";

const VARIANTS = ["a", "b", "c"];
export const ROUTES = ["today", "order", "orders", "approvals", "rules", "audit"];

export const app = {
  variant: VARIANTS.includes(QUERY.get("v")) ? QUERY.get("v") : "a",
  route: "today",
  mode: "replay", // "live" when the demo driver answers
  up: { driver: false, harness: false, assistant: false, merchant: false },
  scenarioId: QUERY.get("scenario") === "substitution" ? "substitution" : "normal-order",
  state: null, // the demo state
  shown: 0, // how many steps of the assistant's work are on screen
  fresh: null, // the step that has just arrived, for the animation
  kitchen: { recipes: null, bookings: null, stock: null },
  lines: [], // the stock table: the count, with the swaps and the changes the chef asked the assistant for
  sentKey: null,
  step: 1, // guided variant only: 1 menu, 2 stock, 3 order
  policy: null,
  rules: { draft: null, saving: false, note: null }, // the rules screen: the chef's unsaved changes
  eco: { data: null, key: null, loading: false, dismissed: new Set() },
  ask: { busy: false, question: null, answer: null, changes: [], failed: false }, // the last exchange with the assistant, nothing older
  history: [], // sample orders from before the demo
  session: { orders: [], approvals: [], loaded: false }, // what the harness and the gateway hold from this session
  ledger: { buyer: [], merchant: [], filter: "all", selected: null, check: null }, // both audit logs
  proof: null, // the order whose proof is open in the side panel
  linesOpen: false, // brief variant: the order lines are folded until asked
  detailsOpen: false, // the full comparison of a substitute
  busy: false,
  problem: null,
  strip: QUERY.get("strip") !== "0",
};

/* ---------- The run ---------- */

export const status = () => app.state?.scenario?.status ?? "idle";
export const hasRun = () => status() !== "idle";
export const finished = () => ["done", "refused"].includes(status());
export const isAttack = () => app.state?.scenario?.id === "attack";
export const missingLines = () => app.lines.filter((line) => line.to_order > 0);
export const neededNow = (line) => round3(Math.max(0, line.need - line.in_stock));

/* The lines the assistant will ask Valio for: what is short in the stock table. */
export const orderLines = () =>
  missingLines().map((line) => ({ product_id: line.product_id, name: line.name, amount: line.to_order, unit: line.unit, dish: line.dishes.join(", ") }));

export const linesKey = (lines) =>
  (lines ?? [])
    .map((line) => `${line.product_id}:${round3(line.amount)}`)
    .sort()
    .join("|");

/* The order on screen is the chef's own (not the attack, which nobody in the kitchen sent). */
export const orderOnScreen = () => hasRun() && !isAttack();

export function reachable() {
  if (!hasRun()) return 0;
  let last = 0;
  (app.state.steps ?? []).forEach((step, index) => {
    if (step.status !== "pending") last = index + 1;
  });
  return last;
}

export const revealing = () => hasRun() && app.shown < reachable();
/* The assistant is at work, or an order waits for a signature: the order cannot change. */
export const inFlight = () => app.busy || revealing() || ["running", "waiting_for_human"].includes(status());
export const canEdit = () => !inFlight() && !orderOnScreen();
export const pendingApproval = () => (app.state?.approval?.status === "pending" && app.shown >= 4 ? app.state.approval : null);

export const limitKnown = () => app.policy && Number.isFinite(app.policy.autonomous_limit_minor);
export const limitText = () => (limitKnown() ? money(app.policy.autonomous_limit_minor, app.policy.currency) : null);

export function quoteTotal(quote) {
  return quote?.totals?.find((item) => item.type === "total")?.amount ?? null;
}

/* ---------- The stock table ---------- */

export function loadLines(stock) {
  app.lines = (stock?.lines ?? []).map((line) => ({ ...line, counted: line.in_stock, by: {} }));
}

/* Change one cell, when the chef asks the assistant for it. Returns what changed, or null. */
export function setStock(productId, field, amount, by) {
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

export const changeText = (change) =>
  `${change.line.name}: ${change.field === "in_stock" ? "in stock" : "to order"} ${qty(change.before, change.line.unit)} → ${qty(change.after, change.line.unit)}`;

/* ---------- The carbon footprint and the weekly greener check ---------- */

export const ecoKey = () => linesKey(orderLines());
export const ecoNow = () => (app.eco.key === ecoKey() ? app.eco.data : null);
export const ecoOffer = (productId) => ecoNow()?.alternatives?.find((offer) => offer.product_id === productId) ?? null;
export const swappedLines = () => app.lines.filter((line) => line.swapped_from);
export const savedByPercent = (offer) => `${Math.round(offer.saving_share * 100)}%`;
export const kitchenName = (offer) => app.lines.find((line) => line.product_id === offer.product_id)?.name ?? offer.name;

/* The chef (or the assistant, when the chef asks) takes Valio's greener product for one line. Returns what changed. */
export function swapLine(productId, swapTo, by) {
  const offer = ecoOffer(productId);
  const line = app.lines.find((entry) => entry.product_id === productId);
  if (!canEdit() || !offer || !line || offer.alternative.id !== swapTo) return null;
  line.swapped_from = { product_id: line.product_id, name: line.name, offer, by };
  line.product_id = offer.alternative.id;
  line.name = offer.alternative.name;
  app.eco.dismissed.delete(productId);
  return { line, offer };
}

export function unswap(line) {
  if (!line.swapped_from) return;
  line.product_id = line.swapped_from.product_id;
  line.name = line.swapped_from.name;
  delete line.swapped_from;
}

/* ---------- The assistant's work, line by line ---------- */

const services = () => app.kitchen.bookings?.services ?? [];
export const serviceDays = () => (services().length ? `${dayShort(services()[0].date)} to ${dayLong(services().at(-1).date)}` : "the coming services");

/* What the assistant did before any order is sent: read the menu, compared it with the stock. The kitchen's own data. */
function prepLines() {
  const recipes = app.kitchen.recipes?.recipes ?? [];
  const stock = app.kitchen.stock;
  const lines = [];
  if (recipes.length) {
    const covers = app.kitchen.recipes.covers_per_service ?? app.state?.kitchen?.covers_per_service;
    lines.push({
      key: "menu",
      tone: "done",
      who: "agent",
      head: "Read your menu",
      detail: `${plural(recipes.length, "recipe", "recipes")}, ${covers} covers a service, ${plural(services().length, "service", "services")} from ${serviceDays()}.`,
    });
  }
  if (stock) {
    const missing = missingLines().length;
    lines.push({
      key: "stock",
      tone: "done",
      who: "agent",
      head: "Compared it with your stock",
      detail: `${missing} of ${app.lines.length} ingredients are short, from the count of ${dayLong(stock.counted_at)}.`,
    });
  }
  return lines;
}

function stepHead(step, state) {
  const { status: s, signer } = step;
  const attack = state.scenario?.id === "attack";
  switch (step.key) {
    case "open_mandate":
      return "Your standing permission";
    case "signed_quote":
      return s === "done" ? "Valio signed the quote" : s === "refused" ? "No quote from Valio" : "Quote from Valio";
    case "verdict": {
      if (s === "skipped") return "Safety checks skipped";
      const verdict = state.verdict;
      if (!verdict) return "Safety checks";
      const total = verdict.rules.length;
      const open = verdict.rules.filter((rule) => rule.outcome !== "pass").length;
      if (verdict.decision === "auto") return `${total} safety checks passed`;
      if (verdict.decision === "human") return `${total - open} of ${total} checks passed, ${open} ${open === 1 ? "needs" : "need"} you`;
      return "Blocked by a safety check";
    }
    case "closed_mandates":
      if (s === "waiting") return "Waiting for your signature";
      if (s === "refused") return "You rejected the order";
      if (s === "skipped") return "Nobody signed";
      if (attack) return "Signed without the safety checks";
      return signer === "manager" ? "You signed this order" : `${ASSISTANT} signed this order`;
    case "merchant_verifies":
      return s === "done" ? "Valio checked the signature" : s === "refused" ? "Valio refused" : "Nothing reached Valio";
    case "sandbox_payment":
      return s === "done" ? "Payment booked, in test mode" : "Nothing is charged";
    case "signed_receipt":
      return s === "done" ? "Valio signed the receipt" : "No order, no receipt";
    default:
      return step.title;
  }
}

/* The verdict line carries the reason in the chef's words, when a check asks for them. */
function verdictDetail(state) {
  const verdict = state.verdict;
  if (!verdict) return null;
  const open = verdict.rules.filter((rule) => rule.outcome !== "pass");
  if (!open.length) return `${ASSISTANT} may sign this order for you.`;
  return `${open.map((rule) => checkLine(rule).label).join(". ")}.`;
}

/* The lines of the assistant's work on screen: what it prepared, then the steps of the order as they arrive. */
export function workLog() {
  const state = app.state;
  const lines = isAttack() ? [] : prepLines();
  if (!hasRun() || !state) return lines;
  state.steps.slice(0, app.shown).forEach((step, index) => {
    const detail = plainDetail(step.detail);
    const short = step.key === "verdict" && step.status !== "skipped" ? verdictDetail(state) ?? firstSentence(detail) : firstSentence(detail);
    // An order signed outside the safety checks is "done" for the services. For the chef it is the thing that went wrong.
    const outside = isAttack() && step.key === "closed_mandates" && step.status === "done";
    lines.push({
      key: step.key,
      tone: outside ? "refused" : step.status,
      who: ["waiting", "skipped"].includes(step.status) ? null : step.signer, // nobody did a step that did not happen
      head: stepHead(step, state),
      detail: short,
      more: detail !== short ? detail : null,
      proof: step.proof,
      term: STEP_TERMS[step.key],
      at: step.at,
      fresh: app.fresh === index,
    });
  });
  return lines;
}

/*
 * How long the order took, from the services' own timestamps: from Valio's quote to the last step.
 * The standing permission is left out: the chef signed it beforehand, it is not part of this order's work.
 */
export function runSeconds() {
  const times = (app.state?.steps ?? [])
    .filter((step) => step.at && step.status === "done" && step.key !== "open_mandate")
    .map((step) => Date.parse(step.at));
  if (times.length < 2) return null;
  return (Math.max(...times) - Math.min(...times)) / 1000;
}

/* ---------- Who signed: the three seals ---------- */

export function seals() {
  const steps = Object.fromEntries((app.state?.steps ?? []).map((step, index) => [step.key, { ...step, on: index < app.shown }]));
  const on = (key) => (steps[key]?.on ? steps[key] : null);
  const open = on("open_mandate");
  const quote = on("signed_quote");
  const closed = on("closed_mandates");
  const verifies = on("merchant_verifies");
  const receipt = on("signed_receipt");
  const attack = isAttack();
  // The step that has just arrived: only the seal it changes is stamped, the others stay still.
  const arrived = app.fresh !== null ? app.state?.steps?.[app.fresh]?.key : null;

  const you = { who: "You", tone: "empty", says: "Standing permission", proof: null, by: null };
  if (open?.status === "done") Object.assign(you, { tone: "inked", proof: open.proof, by: "open_mandate" });
  if (closed?.signer === "manager" && closed.status === "done") Object.assign(you, { tone: "inked", says: "Signed this order", proof: closed.proof, by: "closed_mandates" });
  if (closed?.status === "waiting") Object.assign(you, { tone: "waiting", says: "Your signature is needed", proof: null, by: "closed_mandates" });
  if (closed?.status === "refused") Object.assign(you, { tone: "refused", says: "Rejected this order", proof: null, by: "closed_mandates" });

  const aimo = { who: ASSISTANT, tone: "empty", says: "Signs inside your limit", proof: null, by: null };
  if (closed?.signer === "agent" && closed.status === "done") {
    Object.assign(aimo, attack ? { tone: "refused", says: "Signed without the checks" } : { tone: "inked", says: "Signed this order", proof: closed.proof }, { by: "closed_mandates" });
  } else if (closed && closed.signer !== "agent") {
    aimo.says = "Did not sign";
  }

  const valio = { who: "Valio", tone: "empty", says: "Quote and receipt", proof: null, by: null };
  if (quote?.status === "done") Object.assign(valio, { tone: "inked", says: "Signed the quote", proof: quote.proof, by: "signed_quote" });
  if (receipt?.status === "done") Object.assign(valio, { tone: "inked", says: "Signed quote and receipt", proof: receipt.proof, by: "signed_receipt" });
  if (verifies?.status === "refused") Object.assign(valio, { tone: "refused", says: "Refused the order", proof: null, by: "merchant_verifies" });

  return [you, aimo, valio].map((seal) => ({ ...seal, fresh: Boolean(arrived) && seal.by === arrived }));
}

/* ---------- Checks ---------- */

/* One rule of the harness, as a line a chef can read. */
export function checkLine(rule) {
  const wordsFor = CHECK_WORDS[rule.rule_id];
  const label = wordsFor?.[rule.outcome] ?? lexicon(rule.message);
  let value = "";
  try {
    value = wordsFor?.value?.(rule.evidence ?? {}) ?? "";
  } catch {
    value = "";
  }
  return { id: rule.rule_id, name: wordsFor?.name ?? rule.rule_id, label, value, outcome: rule.outcome, title: lexicon(rule.message) };
}

/* ---------- What the assistant's chat may read: only what the page shows ---------- */

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

export function pageFacts() {
  const state = app.state;
  const facts = {
    step: orderOnScreen() ? "order" : "stock",
    can_edit: canEdit(),
    kitchen: { name: state?.kitchen?.name, covers_per_service: state?.kitchen?.covers_per_service },
    services: services().map((service) => ({ date: dayLong(service.date), meal: service.meal, booked: service.booked, projected: service.projected })),
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
        total_before_tax: money(quoteTotal(quote), quote.currency),
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
        return `${check.outcome}: ${check.label}${check.value ? ` (${check.value})` : ""}`;
      }),
      signature: state.approval && { status: state.approval.status, sign_before: clock(state.approval.deadline) },
      receipt: state.order && { order_id: state.order.order_id, total: money(state.order.total_minor, state.order.currency), delivery: dayLong(state.order.delivery_date), signed_by: state.order.signed_by },
    };
  }
  return facts;
}

/* ---------- The orders table: this session's real orders, then the sample history ---------- */

const summary = (titles) => {
  const names = titles.map((title) => String(title).replace(/^(Valio|VAASAN|Elovena|Meira|Dansukker|Apetit|Myrttisen|Haapalan)\s+/i, ""));
  const text = names.length <= 2 ? names.join(" and ") : `${names.slice(0, 2).join(", ")} and ${names.length - 2} more`;
  return text.charAt(0).toUpperCase() + text.slice(1);
};

/* One row per order or refused request. `real` rows come from the services, the others are the sample history. */
export function orderRows() {
  const rows = [];
  const state = app.state;
  const seen = new Set();
  if (state && orderOnScreen() && state.quote && app.shown >= 2) {
    const quote = state.quote;
    const order = app.shown >= 7 ? state.order : null;
    const approval = state.approval;
    let rowStatus = "working";
    if (order) rowStatus = "accepted";
    else if (approval?.status === "pending") rowStatus = "needs_you";
    else if (approval?.status === "rejected") rowStatus = "rejected";
    else if (approval?.status === "expired") rowStatus = "expired";
    else if (state.verdict?.decision === "deny") rowStatus = "blocked";
    rows.push({
      real: true,
      current: true,
      id: order?.order_id ?? quote.id,
      at: order?.created_at ?? quote.aimo.issued_at,
      items: summary(quote.line_items.map((item) => item.item.title)),
      count: quote.line_items.length,
      total_minor: quoteTotal(quote),
      currency: quote.currency,
      signed_by: order ? order.signed_by : "none",
      status: rowStatus,
      delivery_date: order?.delivery_date ?? null,
      checkout_id: quote.id,
    });
    seen.add(quote.id);
  }
  app.session.orders.forEach((order) => {
    if (seen.has(order.checkout_id)) return;
    seen.add(order.checkout_id);
    rows.push({
      real: true,
      id: order.order_id,
      at: order.created_at,
      items: order.titles ? summary(order.titles) : null,
      count: order.titles?.length ?? null,
      total_minor: order.total_minor,
      currency: order.currency,
      signed_by: order.signed_by,
      status: "accepted",
      delivery_date: order.delivery_date,
      checkout_id: order.checkout_id,
      order,
    });
  });
  app.history.forEach((entry) => {
    rows.push({
      real: false,
      id: entry.order_id ?? entry.checkout_id,
      at: entry.ordered_at,
      items: summary(entry.lines.map((line) => line.title)),
      count: entry.lines.length,
      total_minor: entry.total_minor,
      currency: entry.currency,
      signed_by: entry.signed_by,
      status: entry.status,
      delivery_date: entry.delivery_date,
      checkout_id: entry.checkout_id,
      entry,
    });
  });
  return rows.sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
}

/* Both audit logs as one stream, newest first. In replay the page only holds the lines of the order on screen. */
export function ledgerRows() {
  const buyer = app.ledger.buyer.length ? app.ledger.buyer : app.state?.audit?.buyer ?? [];
  const merchantLog = app.ledger.merchant.length ? app.ledger.merchant : app.state?.audit?.merchant ?? [];
  const rows = [...buyer.map((event) => ({ ...event, side: "buyer" })), ...merchantLog.map((event) => ({ ...event, side: "merchant" }))];
  return rows.sort((a, b) => Date.parse(b.at) - Date.parse(a.at) || (a.side === b.side ? b.seq - a.seq : a.side === "merchant" ? -1 : 1));
}

export const ledgerKey = (event) => `${event.side}:${event.seq}`;
export const isRefusal = (event) => /refused|rejected|denied|expired/.test(event.action) || /^Verdict deny/.test(event.what ?? "");
