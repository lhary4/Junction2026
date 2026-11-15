/*
 * The clean portal, in three versions of the same product (?v=a, b or c):
 *   a  Brief    one column, the assistant's card is the page
 *   b  Console  a sidebar and a dashboard, the order on its own screen
 *   c  Guided   menu, stock, order, one step at a time
 * The orders, approvals, rules and audit screens are the same in all three.
 *
 * This file holds the frames, the home screens, the events and the actions. See core.js for where the data comes from.
 */

import {
  QUERY,
  ASSISTANT,
  REVEAL_MS,
  POLL_MS,
  SERVICES_MS,
  el,
  esc,
  setHtml,
  icon,
  money,
  qty,
  dayShort,
  dayLong,
  kgCo2,
  plural,
  driver,
  harness,
  merchant,
  assistant,
  recorded,
  recordedFootprintFile,
  replayFile,
  policyFile,
  kitchenApi,
  digest,
  verifyChain,
  download,
} from "./core.js";
import {
  app,
  ROUTES,
  status,
  hasRun,
  isAttack,
  missingLines,
  orderLines,
  linesKey,
  orderOnScreen,
  reachable,
  revealing,
  canEdit,
  pendingApproval,
  limitKnown,
  limitText,
  loadLines,
  setStock,
  changeText,
  ecoKey,
  ecoOffer,
  swapLine,
  unswap,
  serviceDays,
  pageFacts,
  ledgerRows,
  ledgerKey,
} from "./state.js";
import { agentCard, linesBlock, guards, orderBar, orderCta, whoSigns, proofPanel, prospectCard, defaultProspectQty } from "./ui.js";
import { ordersPage, approvalsPage, rulesPage, auditPage, rulesChange } from "./pages.js";

const VARIANT_NAMES = { a: "Brief", b: "Console", c: "Guided" };
const NAV = [
  ["today", "Today", "home"],
  ["orders", "Orders", "box"],
  ["approvals", "Approvals", "pen"],
  ["rules", "Rules", "sliders"],
  ["audit", "Audit", "list"],
];

/* ---------- Frames ---------- */

const services = () => app.kitchen.bookings?.services ?? [];
const menuNames = () => (app.kitchen.recipes?.recipes ?? []).map((recipe) => recipe.name);
const kitchenName = () => app.state?.kitchen?.name ?? "Your kitchen";
/* Where the order lives in this version: on the home screen, or on its own screen in the console. */
const orderRoute = () => (app.variant === "b" ? "order" : "today");

function navLinks(withIcons) {
  const pending = pendingApproval() ? 1 : 0;
  return NAV.map(([route, label, glyph]) => {
    const on = app.route === route || (route === "today" && app.route === "order");
    const badge = route === "approvals" && pending ? `<span class="nav__badge">${pending}</span>` : "";
    return `<a class="nav__link${on ? " is-on" : ""}" href="#/${route}" ${on ? 'aria-current="page"' : ""}>${withIcons ? icon(glyph, 18) : ""}<span>${label}</span>${badge}</a>`;
  }).join("");
}

/* The assistant, in one small chip: what it is doing right now. It leads to the order. */
function agentChip() {
  let tone = "ready";
  let text = "ready";
  if (app.busy || revealing() || status() === "running") [tone, text] = ["working", "working"];
  else if (pendingApproval()) [tone, text] = ["waiting", "waiting for you"];
  else if (status() === "done") [tone, text] = ["done", "order placed"];
  else if (status() === "refused") [tone, text] = ["refused", isAttack() ? "3 orders refused" : "nothing ordered"];
  return `<a class="agentchip agentchip--${tone}" href="#/${isAttack() ? "audit" : orderRoute()}">${icon("spark", 14)}<b>${ASSISTANT}</b><span>${text}</span></a>`;
}

const brand = () => `<a class="brand" href="#/today" aria-label="Valio Aimo, home">
    <img src="../img/valio-aimo-logo-petrol.svg" alt="Valio Aimo" width="78" height="26" />
  </a>`;

function frameTop(view) {
  return `<div class="shell shell--top">
      <header class="top">
        ${brand()}
        <nav class="nav nav--top" aria-label="Sections">${navLinks(false)}</nav>
        <div class="top__right">${agentChip()}<span class="account">${esc(kitchenName())}</span></div>
      </header>
      <main class="view">${view}</main>
    </div>`;
}

function frameSide(view) {
  const limit = limitKnown()
    ? `<div class="sidecard">
        <p class="sidecard__label">${ASSISTANT} signs alone up to</p>
        <p class="sidecard__value">${esc(limitText())}</p>
        <a class="link" href="#/rules">Change the rules</a>
      </div>`
    : "";
  return `<div class="shell shell--side">
      <aside class="side">
        ${brand()}
        <nav class="nav nav--side" aria-label="Sections">${navLinks(true)}</nav>
        <a class="btn btn--go btn--wide side__new" href="#/order">New order</a>
        <div class="side__foot">
          ${limit}
          ${agentChip()}
          <p class="account">${esc(kitchenName())}</p>
        </div>
      </aside>
      <main class="view">${view}</main>
    </div>`;
}

/* ---------- Home, version A: the brief ---------- */

function headline() {
  const first = services()[0]?.date;
  const day = first ? new Intl.DateTimeFormat("en-GB", { weekday: "long", timeZone: "UTC" }).format(new Date(`${first}T00:00:00Z`)) : "This week";
  if (app.busy || revealing() || status() === "running") return `${ASSISTANT} is on it.`;
  if (pendingApproval()) return "One order needs your signature.";
  if (orderOnScreen() && status() === "done") return `${day}'s order is placed.`;
  if (orderOnScreen() && status() === "refused") return "Nothing was ordered.";
  return missingLines().length ? `${day}'s order is ready.` : "Nothing to order today.";
}

function weekLine() {
  const list = services();
  if (!list.length) return "";
  const booked = list.reduce((sum, service) => sum + service.booked, 0);
  const projected = list.reduce((sum, service) => sum + service.projected, 0);
  const menu = menuNames();
  return `${menu.length ? `${menu.join(", ")}. ` : ""}${plural(list.length, "dinner service", "dinner services")}, ${serviceDays()}: ${booked} covers booked, ${projected} planned.`;
}

function todayBrief() {
  const count = orderOnScreen() && app.shown >= 2 && app.state.quote ? app.state.quote.line_items.length : missingLines().length;
  const label = orderOnScreen() && app.shown >= 2 ? `${plural(count, "line", "lines")} in Valio's signed quote` : `${plural(count, "ingredient", "ingredients")} to order`;
  return `<div class="page page--brief">
      <p class="brief__eyebrow">${esc(kitchenName())}</p>
      <h1 class="brief__title">${esc(headline())}</h1>
      <p class="brief__lead">${esc(weekLine())}</p>
      ${agentCard({ cta: `${orderCta({ wide: false })}<p class="agent__who agent__who--${esc(whoSigns().tone)}"><span>Who signs</span>${esc(whoSigns().text)}</p>` })}
      <details class="fold fold--card" data-fold="lines" ${app.linesOpen ? "open" : ""}>
        <summary>${esc(label)}</summary>
        ${linesBlock()}
      </details>
      ${guards()}
    </div>`;
}

/* ---------- Home, version B: the console ---------- */

function consoleNotice() {
  const first = services()[0]?.date;
  const count = missingLines().length;
  if (pendingApproval()) {
    return `<div class="notice notice--warn"><span class="notice__icon">${icon("pen", 18)}</span>
        <p class="notice__text"><b>1 order needs your signature.</b> ${ASSISTANT} stopped where your rules told it to.</p>
        <a class="btn btn--sign" href="#/approvals">Review and sign</a></div>`;
  }
  if (isAttack()) {
    return `<div class="notice notice--bad"><span class="notice__icon">${icon("shield", 18)}</span>
        <p class="notice__text"><b>3 orders were sent to Valio without your safety checks.</b> Valio refused all three: no valid signature, no order.</p>
        <a class="btn btn--quiet" href="#/audit">Open the audit log</a></div>`;
  }
  if (orderOnScreen() && status() === "done") {
    const order = app.state.order;
    return `<div class="notice notice--ok"><span class="notice__icon">${icon("check", 18)}</span>
        <p class="notice__text"><b>Order ${esc(order.order_id)} is placed.</b> ${esc(money(order.total_minor, order.currency))} before tax, delivery ${esc(dayLong(order.delivery_date))}, ${order.signed_by === "human" ? "signed by you" : `signed by ${ASSISTANT} inside your limit`}.</p>
        <button class="btn btn--quiet" type="button" data-proof="current">View proof</button></div>`;
  }
  if (!count) return "";
  return `<div class="notice notice--lime"><span class="notice__icon">${icon("spark", 18)}</span>
      <p class="notice__text"><b>${esc(plural(count, "ingredient is", "ingredients are"))} short for ${esc(first ? dayLong(first) : "the next service")}.</b> ${ASSISTANT} read the menu, compared it with your stock and prepared the order.</p>
      <a class="btn btn--go" href="#/order">Review the order${icon("arrow", 16)}</a></div>`;
}

function stockTable() {
  const rows = app.lines
    .map(
      (line) => `<tr class="${line.to_order > 0 ? "is-short" : ""}">
        <td><b>${esc(line.name)}</b></td>
        <td class="muted">${esc(line.dishes.join(", "))}</td>
        <td class="num">${esc(qty(line.need, line.unit))}</td>
        <td class="num">${esc(qty(line.in_stock, line.unit))}</td>
        <td class="num">${line.to_order > 0 ? `<b>${esc(qty(line.to_order, line.unit))}</b>` : '<span class="muted">covered</span>'}</td>
      </tr>`
    )
    .join("");
  return `<table class="tbl tbl--rows">
      <thead><tr><th>Ingredient</th><th>Used in</th><th class="num">Needed</th><th class="num">In stock</th><th class="num">To order</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function todayConsole() {
  const next = orderOnScreen() && app.shown >= 7 && app.state.order ? dayLong(app.state.order.delivery_date) : null;
  const stock = app.kitchen.stock;
  return `<div class="page page--wide">
      <header class="page__head">
        <div><h1 class="page__title">Kitchen</h1><p class="page__lead">${esc(weekLine())}</p></div>
      </header>
      ${consoleNotice()}
      <div class="tiles tiles--4">
        <div class="tile"><p class="tile__label">To order</p><p class="tile__value">${missingLines().length}<span> of ${app.lines.length} ingredients</span></p></div>
        <div class="tile${pendingApproval() ? " tile--warn" : ""}"><p class="tile__label">Needs your signature</p><p class="tile__value">${pendingApproval() ? 1 : 0}</p></div>
        <div class="tile"><p class="tile__label">Next delivery</p><p class="tile__value tile__value--text">${esc(next ?? "None yet")}</p></div>
        <div class="tile"><p class="tile__label">${ASSISTANT} signs alone up to</p><p class="tile__value tile__value--text">${esc(limitText() ?? "unknown")}</p></div>
      </div>
      <section class="section">
        <div class="section__head"><h2 class="section__title">Stock for the ${esc(String(stock?.for_services ?? ""))} services</h2><p class="muted">Counted on ${esc(stock ? dayLong(stock.counted_at) : "unknown")}</p></div>
        <div class="card card--table">${stockTable()}</div>
      </section>
    </div>`;
}

/* The order on its own screen: the lines and the rules on the left, the assistant on the right, the bar below. */
function orderScreen() {
  const quote = orderOnScreen() && app.shown >= 2 ? app.state.quote : null;
  return `<div class="page page--wide page--order">
      <header class="page__head">
        <div>
          <h1 class="page__title">${quote ? "Quote signed by Valio Aimo" : "Order for the week"}</h1>
          <p class="page__lead">${esc(quote ? `Delivery ${dayLong(quote.aimo.delivery_date)}. Prices before tax.` : weekLine())}</p>
        </div>
      </header>
      <div class="split split--order">
        <div class="split__main">
          <div class="card card--table">${linesBlock()}</div>
          ${prospectCard()}
          ${guards()}
        </div>
        <div class="split__side">${agentCard({ compact: true })}</div>
      </div>
      ${orderBar()}
    </div>`;
}

/* ---------- Home, version C: guided ---------- */

function guidedSteps() {
  const names = ["Menu", "Stock", "Order"];
  const metas = [`${plural(menuNames().length, "recipe", "recipes")}`, `${missingLines().length} short`, orderOnScreen() ? whoSigns().text : "then the signatures"];
  return `<ol class="stepper">${names
    .map((name, index) => {
      const number = index + 1;
      const state = app.step === number ? " is-on" : app.step > number ? " is-done" : "";
      return `<li><button class="stepper__step${state}" type="button" data-step="${number}">
          <span class="stepper__num">${app.step > number ? icon("check", 14) : number}</span>
          <span><b>${name}</b><small>${esc(metas[index])}</small></span>
        </button></li>`;
    })
    .join("")}</ol>`;
}

/* One sentence from the assistant, for the step on screen. It replaces the conversation of the first page. */
function guidedLine() {
  const stock = app.kitchen.stock;
  let text = "";
  if (app.step === 1) text = `These are the ${menuNames().length} recipes on the menu for ${serviceDays()}. I worked out what they need for ${app.state?.kitchen?.covers_per_service ?? 50} covers a service.`;
  else if (app.step === 2) text = `${missingLines().length} of ${app.lines.length} ingredients are short, from your count of ${stock ? dayLong(stock.counted_at) : "the last count"}. I order only what is missing.`;
  else if (!hasRun()) text = `I will ask Valio Aimo for a signed quote for ${plural(missingLines().length, "ingredient", "ingredients")}${limitKnown() ? `. Up to ${limitText()} I may sign alone, if every check passes` : ""}.`;
  else if (pendingApproval()) text = "I stopped: one of your rules asks for your signature.";
  else if (status() === "done") text = "Done. Valio accepted the order and signed the receipt.";
  else if (status() === "refused") text = "Nothing was ordered.";
  else text = "Working on it.";
  return `<p class="guideline">${icon("spark", 16)}<b>${ASSISTANT}</b>${esc(text)}</p>`;
}

function menuStep() {
  const recipes = app.kitchen.recipes?.recipes ?? [];
  const cards = recipes
    .map(
      (recipe) => `<article class="card recipe">
        <p class="eyebrow">${esc(recipe.course)}</p>
        <h3 class="recipe__name">${esc(recipe.name)}</h3>
        <ul class="recipe__list">${recipe.ingredients.map((item) => `<li><span>${esc(item.name)}</span><span class="muted">${esc(item.per_service)}</span></li>`).join("")}</ul>
      </article>`
    )
    .join("");
  const days = services()
    .map((service) => `<div class="day"><p class="day__date">${esc(dayShort(service.date))}</p><p class="day__covers"><b>${service.booked}</b> booked · ${service.projected} planned</p></div>`)
    .join("");
  return `<div class="days">${days}</div><div class="recipes">${cards}</div>
    <p class="tbl__note">Quantities for one service of ${esc(String(app.kitchen.recipes?.covers_per_service ?? 50))} covers.</p>`;
}

function todayGuided() {
  let body = "";
  let next = "";
  if (app.step === 1) {
    body = menuStep();
    next = `<button class="btn btn--go" type="button" data-step="2">Check the stock${icon("arrow", 16)}</button>`;
  } else if (app.step === 2) {
    body = `<div class="card card--table">${stockTable()}</div>`;
    next = `<button class="btn btn--go" type="button" data-step="3">Prepare the order${icon("arrow", 16)}</button>`;
  } else {
    body = `<div class="split split--order">
        <div class="split__main"><div class="card card--table">${linesBlock()}</div>${guards()}</div>
        <div class="split__side">${agentCard({ compact: true })}</div>
      </div>`;
  }
  return `<div class="page page--wide page--order">
      <div class="guided__head">${guidedSteps()}${next ? `<div class="guided__next">${next}</div>` : ""}</div>
      ${guidedLine()}
      ${body}
      ${app.step === 3 ? orderBar() : ""}
    </div>`;
}

/* ---------- Drawing ---------- */

function viewHtml() {
  const problem = app.problem ? `<div class="notice notice--bad" role="alert"><span class="notice__icon">${icon("cross", 18)}</span><p class="notice__text"><b>Something did not answer.</b> ${esc(app.problem)}</p></div>` : "";
  let view = "";
  if (app.route === "orders") view = ordersPage();
  else if (app.route === "approvals") view = approvalsPage();
  else if (app.route === "rules") view = rulesPage();
  else if (app.route === "audit") view = auditPage();
  else if (app.route === "order" && app.variant === "b") view = orderScreen();
  else view = app.variant === "b" ? todayConsole() : app.variant === "c" ? todayGuided() : todayBrief();
  return problem ? view.replace('<div class="page', `<div class="page-problem">${problem}</div><div class="page`) : view;
}

function devStrip() {
  if (!app.strip) return "";
  const scenarios = [
    ["normal-order", "1 Order"],
    ["substitution", "2 Substitute"],
    ["attack", "3 Attack"],
  ]
    .map(([id, label]) => {
      const on = app.state?.scenario?.id ? app.state.scenario.id === id : app.scenarioId === id;
      return `<button class="dev__btn${on ? " is-on" : ""}" type="button" data-scenario="${id}" ${app.busy ? "disabled" : ""}>${label}</button>`;
    })
    .join("");
  const versions = Object.entries(VARIANT_NAMES)
    .map(([key, name]) => `<button class="dev__btn${app.variant === key ? " is-on" : ""}" type="button" data-variant="${key}">${key.toUpperCase()} ${name}</button>`)
    .join("");
  const light = (name, on) => `<span class="dev__light${on ? " is-on" : ""}">${name}</span>`;
  // The console is the main version. The two others only show here once someone asked for a version (?v= or the v key).
  const compare = app.comparing ? `<span class="dev__sep"></span><span class="dev__label">Version</span>${versions}` : "";
  return `<span class="dev__label">Demo</span>${scenarios}
    <button class="dev__btn" type="button" data-reset ${app.busy ? "disabled" : ""}>Reset</button>
    ${compare}
    <span class="dev__sep"></span>${light(`driver ${app.mode}`, app.up.driver)}${light("harness", app.up.harness)}${light("gateway", app.up.merchant)}${light("chat", app.up.assistant)}
    <span class="dev__hint">keys: 1 2 3 scenario · r reset · v version · h hide</span>`;
}

/* Redraw, and keep the field the chef is typing in: its focus, its text and its caret survive. */
function draw() {
  const active = document.activeElement;
  const keep =
    active && active !== document.body && (active.id || active.dataset?.rule)
      ? { id: active.id, rule: active.dataset.rule, type: active.type, value: active.value, start: active.selectionStart, end: active.selectionEnd }
      : null;
  const frame = app.variant === "b" ? frameSide : frameTop;
  setHtml(el("app"), frame(viewHtml()) + proofPanel());
  setHtml(el("dev"), devStrip());
  document.body.dataset.variant = app.variant;
  document.body.classList.toggle("has-strip", app.strip);
  document.title = `Valio Aimo: ${NAV.find(([route]) => route === app.route)?.[1] ?? "Order"} (concept mock-up)`;
  if (keep && document.activeElement !== active) {
    const again = keep.id ? el(keep.id) : [...document.querySelectorAll(`[data-rule="${keep.rule}"]`)].find((node) => node.type === keep.type);
    if (again) {
      if (keep.id === "ask-text") again.value = keep.value;
      again.focus({ preventScroll: true });
      try {
        if (keep.start !== null && again.setSelectionRange && again.type !== "number" && again.type !== "range") again.setSelectionRange(keep.start, keep.end);
      } catch {
        /* some field types have no caret */
      }
    }
  }
  if (app.eco.key !== ecoKey() && !app.eco.loading) refreshEco();
}

let toastTimer = null;
function toast(text) {
  const node = el("toast");
  node.textContent = text;
  node.classList.add("is-on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("is-on"), 2600);
}

/* ---------- The run: the steps arrive one after the other ---------- */

let revealTimer = null;
let freshTimer = null;
function reveal() {
  clearTimeout(revealTimer);
  clearTimeout(freshTimer);
  if (app.shown >= reachable()) {
    freshTimer = setTimeout(() => {
      app.fresh = null;
      draw();
    }, 900);
    draw();
    afterRun();
    return;
  }
  app.shown += 1;
  app.fresh = app.shown - 1;
  draw();
  revealTimer = setTimeout(reveal, REVEAL_MS);
}

/* Once the steps are all on screen: read again what the services hold, so the other screens are up to date. */
function afterRun() {
  if (app.mode === "live") {
    loadSession();
    loadLedger();
  }
}

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

const idleState = () => (app.mode === "live" ? driver.reset() : recorded("idle"));

/* The driver is there but could not run the scenario: the page shows the recorded run instead, and says so. */
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

function startOver() {
  clearTimeout(revealTimer);
  app.shown = 0;
  app.fresh = null;
  app.sentKey = null;
  app.detailsOpen = false;
  app.proof = null;
  app.step = 1;
  app.ask = { busy: false, question: null, answer: null, changes: [], failed: false };
  app.eco.dismissed = new Set();
  loadLines(app.kitchen.stock);
}

async function chooseScenario(id) {
  await guarded(async () => {
    app.state = await idleState();
    app.scenarioId = id === "attack" ? "normal-order" : id;
    app.kitchen.stock = await kitchenApi.stock(id);
    startOver();
    if (id === "attack") {
      // The attack is not something the chef does: it runs at once, and its place is the audit log.
      go("audit");
      draw();
      app.state = await liveOrRecorded(
        () => driver.run("attack"),
        () => recorded("attack")
      );
      reveal();
      watch();
    } else if (!["today", "order"].includes(app.route)) {
      go("today");
    }
  });
}

/* In replay mode, the recorded run that asked for exactly these quantities, or else the run of the scenario. */
async function replayRun(lines) {
  for (const name of [replayFile("normal-order"), replayFile("substitution"), "normal-order.greener"]) {
    const run = await recorded(name);
    if (linesKey(run.request?.lines) === linesKey(lines)) return run;
  }
  return recorded(replayFile(app.scenarioId));
}

async function send() {
  if (app.busy || !missingLines().length) return;
  await guarded(async () => {
    const lines = orderLines();
    const deliveryDate = services()[0]?.date ?? null;
    clearTimeout(revealTimer);
    if (hasRun()) app.state = await idleState(); // a new order starts from a clean trail
    app.shown = 0;
    app.fresh = null;
    app.linesOpen = true;
    if (app.variant === "c") app.step = 3;
    draw();
    app.state = await liveOrRecorded(
      () => driver.run(app.scenarioId, { lines, delivery_date: deliveryDate }),
      () => replayRun(lines)
    );
    app.sentKey = linesKey(lines);
    reveal();
    watch();
  });
}

async function newOrder() {
  await guarded(async () => {
    app.state = await idleState();
    startOver();
    if (app.variant === "c") app.step = 3;
    go(orderRoute());
  });
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

async function decide(decision, thenEdit = false) {
  const approval = app.state?.approval;
  if (!approval || approval.status !== "pending") return;
  await guarded(async () => {
    if (app.mode === "live") {
      await harness.decide(approval.approval_id, decision);
      app.state = await driver.state();
    } else {
      app.state = decision === "approve" ? await recorded("substitution.approved") : rejectedReplay(app.state);
    }
    toast(decision === "approve" ? "Signed" : "Rejected: nothing is ordered");
    if (thenEdit) {
      app.state = await idleState();
      startOver();
      if (app.variant === "c") app.step = 2;
      go(orderRoute());
      return;
    }
    app.shown = Math.min(app.shown, 3); // the signature step arrives again, signed this time
    go(orderRoute());
    reveal();
    watch();
  });
}

/* ---------- Footprint, and the assistant's answers ---------- */

async function recordedFootprint(key) {
  for (const name of ["normal-order", "normal-order.greener"]) {
    const found = await recordedFootprintFile(name).catch(() => null);
    if (found && linesKey(found.lines) === key) return found;
  }
  return null;
}

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

function applySwap(productId, by) {
  const swap = swapLine(productId, ecoOffer(productId)?.alternative.id, by);
  if (!swap) return;
  toast(`Greener swap: ${kgCo2(swap.offer.saving_kg_co2e)} less`);
  draw();
}

async function sendChat(text) {
  if (!text || app.ask.busy) return;
  const before = app.ask.question && app.ask.answer ? [{ who: "chef", text: app.ask.question }, { who: "assistant", text: app.ask.answer }] : [];
  app.ask = { busy: true, question: text, answer: null, changes: [], failed: false };
  draw();
  try {
    const answer = await assistant.chat([...before, { who: "chef", text: text.slice(0, 2000) }], pageFacts());
    // The page applies the changes itself and shows what really changed, whatever the reply says.
    const applied = (answer.stock_changes ?? []).map((change) => setStock(change.product_id, change.field, change.amount, ASSISTANT)).filter(Boolean);
    const swaps = (answer.swaps ?? []).map((swap) => swapLine(swap.product_id, swap.swap_to, ASSISTANT)).filter(Boolean);
    app.ask.answer = answer.reply;
    app.ask.changes = [...applied.map(changeText), ...swaps.map((swap) => `${swap.line.swapped_from.name} → ${swap.offer.alternative.name}: ${kgCo2(swap.offer.saving_kg_co2e)} less`)];
    if (swaps.length || applied.length) app.linesOpen = true;
  } catch (error) {
    app.up.assistant = Boolean(error.status) && error.status !== 503;
    app.ask.answer = "No answer just now. Nothing was changed.";
    app.ask.failed = true;
  } finally {
    app.ask.busy = false;
    draw();
    el("ask-text")?.focus();
  }
}

/* ---------- What the services hold from this session: orders, approvals, both audit logs ---------- */

const orderCache = new Map();
async function loadSession() {
  if (app.mode !== "live") return;
  const [approvals, authorizations] = await Promise.all([harness.approvals().catch(() => null), harness.authorizations().catch(() => null)]);
  if (approvals) app.session.approvals = approvals;
  if (authorizations) {
    const ordered = authorizations.filter((entry) => entry.order_id);
    const orders = await Promise.all(
      ordered.map(async (entry) => {
        if (!orderCache.has(entry.order_id)) {
          // The order says who signed and what it cost; the quote it was signed for says what was in it.
          const [order, quoted] = await Promise.all([merchant.order(entry.order_id).catch(() => null), merchant.checkout(entry.checkout_id).catch(() => null)]);
          if (order) orderCache.set(entry.order_id, { ...order, titles: quoted?.checkout?.line_items?.map((item) => item.item.title) ?? null });
        }
        return orderCache.get(entry.order_id) ?? null;
      })
    );
    app.session.orders = orders.filter(Boolean);
  }
  app.session.loaded = true;
  draw();
}

async function loadLedger() {
  if (app.mode !== "live") return;
  const [buyer, merchantLog] = await Promise.all([harness.audit().catch(() => null), merchant.audit().catch(() => null)]);
  app.up.merchant = Boolean(merchantLog);
  if (buyer) app.ledger.buyer = buyer;
  if (merchantLog) app.ledger.merchant = merchantLog;
  draw();
}

async function runChainCheck() {
  app.ledger.check = { running: true };
  draw();
  const rows = ledgerRows();
  const bySide = (side) => rows.filter((event) => event.side === side).sort((a, b) => a.seq - b.seq);
  const strip = ({ side: _side, ...event }) => event;
  const sideOf = (side) => bySide(side).map((event) => ({ ...strip(event), side }));
  const [buyerBroken, merchantBroken] = await Promise.all([verifyChain(sideOf("buyer")), verifyChain(sideOf("merchant"))]);
  app.ledger.check = {
    running: false,
    count: rows.length,
    broken: [...buyerBroken.map((seq) => `your log #${seq}`), ...merchantBroken.map((seq) => `Valio's log #${seq}`)],
  };
  draw();
}

async function recomputeOne(key) {
  const event = ledgerRows().find((entry) => ledgerKey(entry) === key);
  if (!event) return;
  app.ledger.one = { key, ok: (await digest(event)) === event.hash };
  draw();
}

/* The proof of one order: the current one from the demo state, an earlier one from the services, or a sample. */
async function openProof(id) {
  const state = app.state;
  const eventsFor = (checkoutId) =>
    ledgerRows()
      .filter((event) => event.checkout_id === checkoutId)
      .reverse();
  if (id === "current" || (state?.quote && id === state.quote.id)) {
    if (!state?.quote) return;
    app.proof = { kind: "real", order: app.shown >= 7 ? state.order : null, quote: state.quote, verdict: state.verdict, request: state.request, steps: state.steps, events: eventsFor(state.quote.id) };
  } else {
    const order = app.session.orders.find((entry) => entry.checkout_id === id);
    const sample = app.history.find((entry) => entry.checkout_id === id);
    if (order) {
      const verdict = await harness.verdict(id).catch(() => null);
      app.proof = { kind: "real", order, quote: null, verdict, request: null, steps: [], events: eventsFor(id) };
    } else if (sample) {
      app.proof = { kind: "sample", entry: sample };
    }
  }
  draw();
}

/* ---------- The rules screen ---------- */

function draft() {
  if (!app.rules.draft && app.policy) app.rules.draft = structuredClone(app.policy);
  return app.rules.draft;
}

function setRule(path, value) {
  const target = draft();
  if (!target) return;
  const keys = path.split(".");
  const last = keys.pop();
  const holder = keys.reduce((object, key) => object[key], target);
  holder[last] = value;
  if (!Object.keys(rulesChange()).length) app.rules.draft = null;
  app.rules.note = null;
}

async function saveRules() {
  const change = rulesChange();
  if (!Object.keys(change).length || app.rules.saving) return;
  app.rules.saving = true;
  draw();
  try {
    app.policy = await harness.changePolicy(change);
    app.rules.draft = null;
    app.rules.editingText = false;
    app.rules.note = { tone: "ok", text: "Rules signed and saved. They apply to the next order, and Valio checks the new limit on its side." };
    toast("Rules saved");
  } catch (error) {
    // The rules live in the harness, which enforces them. The page never keeps a rule of its own.
    const text =
      error.status === 404 || error.status === 405
        ? "This safety service cannot save rule changes yet (route PUT /policy not there). Nothing has changed."
        : error.status
          ? `The safety service refused: ${error.message}. Nothing has changed.`
          : "The safety service (harness) is not running, and only it can change the rules. Nothing has changed.";
    app.rules.note = { tone: "bad", text };
  } finally {
    app.rules.saving = false;
    draw();
  }
}

/* Forget the chef's changes: the harness goes back to the rules of the demo file. Used before a rehearsal. */
async function resetRules() {
  app.rules.saving = true;
  draw();
  try {
    app.policy = await harness.resetPolicy();
    app.rules.draft = null;
    app.rules.note = { tone: "ok", text: "Back to the demo rules. They apply to the next order." };
  } catch (error) {
    app.rules.note = {
      tone: "bad",
      text: error.status === 404 || error.status === 405 ? "This safety service cannot reset the rules yet (route POST /policy/reset not there). Nothing has changed." : "The safety service did not answer. Nothing has changed.",
    };
  } finally {
    app.rules.saving = false;
    draw();
  }
}

/* ---------- Routes ---------- */

function go(route) {
  if (window.location.hash !== `#/${route}`) window.location.hash = `#/${route}`;
  else readRoute();
}

function readRoute() {
  const wanted = window.location.hash.replace(/^#\//, "").split("/")[0];
  app.route = ROUTES.includes(wanted) ? wanted : "today";
  if (app.route === "order" && app.variant !== "b") {
    app.route = "today";
    if (app.variant === "c") app.step = 3;
  }
  app.proof = null;
  if (["orders", "approvals"].includes(app.route)) loadSession();
  if (app.route === "audit") loadLedger();
  window.scrollTo(0, 0);
  draw();
}

function setVariant(variant) {
  app.variant = variant;
  app.comparing = true;
  const url = new URL(window.location.href);
  url.searchParams.set("v", variant);
  window.history.replaceState(null, "", url);
  if (variant === "c" && hasRun()) app.step = 3;
  readRoute();
}

/* ---------- Events ---------- */

document.addEventListener("click", (event) => {
  // button[data-variant], not [data-variant]: the body carries data-variant too (for the stylesheet), and a click
  // on plain text must not be read as "switch to the version on screen".
  const target = event.target.closest("[data-action],[data-proof],[data-scenario],button[data-variant],[data-reset],[data-step],[data-eco-swap],[data-eco-dismiss],[data-unswap],[data-ledger],[data-ledger-filter],[data-rule-set],[data-rule-toggle],[data-allergen-remove]");
  if (!target) return;
  const data = target.dataset;
  if (data.scenario) return void chooseScenario(data.scenario);
  if (data.variant) return void setVariant(data.variant);
  if ("reset" in data) return void chooseScenario(app.scenarioId);
  if (data.step) {
    app.step = Number(data.step);
    return void draw();
  }
  if (data.proof) return void openProof(data.proof);
  if (data.ecoSwap) return void applySwap(data.ecoSwap, "you");
  if (data.ecoDismiss) {
    app.eco.dismissed.add(data.ecoDismiss);
    return void draw();
  }
  if (data.unswap) {
    const line = app.lines.find((entry) => entry.product_id === data.unswap);
    if (line && canEdit()) unswap(line);
    return void draw();
  }
  if (data.ledger) {
    app.ledger.selected = data.ledger;
    return void draw();
  }
  if (data.ledgerFilter) {
    app.ledger.filter = data.ledgerFilter;
    return void draw();
  }
  if (data.ruleSet) {
    setRule(data.ruleSet, data.value);
    return void draw();
  }
  if (data.ruleToggle) {
    const current = data.ruleToggle.split(".").reduce((object, key) => object?.[key], draft());
    setRule(data.ruleToggle, !current);
    return void draw();
  }
  if (data.allergenRemove) {
    setRule("blocked_allergens", draft().blocked_allergens.filter((code) => code !== data.allergenRemove));
    return void draw();
  }
  switch (data.action) {
    case "send":
      return void send();
    case "new-order":
      return void newOrder();
    case "approve":
      return void decide("approve");
    case "reject":
      return void decide("reject");
    case "reject-edit":
      return void decide("reject", true);
    case "close-proof":
      app.proof = null;
      return void draw();
    case "proof-json":
      return void download(`proof-${app.proof?.order?.order_id ?? app.proof?.quote?.id ?? "order"}.json`, app.proof);
    case "verify-chain":
      return void runChainCheck();
    case "audit-json":
      return void download("audit-logs.json", { buyer: ledgerRows().filter((row) => row.side === "buyer"), merchant: ledgerRows().filter((row) => row.side === "merchant") });
    case "recompute":
      return void recomputeOne(data.key);
    case "rules-save":
      return void saveRules();
    case "rules-reset":
      return void resetRules();
    case "rules-discard":
      app.rules.draft = null;
      app.rules.note = null;
      app.rules.editingText = false;
      return void draw();
    case "edit-prefs":
      app.rules.editingText = !app.rules.editingText;
      return void draw();
    case "toggle-prospect": {
      app.prospect.open = !app.prospect.open;
      draw();
      const customer = kitchenName();
      if (app.prospect.open && (!app.prospect.data || app.prospect.data.customer !== customer) && !app.prospect.busy) {
        fetchProspect(customer);
      }
      return;
    }
    case "add-prospect":
      if (data.productId) addProspectItem(data.productId);
      return;
    default:
  }
});

/* A gauge moves: the other field of the same rule follows at once, the screen is redrawn when the hand lets go. */
function readGauge(node) {
  const path = node.dataset.rule;
  if (node.tagName === "TEXTAREA") return setRule(path, node.value);
  const raw = Number(node.value);
  if (!Number.isFinite(raw)) return;
  if (path === "autonomous_limit_minor") setRule(path, Math.max(100, Math.round(raw * 100)));
  else if ("percent" in node.dataset) setRule(path, Math.min(1, Math.max(0, raw / 100)));
}

document.addEventListener("input", (event) => {
  const node = event.target;
  if (node.id === "ask-text") return;
  if (node.dataset?.prospectQty) {
    const pid = node.dataset.prospectQty;
    const item = (app.prospect.data?.items ?? []).find((entry) => entry.product.id === pid);
    const val = Number(String(node.value).replace(",", "."));
    if (Number.isFinite(val) && val > 0) {
      app.prospect.qty[pid] = item?.available_base_quantity ? Math.min(val, Number(item.available_base_quantity)) : val;
    }
    return;
  }
  if (!node.dataset?.rule) return;
  readGauge(node);
  if (node.tagName === "TEXTAREA") return void draw();
  document.querySelectorAll(`[data-rule="${node.dataset.rule}"]`).forEach((other) => {
    if (other !== node) other.value = node.value;
  });
  const bar = document.querySelector(".savebar");
  if (bar) bar.classList.toggle("is-on", Object.keys(rulesChange()).length > 0);
});

document.addEventListener("change", (event) => {
  const node = event.target;
  if (node.matches?.("[data-allergen-add]") && node.value) {
    setRule("blocked_allergens", [...draft().blocked_allergens, node.value]);
    return void draw();
  }
  if (node.dataset?.rule) {
    readGauge(node);
    draw();
  }
});

document.addEventListener("submit", (event) => {
  if (event.target.id !== "ask") return;
  event.preventDefault();
  const field = el("ask-text");
  const text = field.value.trim();
  field.value = "";
  sendChat(text);
});

/* A folded block remembers whether the chef opened it. The toggle event does not bubble: listen on the way down. */
document.addEventListener(
  "toggle",
  (event) => {
    const fold = event.target.dataset?.fold;
    if (fold === "lines") app.linesOpen = event.target.open;
    if (fold === "details") app.detailsOpen = event.target.open;
    if (fold === "prefs") app.rules.prefsOpen = event.target.open;
  },
  true
);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && app.proof) {
    app.proof = null;
    return void draw();
  }
  if (event.target.matches?.("input, textarea, select") || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "Enter" && event.target.matches?.("[data-ledger]")) {
    app.ledger.selected = event.target.dataset.ledger;
    return void draw();
  }
  const scenario = { 1: "normal-order", 2: "substitution", 3: "attack" }[event.key];
  if (scenario) return void chooseScenario(scenario);
  if (event.key === "r") return void chooseScenario(app.scenarioId);
  if (event.key === "h") {
    app.strip = !app.strip;
    return void draw();
  }
  if (event.key === "v") setVariant({ a: "b", b: "c", c: "a" }[app.variant]);
});

window.addEventListener("hashchange", readRoute);

/* ---------- Start ---------- */

/* Are the services there? The page looks again every few seconds, so a service started later shows up by itself. */
async function checkServices() {
  const [policy, health, state] = await Promise.all([
    harness.policy().catch(() => null),
    assistant.health().catch(() => null),
    QUERY.has("replay") ? null : driver.state().catch(() => null),
  ]);
  app.up.harness = Boolean(policy);
  if (policy && !app.rules.saving) {
    app.policy = policy;
    app.policyFromFile = false;
  } else if (!policy && (!app.policy || app.policyFromFile)) {
    // No harness: the rules of the demo file can still be read. They cannot be changed, and the page says so.
    const file = await policyFile().catch(() => null);
    if (file && !app.up.harness) {
      app.policy = file;
      app.policyFromFile = true;
      app.rules.draft = null;
    }
  }
  app.up.assistant = Boolean(health?.chat);
  app.up.driver = Boolean(state && Array.isArray(state.steps));
  // The driver arrived while nothing was running: from now on the page is live.
  if (app.up.driver && app.mode === "replay" && !hasRun() && !app.busy) {
    app.mode = "live";
    app.state = state;
    if (hasRun()) {
      // An order was already open when the page loaded: show it as it is, with the stock count it was made from.
      app.shown = reachable();
      const open = state.scenario.id;
      if (["normal-order", "substitution"].includes(open) && open !== app.scenarioId) {
        app.scenarioId = open;
        app.kitchen.stock = await kitchenApi.stock(open).catch(() => app.kitchen.stock);
        loadLines(app.kitchen.stock);
      }
      if (app.variant === "c") app.step = 3;
    }
    loadSession();
    loadLedger();
  }
  draw();
  setTimeout(checkServices, SERVICES_MS);
}

async function fetchProspect(customer) {
  if (app.prospect.busy) return;
  app.prospect.busy = true;
  draw();
  try {
    app.prospect.data = await merchant.prospect(customer);
  } catch (error) {
    app.prospect.data = null;
    toast(`Could not load prospect: ${error.message}`);
  } finally {
    app.prospect.busy = false;
    draw();
  }
}

function addProspectItem(productId) {
  const item = (app.prospect.data?.items ?? []).find((entry) => entry.product.id === productId);
  if (!item || !canEdit() || app.prospect.added.has(productId)) return;
  const input = document.querySelector(`[data-prospect-qty="${CSS.escape(productId)}"]`);
  const raw = Number(String(input?.value ?? app.prospect.qty[productId] ?? "").replace(",", "."));
  const addQty = Number.isFinite(raw) && raw > 0 ? Math.min(raw, Number(item.available_base_quantity ?? raw)) : defaultProspectQty(item);
  app.prospect.qty[productId] = addQty;
  const existing = app.lines.find((line) => line.product_id === productId);
  if (existing) {
    existing.to_order = Math.round((existing.to_order + addQty) * 1000) / 1000;
    existing.need = Math.round((existing.need + addQty) * 1000) / 1000;
    existing.claim_promo = true;
    existing.by.to_order = "prospect";
  } else {
    app.lines.push({
      product_id: productId,
      name: item.product.name,
      unit: item.product.base_unit ?? "KG",
      need: addQty,
      in_stock: 0,
      to_order: addQty,
      counted: 0,
      dishes: ["Clearance / MHD deal"],
      by: { to_order: "prospect" },
      claim_promo: true,
    });
  }
  app.prospect.added.add(productId);
  toast(`Added ${addQty} ${item.product.base_unit ?? "KG"} of ${item.product.name}`);
  draw();
}

async function start() {
  const [recipes, bookings, stock, history, idle] = await Promise.all([
    kitchenApi.recipes().catch(() => null),
    kitchenApi.bookings().catch(() => null),
    kitchenApi.stock(app.scenarioId).catch(() => null),
    kitchenApi.history().catch(() => null),
    recorded("idle").catch(() => null),
  ]);
  app.kitchen = { recipes, bookings, stock };
  app.history = history?.orders ?? [];
  app.state = idle;
  loadLines(stock);
  readRoute();
  checkServices();
}

start();
