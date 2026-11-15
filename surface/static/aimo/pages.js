/*
 * The four screens every version of the portal shares: orders, approvals, rules, audit.
 * Each function returns HTML as text.
 */

import {
  ASSISTANT,
  ALLERGEN_WORDS,
  ACTION_WORDS,
  CHECK_WORDS,
  esc,
  icon,
  money,
  dayLong,
  clock,
  dateTime,
  timeOf,
  words,
  lexicon,
  plural,
} from "./core.js";
import { app, isAttack, pendingApproval, orderRows, ledgerRows, ledgerKey, isRefusal } from "./state.js";
import { pill, whoChip, signedBy, approvalReason, signoff, attacksCard, agentCard } from "./ui.js";

const pageHead = (title, lead, actions = "") => `<header class="page__head">
    <div><h1 class="page__title">${esc(title)}</h1><p class="page__lead">${esc(lead)}</p></div>
    ${actions ? `<div class="page__actions">${actions}</div>` : ""}
  </header>`;

/* ---------- Orders ---------- */

/* The delivery of the latest order Valio accepted. Only what happened is ticked: the rest is what comes next. */
function deliveryCard(rows) {
  const next = rows.find((row) => row.real && row.status === "accepted");
  if (!next) {
    return `<section class="card delivery delivery--none">
        <p class="eyebrow">Next delivery</p>
        <p class="delivery__none">Nothing on the way. An order shows here as soon as Valio Aimo accepts it.</p>
      </section>`;
  }
  const order = next.order ?? app.state?.order;
  const steps = [
    { name: "Signed", meta: `${next.signed_by === "human" ? "by you" : `by ${ASSISTANT}`} · ${dateTime(next.at)}`, done: true },
    { name: "Accepted by Valio", meta: order?.receipt_jwt ? "receipt signed" : "", done: true },
    { name: "Prepared at Valio's warehouse", meta: "scheduled" },
    { name: "On the road", meta: "scheduled" },
    { name: "Delivered to your kitchen", meta: dayLong(next.delivery_date) },
  ];
  return `<section class="card delivery">
      <div class="delivery__head">
        <div>
          <p class="eyebrow">Next delivery</p>
          <p class="delivery__date">${esc(dayLong(next.delivery_date))}</p>
          <p class="muted">Order <span class="mono">${esc(next.id)}</span>${next.count ? ` · ${esc(plural(next.count, "product", "products"))}` : ""} · ${esc(money(next.total_minor, next.currency))} before tax</p>
        </div>
        <button class="btn btn--quiet" type="button" data-proof="${esc(next.checkout_id)}">View proof</button>
      </div>
      <ol class="track">${steps
        .map(
          (step, index) => `<li class="track__step${step.done ? " is-done" : ""}${!step.done && steps[index - 1]?.done ? " is-next" : ""}">
            <span class="track__dot">${step.done ? icon("check", 12) : ""}</span>
            <p class="track__name">${esc(step.name)}</p>
            <p class="track__meta">${esc(step.meta)}</p>
          </li>`
        )
        .join("")}</ol>
    </section>`;
}

export function ordersPage() {
  const rows = orderRows();
  const signedByAimo = rows.filter((row) => row.signed_by === "agent").length;
  const signedByYou = rows.filter((row) => row.signed_by === "human").length;
  const stopped = rows.filter((row) => ["rejected", "blocked", "expired"].includes(row.status)).length;
  const body = rows
    .map(
      (row) => `<tr class="${row.current ? "is-current" : ""}">
        <td class="nowrap"><span class="mono">${esc(row.id)}</span>${row.real ? "" : '<span class="tag tag--sample">sample</span>'}</td>
        <td class="muted nowrap">${esc(dateTime(row.at))}</td>
        <td class="items">${row.items ? `<b>${esc(plural(row.count, "product", "products"))}</b><span class="items__names">${esc(row.items)}</span>` : '<span class="muted">not loaded</span>'}</td>
        <td class="num"><b>${esc(money(row.total_minor, row.currency))}</b></td>
        <td class="signed">${signedBy(row.signed_by, row.entry?.decision)}</td>
        <td class="muted nowrap">${row.delivery_date ? esc(dayLong(row.delivery_date)) : "none"}</td>
        <td>${pill(row.real ? row.status : row.status)}</td>
        <td class="num"><button class="link" type="button" data-proof="${esc(row.checkout_id)}">Proof</button></td>
      </tr>`
    )
    .join("");
  return `<div class="page page--wide">
      ${pageHead("Orders", "Every order, who signed it, and its proof.")}
      ${deliveryCard(rows)}
      <div class="tiles tiles--3">
        <div class="tile"><p class="tile__label">Signed by ${ASSISTANT}, inside your limit</p><p class="tile__value">${signedByAimo}</p></div>
        <div class="tile"><p class="tile__label">Signed by you</p><p class="tile__value">${signedByYou}</p></div>
        <div class="tile"><p class="tile__label">Stopped: nobody signed</p><p class="tile__value">${stopped}</p></div>
      </div>
      <div class="card card--table">
        <table class="tbl tbl--rows">
          <thead><tr><th>Order</th><th>Sent</th><th>Items</th><th class="num">Total</th><th>Signed by</th><th>Delivery</th><th>Status</th><th></th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      <p class="tbl__note">Rows marked "sample" are made-up history for the mock-up, built on real products and prices of the quote recorded on 14 Nov. The others are orders of this session.</p>
    </div>`;
}

/* ---------- Approvals ---------- */

function pastDecisions() {
  const real = app.session.approvals
    .filter((approval) => approval.status !== "pending")
    .map((approval) => ({
      id: approval.approval_id,
      at: approval.decided_at ?? approval.requested_at,
      why: approval.reasons.map((reason) => CHECK_WORDS[reason.rule_id]?.human ?? lexicon(reason.message)).join(". "),
      total: money(approval.total_minor, approval.currency),
      status: approval.status,
      real: true,
    }));
  const sample = app.history
    .filter((entry) => entry.rule)
    .map((entry) => ({
      id: entry.order_id ?? entry.checkout_id,
      at: entry.ordered_at,
      why: entry.note,
      total: money(entry.total_minor, entry.currency),
      status: entry.status === "delivered" ? "approved" : entry.status,
      real: false,
    }));
  const rows = [...real, ...sample].sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  if (!rows.length) return "";
  const label = { approved: ["ok", "You signed"], rejected: ["bad", "You rejected"], expired: ["bad", "Expired"], blocked: ["bad", "Blocked by a rule"] };
  return `<section class="section">
      <h2 class="section__title">Past decisions</h2>
      <div class="card card--table">
        <table class="tbl tbl--rows">
          <thead><tr><th>Request</th><th>When</th><th>Why you were asked</th><th class="num">Total</th><th>Outcome</th></tr></thead>
          <tbody>${rows
            .map(
              (row) => `<tr>
                <td class="nowrap"><span class="mono">${esc(row.id)}</span>${row.real ? "" : '<span class="tag tag--sample">sample</span>'}</td>
                <td class="muted nowrap">${esc(dateTime(row.at))}</td>
                <td>${esc(row.why)}</td>
                <td class="num"><b>${esc(row.total)}</b></td>
                <td><span class="pill pill--${label[row.status]?.[0] ?? "info"}">${esc(label[row.status]?.[1] ?? row.status)}</span></td>
              </tr>`
            )
            .join("")}</tbody>
        </table>
      </div>
    </section>`;
}

export function approvalsPage() {
  const state = app.state;
  const pending = pendingApproval();
  let main = "";
  if (pending && state.quote) {
    const reasons = pending.reasons.map((reason) => CHECK_WORDS[reason.rule_id]?.human ?? lexicon(reason.message)).join(". ");
    main = `<div class="notice notice--warn" role="status">
        <span class="notice__icon">${icon("pen", 18)}</span>
        <p class="notice__text"><b>1 order needs your signature.</b> ${esc(reasons)}.</p>
        <p class="notice__side">Sign before <b>${esc(clock(pending.deadline))}</b>, Valio's order cut-off</p>
      </div>
      <div class="split split--approval">
        <div class="split__main">${approvalReason(state)}</div>
        <div class="split__side">${signoff(state)}</div>
      </div>`;
  } else {
    const decided = state?.approval && state.approval.status !== "pending" && !isAttack() ? state.approval : null;
    const outcome = decided
      ? { approved: "You signed. Valio accepted the order.", rejected: "You rejected it. Nobody signed, nothing was ordered.", expired: "Nobody signed in time. Nothing was ordered." }[decided.status]
      : null;
    main = `<section class="card empty-card">
        <span class="empty-card__icon">${icon(decided?.status === "approved" ? "check" : "shield", 22)}</span>
        <div>
          <p class="empty-card__title">${esc(outcome ?? "Nothing needs you right now.")}</p>
          <p class="muted">${ASSISTANT} signs alone inside your rules. When a rule says so, the order waits here for your signature, and nobody else can give it.</p>
        </div>
        ${decided?.status === "approved" ? '<button class="btn btn--quiet" type="button" data-proof="current">View proof</button>' : '<a class="btn btn--quiet" href="#/rules">See your rules</a>'}
      </section>`;
  }
  return `<div class="page">
      ${pageHead("Approvals", "Orders that wait for your signature. You sign here, never in a chat.")}
      ${main}
      ${pastDecisions()}
    </div>`;
}

/* ---------- Rules ---------- */

const ESCALATION = [
  ["human", "Ask me"],
  ["deny", "Block the order"],
];

const rulesNow = () => app.rules.draft ?? app.policy;

/* The chef's unsaved changes, as the body the harness expects: only the fields that differ. */
export function rulesChange() {
  const draft = app.rules.draft;
  const policy = app.policy;
  if (!draft || !policy) return {};
  const change = {};
  ["autonomous_limit_minor", "unknown_allergen_data", "allergen_change_on_substitution", "late_delivery"].forEach((key) => {
    if (draft[key] !== policy[key]) change[key] = draft[key];
  });
  if (JSON.stringify(draft.blocked_allergens) !== JSON.stringify(policy.blocked_allergens)) change.blocked_allergens = draft.blocked_allergens;
  const substitution = {};
  ["allowed", "pre_accepted", "preferences_text", "judge_auto_threshold", "judge_floor"].forEach((key) => {
    if (draft.substitution[key] !== policy.substitution[key]) substitution[key] = draft.substitution[key];
  });
  if (Object.keys(substitution).length) change.substitution = substitution;
  return change;
}

const segmented = (path, options, current) => `<div class="seg" role="radiogroup">${options
  .map(
    ([value, label]) =>
      `<button class="seg__btn${String(current) === String(value) ? " is-on" : ""}" type="button" role="radio" aria-checked="${String(current) === String(value)}" data-rule-set="${esc(path)}" data-value="${esc(value)}">${esc(label)}</button>`
  )
  .join("")}</div>`;

const ruleRow = (title, help, control) => `<div class="rule">
    <div class="rule__text"><p class="rule__title">${esc(title)}</p><p class="rule__help">${esc(help)}</p></div>
    <div class="rule__control">${control}</div>
  </div>`;

/* The kitchen's preferences are one text the assistant reads. Shown as its three lists; edited as the text it is. */
function preferences(text) {
  const sections = [
    ["NEVER ACCEPT:", "Never accept", "deny"],
    ["A HUMAN DECIDES:", "Ask me", "human"],
    ["ACCEPT WITHOUT ASKING:", "Accept without asking", "pass"],
  ];
  const lines = String(text ?? "").split("\n");
  const found = sections.map(([marker, label, tone]) => {
    const start = lines.findIndex((line) => line.trim() === marker);
    if (start < 0) return null;
    const items = [];
    for (let index = start + 1; index < lines.length && lines[index].trim().startsWith("-"); index += 1) items.push(lines[index].trim().replace(/^-\s*/, ""));
    return { label, tone, items };
  });
  if (found.some((section) => !section)) return `<p class="prefs__raw">${esc(text)}</p>`;
  return `<div class="prefs">${found
    .map(
      (section) => `<div class="prefs__col prefs__col--${section.tone}">
        <p class="prefs__label">${esc(section.label)}</p>
        <ul>${section.items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
      </div>`
    )
    .join("")}</div>`;
}

export function rulesPage() {
  const policy = rulesNow();
  if (!policy) {
    return `<div class="page">${pageHead("Rules", "What Aimo may do alone, and when it must ask you.")}
      <section class="card empty-card"><span class="empty-card__icon">${icon("sliders", 22)}</span>
        <div><p class="empty-card__title">Your rules are not loaded.</p><p class="muted">They live in the safety service (harness), which is not running. Start it and this screen fills in.</p></div>
      </section></div>`;
  }
  const change = rulesChange();
  const changed = Object.keys(change).length + (change.substitution ? Object.keys(change.substitution).length - 1 : 0);
  const limit = policy.autonomous_limit_minor / 100;
  const sub = policy.substitution;
  const banned = policy.blocked_allergens ?? [];
  const addable = Object.keys(ALLERGEN_WORDS).filter((code) => !banned.includes(code));
  const auto = Math.round(sub.judge_auto_threshold * 100);
  const floor = Math.round(sub.judge_floor * 100);
  const note = app.rules.note;

  return `<div class="page page--rules">
      ${pageHead(
        "Rules",
        `What ${ASSISTANT} may do alone, and when it must ask you. Checked in code on every order, before anyone signs.`,
        app.policyFromFile ? "" : '<button class="btn btn--quiet" type="button" data-action="rules-reset">Back to the demo rules</button>'
      )}
      ${note ? `<div class="notice notice--${esc(note.tone)}" role="status"><span class="notice__icon">${icon(note.tone === "ok" ? "check" : "shield", 18)}</span><p class="notice__text">${esc(note.text)}</p></div>` : ""}
      ${app.policyFromFile && !note ? `<div class="notice" role="status"><span class="notice__icon">${icon("lock", 18)}</span><p class="notice__text">The safety service is not running. These are the rules of the demo file: you can read them, a change cannot be saved.</p></div>` : ""}

      <section class="card rules">
        <h2 class="rules__title">Spending</h2>
        ${ruleRow(
          `${ASSISTANT} signs alone up to`,
          "For one order, before tax. Above this amount the order waits for your signature. Valio checks the same limit on its side.",
          `<div class="gauge">
            <div class="gauge__field"><span>${esc(policy.currency)}</span><input class="gauge__num" type="number" min="1" max="20000" step="10" value="${limit}" data-rule="autonomous_limit_minor" aria-label="Spending limit" /></div>
            <input class="gauge__range" type="range" min="50" max="5000" step="50" value="${Math.min(limit, 5000)}" data-rule="autonomous_limit_minor" aria-label="Spending limit" />
            <div class="gauge__scale"><span>50</span><span>5,000</span></div>
          </div>`
        )}
        <p class="rules__foot">Supplier allowed: ${esc(policy.allowed_merchants.map((merchant) => merchant.name).join(", "))}. This permission is valid until ${esc(clock(policy.valid_until))}.</p>
      </section>

      <section class="card rules">
        <h2 class="rules__title">Allergens</h2>
        ${ruleRow(
          "Never order",
          "An order with one of these is blocked. Nobody can sign it, not even you.",
          `<div class="chips">
            ${banned.map((code) => `<span class="chip chip--ban">${esc(ALLERGEN_WORDS[code] ?? code)}<button type="button" data-allergen-remove="${esc(code)}" aria-label="Remove ${esc(ALLERGEN_WORDS[code] ?? code)}">${icon("close", 12)}</button></span>`).join("")}
            <select class="chip chip--add" data-allergen-add aria-label="Add an allergen">
              <option value="">Add</option>
              ${addable.map((code) => `<option value="${esc(code)}">${esc(ALLERGEN_WORDS[code])}</option>`).join("")}
            </select>
          </div>`
        )}
        ${ruleRow("Allergen information is missing", "Unknown is never read as safe.", segmented("unknown_allergen_data", ESCALATION, policy.unknown_allergen_data))}
        ${ruleRow("A substitute changes the allergens", "Compared with the product you asked for.", segmented("allergen_change_on_substitution", ESCALATION, policy.allergen_change_on_substitution))}
      </section>

      <section class="card rules">
        <h2 class="rules__title">Substitutes</h2>
        ${ruleRow(
          "Allow substitutes",
          "When Valio cannot deliver a product, it may propose another one.",
          `<button class="switch${sub.allowed ? " is-on" : ""}" type="button" role="switch" aria-checked="${sub.allowed}" data-rule-toggle="substitution.allowed"><span class="switch__knob"></span></button>`
        )}
        ${ruleRow(
          "Accept without asking",
          "A substitute of the same category with the same allergens.",
          segmented(
            "substitution.pre_accepted",
            [
              ["same_category_and_same_allergens", "Same category and allergens"],
              ["none", "Never"],
            ],
            sub.pre_accepted
          )
        )}
        ${ruleRow(
          `How sure ${ASSISTANT} must be to accept alone`,
          "It reads your preferences below and scores the substitute. Under this score, it asks you.",
          `<div class="gauge">
            <div class="gauge__field"><input class="gauge__num" type="number" min="${floor}" max="100" step="1" value="${auto}" data-rule="substitution.judge_auto_threshold" data-percent aria-label="Score to accept alone" /><span>%</span></div>
            <input class="gauge__range" type="range" min="50" max="100" step="1" value="${auto}" data-rule="substitution.judge_auto_threshold" data-percent aria-label="Score to accept alone" />
          </div>`
        )}
        ${ruleRow(
          "Refuse under",
          "Below this score the substitute is refused, without asking you.",
          `<div class="gauge">
            <div class="gauge__field"><input class="gauge__num" type="number" min="0" max="${auto}" step="1" value="${floor}" data-rule="substitution.judge_floor" data-percent aria-label="Score to refuse" /><span>%</span></div>
            <input class="gauge__range" type="range" min="0" max="50" step="1" value="${floor}" data-rule="substitution.judge_floor" data-percent aria-label="Score to refuse" />
          </div>`
        )}
        <details class="rule rule--block fold" data-fold="prefs" ${app.rules.prefsOpen ? "open" : ""}>
          <summary>Your kitchen's preferences, the text ${ASSISTANT} reads to judge a substitute</summary>
          ${
            app.rules.editingText
              ? `<textarea class="prefs__edit" rows="14" data-rule="substitution.preferences_text" aria-label="Your kitchen's preferences">${esc(sub.preferences_text)}</textarea>`
              : preferences(sub.preferences_text)
          }
          <button class="link" type="button" data-action="edit-prefs">${app.rules.editingText ? "Show as lists" : "Edit the text"}</button>
        </details>
      </section>

      <section class="card rules">
        <h2 class="rules__title">Delivery</h2>
        ${ruleRow("It arrives later than you asked", "For example when the order cut-off has passed.", segmented("late_delivery", ESCALATION, policy.late_delivery))}
      </section>

      <div class="savebar${changed ? " is-on" : ""}" aria-hidden="${changed ? "false" : "true"}">
        <p class="savebar__text">${esc(plural(changed, "change", "changes"))} not saved. New rules apply to the next order.</p>
        <button class="btn btn--quiet" type="button" data-action="rules-discard" ${app.rules.saving ? "disabled" : ""}>Discard</button>
        <button class="btn btn--sign" type="button" data-action="rules-save" ${app.rules.saving ? "disabled" : ""}>${icon("pen", 16)}${app.rules.saving ? "Saving" : "Sign and save"}</button>
      </div>
    </div>`;
}

/* ---------- Audit ---------- */

function inspector(event) {
  if (!event) return `<aside class="card inspector"><p class="muted">Choose a line to see its proof.</p></aside>`;
  const one = app.ledger.one?.key === ledgerKey(event) ? app.ledger.one : null;
  const item = (label, value, mono = false) => (value !== null && value !== undefined && value !== "" ? `<dt>${esc(label)}</dt><dd${mono ? ' class="mono"' : ""}>${esc(value)}</dd>` : "");
  const sameOrder = app.state?.quote?.id && event.checkout_id === app.state.quote.id;
  return `<aside class="card inspector">
      <p class="eyebrow">Proof of this line</p>
      <h3 class="inspector__title">${esc(ACTION_WORDS[event.action] ?? titleWords(event.action))}</h3>
      <p class="inspector__who">${whoChip(event.actor)}<span class="muted">${event.side === "buyer" ? "in your log" : "in Valio's log"} · line ${esc(event.seq)}</span></p>
      <div class="inspector__said">
        <p>${esc(lexicon(event.what))}</p>
        <p class="muted">${esc(lexicon(event.why))}</p>
      </div>
      <dl class="facts facts--proof">
        ${item("Time", `${dayLong(event.at)}, ${timeOf(event.at)}`)}
        ${item("Rule", event.rule ? CHECK_WORDS[event.rule]?.name ?? event.rule : null)}
        ${item("Quote", event.checkout_id, true)}
        ${item("Quote hash", event.checkout_hash, true)}
        ${item("Line before", event.prev_hash ?? "first line of the log", Boolean(event.prev_hash))}
        ${item("Fingerprint", event.hash, true)}
      </dl>
      ${one ? `<p class="inspector__result inspector__result--${one.ok ? "ok" : "bad"}">${icon(one.ok ? "check" : "cross", 16)}${one.ok ? "Recomputed in your browser: same fingerprint." : "Recomputed in your browser: the fingerprint differs. This line was changed."}</p>` : ""}
      <div class="inspector__actions">
        <button class="btn btn--quiet" type="button" data-action="recompute" data-key="${esc(ledgerKey(event))}">Recompute the fingerprint</button>
        ${sameOrder ? '<button class="btn btn--quiet" type="button" data-proof="current">Proof of the order</button>' : ""}
      </div>
    </aside>`;
}

const titleWords = (code) => {
  const text = words(code);
  return text.charAt(0).toUpperCase() + text.slice(1);
};

export function auditPage() {
  const all = ledgerRows();
  const filter = app.ledger.filter;
  const rows = all.filter((event) => filter === "all" || (filter === "refused" ? isRefusal(event) : event.side === filter));
  const selected = all.find((event) => ledgerKey(event) === app.ledger.selected) ?? rows[0] ?? null;
  const check = app.ledger.check;
  const attack = isAttack() && app.state.attacks?.length;
  const counts = { all: all.length, buyer: all.filter((event) => event.side === "buyer").length, merchant: all.filter((event) => event.side === "merchant").length, refused: all.filter(isRefusal).length };
  const chips = [
    ["all", "All"],
    ["buyer", "Your log"],
    ["merchant", "Valio's log"],
    ["refused", "Refused"],
  ]
    .map(([key, label]) => `<button class="chipbtn${filter === key ? " is-on" : ""}" type="button" data-ledger-filter="${key}">${label}<span>${counts[key]}</span></button>`)
    .join("");
  const table = rows.length
    ? `<table class="tbl tbl--rows tbl--ledger">
        <thead><tr><th>Time</th><th>Who</th><th>What happened</th><th>Log</th><th>Fingerprint</th></tr></thead>
        <tbody>${rows
          .map((event) => {
            const key = ledgerKey(event);
            return `<tr class="${selected && ledgerKey(selected) === key ? "is-selected" : ""}${isRefusal(event) ? " is-refused" : ""}" data-ledger="${esc(key)}" tabindex="0">
              <td class="muted nowrap">${esc(timeOf(event.at))}</td>
              <td>${whoChip(event.actor)}</td>
              <td><b>${esc(ACTION_WORDS[event.action] ?? titleWords(event.action))}</b><span class="ledger__what">${esc(lexicon(event.what))}</span></td>
              <td class="muted nowrap">${event.side === "buyer" ? "Yours" : "Valio's"} #${esc(event.seq)}</td>
              <td class="mono muted">${esc(event.hash.slice(0, 10))}</td>
            </tr>`;
          })
          .join("")}</tbody>
      </table>`
    : `<p class="empty">Nothing here yet. Send an order: every step is written in both logs.</p>`;
  const verdict = check
    ? check.running
      ? `<div class="notice notice--info"><span class="spinner"></span><p class="notice__text">Recomputing every fingerprint</p></div>`
      : check.broken.length
        ? `<div class="notice notice--bad"><span class="notice__icon">${icon("cross", 18)}</span><p class="notice__text"><b>The chain is broken.</b> ${esc(plural(check.broken.length, "line does", "lines do"))} not match: ${esc(check.broken.join(", "))}.</p></div>`
        : `<div class="notice notice--ok"><span class="notice__icon">${icon("shield", 18)}</span><p class="notice__text"><b>Both chains hold.</b> ${esc(plural(check.count, "fingerprint", "fingerprints"))} recomputed in your browser with SHA-256, each line points at the one before it.</p></div>`
    : "";
  return `<div class="page page--wide">
      ${pageHead(
        "Audit log",
        "You and Valio each keep a log. Every line carries the fingerprint of the line before it, so a changed line shows.",
        `<button class="btn btn--quiet" type="button" data-action="verify-chain">${icon("shield", 16)}Verify both chains</button>
         <button class="btn btn--quiet" type="button" data-action="audit-json">${icon("down", 16)}JSON</button>`
      )}
      ${
        attack
          ? `<section class="card attackcard">
              <div class="attackcard__text">
                <p class="eyebrow eyebrow--bad">3 orders sent to Valio without your safety checks</p>
                <p class="attackcard__lead">No valid signature, no order. Valio refused all ${app.state.attacks.length}.</p>
                ${attacksCard(app.state)}
              </div>
              ${agentCard({ ask: false, title: "What happened" })}
            </section>`
          : ""
      }
      ${verdict}
      <div class="split split--audit">
        <div class="split__main">
          <div class="chipbar">${chips}</div>
          <div class="card card--table">${table}</div>
        </div>
        <div class="split__side">${inspector(selected)}</div>
      </div>
    </div>`;
}
