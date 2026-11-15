/*
 * The pieces every screen is made of: the assistant's card (its work, line by line, and who signed),
 * the order's lines, the rules that guard it, the bar with the total, and the proof panel.
 * Each function returns HTML as text. Everything from the data goes through esc().
 */

import {
  ASSISTANT,
  WHO,
  SHORTFALL_WORDS,
  JUDGE_WORDS,
  OUTCOME_WORDS,
  esc,
  icon,
  money,
  qty,
  num,
  dayLong,
  clock,
  words,
  shortProof,
  allergenText,
  allergenNames,
  stockText,
  kgCo2,
  lexicon,
  plural,
} from "./core.js";
import {
  app,
  status,
  hasRun,
  finished,
  isAttack,
  missingLines,
  orderOnScreen,
  revealing,
  canEdit,
  pendingApproval,
  limitKnown,
  limitText,
  quoteTotal,
  ecoNow,
  ecoOffer,
  swappedLines,
  savedByPercent,
  kitchenName,
  workLog,
  runSeconds,
  seals,
  checkLine,
  tradeOffs,
  storageText,
} from "./state.js";

/* ---------- Small pieces ---------- */

const PILL = {
  accepted: ["ok", "Accepted"],
  delivered: ["ok", "Delivered"],
  working: ["info", "In progress"],
  needs_you: ["warn", "Needs you"],
  rejected: ["bad", "Rejected"],
  expired: ["bad", "Expired"],
  blocked: ["bad", "Blocked"],
  refused: ["bad", "Refused"],
};
export const pill = (key, label) => {
  const [tone, text] = PILL[key] ?? ["info", words(key)];
  return `<span class="pill pill--${tone}">${esc(label ?? text)}</span>`;
};

/* Who did it: you, Aimo, Valio, or the checks that run in code. One small chip, always the same four. */
export const whoChip = (who) => {
  const tone = { manager: "you", human: "you", agent: "aimo", merchant: "valio", none: "checks", harness: "checks" }[who] ?? "checks";
  return `<span class="who who--${tone}">${esc(WHO[who] ?? who)}</span>`;
};

/* How an order was signed, for the tables: the answer to "who signs?" in three words. */
export function signedBy(signer, decision) {
  if (signer === "agent") return `${whoChip("agent")}<span class="muted">inside your limit</span>`;
  if (signer === "human" || signer === "manager") return `${whoChip("manager")}<span class="muted">on this page</span>`;
  if (decision === "deny") return '<span class="muted">Nobody: blocked by a rule</span>';
  return '<span class="muted">Nobody</span>';
}

const LOG_ICON = { done: "check", waiting: "pen", refused: "cross", skipped: "skip", pending: "dot", next: "dot", working: "dot" };

/* ---------- The assistant's card ---------- */

function agentState() {
  if (app.busy && !hasRun()) return ["working", "Working"];
  if (!hasRun()) return missingLines().length ? ["ready", "Order ready to send"] : ["ready", "Nothing to order"];
  if (revealing() || status() === "running") return ["working", "Working"];
  if (status() === "waiting_for_human") return ["waiting", "Waiting for you"];
  if (status() === "done") return ["done", "Done: order accepted"];
  return ["refused", isAttack() ? "Stopped by Valio" : "Stopped: nothing ordered"];
}

/* One line of work: what was done, by whom, and on the right the protocol's word with the start of the proof. */
function logLine(line) {
  const proof = line.proof ? `<span class="log__proof mono" title="${esc(line.proof)}">${esc(shortProof(line.proof))}</span>` : "";
  const full = line.more ?? line.detail ?? "";
  return `<li class="log__line log__line--${esc(line.tone)}${line.fresh ? " is-fresh" : ""}">
      <span class="log__dot">${line.tone === "working" ? '<span class="spinner"></span>' : icon(LOG_ICON[line.tone] ?? "dot", 14)}</span>
      <span class="log__who">${line.who ? whoChip(line.who) : ""}</span>
      <div class="log__body">
        <p class="log__head">${esc(line.head)}</p>
        ${line.detail ? `<p class="log__detail" title="${esc(full)}">${esc(line.detail)}</p>` : ""}
      </div>
      ${line.term ? `<span class="log__side"><span class="log__term">${esc(line.term)}</span>${proof}</span>` : ""}
    </li>`;
}

function sealsBlock() {
  const items = seals()
    .map(
      (seal) => `<div class="seal seal--${esc(seal.tone)}${seal.fresh ? " is-fresh" : ""}">
        <span class="seal__who">${esc(seal.who)}</span>
        <span class="seal__says">${esc(seal.says)}</span>
        ${seal.proof ? `<span class="seal__proof mono" title="${esc(seal.proof)}">${esc(shortProof(seal.proof, 12))}</span>` : '<span class="seal__proof seal__proof--none">no signature</span>'}
      </div>`
    )
    .join("");
  return `<div class="seals" aria-label="Who signed">${items}</div>`;
}

/* The last exchange with the assistant, and the field to ask. One answer on screen, never a scrolling conversation. */
function askBlock() {
  const { busy, question, answer, changes, failed } = app.ask;
  const last = question
    ? `<div class="ask__last">
        <p class="ask__q">${esc(question)}</p>
        ${busy ? '<p class="ask__a"><span class="spinner"></span> Thinking</p>' : `<p class="ask__a${failed ? " ask__a--failed" : ""}">${esc(answer)}</p>`}
        ${changes.length ? `<ul class="ask__changes">${changes.map((change) => `<li>${icon("check", 14)}${esc(change)}</li>`).join("")}</ul>` : ""}
      </div>`
    : "";
  const placeholder = app.up.assistant ? "Ask Aimo, or say what changed in the stock" : "Aimo's chat is not running";
  return `<div class="ask">
      ${last}
      <form class="ask__form" id="ask" autocomplete="off">
        <label class="visually-hidden" for="ask-text">Message to ${ASSISTANT}</label>
        <input class="ask__text" id="ask-text" name="text" type="text" maxlength="500" placeholder="${esc(placeholder)}" ${busy ? "disabled" : ""} />
        <button class="ask__send" type="submit" aria-label="Send" ${busy ? "disabled" : ""}>${icon("send", 16)}</button>
      </form>
    </div>`;
}

/* The order Valio accepted, in one line under the seals. */
function receiptNote() {
  const order = app.state?.order;
  if (!order || app.shown < 7) return "";
  return `<div class="receipt">
      <p class="receipt__line">${icon("check", 16)}<span><b>Order ${esc(order.order_id)}</b> accepted by Valio Aimo</span></p>
      <p class="receipt__facts">${esc(money(order.total_minor, order.currency))} before tax · delivery ${esc(dayLong(order.delivery_date))} · ${order.payment?.sandbox ? "test payment, no real money" : "payment booked"}</p>
      <div class="receipt__actions">
        <button class="btn btn--quiet" type="button" data-proof="current">View proof</button>
        <a class="btn btn--quiet" href="#/orders">Follow the delivery</a>
      </div>
    </div>`;
}

/*
 * The assistant's card. `cta` is the button of the screen it sits on, when that screen wants it inside the card.
 * Before an order: what it prepared and what it will do. During: each step as it happens. After: who signed.
 */
export function agentCard({ cta = "", ask = true, title = null, compact = false } = {}) {
  const [tone, label] = agentState();
  const lines = workLog();
  if (app.busy && !hasRun()) lines.push({ key: "wait", tone: "working", who: "agent", head: "Asking Valio Aimo for a signed quote" });
  else if (!hasRun() && missingLines().length) {
    lines.push({
      key: "next",
      tone: "next",
      head: "Next, when you send it",
      detail: `Ask Valio Aimo for a signed quote, run your safety checks, and sign only if they all pass${limitKnown() ? ` and the total stays under ${limitText()}` : ""}.`,
    });
  }
  const seconds = finished() && !revealing() ? runSeconds() : null;
  const steps = hasRun() ? app.shown : 0;
  const meta = steps ? `${plural(steps, "step", "steps")}${seconds !== null ? ` · ${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s` : ""}` : "";
  return `<section class="agent agent--${tone}${compact ? " agent--compact" : ""}" aria-label="${ASSISTANT}, your purchasing assistant">
      <header class="agent__head">
        <span class="agent__mark">${icon("spark", 18)}</span>
        <div class="agent__id">
          <p class="agent__name">${esc(title ?? ASSISTANT)}</p>
          <p class="agent__state"><span class="agent__light"></span>${esc(label)}</p>
        </div>
        ${meta ? `<span class="agent__meta">${esc(meta)}</span>` : ""}
      </header>
      ${hasRun() && app.shown >= 1 ? sealsBlock() : ""}
      ${receiptNote()}
      <ol class="log" aria-live="polite">${lines.map(logLine).join("")}</ol>
      ${cta ? `<div class="agent__cta">${cta}</div>` : ""}
      ${ask && !isAttack() ? askBlock() : ""}
    </section>`;
}

/* ---------- The order's lines ---------- */

/* Valio's stock claim, short enough for a table cell. Unknown stays unknown. */
function stockShort(claim) {
  if (!claim || claim.value === null || claim.certainty === "unknown") return "unknown";
  if (claim.value === "not_given") return "available, no count";
  return qty(claim.value, claim.unit);
}

function ecoMarks(line) {
  if (line.swapped_from) {
    return ` <span class="tag tag--eco">Greener swap</span> <span class="muted">was ${esc(line.swapped_from.name)}</span>
      ${canEdit() ? `<button class="link" type="button" data-unswap="${esc(line.product_id)}">Undo</button>` : ""}`;
  }
  return "";
}

/* One line under the lines: the estimated footprint, and Valio's greener product when it offers one this week. */
export function ecoRow() {
  const data = ecoNow();
  if (!data) return "";
  const swaps = swappedLines();
  const saved = swaps.reduce((sum, line) => sum + line.swapped_from.offer.saving_kg_co2e, 0);
  const offers = canEdit() ? (data.alternatives ?? []).filter((offer) => !app.eco.dismissed.has(offer.product_id) && ecoOffer(offer.product_id)) : [];
  const offer = offers[0];
  const offerHtml = offer
    ? `<div class="eco__offer">
        <p><b>${esc(kitchenName(offer))}</b> → <b>${esc(offer.alternative.name)}</b>: ${esc(kgCo2(offer.kg_co2e_before))} → ${esc(kgCo2(offer.kg_co2e_after))}, ${esc(savedByPercent(offer))} less. Same amount, ${esc(allergenText(offer.alternative.allergens) === "unknown" ? "allergens unknown" : `contains ${allergenText(offer.alternative.allergens)}`)}.</p>
        <button class="btn btn--quiet" type="button" data-eco-swap="${esc(offer.product_id)}">Switch</button>
        <button class="link" type="button" data-eco-dismiss="${esc(offer.product_id)}">Not this week</button>
      </div>`
    : "";
  const missing = data.unknown?.length ?? 0;
  // No data is not zero: when Valio has no footprint for any line, the page says so instead of showing 0 kg.
  if (missing && !data.total_kg_co2e) {
    return `<div class="eco"><p class="eco__total">${icon("leaf", 16)}<span class="muted">Footprint: no estimate. Valio has no footprint data for ${missing === 1 ? "this product" : `these ${missing} products`}.</span></p></div>`;
  }
  return `<div class="eco" title="${esc(data.method)}">
      <p class="eco__total">${icon("leaf", 16)}Estimated footprint <b>${esc(kgCo2(data.total_kg_co2e))}</b>
        ${saved ? `<span class="eco__saved">${esc(kgCo2(saved))} less with your greener swap</span>` : ""}
        <span class="muted">Product-group averages, an estimate${missing ? `, ${esc(plural(missing, "line", "lines"))} without data left out` : ""}. Not part of the signed quote.</span></p>
      ${offerHtml}
    </div>`;
}

function requestTable() {
  const lines = missingLines();
  if (!lines.length) return '<p class="empty">Everything is covered by the stock: there is nothing to order.</p>';
  const rows = lines
    .map(
      (line) => `<tr>
        <td><b>${esc(line.name)}</b>${ecoMarks(line)}</td>
        <td class="muted">${esc(line.dishes.join(", "))}</td>
        <td class="num muted">${esc(qty(line.need, line.unit))}</td>
        <td class="num muted">${esc(qty(line.in_stock, line.unit))}</td>
        <td class="num"><b>${esc(qty(line.to_order, line.unit))}</b></td>
      </tr>`
    )
    .join("");
  const covered = app.lines.length - lines.length;
  return `<table class="tbl">
      <thead><tr><th>Ingredient</th><th>Used in</th><th class="num">Needed</th><th class="num">In stock</th><th class="num">To order</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    ${covered > 0 ? `<p class="tbl__note">${esc(plural(covered, "other ingredient is", "other ingredients are"))} covered by the stock. Prices and Valio's stock come with the signed quote.</p>` : ""}`;
}

function quoteTable(state) {
  const quote = state.quote;
  const rows = quote.line_items
    .map((item) => {
      const facts = quote.aimo.lines[item.id] ?? {};
      const lineTotal = item.totals.find((entry) => entry.type === "total");
      const replaces = facts.substitute_for ? `<br /><span class="tag tag--warn">Substitute</span> <span class="muted">for ${esc(facts.substitute_for.name)}</span>` : "";
      return `<tr>
          <td><b>${esc(item.item.title)}</b>${replaces}</td>
          <td class="num">${esc(qty(item.quantity, facts.sales_unit))}</td>
          <td class="num">${esc(money(item.item.price, quote.currency))}</td>
          <td class="num"><b>${esc(money(lineTotal.amount, quote.currency))}</b></td>
          <td class="muted nowrap">${esc(stockShort(facts.stock))}</td>
        </tr>`;
    })
    .join("");
  return `<table class="tbl">
      <thead><tr><th>Product, as Valio names it</th><th class="num">Quantity</th><th class="num">Unit price</th><th class="num">Total</th><th>Valio's stock</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td colspan="3">Total before tax, signed by Valio Aimo</td><td class="num"><b>${esc(money(quoteTotal(quote), quote.currency))}</b></td><td></td></tr></tfoot>
    </table>`;
}

/* The lines of the order: what the kitchen is short of, then Valio's signed quote once it is there. */
export function linesBlock() {
  const state = app.state;
  if (orderOnScreen() && app.shown >= 2 && state.quote) return quoteTable(state) + ecoRow();
  return requestTable() + ecoRow();
}

/* ---------- The rules that guard the order ---------- */

const GUARDS = [
  { key: "spend", label: "Spending limit", rules: ["spend-limit"] },
  { key: "allergens", label: "Allergens", rules: ["allergen-not-blocked", "allergen-data-known", "allergen-unchanged-on-substitution"] },
  { key: "substitutes", label: "Substitutes", rules: ["substitution-within-preferences"] },
  { key: "delivery", label: "Delivery", rules: ["delivery-on-time"] },
];
const ASKS = { human: "you decide", deny: "blocked" };

/* What each rule says before an order, straight from the policy the harness enforces. */
function guardRule(key) {
  const policy = app.policy;
  if (!policy) return "Rules not loaded: the safety service is not running.";
  if (key === "spend") return `${ASSISTANT} signs alone up to ${money(policy.autonomous_limit_minor, policy.currency)}. Above, you sign.`;
  if (key === "allergens") {
    const banned = policy.blocked_allergens?.length ? `Never ${allergenNames(policy.blocked_allergens)}.` : "No banned allergen.";
    return `${banned} Missing information: ${ASKS[policy.unknown_allergen_data] ?? policy.unknown_allergen_data}.`;
  }
  if (key === "substitutes") {
    if (!policy.substitution?.allowed) return "No substitute without you.";
    return `${ASSISTANT} accepts one alone only when it is ${Math.round(policy.substitution.judge_auto_threshold * 100)}% sure it fits your kitchen.`;
  }
  const first = app.kitchen.bookings?.services?.[0]?.date;
  return `${first ? `Needed for ${dayLong(first)}. ` : ""}Later than asked: ${ASKS[policy.late_delivery] ?? policy.late_delivery}.`;
}

/* The rules of the order: before it is sent, what they are; once the checks have run, what each one found. */
export function guards() {
  const verdict = orderOnScreen() && app.shown >= 3 ? app.state.verdict : null;
  const cards = GUARDS.map((guard) => {
    let tone = "rule";
    let text = guardRule(guard.key);
    let out = "";
    if (verdict) {
      const found = verdict.rules.filter((rule) => guard.rules.includes(rule.rule_id)).map(checkLine);
      if (found.length) {
        const worst = found.find((check) => check.outcome === "deny") ?? found.find((check) => check.outcome === "human") ?? found[0];
        tone = worst.outcome;
        text = `${worst.label}${worst.value ? `: ${worst.value}` : ""}.`;
        out = OUTCOME_WORDS[worst.outcome] ?? worst.outcome;
      } else {
        tone = "none";
        text = guard.key === "substitutes" ? "No substitute in this order." : "Nothing to check on this order.";
        out = "Not needed";
      }
    }
    return `<div class="guard guard--${esc(tone)}">
        <p class="guard__label">${esc(guard.label)}${out ? `<span class="guard__out">${esc(out)}</span>` : ""}</p>
        <p class="guard__text">${esc(text)}</p>
      </div>`;
  }).join("");
  const others = verdict ? verdict.rules.filter((rule) => !GUARDS.some((guard) => guard.rules.includes(rule.rule_id))).map(checkLine) : [];
  const also = verdict
    ? others.length
      ? `Also checked: ${others.map((check) => check.name.charAt(0).toLowerCase() + check.name.slice(1)).join(", ")}.`
      : ""
    : "Checked on every order, in code: the prices are signed by Valio Aimo and still valid.";
  return `<section class="guards" aria-label="Your rules for this order">
      <div class="guards__head">
        <h3 class="eyebrow">${verdict ? "What your rules found" : "Your rules for this order"}</h3>
        ${verdict ? "" : '<a class="link" href="#/rules">Change the rules</a>'}
      </div>
      <div class="guards__grid">${cards}</div>
      ${also ? `<p class="guards__also">${esc(also)}</p>` : ""}
    </section>`;
}

/* ---------- The bar under the order: total, delivery, who signs, and the one button ---------- */

export function whoSigns() {
  const state = app.state;
  if (orderOnScreen() && app.shown >= 4) {
    const order = app.shown >= 7 ? state.order : null;
    if (order) return { tone: "ok", text: order.signed_by === "human" ? "Signed by you, on this page" : `Signed by ${ASSISTANT}, inside your limit` };
    if (state.approval?.status === "pending") return { tone: "warn", text: "Needs your signature" };
    if (state.approval?.status === "rejected") return { tone: "bad", text: "You rejected it: nobody signed" };
    if (state.verdict?.decision === "deny") return { tone: "bad", text: "Blocked: nobody may sign" };
  }
  if (orderOnScreen() && app.shown >= 3 && state.verdict) {
    return state.verdict.decision === "auto" ? { tone: "ok", text: `${ASSISTANT} may sign` } : { tone: "warn", text: "Needs your signature" };
  }
  return { tone: "idle", text: limitKnown() ? `${ASSISTANT}, if every check passes. Otherwise you.` : "Decided by your safety checks" };
}

/* The button of the order, wherever the screen puts it. */
export function orderCta({ wide = false } = {}) {
  const size = wide ? " btn--wide" : "";
  if (!hasRun() || isAttack()) {
    const none = !missingLines().length;
    return `<button class="btn btn--go${size}" type="button" data-action="send" ${app.busy || none ? "disabled" : ""}>
        ${app.busy ? '<span class="spinner"></span>Working' : `Send the order to ${ASSISTANT}${icon("arrow", 16)}`}
      </button>`;
  }
  if (revealing() || status() === "running") return `<button class="btn btn--go${size}" type="button" disabled><span class="spinner"></span>${ASSISTANT} is working</button>`;
  if (pendingApproval()) return `<a class="btn btn--sign${size}" href="#/approvals">${icon("pen", 16)}Review and sign</a>`;
  return `<button class="btn btn--quiet${size}" type="button" data-action="new-order">New order</button>`;
}

export function orderBar() {
  const state = app.state;
  const quote = orderOnScreen() && app.shown >= 2 ? state.quote : null;
  const first = app.kitchen.bookings?.services?.[0]?.date;
  const delivery = quote ? dayLong(quote.aimo.delivery_date) : first ? dayLong(first) : "unknown";
  const who = whoSigns();
  return `<div class="bar">
      <div class="bar__cell">
        <p class="bar__label">Total before tax</p>
        <p class="bar__value${quote ? " bar__value--big" : " bar__value--none"}">${quote ? esc(money(quoteTotal(quote), quote.currency)) : "Comes with Valio's signed quote"}</p>
      </div>
      <div class="bar__cell">
        <p class="bar__label">${quote ? "Delivery" : "Needed for"}</p>
        <p class="bar__value">${esc(delivery)}</p>
      </div>
      <div class="bar__cell bar__cell--who bar__cell--${esc(who.tone)}">
        <p class="bar__label">Who signs</p>
        <p class="bar__value">${esc(who.text)}</p>
      </div>
      <div class="bar__cta">${orderCta()}</div>
    </div>`;
}

/* ---------- The substitute the chef is asked about ---------- */

function productFacts(title, name, facts, extra = "") {
  const size = facts.size_per_sales_unit ? `${num(facts.size_per_sales_unit.value)} ${String(facts.size_per_sales_unit.unit).toLowerCase()} a unit` : "unknown";
  const claims = (facts.nutritional_claims ?? []).map(words).join(", ") || "none stated";
  const labels = (facts.labels ?? []).map(words).join(", ") || "none stated";
  return `<div class="versus__side">
      <p class="eyebrow">${esc(title)}</p>
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

function judgeBars(approval) {
  return (approval.judge ?? [])
    .map((answer) => {
      const label = JUDGE_WORDS[answer.question_key] ?? words(answer.question_key);
      if (!Number.isFinite(answer.probability)) return `<li class="judge"><span class="judge__q">${esc(label)}</span><span class="judge__p">unknown</span></li>`;
      const percent = Math.round(answer.probability * 100);
      const threshold = Math.round(answer.auto_threshold * 100);
      return `<li class="judge judge--${esc(answer.routed)}">
          <span class="judge__q">${esc(label)}</span>
          <span class="judge__bar" role="img" aria-label="${percent} percent sure, asks you below ${threshold} percent">
            <span class="judge__fill" style="width:${percent}%"></span>
            <span class="judge__mark" style="left:${threshold}%"></span>
          </span>
          <span class="judge__p">${percent}%</span>
        </li>`;
    })
    .join("");
}

/* Why the chef is asked, and what to compare. Left column of the approval screen. */
export function approvalReason(state) {
  const { approval, quote, verdict } = state;
  const item = quote.line_items.find((entry) => quote.aimo.lines[entry.id]?.substitute_for);
  const checks = (verdict?.rules ?? []).map(checkLine);
  const open = checks.filter((check) => check.outcome !== "pass");
  const passed = checks.filter((check) => check.outcome === "pass");
  const checkRow = (check) => `<li class="check check--${esc(check.outcome)}" title="${esc(check.title)}">
      ${check.outcome === "pass" ? icon("check", 16) : check.outcome === "deny" ? icon("cross", 16) : icon("pen", 16)}
      <span class="check__label">${esc(check.label)}${check.value ? `<span class="check__value">${esc(check.value)}</span>` : ""}</span>
      <span class="check__out">${esc(OUTCOME_WORDS[check.outcome] ?? check.outcome)}</span>
    </li>`;
  const checksHtml = `<section class="card">
      <h3 class="eyebrow">Safety checks, run in code</h3>
      <ul class="checks">${open.map(checkRow).join("")}</ul>
      <details class="fold"><summary>The ${passed.length} other checks passed</summary><ul class="checks">${passed.map(checkRow).join("")}</ul></details>
    </section>`;

  if (!item) {
    return `<section class="card">
        <h3 class="eyebrow">Why you are asked</h3>
        <ul class="reasons">${approval.reasons.map((reason) => `<li>${esc(checkLine(reason).label)}${checkLine(reason).value ? `: ${esc(checkLine(reason).value)}` : ""}</li>`).join("")}</ul>
      </section>${checksHtml}`;
  }

  const facts = quote.aimo.lines[item.id];
  const shortfall = (quote.aimo.shortfalls ?? []).find((entry) => entry.product_id === facts.substitute_for.product_id);
  const why = shortfall ? `Valio cannot deliver what you asked for: ${SHORTFALL_WORDS[shortfall.reason] ?? words(shortfall.reason)}.` : "Valio proposes another product than the one you asked for.";
  // Valio's gateway ranks substitutes in three tiers (good, better, best) and says why: the page repeats both.
  const candidates = (quote.aimo.alternatives ?? []).length;
  const chosen = (quote.aimo.alternatives ?? []).find((entry) => entry.chosen && entry.product_id === facts.product_id);
  const found = candidates === 1 ? " Valio found one substitute and proposes it" : candidates ? ` Valio ranked ${candidates} substitutes and proposes this one` : "";
  const ranked = found ? `${found}${chosen ? `, in its "${chosen.tier}" tier (${chosen.why})` : ""}.` : "";
  const allergens = checks.find((check) => check.id === "allergen-unchanged-on-substitution");
  const perUnit = (minor, unit) => `${money(minor, quote.currency)} a ${String(unit).toLowerCase()}`;
  const askedMinor = facts.substitute_for.comparison_price_minor;
  const askedPrice = `<dt>Price</dt><dd>${esc(Number.isFinite(askedMinor) ? perUnit(askedMinor, facts.substitute_for.comparison_unit) : "not in the quote")}</dd>`;
  const extra = `<dt>Price</dt><dd>${esc(perUnit(facts.comparison_price_minor, facts.comparison_unit))}</dd>
    <dt>Valio's stock</dt><dd>${esc(stockText(facts.stock))}</dd>`;
  // What changes on four sides. The mark says how much there is to weigh: nothing, something, or a reason you are asked.
  const mark = { good: "check", note: "arrow", ask: "pen" };
  const changes = tradeOffs(state)
    .map(
      (row) => `<li class="tradeoff tradeoff--${esc(row.tone)}">
          <span class="tradeoff__side">${icon(mark[row.tone], 16)}${esc(row.label)}</span>
          <span class="tradeoff__text">${esc(row.text)}</span>
        </li>`
    )
    .join("");
  return `<section class="card">
      <h3 class="eyebrow">Why you are asked</h3>
      <p class="card__lead">${esc(why)}${esc(ranked)}</p>
      <div class="swap">
        <div class="swap__side"><p class="eyebrow">You asked for</p><p class="swap__name">${esc(facts.substitute_for.name)}</p></div>
        <span class="swap__arrow" aria-hidden="true">${icon("arrow", 20)}</span>
        <div class="swap__side swap__side--to"><p class="eyebrow">Valio proposes</p><p class="swap__name">${esc(item.item.title)}</p></div>
      </div>
      ${allergens ? `<ul class="keys"><li class="key key--${esc(allergens.outcome)}">${allergens.outcome === "pass" ? icon("check", 16) : icon("pen", 16)}${esc(allergens.label)}${allergens.value ? `: ${esc(allergens.value)}` : ""}</li></ul>` : ""}
      <h4 class="eyebrow tradeoffs__title">What changes if you take it</h4>
      <ul class="tradeoffs">${changes}</ul>
      <p class="card__note">${ASSISTANT}'s opinion is advice. The prices, the allergens, the storage and the stock are Valio's signed facts.</p>
      <details class="fold" ${app.detailsOpen ? "open" : ""} data-fold="details">
        <summary>All details of both products</summary>
        <div class="versus">
          ${productFacts("You asked for", facts.substitute_for.name, facts.substitute_for, askedPrice)}
          ${productFacts("Valio proposes", item.item.title, facts, extra)}
        </div>
        <ul class="judges">${judgeBars(approval)}</ul>
      </details>
    </section>${checksHtml}`;
}

/* What the chef signs, and the three buttons. Right column of the approval screen. */
export function signoff(state) {
  const { approval, quote } = state;
  const lines = quote.line_items
    .map((item) => `<li><span>${esc(item.item.title)}</span><b>${esc(qty(item.quantity, quote.aimo.lines[item.id]?.sales_unit))}</b></li>`)
    .join("");
  return `<section class="card signoff">
      <h3 class="eyebrow">Your sign-off</h3>
      <ul class="signoff__lines">${lines}</ul>
      <dl class="facts signoff__facts">
        <dt>Total before tax</dt><dd class="signoff__total">${esc(money(approval.total_minor, approval.currency))}</dd>
        <dt>Delivery</dt><dd>${esc(dayLong(quote.aimo.delivery_date))}</dd>
        <dt>Sign before</dt><dd>${esc(clock(approval.deadline))}</dd>
        <dt>Quote</dt><dd class="mono" title="${esc(approval.checkout_hash)}">${esc(shortProof(approval.checkout_hash, 14))}</dd>
      </dl>
      <button class="btn btn--sign btn--wide" type="button" data-action="approve" ${app.busy ? "disabled" : ""}>${icon("pen", 16)}Approve and sign</button>
      <div class="signoff__row">
        <button class="btn btn--reject" type="button" data-action="reject" ${app.busy ? "disabled" : ""}>Reject</button>
        <button class="btn btn--quiet" type="button" data-action="reject-edit" ${app.busy ? "disabled" : ""}>Reject and edit the order</button>
      </div>
      <p class="signoff__note">${icon("lock", 14)}Your signature is for this exact quote and nothing else. Valio checks it before it accepts the order.</p>
    </section>`;
}

/* The three orders sent to Valio without the safety checks, and what Valio answered. */
export function attacksCard(state) {
  const items = state.attacks
    .map((attack) => {
      const refused = attack.status === "refused";
      const label = { refused: "Refused by Valio", accepted: "ACCEPTED: this must not happen", pending: "Not sent yet" }[attack.status] ?? attack.status;
      const problems = attack.problems.map((problem) => `<li>${esc(lexicon(problem))}</li>`).join("");
      return `<li class="attack attack--${esc(attack.status)}">
          <p class="attack__title">${refused ? icon("cross", 16) : icon("wait", 16)}${esc(lexicon(attack.title))}</p>
          <p class="attack__status">${esc(label)}</p>
          ${problems ? `<ul class="attack__problems">${problems}</ul>` : ""}
        </li>`;
    })
    .join("");
  return `<ul class="attacks">${items}</ul>`;
}

/* ---------- The proof of one order, in a side panel ---------- */

const row = (label, value, mono = false) => (value ? `<dt>${esc(label)}</dt><dd${mono ? ' class="mono"' : ""} title="${esc(value)}">${esc(value)}</dd>` : "");

/* The receipt is a signed token: its first part says how it was signed. Read it, never trust it for a fact. */
function jwtHeader(token) {
  try {
    const part = String(token).split(".")[0].replaceAll("-", "+").replaceAll("_", "/");
    return JSON.parse(atob(part));
  } catch {
    return null;
  }
}

export function proofPanel() {
  const target = app.proof;
  if (!target) return "";
  let body = "";
  let title = "";
  if (target.kind === "sample") {
    const entry = target.entry;
    title = entry.order_id ?? "Request not ordered";
    const lines = entry.lines.map((line) => `<li><span>${esc(line.title)}</span><b>${esc(String(line.quantity))} × ${esc(money(line.unit_price_minor, entry.currency))}</b></li>`).join("");
    body = `<p class="proof__sample">Sample history for the mock-up. Identifiers and hashes below are made up.</p>
      ${entry.note ? `<p class="proof__note">${esc(entry.note)}</p>` : ""}
      <h4 class="eyebrow">Lines</h4><ul class="signoff__lines">${lines}</ul>
      <h4 class="eyebrow">Signatures</h4>
      <dl class="facts facts--proof">
        ${row("Signed by", entry.signed_by === "agent" ? `${ASSISTANT}, inside your limit` : entry.signed_by === "human" ? "You, on this page" : "Nobody")}
        ${row("Total", money(entry.total_minor, entry.currency))}
        ${row("Quote hash", entry.checkout_hash, true)}
        ${row("Mandate", entry.mandate_reference, true)}
        ${row("Receipt", entry.receipt_hash, true)}
        ${row("Payment", entry.payment_id, true)}
      </dl>`;
  } else {
    const { order, quote, verdict, request, steps, events } = target;
    title = order?.order_id ?? quote?.id ?? "Order";
    const header = order?.receipt_jwt ? jwtHeader(order.receipt_jwt) : null;
    const checks = (verdict?.rules ?? []).map(checkLine);
    const open = (steps ?? []).find((step) => step.key === "open_mandate");
    body = `${
      request?.text
        ? `<div class="claim">
            <p class="eyebrow">What ${ASSISTANT} was asked <span class="claim__tag">words, not proof</span></p>
            <p class="claim__text">“${esc(request.text)}”</p>
          </div>`
        : ""
    }
      ${
        checks.length
          ? `<h4 class="eyebrow">Checked in code, before anyone signed</h4>
            <ul class="checks checks--tight">${checks
              .map(
                (check) => `<li class="check check--${esc(check.outcome)}">${check.outcome === "pass" ? icon("check", 14) : icon("pen", 14)}
                <span class="check__label">${esc(check.name)}${check.value ? `<span class="check__value">${esc(check.value)}</span>` : ""}</span>
                <span class="check__out">${esc(OUTCOME_WORDS[check.outcome] ?? check.outcome)}</span></li>`
              )
              .join("")}</ul>`
          : ""
      }
      <h4 class="eyebrow">Signatures</h4>
      <dl class="facts facts--proof">
        ${row("Your standing permission", open?.proof, true)}
        ${row("Quote, signed by Valio", order?.checkout_hash ?? verdict?.checkout_hash, true)}
        ${row("Order signed by", order ? (order.signed_by === "human" ? "You, on this page" : `${ASSISTANT}'s key, inside your limit`) : null)}
        ${row("Mandate", order?.mandate_reference, true)}
        ${row("Limit Valio checked", order?.mandate?.cap_minor ? `${money(order.mandate.amount_minor, order.currency)} of ${money(order.mandate.cap_minor, order.currency)}` : null)}
        ${row("Payment (test mode)", order?.payment ? [order.payment.payment_id, order.payment.terms].join(" · ") : null)}
        ${row("Receipt signature", header ? `${header.alg}, key "${header.kid}"` : null)}
        ${row("Receipt", order?.receipt_jwt ? `${order.receipt_jwt.slice(0, 28)}…${order.receipt_jwt.slice(-12)}` : null, true)}
      </dl>
      ${
        events?.length
          ? `<h4 class="eyebrow">In the audit logs</h4>
            <ol class="proof__events">${events
              .map((event) => `<li>${whoChip(event.actor)}<span>${esc(lexicon(event.what))}</span><span class="mono muted">${esc(event.hash.slice(0, 8))}</span></li>`)
              .join("")}</ol>`
          : ""
      }
      <div class="proof__actions">
        <button class="btn btn--quiet" type="button" data-action="proof-json">${icon("down", 16)}Proof as JSON</button>
        <a class="btn btn--quiet" href="#/audit" data-action="close-proof">Open the audit log</a>
      </div>`;
  }
  return `<aside class="proof" aria-label="Proof of the order">
      <header class="proof__head">
        <div><p class="eyebrow">Proof of the order</p><h3 class="proof__title mono">${esc(title)}</h3></div>
        <button class="iconbtn" type="button" data-action="close-proof" aria-label="Close">${icon("close", 18)}</button>
      </header>
      <div class="proof__body">${body}</div>
    </aside>
    <div class="scrim" data-action="close-proof"></div>`;
}
