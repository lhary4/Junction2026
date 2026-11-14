/*
 * The trusted surface: the page where a human sees the offers, approves or rejects an order,
 * and reads the two audit logs. Plain JavaScript, no framework, no build step.
 *
 * This file is in eight parts:
 *   1. Settings read from the address bar
 *   2. Small helpers: safe text, money, dates, readable names
 *   3. Loading the data (mock mode reads contract/examples/)
 *   4. Shared pieces: badges, facts, the lines of a quote
 *   5. Offers
 *   6. Approvals
 *   7. Audit
 *   8. Routing, the clock, and the start
 *
 * Two rules this page keeps:
 *   - It never invents a fact. Every number shown comes from a loaded file. What is missing reads "unknown".
 *   - Every piece of text from the data goes through esc() before it reaches the page, so a sentence
 *     written by the agent can never add a button or a script to the approval card.
 */
"use strict";

// ---------- 1. Settings read from the address bar ----------

const IN_BROWSER = typeof window !== "undefined";
const params = new URLSearchParams(IN_BROWSER ? window.location.search : "");

// ?mock=1 : read the example files instead of the live services (the live routes come in step C4).
const MOCK = params.get("mock") === "1";
const EXAMPLES = "../../contract/examples/";

const VIEWS = ["offers", "approvals", "audit"];
const STATES = ["pending", "approved", "rejected", "expired"];
const CASES = ["spend", "substitution"];

// ?now=2026-11-15T16:59:50+02:00 : start the clock at that instant, to rehearse a deadline.
const startedAt = Date.now();
const frozenStart = Date.parse(params.get("now") || "");
function now() {
  return Number.isNaN(frozenStart) ? Date.now() : frozenStart + (Date.now() - startedAt);
}

// ---------- 2. Small helpers ----------

/** Make any value safe to put inside HTML. */
function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

const numberFormat = new Intl.NumberFormat("en-US");
const moneyFormat = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** 101000 cents, "EUR" -> "EUR 1,010.00". Money is always an integer in cents in the contract. */
function money(minor, currency) {
  if (minor === null || minor === undefined) return "unknown";
  return `${currency || "EUR"} ${moneyFormat.format(minor / 100)}`;
}

function quantity(value) {
  return numberFormat.format(value);
}

// All times are shown in Helsinki time, whatever the laptop's own time zone is.
function helsinki(isoTime, options) {
  return new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Helsinki", hour12: false, ...options }).format(
    new Date(isoTime),
  );
}

/** "2026-11-15T17:00:00+02:00" -> "Sun 15 Nov, 17:00" */
function dayAndTime(isoTime) {
  if (!isoTime) return "unknown";
  const day = helsinki(isoTime, { weekday: "short", day: "numeric", month: "short" }).replace(",", "");
  return `${day}, ${helsinki(isoTime, { hour: "2-digit", minute: "2-digit" })}`;
}

/** "2026-11-14T13:15:03+02:00" -> "13:15:03" */
function clockTime(isoTime) {
  return helsinki(isoTime, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** A date without a time, "2026-11-16" -> "Mon 16 Nov" */
function dayOnly(dateText) {
  if (!dateText) return "unknown";
  const noon = new Date(`${dateText}T12:00:00Z`);
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "short", day: "numeric", month: "short" })
    .format(noon)
    .replace(",", "");
}

/** Milliseconds left -> "26 h 14 min 03 s" */
function countdownText(milliseconds) {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours} h ${minutes} min ${seconds} s` : `${minutes} min ${seconds} s`;
}

function shortHash(hash) {
  if (!hash) return "unknown";
  return hash.length > 14 ? `${hash.slice(0, 6)}…${hash.slice(-4)}` : hash;
}

// GS1 allergen codes, from docs/contract.md.
const ALLERGEN_NAMES = {
  AM: "milk",
  AW: "cereals with gluten",
  GO: "oats",
  AP: "peanuts",
  AN: "tree nuts",
  ML: "lactose",
};
function allergenName(code) {
  return ALLERGEN_NAMES[code] || code;
}

const SOURCE_NAMES = {
  aimo_stock_count: "Aimo stock count",
  supplier_warehouse: "supplier warehouse",
  aimo_price_api: "Aimo price API",
  gs1_synkka: "GS1 Synkka",
  aimo_delivery_history: "Aimo delivery history",
  product_group_average: "product group average",
  none: "no source",
};

// The rule that sent an order to a human, in plain words.
const RULE_TITLES = {
  "quote-signature": "Valio's signature on the quote",
  "quote-not-expired": "Quote still valid",
  "merchant-allowed": "Allowed merchant",
  "allergen-not-blocked": "No blocked allergen",
  "allergen-data-known": "Allergen data is known",
  "allergen-unchanged-on-substitution": "The substitute changes the allergens",
  "delivery-on-time": "Delivery on time",
  "spend-limit": "Above what the agent may spend alone",
  "substitution-within-preferences": "The substitute is outside the buyer's preferences",
};

const LABEL_NAMES = { GOODS_FROM_FINLAND_BLUE_SWAN: "Goods from Finland (Blue Swan)" };
/** "FREE_FROM_LACTOSE" -> "Free from lactose" */
function labelName(code) {
  if (LABEL_NAMES[code]) return LABEL_NAMES[code];
  const words = String(code).replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function countryName(code) {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code) || code;
  } catch {
    return code;
  }
}

const UNIT_NAMES = { L: "litre", KG: "kilo", ST: "unit" };
function unitName(unit) {
  return UNIT_NAMES[unit] || unit;
}

/** The value of a claim as readable text. A claim is a fact with its source and certainty. */
function claimValueText(claim) {
  if (!claim || claim.certainty === "unknown" || claim.value === null || claim.value === undefined) return "unknown";
  switch (claim.unit) {
    case "kg_co2e_per_kg":
      return `${claim.value} kg CO₂e/kg`;
    case "share_delivered":
      return `${Math.round(claim.value * 1000) / 10}% delivered`;
    case "country":
      return countryName(claim.value);
    case "eur_minor_per_sales_unit":
      return money(claim.value, "EUR");
    default:
      // Stock: Valio sometimes says "we can deliver" without giving a count.
      if (claim.value === "not_given") return "available, no count given";
      return typeof claim.value === "number" ? `${quantity(claim.value)} ${claim.unit}` : `${claim.value} ${claim.unit}`;
  }
}

// ---------- 3. Loading the data ----------

async function readExample(name) {
  const answer = await fetch(EXAMPLES + name);
  if (!answer.ok) throw new Error(`${name}: HTTP ${answer.status}`);
  return answer.json();
}

/**
 * Mock mode. Reads contract/examples/ and returns everything the page draws, in one object.
 * The live mode of step C4 will return the same shape from the gateway and the harness.
 */
async function loadMockData() {
  const names = [
    "policy.demo.json",
    "product-cards.json",
    "checkout.act1.json",
    "checkout.act2.json",
    "checkout.act3.json",
    "verdict.auto.json",
    "verdict.human.spend.json",
    "verdict.human.substitution.json",
    "verdict.deny.json",
    "approval-request.pending.json",
    "authorization-status.json",
    "order.json",
    "audit-events.json",
  ];
  const files = await Promise.all(names.map(readExample));
  return buildMockData(Object.fromEntries(names.map((name, index) => [name, files[index]])));
}

/** Arrange the example files into the shape the page draws. Kept apart from the loading so a test can call it. */
function buildMockData(files) {
  const statuses = files["authorization-status.json"];
  const order = files["order.json"];
  const act1 = files["checkout.act1.json"];
  const act2 = files["checkout.act2.json"];
  const act3 = files["checkout.act3.json"];

  return {
    policy: files["policy.demo.json"],
    products: files["product-cards.json"],
    // One entry per screen of the demo. Act 4 is the act 1 quote, presented with a changed price.
    quotes: [
      { key: "act1", label: "Act 1", checkout: act1, verdict: files["verdict.auto.json"], status: statuses.ordered },
      {
        key: "act2",
        label: "Act 2",
        checkout: act2,
        verdict: files["verdict.human.spend.json"],
        status: statuses.pending_approval,
      },
      { key: "act3", label: "Act 3", checkout: act3, verdict: null, status: null },
      {
        key: "act4",
        label: "Act 4",
        hint: "tampered quote",
        checkout: act1,
        verdict: files["verdict.deny.json"],
        status: statuses.denied,
      },
    ],
    approvals: [
      {
        kind: "spend",
        approval: files["approval-request.pending.json"],
        checkout: act2,
        orderIdOnceApproved: statuses.ordered_after_approval.order_id,
      },
      {
        kind: "substitution",
        approval: approvalFromVerdict(files["verdict.human.substitution.json"]),
        checkout: null, // there is no example quote for the oat drink yet: asked to Adrien in team/colette/notes.md
        orderIdOnceApproved: null,
      },
    ],
    orders: { [order.order_id]: order },
    audit: files["audit-events.json"],
  };
}

/**
 * The examples have no approval request for a substitution, only the verdict.
 * The harness builds one from the other, so the mock does the same: the rules that did not pass become the reasons.
 */
function approvalFromVerdict(verdict) {
  return {
    approval_id: "apr_example_substitution",
    checkout_id: verdict.checkout_id,
    checkout_hash: verdict.checkout_hash,
    status: "pending",
    total_minor: verdict.total_minor,
    currency: verdict.currency,
    reasons: verdict.rules.filter((rule) => rule.outcome !== "pass"),
    judge: verdict.judge,
    request_text: "600 litres of the Arla one.", // the sentence of act 3 in PLAN.md
    requested_at: verdict.decided_at,
    deadline: verdict.deadline,
    decided_by: null,
    decided_at: null,
    order_id: null,
  };
}

/** Mock mode only: put an approval in the state asked by the link (?state=approved) or by a button. */
function setMockState(entry, state, policy, decidedAt) {
  const approval = entry.approval;
  approval.status = state;
  const decided = state === "approved" || state === "rejected";
  approval.decided_by = decided ? policy.approver : null;
  approval.decided_at = decided ? decidedAt || twoMinutesAfter(approval.requested_at) : null;
  approval.order_id = state === "approved" ? entry.orderIdOnceApproved : null;
}

function twoMinutesAfter(isoTime) {
  return new Date(Date.parse(isoTime) + 2 * 60 * 1000).toISOString();
}

// ---------- 4. Shared pieces ----------

/** The small badge next to a fact: measured, declared, estimated or unknown. */
function badge(certainty) {
  const known = ["measured", "declared", "estimated", "unknown"].includes(certainty);
  const kind = known ? certainty : "unstated";
  const text = known ? certainty : "certainty not stated";
  return `<span class="badge badge--${kind}">${esc(text)}</span>`;
}

/** One claim: its value, its certainty badge, and where it comes from. */
function fact(claim) {
  if (!claim) return unknownFact("not in the data");
  const source = SOURCE_NAMES[claim.source] || claim.source;
  const when = claim.as_of ? ` · ${dayAndTime(claim.as_of)}` : "";
  if (claimValueText(claim) === "unknown") return unknownFact(`${source}${when}`);
  return `
    <div class="fact">
      <div class="fact__value">${esc(claimValueText(claim))}</div>
      <div class="fact__meta">${badge(claim.certainty)} <span class="fact__source">${esc(source)}${esc(when)}</span></div>
    </div>`;
}

/** A value that is not there. The cell always reads "unknown" (the badge), never an empty cell. */
function unknownFact(note) {
  return `
    <div class="fact fact--unknown">
      <div class="fact__meta">${badge("unknown")} <span class="fact__source">${esc(note)}</span></div>
    </div>`;
}

/** A value the quote gives without a certainty level. We say so instead of guessing one. */
function unstatedFact(valueText, note) {
  return `
    <div class="fact">
      <div class="fact__value">${esc(valueText)}</div>
      <div class="fact__meta">${badge("unstated")} <span class="fact__source">${esc(note)}</span></div>
    </div>`;
}

/** Allergens. Per the contract they are declared in GS1 Synkka. Missing data is never read as "free from". */
function allergensBlock(allergens, highlight = {}) {
  if (!allergens || allergens.data !== "complete") {
    return `
      <div class="fact fact--unknown">
        <div class="fact__meta">${badge("unknown")} <span class="fact__source">no allergen data: not the same as free from</span></div>
      </div>`;
  }
  const chips = (codes, kind) =>
    codes
      .map((code) => {
        // highlight says which allergens a substitute brings in ("new") or drops ("gone").
        const mark = highlight[code] ? ` chip--${highlight[code]}` : "";
        const note = highlight[code] ? ` <span class="chip__note">${highlight[code] === "new" ? "new" : "goes away"}</span>` : "";
        return `<span class="chip chip--${kind}${mark}">${esc(allergenName(code))}${note}</span>`;
      })
      .join(" ");
  const contains = allergens.contains.length
    ? chips(allergens.contains, "contains")
    : '<span class="muted">nothing declared</span>';
  const freeFrom = allergens.free_from.length
    ? `<div class="allergens__row"><span class="allergens__label">Free from</span> ${chips(allergens.free_from, "free")}</div>`
    : "";
  return `
    <div class="fact">
      <div class="allergens__row"><span class="allergens__label">Contains</span> ${contains}</div>
      ${freeFrom}
      <div class="fact__meta">${badge("declared")} <span class="fact__source">GS1 Synkka</span></div>
    </div>`;
}

function lineTotal(lineItem) {
  const total = (lineItem.totals || []).find((entry) => entry.type === "total");
  return total ? total.amount : null;
}

function checkoutTotal(checkout) {
  const total = (checkout.totals || []).find((entry) => entry.type === "total");
  return total ? total.amount : null;
}

/** The lines of a quote: what, how many, at what price. Used on the offers area and on the approval card. */
function linesTable(checkout, { withStock = false } = {}) {
  const rows = checkout.line_items
    .map((lineItem) => {
      const facts = checkout.aimo.lines[lineItem.id];
      const substitute = facts.substitute_for
        ? `<div class="tag tag--substitute">Substitute for ${esc(facts.substitute_for.product_id)} ${esc(facts.substitute_for.name)}</div>`
        : "";
      return `
        <tr>
          <td>
            <div class="product__name">${esc(lineItem.item.title)}</div>
            <div class="product__id">Product ${esc(lineItem.item.id)}</div>
            ${substitute}
          </td>
          <td class="num">
            <div class="strong">${esc(quantity(lineItem.quantity))} ${esc(facts.sales_unit)}</div>
            <div class="muted">${esc(quantity(facts.base_quantity))} ${esc(facts.base_unit)}</div>
          </td>
          <td class="num">${esc(money(lineItem.item.price, checkout.currency))}<div class="muted">per ${esc(facts.sales_unit)}</div></td>
          ${withStock ? `<td>${fact(facts.stock)}</td>` : ""}
          <td class="num strong">${esc(money(lineTotal(lineItem), checkout.currency))}</td>
        </tr>`;
    })
    .join("");
  return `
    <table class="lines">
      <thead>
        <tr><th>Product</th><th class="num">Quantity</th><th class="num">Unit price</th>${withStock ? "<th>Stock</th>" : ""}<th class="num">Line total</th></tr>
      </thead>
      <tbody>${rows}</tbody>
      <tfoot>
        <tr>
          <td colspan="${withStock ? 4 : 3}">Total${checkout.aimo.totals_exclude_tax ? ", excluding tax" : ""}</td>
          <td class="num total">${esc(money(checkoutTotal(checkout), checkout.currency))}</td>
        </tr>
      </tfoot>
    </table>`;
}

/** A link that keeps mock mode (and the frozen clock) and changes the other settings. */
function mockLink(settings, hash) {
  const next = new URLSearchParams();
  next.set("mock", "1");
  if (params.get("now")) next.set("now", params.get("now"));
  for (const [key, value] of Object.entries(settings)) next.set(key, value);
  return `?${next.toString()}${hash}`;
}

// ---------- 5. Offers ----------

/** The price of one product inside one quote: from a line, or from the list of alternatives. */
function priceInQuote(checkout, productId) {
  for (const facts of Object.values(checkout.aimo.lines)) {
    if (facts.product_id === productId) {
      return { minor: facts.comparison_price_minor, unit: facts.comparison_unit, claim: facts.price, quote: checkout.id };
    }
  }
  const alternative = checkout.aimo.alternatives.find((entry) => entry.product_id === productId);
  if (alternative) {
    return { minor: alternative.comparison_price_minor, unit: alternative.comparison_unit, claim: null, quote: checkout.id };
  }
  return null;
}

function priceFact(price, currency) {
  if (!price) return unknownFact("not in this quote");
  const value = `${esc(money(price.minor, currency))} <span class="per">per ${esc(unitName(price.unit))}</span>`;
  if (!price.claim) {
    return `
    <div class="fact">
      <div class="fact__value">${value}</div>
      <div class="fact__meta">${badge("unstated")} <span class="fact__source">listed as an alternative in the signed quote</span></div>
    </div>`;
  }
  const source = SOURCE_NAMES[price.claim.source] || price.claim.source;
  return `
    <div class="fact">
      <div class="fact__value">${value}</div>
      <div class="fact__meta">${badge(price.claim.certainty)} <span class="fact__source">${esc(source)} · ${esc(dayAndTime(price.claim.as_of))}</span></div>
    </div>`;
}

/**
 * The rows of the comparison table for one quote, in reading order:
 * the lines of the quote, then the alternatives the gateway offers, then the other products found.
 */
function comparisonRows(checkout, products) {
  const cards = new Map(products.map((card) => [card.id, card]));
  const rows = [];
  const seen = new Set();

  for (const lineItem of checkout.line_items) {
    const facts = checkout.aimo.lines[lineItem.id];
    const card = cards.get(facts.product_id);
    seen.add(facts.product_id);
    rows.push({
      id: facts.product_id,
      name: lineItem.item.title,
      brand: card ? card.brand : null,
      role: facts.substitute_for ? `Substitute for ${facts.substitute_for.product_id}` : "In this quote",
      roleKind: facts.substitute_for ? "substitute" : "quoted",
      price: priceInQuote(checkout, facts.product_id),
      deliveryDate: facts.available_date,
      reliability: facts.delivery_reliability,
      carbon: facts.carbon_footprint,
      origin: facts.origin,
      labels: facts.labels,
      nutritionalClaims: card ? card.nutritional_claims : [],
      allergens: facts.allergens,
    });
  }

  const fromCard = (card, role, roleKind) => ({
    id: card.id,
    name: card.name,
    brand: card.brand,
    role,
    roleKind,
    price: priceInQuote(checkout, card.id),
    deliveryDate: null,
    reliability: card.delivery_reliability,
    carbon: card.carbon_footprint,
    origin: card.origin,
    labels: card.labels,
    nutritionalClaims: card.nutritional_claims,
    allergens: card.allergens,
  });

  for (const alternative of checkout.aimo.alternatives) {
    const card = cards.get(alternative.product_id);
    if (seen.has(alternative.product_id) || !card) continue;
    seen.add(alternative.product_id);
    rows.push(fromCard(card, `Alternative: ${alternative.tier}`, "alternative"));
  }
  for (const card of products) {
    if (!seen.has(card.id)) rows.push(fromCard(card, "Also found", "other"));
  }
  return rows;
}

function comparisonTable(checkout, products) {
  const rows = comparisonRows(checkout, products)
    .map((row) => {
      const chips = [...row.labels, ...row.nutritionalClaims]
        .map((code) => `<span class="chip chip--label">${esc(labelName(code))}</span>`)
        .join(" ");
      const date = row.deliveryDate
        ? unstatedFact(dayOnly(row.deliveryDate), "promised in the signed quote")
        : unknownFact("not in this quote");
      return `
        <tr class="row--${esc(row.roleKind)}">
          <td>
            <div class="tag tag--${esc(row.roleKind)}">${esc(row.role)}</div>
            <div class="product__name">${esc(row.name)}</div>
            <div class="product__id">${esc(row.brand || "brand unknown")} · product ${esc(row.id)}</div>
          </td>
          <td>${priceFact(row.price, checkout.currency)}</td>
          <td>${date}</td>
          <td>${fact(row.reliability)}</td>
          <td>${fact(row.carbon)}</td>
          <td>
            <div class="chips">${chips || '<span class="muted">no label listed</span>'}</div>
            <div class="origin">Origin: ${esc(claimValueText(row.origin))} ${badge(row.origin ? row.origin.certainty : "unknown")}</div>
          </td>
          <td>${allergensBlock(row.allergens)}</td>
        </tr>`;
    })
    .join("");
  return `
    <table class="compare">
      <thead>
        <tr>
          <th>Product</th><th>Price</th><th>Delivery date</th><th>Delivery reliability</th>
          <th>Carbon footprint</th><th>Labels and origin</th><th>Allergens</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

/**
 * Has the harness checked Valio's signature on this quote? The page does not check it itself:
 * it reads the harness's answer, from the verdict or from the buyer's audit log.
 * No answer is shown as "not checked yet", never as verified.
 */
function signatureState(quote, audit) {
  const rule = quote.verdict ? quote.verdict.rules.find((entry) => entry.rule_id === "quote-signature") : null;
  if (rule && rule.outcome === "deny") return { kind: "bad", text: "Signature does not match", detail: rule.message };
  if (rule && rule.outcome === "pass") {
    const key = rule.evidence && rule.evidence.kid ? `key ${rule.evidence.kid}` : "";
    return { kind: "ok", text: `Signed by ${quote.checkout.merchant.name}, verified`, detail: key };
  }
  const logged = (audit.buyer || []).find(
    (event) => event.action === "quote_verified" && event.checkout_id === quote.checkout.id,
  );
  if (logged) return { kind: "ok", text: `Signed by ${quote.checkout.merchant.name}, verified`, detail: logged.why };
  return {
    kind: "wait",
    text: `Signed by ${quote.checkout.merchant.name}, not checked yet`,
    detail: "The harness has not been asked to verify this quote.",
  };
}

function signatureLine(state) {
  const icon = { ok: "✓", bad: "✕", wait: "…" }[state.kind];
  return `
    <div class="signature signature--${state.kind}">
      <span class="signature__icon" aria-hidden="true">${icon}</span>
      <div><div class="signature__text">${esc(state.text)}</div><div class="signature__detail">${esc(state.detail)}</div></div>
    </div>`;
}

const VERDICT_WORDS = {
  auto: "The agent's key signs, inside the limits the manager signed beforehand.",
  human: "A person must sign this exact quote on this page.",
  deny: "Nobody signs, so no order exists.",
};

function verdictPanel(quote, data) {
  const verdict = quote.verdict;
  if (!verdict) {
    return `<div class="verdict verdict--none"><div class="verdict__head">No verdict yet</div><p>The agent has not asked to order this quote.</p></div>`;
  }
  const status = quote.status;
  const order = status && status.order_id ? data.orders[status.order_id] : null;
  let outcome = "";
  if (status && status.order_id) {
    const delivery = order ? `, delivery ${dayOnly(order.delivery_date)}` : "";
    outcome = `<p class="verdict__outcome">Order ${esc(status.order_id)} accepted by ${esc(quote.checkout.merchant.name)}${esc(delivery)}.</p>`;
  } else if (status && status.status === "pending_approval") {
    outcome = `<p class="verdict__outcome"><a class="button button--small" href="#/approvals/${esc(status.approval_id)}">Open the approval</a></p>`;
  }
  // Act 4: the copy shown to the harness does not carry the total Valio signed.
  const signedTotal = checkoutTotal(quote.checkout);
  const changed =
    verdict.decision === "deny" && verdict.total_minor !== signedTotal
      ? `<p class="verdict__outcome">The copy presented said ${esc(money(verdict.total_minor, verdict.currency))}. ${esc(quote.checkout.merchant.name)} signed ${esc(money(signedTotal, quote.checkout.currency))}.</p>`
      : "";
  const rules = verdict.rules
    .map(
      (rule) => `
        <li class="rule rule--${esc(rule.outcome)}">
          <span class="rule__outcome">${esc(rule.outcome)}</span>
          <span class="rule__id">${esc(rule.rule_id)}</span>
          <span class="rule__message">${esc(rule.message)}</span>
        </li>`,
    )
    .join("");
  const passed = verdict.rules.filter((rule) => rule.outcome === "pass").length;
  return `
    <div class="verdict verdict--${esc(verdict.decision)}">
      <div class="verdict__head">Verdict: ${esc(verdict.decision)}</div>
      <p>${esc(VERDICT_WORDS[verdict.decision] || "")}</p>
      ${changed}
      ${outcome}
      <details class="rules"${verdict.decision === "auto" ? "" : " open"}>
        <summary>Rules checked: ${verdict.rules.length}, passed: ${passed}</summary>
        <ul>${rules}</ul>
      </details>
    </div>`;
}

function shortfallPanel(checkout, products) {
  if (!checkout.aimo.shortfalls.length) return "";
  const names = new Map(products.map((card) => [card.id, card.name]));
  const shortfalls = checkout.aimo.shortfalls
    .map(
      (shortfall) => `
        <p class="shortfall__line">
          Product ${esc(shortfall.product_id)}: asked ${esc(quantity(shortfall.requested_base_quantity))} ${esc(shortfall.base_unit)},
          available ${esc(quantity(shortfall.available_base_quantity))} ${esc(shortfall.base_unit)},
          <strong>missing ${esc(quantity(shortfall.missing_base_quantity))} ${esc(shortfall.base_unit)}</strong>
          (${esc(shortfall.reason.replaceAll("_", " "))}).
        </p>`,
    )
    .join("");
  const alternatives = checkout.aimo.alternatives
    .map(
      (alternative) => `
        <li class="alternative${alternative.chosen ? " alternative--chosen" : ""}">
          <span class="tier tier--${esc(alternative.tier)}">${esc(alternative.tier)}</span>
          <div class="alternative__body">
            <div class="product__name">${esc(names.get(alternative.product_id) || `Product ${alternative.product_id}`)}</div>
            <div class="alternative__why">${esc(alternative.why)}</div>
          </div>
          <div class="alternative__price">${esc(money(alternative.comparison_price_minor, checkout.currency))}<span class="muted"> per ${esc(unitName(alternative.comparison_unit))}</span></div>
          <div class="alternative__chosen">${alternative.chosen ? "Chosen by the gateway" : ""}</div>
        </li>`,
    )
    .join("");
  return `
    <section class="panel shortfall">
      <h3>Not enough stock: substitutes ranked by the gateway</h3>
      ${shortfalls}
      <ol class="alternatives">${alternatives}</ol>
    </section>`;
}

function offersView(data) {
  const quote = data.quotes.find((entry) => entry.key === params.get("quote")) || data.quotes[0];
  const checkout = quote.checkout;
  const picker = data.quotes
    .map((entry) => {
      const asked = entry.checkout.aimo.requested
        .map((need) => `${quantity(need.amount)} ${need.unit} of ${need.product_id}`)
        .join(", ");
      const current = entry === quote ? ' aria-current="true"' : "";
      return `<a class="pick"${current} href="${esc(mockLink({ quote: entry.key }, "#/offers"))}"><span class="pick__label">${esc(entry.label)}</span><span class="pick__hint">${esc(entry.hint || asked)}</span></a>`;
    })
    .join("");
  const asked = checkout.aimo.requested
    .map((need) => `${quantity(need.amount)} ${unitName(need.unit)}s of product ${need.product_id}`)
    .join(", ");

  return `
    <nav class="picker" aria-label="Quote">${picker}</nav>

    <section class="panel quote">
      <div class="quote__head">
        <div>
          <h2>Quote <span class="mono">${esc(checkout.id)}</span></h2>
          <p class="quote__asked">Asked: ${esc(asked)}, delivered by ${esc(dayOnly(checkout.aimo.requested_delivery_date))}.</p>
        </div>
        ${signatureLine(signatureState(quote, data.audit))}
      </div>
      ${linesTable(checkout, { withStock: true })}
      <dl class="keyfacts">
        <div><dt>Delivery</dt><dd>${esc(dayOnly(checkout.aimo.delivery_date))}</dd></div>
        <div><dt>Order cut-off</dt><dd>${esc(dayAndTime(checkout.aimo.closing_time))}</dd></div>
        <div><dt>Price held until</dt><dd>${esc(dayAndTime(checkout.expires_at))}</dd></div>
      </dl>
      ${verdictPanel(quote, data)}
    </section>

    ${shortfallPanel(checkout, data.products)}

    <section class="panel">
      <h3>Comparison</h3>
      <p class="legend">
        Every fact states how sure it is:
        ${badge("measured")} counted or recorded by Valio
        ${badge("declared")} stated by a supplier
        ${badge("estimated")} derived, not specific to the product
        ${badge("unknown")} no data
      </p>
      <div class="scroll">${comparisonTable(checkout, data.products)}</div>
    </section>`;
}

// ---------- 6. Approvals ----------

const STATUS_WORDS = {
  pending: "Waiting for your signature",
  approved: "Approved and signed",
  rejected: "Rejected",
  expired: "Expired",
};

/** Everything known about one product: from the lines of the quotes first (signed), then from the product cards. */
function productFacts(productId, data, ownCheckout) {
  const checkouts = [ownCheckout, ...data.quotes.map((quote) => quote.checkout)].filter(Boolean);
  let found = null;
  let price = null;
  for (const checkout of checkouts) {
    for (const lineItem of checkout.line_items) {
      const facts = checkout.aimo.lines[lineItem.id];
      if (facts.product_id === productId && !found) {
        found = {
          name: lineItem.item.title,
          allergens: facts.allergens,
          carbon: facts.carbon_footprint,
          origin: facts.origin,
          reliability: facts.delivery_reliability,
        };
      }
    }
    if (!price && priceInQuote(checkout, productId)) {
      price = { ...priceInQuote(checkout, productId), currency: checkout.currency };
    }
  }
  const card = data.products.find((entry) => entry.id === productId);
  if (!found && card) {
    found = {
      name: card.name,
      allergens: card.allergens,
      carbon: card.carbon_footprint,
      origin: card.origin,
      reliability: card.delivery_reliability,
    };
  }
  return { id: productId, brand: card ? card.brand : null, price, ...(found || { name: `Product ${productId}` }) };
}

/** Which product replaces which, read from the reasons and the judge's answers. */
function substitutionPairs(approval) {
  const pairs = new Map();
  for (const reason of approval.reasons) {
    const evidence = reason.evidence || {};
    if (evidence.original && evidence.substitute) {
      pairs.set(`${evidence.original}>${evidence.substitute}`, [evidence.original, evidence.substitute]);
    }
  }
  for (const answer of approval.judge || []) {
    pairs.set(`${answer.subject.original}>${answer.subject.candidate}`, [answer.subject.original, answer.subject.candidate]);
  }
  return [...pairs.values()];
}

function carbonCell(claim, largest) {
  const known = claim && typeof claim.value === "number";
  const width = known && largest > 0 ? Math.max(4, Math.round((claim.value / largest) * 100)) : 0;
  return `${fact(claim)}${known ? `<div class="bar"><div class="bar__fill" style="width:${width}%"></div></div>` : ""}`;
}

function substitutionCompare(originalId, substituteId, data, checkout) {
  const original = productFacts(originalId, data, checkout);
  const substitute = productFacts(substituteId, data, checkout);
  const before = original.allergens && original.allergens.data === "complete" ? original.allergens.contains : null;
  const after = substitute.allergens && substitute.allergens.data === "complete" ? substitute.allergens.contains : null;

  // Which allergens go away and which come in. Only said when both lists are known.
  let change = '<p class="change change--unknown">Allergen data is missing for one of the two products: treat the change as unknown.</p>';
  const gone = {};
  const added = {};
  if (before && after) {
    before.filter((code) => !after.includes(code)).forEach((code) => (gone[code] = "gone"));
    after.filter((code) => !before.includes(code)).forEach((code) => (added[code] = "new"));
    const goneNames = Object.keys(gone).map(allergenName).join(", ");
    const addedNames = Object.keys(added).map(allergenName).join(", ");
    change =
      goneNames || addedNames
        ? `<p class="change">The allergens change.${addedNames ? ` New: <strong>${esc(addedNames)}</strong>.` : ""}${goneNames ? ` No longer there: <strong>${esc(goneNames)}</strong>.` : ""}</p>`
        : '<p class="change change--same">Same declared allergens.</p>';
  }

  const carbonValues = [original.carbon, substitute.carbon].map((claim) => (claim && typeof claim.value === "number" ? claim.value : null));
  const largest = Math.max(...carbonValues.map((value) => value || 0));
  let carbonNote = "";
  if (carbonValues[0] && carbonValues[1] !== null) {
    const percent = Math.round(((carbonValues[1] - carbonValues[0]) / carbonValues[0]) * 100);
    carbonNote = percent === 0 ? "same as the original" : `${Math.abs(percent)}% ${percent < 0 ? "lower" : "higher"} than the original`;
  }

  const priceCell = (product) =>
    product.price
      ? `${priceFact(product.price, product.price.currency)}<div class="muted small">from quote ${esc(product.price.quote)}</div>`
      : unknownFact("not in a signed quote");
  const head = (product, title) => `
    <div class="versus__head">
      <div class="versus__title">${esc(title)}</div>
      <div class="product__name">${esc(product.name)}</div>
      <div class="product__id">${esc(product.brand || "brand unknown")} · product ${esc(product.id)}</div>
    </div>`;

  return `
    ${change}
    <div class="versus">
      <div class="versus__corner"></div>
      ${head(original, "Asked for")}
      ${head(substitute, "Proposed instead")}

      <div class="versus__label">Allergens</div>
      <div>${allergensBlock(original.allergens, gone)}</div>
      <div>${allergensBlock(substitute.allergens, added)}</div>

      <div class="versus__label">Carbon footprint</div>
      <div>${carbonCell(original.carbon, largest)}</div>
      <div>${carbonCell(substitute.carbon, largest)}${carbonNote ? `<div class="delta">${esc(carbonNote)}</div>` : ""}</div>

      <div class="versus__label">Price</div>
      <div>${priceCell(original)}</div>
      <div>${priceCell(substitute)}</div>

      <div class="versus__label">Origin</div>
      <div>${fact(original.origin)}</div>
      <div>${fact(substitute.origin)}</div>

      <div class="versus__label">Delivery reliability</div>
      <div>${fact(original.reliability)}</div>
      <div>${fact(substitute.reliability)}</div>
    </div>`;
}

/** One answer of the judge, as a bar from 0 to 100% with the two thresholds marked. */
function judgeBar(answer) {
  const percent = (value) => Math.round(value * 100);
  if (answer.probability === null || answer.probability === undefined) {
    return `
      <div class="judge">
        <div class="judge__question">${esc(answer.instructions)}</div>
        <p class="judge__reading judge__reading--human">The judge did not answer: a human decides.</p>
      </div>`;
  }
  let reading = "the judge is unsure";
  let zone = "unsure";
  if (answer.probability >= answer.auto_threshold) {
    reading = "accepted by the judge";
    zone = "yes";
  } else if (answer.probability < answer.floor) {
    reading = "clearly no";
    zone = "no";
  }
  const confidence =
    answer.confidence === null || answer.confidence === undefined ? "" : ` · confidence ${percent(answer.confidence)}%`;
  return `
    <div class="judge">
      <div class="judge__question">${esc(answer.instructions)}</div>
      <div class="judge__row">
        <div class="judge__value judge__value--${zone}">${percent(answer.probability)}%<span class="judge__unit"> yes</span></div>
        <div class="judge__track" role="img" aria-label="Probability of yes: ${percent(answer.probability)} percent">
          <div class="judge__zone judge__zone--no" style="width:${percent(answer.floor)}%"></div>
          <div class="judge__zone judge__zone--unsure" style="width:${percent(answer.auto_threshold - answer.floor)}%"></div>
          <div class="judge__zone judge__zone--yes" style="width:${percent(1 - answer.auto_threshold)}%"></div>
          <div class="judge__marker" style="left:${percent(answer.probability)}%"></div>
        </div>
      </div>
      <div class="judge__scale">
        <span>below ${percent(answer.floor)}%: a clear no</span>
        <span>in between: unsure, a human decides</span>
        <span>from ${percent(answer.auto_threshold)}%: accepted</span>
      </div>
      <p class="judge__reading judge__reading--${zone}">Reading: ${esc(reading)} · model ${esc(answer.model)}${esc(confidence)}</p>
    </div>`;
}

function spendMeter(reason, currency) {
  const evidence = reason.evidence || {};
  if (typeof evidence.total_minor !== "number" || typeof evidence.limit_minor !== "number") return "";
  const largest = Math.max(evidence.total_minor, evidence.limit_minor);
  const width = (value) => Math.round((value / largest) * 100);
  return `
    <div class="meter">
      <div class="meter__row"><span class="meter__label">This order</span><div class="bar bar--over"><div class="bar__fill" style="width:${width(evidence.total_minor)}%"></div></div><span class="meter__value">${esc(money(evidence.total_minor, currency))}</span></div>
      <div class="meter__row"><span class="meter__label">Agent alone, up to</span><div class="bar"><div class="bar__fill" style="width:${width(evidence.limit_minor)}%"></div></div><span class="meter__value">${esc(money(evidence.limit_minor, currency))}</span></div>
    </div>`;
}

function reasonsBlock(approval) {
  const reasons = approval.reasons
    .map(
      (reason) => `
        <li class="reason">
          <div class="reason__title">${esc(RULE_TITLES[reason.rule_id] || reason.rule_id)}</div>
          <div class="reason__message">${esc(reason.message)}</div>
          <div class="reason__rule">rule <span class="mono">${esc(reason.rule_id)}</span></div>
          ${reason.rule_id === "spend-limit" ? spendMeter(reason, approval.currency) : ""}
        </li>`,
    )
    .join("");
  return `<ul class="reasons">${reasons || '<li class="reason">No reason given by the harness.</li>'}</ul>`;
}

/** The bottom of the card: the countdown and the two buttons while pending, the outcome afterwards. */
function decisionBlock(approval) {
  const who = esc(approval.decided_by || "unknown");
  const when = esc(dayAndTime(approval.decided_at));
  if (approval.status === "approved") {
    const order = approval.order_id ? `Order ${esc(approval.order_id)} placed with Valio Aimo.` : "No order number yet.";
    return `
      <div class="outcome outcome--approved">
        <div class="outcome__title">✓ Approved and signed</div>
        <p>By ${who} on ${when}. The signature covers this exact quote and no other.</p>
        <p>${order}</p>
      </div>`;
  }
  if (approval.status === "rejected") {
    return `
      <div class="outcome outcome--rejected">
        <div class="outcome__title">✕ Rejected</div>
        <p>By ${who} on ${when}. Nothing was signed, nothing was ordered.</p>
      </div>`;
  }
  if (approval.status === "expired") {
    return `
      <div class="outcome outcome--expired">
        <div class="outcome__title">Expired</div>
        <p>No answer before the order cut-off (${esc(dayAndTime(approval.deadline))}). Nothing was signed, nothing was ordered.</p>
      </div>`;
  }
  const countdown = approval.deadline
    ? `
      <div class="countdown" data-deadline="${esc(approval.deadline)}">
        <div class="countdown__digits">${esc(countdownText(Date.parse(approval.deadline) - now()))}</div>
        <div class="countdown__label">left to decide · order cut-off ${esc(dayAndTime(approval.deadline))}</div>
      </div>`
    : `<div class="countdown"><div class="countdown__label">No deadline given.</div></div>`;
  return `
    <div class="decide">
      ${countdown}
      <div class="decide__buttons">
        <button class="button button--approve" data-decision="approve" data-approval="${esc(approval.approval_id)}">Approve and sign</button>
        <button class="button button--reject" data-decision="reject" data-approval="${esc(approval.approval_id)}">Reject</button>
      </div>
    </div>`;
}

function approvalCard(entry, data) {
  const approval = entry.approval;
  const pairs = substitutionPairs(approval);
  const lines = entry.checkout
    ? linesTable(entry.checkout)
    : `<p class="missing">The lines of quote <span class="mono">${esc(approval.checkout_id)}</span> are not in the example files. The total below comes from the harness.</p>`;
  const delivery = entry.checkout ? dayOnly(entry.checkout.aimo.delivery_date) : "unknown";
  const substitution = pairs
    .map(([originalId, substituteId]) => substitutionCompare(originalId, substituteId, data, entry.checkout))
    .join("");
  const judge = (approval.judge || []).length
    ? `
      <h3>What the judge said</h3>
      <p class="preferences"><span class="preferences__label">The buyer's wishes, as the judge reads them:</span> “${esc(data.policy.substitution.preferences_text)}”</p>
      ${approval.judge.map(judgeBar).join("")}`
    : "";

  return `
    <article class="card card--${esc(approval.status)}" id="${esc(approval.approval_id)}">
      <header class="card__head">
        <span class="status status--${esc(approval.status)}">${esc(STATUS_WORDS[approval.status] || approval.status)}</span>
        <span class="card__ids">Approval <span class="mono">${esc(approval.approval_id)}</span> · quote <span class="mono">${esc(approval.checkout_id)}</span></span>
      </header>

      <p class="card__request">The agent was asked: <q>${esc(approval.request_text)}</q> <span class="muted">${esc(dayAndTime(approval.requested_at))}</span></p>

      <h3>Why this needs you</h3>
      ${reasonsBlock(approval)}

      ${substitution ? `<h3>What changes</h3>${substitution}` : ""}
      ${judge}

      <h3>The order</h3>
      ${lines}
      <dl class="keyfacts">
        ${entry.checkout ? "" : `<div><dt>Total</dt><dd>${esc(money(approval.total_minor, approval.currency))}</dd></div>`}
        <div><dt>Delivery</dt><dd>${esc(delivery)}</dd></div>
        <div><dt>You sign quote</dt><dd class="mono" title="${esc(approval.checkout_hash)}">${esc(shortHash(approval.checkout_hash))}</dd></div>
      </dl>

      ${decisionBlock(approval)}
    </article>`;
}

function approvalsView(data, focusId) {
  let entries = data.approvals;
  if (focusId && entries.some((entry) => entry.approval.approval_id === focusId)) {
    entries = entries.filter((entry) => entry.approval.approval_id === focusId);
  } else if (CASES.includes(params.get("case"))) {
    entries = entries.filter((entry) => entry.kind === params.get("case"));
  }
  if (!entries.length) return '<section class="panel"><h2>Nothing to approve</h2><p>No order is waiting for a signature.</p></section>';
  return `
    <p class="intro">An order above the agent's limits only exists if you sign it here. The agent cannot reach this page.</p>
    ${entries.map((entry) => approvalCard(entry, data)).join("")}`;
}

// ---------- 7. Audit ----------

const ACTOR_NAMES = { agent: "Agent", harness: "Harness", human: "Human", merchant: "Valio Aimo" };

/** Does each line carry the hash of the line before it? This checks the links, not the hashes themselves. */
function chainState(events) {
  const ordered = [...events].sort((a, b) => a.seq - b.seq);
  for (let index = 0; index < ordered.length; index += 1) {
    const expected = index === 0 ? null : ordered[index - 1].hash;
    if ((ordered[index].prev_hash ?? null) !== expected) return { ok: false, brokenAt: ordered[index].seq };
  }
  return { ok: true, brokenAt: null };
}

function auditEvent(event) {
  return `
    <li class="event">
      <div class="event__time">${esc(clockTime(event.at))}</div>
      <div class="event__body">
        <div class="event__who"><span class="actor actor--${esc(event.actor)}">${esc(ACTOR_NAMES[event.actor] || event.actor)}</span> <span class="event__action">${esc(String(event.action).replaceAll("_", " "))}</span></div>
        <div class="event__what">${esc(event.what)}</div>
        <div class="event__why"><span class="event__label">Why</span> ${esc(event.why)}</div>
        <div class="event__foot">
          <span><span class="event__label">Rule</span> ${event.rule ? `<span class="mono">${esc(event.rule)}</span>` : "none"}</span>
          <span class="event__chain mono" title="This line's hash, and the hash of the line before it">#${esc(event.seq)} · ${esc(event.hash)} ← ${esc(event.prev_hash || "start")}</span>
        </div>
      </div>
    </li>`;
}

/** Group both logs by quote, in the order the quotes first appear. */
function auditGroups(audit) {
  const all = [...(audit.buyer || []), ...(audit.merchant || [])].sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  const ids = [...new Set(all.map((event) => event.checkout_id || ""))];
  return ids.map((id) => {
    const mine = (events) => (events || []).filter((event) => (event.checkout_id || "") === id).sort((a, b) => a.seq - b.seq);
    const buyer = mine(audit.buyer);
    const merchant = mine(audit.merchant);
    const hashes = new Set([...buyer, ...merchant].map((event) => event.checkout_hash).filter(Boolean));
    return { id, buyer, merchant, hashes: [...hashes] };
  });
}

function auditView(data) {
  const sides = [
    { key: "buyer", title: "Buyer", sub: "the harness's log" },
    { key: "merchant", title: "Valio Aimo", sub: "the gateway's log" },
  ];
  const heads = sides
    .map((side) => {
      const events = data.audit[side.key] || [];
      const chain = chainState(events);
      const chainText = chain.ok ? "each line links to the one before" : `chain broken at line ${chain.brokenAt}`;
      return `
        <div class="audit__head">
          <h2>${esc(side.title)}</h2>
          <div class="audit__sub">${esc(side.sub)} · ${events.length} lines · <span class="${chain.ok ? "ok" : "bad"}">${esc(chainText)}</span></div>
        </div>`;
    })
    .join("");

  const groups = auditGroups(data.audit)
    .map((group) => {
      const sameHash = group.buyer.length && group.merchant.length && group.hashes.length === 1;
      let hashNote = '<span class="muted">only one side has lines for this quote</span>';
      if (sameHash) hashNote = '<span class="ok">✓ both logs name the same signed quote</span>';
      else if (group.hashes.length > 1) hashNote = '<span class="bad">✕ the two logs do not name the same quote hash</span>';
      const column = (events) =>
        events.length ? `<ol class="events">${events.map(auditEvent).join("")}</ol>` : '<p class="muted events--empty">No line on this side.</p>';
      return `
        <section class="audit__group">
          <header class="audit__quote">
            <span>${group.id ? `Quote <span class="mono">${esc(group.id)}</span>` : "Not tied to a quote"}</span>
            ${group.hashes.length === 1 ? `<span class="mono muted" title="${esc(group.hashes[0])}">hash ${esc(shortHash(group.hashes[0]))}</span>` : ""}
            ${hashNote}
          </header>
          <div class="audit__columns">${column(group.buyer)}${column(group.merchant)}</div>
        </section>`;
    })
    .join("");

  return `
    <p class="intro">Each side keeps its own log, and keeps the piece signed by the other. The two back each other up.</p>
    <div class="audit__columns audit__columns--head">${heads}</div>
    ${groups || '<section class="panel"><p>No audit line yet.</p></section>'}`;
}

// ---------- 8. Routing, the clock, and the start ----------

let data = null;

/** "#/approvals/apr_7c1e0b52" -> { view: "approvals", id: "apr_7c1e0b52" } */
function currentRoute() {
  const parts = window.location.hash.replace(/^#\/?/, "").split("/");
  if (VIEWS.includes(parts[0])) return { view: parts[0], id: parts[1] || null };
  // A rehearsal link like ?mock=1&state=expired opens the approvals directly.
  return { view: params.has("state") || params.has("case") ? "approvals" : "offers", id: null };
}

function render() {
  const route = currentRoute();
  const app = document.getElementById("app");
  if (route.view === "offers") app.innerHTML = offersView(data);
  if (route.view === "approvals") app.innerHTML = approvalsView(data, route.id);
  if (route.view === "audit") app.innerHTML = auditView(data);
  app.dataset.view = route.view;

  for (const tab of document.querySelectorAll(".tab")) {
    if (tab.dataset.view === route.view) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
  }
  const pending = data.approvals.filter((entry) => entry.approval.status === "pending").length;
  const count = document.getElementById("pending-count");
  count.textContent = pending;
  count.hidden = pending === 0;
}

/** Every second: refresh the countdowns, and let a pending approval expire when its deadline passes. */
function tick() {
  let expiredNow = false;
  for (const entry of data.approvals) {
    const approval = entry.approval;
    if (approval.status === "pending" && approval.deadline && Date.parse(approval.deadline) <= now()) {
      // Mock mode only. In live mode the harness decides when an approval expires and the page reads it.
      setMockState(entry, "expired", data.policy);
      expiredNow = true;
    }
  }
  if (expiredNow) return render();
  for (const element of document.querySelectorAll("[data-deadline]")) {
    const left = Date.parse(element.dataset.deadline) - now();
    element.querySelector(".countdown__digits").textContent = countdownText(left);
    element.classList.toggle("countdown--urgent", left < 60 * 60 * 1000);
  }
}

/** A click on "Approve and sign" or "Reject". In mock mode the card changes on this page only. */
function onDecision(event) {
  const button = event.target.closest("[data-decision]");
  if (!button) return;
  const entry = data.approvals.find((candidate) => candidate.approval.approval_id === button.dataset.approval);
  if (!entry || entry.approval.status !== "pending") return;
  const state = button.dataset.decision === "approve" ? "approved" : "rejected";
  setMockState(entry, state, data.policy, new Date(now()).toISOString());
  render();
}

/** The strip at the bottom in mock mode: one link per screen, to rehearse. */
function rehearsalStrip() {
  const group = (title, links) =>
    `<span class="rehearsal__group"><span class="rehearsal__title">${esc(title)}</span>${links
      .map(([text, href]) => `<a href="${esc(href)}">${esc(text)}</a>`)
      .join("")}</span>`;
  const states = (caseName) => STATES.map((state) => [state, mockLink({ case: caseName, state }, "#/approvals")]);
  return `
    <span class="rehearsal__note">Example data from contract/examples. Nothing is checked or signed for real in mock mode.</span>
    ${group("Offers", data.quotes.map((quote) => [quote.label, mockLink({ quote: quote.key }, "#/offers")]))}
    ${group("Spend approval", states("spend"))}
    ${group("Substitution approval", states("substitution"))}
    ${group("Audit", [["both logs", mockLink({}, "#/audit")]])}`;
}

function showMessage(title, text) {
  document.getElementById("app").innerHTML = `<section class="panel message"><h2>${esc(title)}</h2><p>${text}</p></section>`;
}

async function start() {
  if (!MOCK) {
    showMessage(
      "Live mode is not built yet",
      'This page reads the example files for now. Open it with <a href="?mock=1">?mock=1</a>. The live routes of the gateway and the harness arrive in step C4.',
    );
    return;
  }
  try {
    data = await loadMockData();
  } catch (error) {
    showMessage(
      "The example files could not be read",
      `${esc(error.message)}<br />Start a web server from the root of the repo, <code>python3 -m http.server 8003</code>, then open <code>http://localhost:8003/surface/static/index.html?mock=1</code>.`,
    );
    return;
  }

  // ?state=approved puts the approvals in that state, so every screen can be reached by a link.
  const state = params.get("state");
  if (STATES.includes(state)) {
    for (const entry of data.approvals) setMockState(entry, state, data.policy);
  }

  document.getElementById("buyer-line").textContent = `Buyer: ${data.policy.customer} · approver: ${data.policy.approver}`;
  const strip = document.getElementById("rehearsal");
  strip.innerHTML = rehearsalStrip();
  strip.hidden = false;

  document.getElementById("app").addEventListener("click", onDecision);
  window.addEventListener("hashchange", render);
  render();
  tick();
  setInterval(tick, 1000);
}

if (IN_BROWSER) {
  start();
} else {
  // Loaded by Node in tests/test_surface_static.py: hand over the functions that have no page to draw on.
  module.exports = {
    esc,
    money,
    dayAndTime,
    dayOnly,
    countdownText,
    claimValueText,
    buildMockData,
    setMockState,
    comparisonRows,
    signatureState,
    substitutionPairs,
    chainState,
    auditGroups,
    offersView,
    approvalsView,
    auditView,
  };
}
