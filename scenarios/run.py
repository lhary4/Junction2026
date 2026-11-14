"""The demo driver, port 8003: it plays the buying agent for the demo page, and tells the page everything it shows.

Run: uv run uvicorn scenarios.run:app --port 8003        (or the three services at once: uv run python scripts/dev.py)
From the terminal, with the gateway and the harness running:  uv run python scenarios/run.py normal-order

It makes the same calls as the MCP tools: POST /checkouts on the gateway, then POST /authorize on the harness. For an
order it holds no key and signs nothing. GET /state reads the quote, the verdict, the approval, the order and both audit
logs back from the two services and returns one DemoState (contract/models.py). The page renders it and works out no
fact itself.

The chef's decision does not come through here: the page sends it to the harness, and the next GET /state shows it.
The driver only remembers which scenario is on screen and which quote it asked for. Everything else is read again on
every call, so the state can never disagree with what the gateway and the harness hold.

The attack scenario is the one exception to "no key". There the driver plays an agent whose key leaked, together with
a copy of the open mandates: it skips the harness and sends three bad mandates straight to the gateway. It builds them
from the demo keys of the repo (contract/fixtures/keys/), the way the gateway's own tests do.
"""

import base64
import json
import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `python scenarios/run.py` finds contract/ and trust/, like the scripts do

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from common.money import money
from contract.models import (
    ApprovalRequest,
    AuditEvent,
    Authorization,
    AuthorizationStatus,
    BuyerPolicy,
    CheckoutResponse,
    DemoState,
    Order,
    Verdict,
)
from trust.checkout import checkout_hash
from trust.keys import private_key, public_jwk
from trust.mandates import close_as_agent, issue_open_mandates

HELSINKI = ZoneInfo("Europe/Helsinki")
CASE = json.loads((ROOT / "scenarios" / "restaurant-case" / "order.json").read_text(encoding="utf-8"))
# What the kitchen calls each product, and the dish it goes into: from the restaurant case, never typed again here.
INGREDIENTS = {line["product"]["product_id"]: (line["ingredient"], line["dish"].capitalize()) for line in CASE["lines"]}
CUSTOMER = "demo-restaurant-helsinki"
DELIVERY_DATE = CASE["requested_delivery_date"]
ANSWER_TIMEOUT_SECONDS = 60  # a quote asks Valio twice, an authorization may ask the judge

KITCHEN = {
    "customer": CUSTOMER,
    "name": "Demo Restaurant Helsinki",
    "covers_per_service": CASE["covers_per_service"],
    "services": CASE["services"],
    "menu": [
        {
            "course": "Starter",
            "dish": "Cured rainbow trout, roasted Finnish beetroot, horseradish smetana, rye crisp, dill",
        },
        {
            "course": "Main",
            "dish": "Sautéed reindeer (poronkäristys), butter-mashed almond potatoes, lingonberries, pickled cucumber",
        },
        {"course": "Dessert", "dish": "Warm squeaky cheese (leipäjuusto), cloudberry jam, whipped cream, oat crumble"},
    ],
}

# The seven steps of the AP2 trail, with who signs each one when nothing says otherwise yet.
TRAIL = (
    ("open_mandate", "Open mandate", "manager"),
    ("signed_quote", "Signed quote", "merchant"),
    ("verdict", "Verdict", "none"),
    ("closed_mandates", "Closed mandates", "none"),
    ("merchant_verifies", "Valio verifies", "merchant"),
    ("sandbox_payment", "Sandbox payment", "merchant"),
    ("signed_receipt", "Signed receipt", "merchant"),
)
SCENARIO_STATUS = {
    "ordered": "done",
    "pending_approval": "waiting_for_human",
    "denied": "refused",
    "rejected": "refused",
    "expired": "refused",
}


@dataclass(frozen=True)
class Scenario:
    """One button of the page: what the kitchen is missing, in its own units, and the sentence the agent was given."""

    id: str
    title: str
    hint: str
    text: str
    needs: tuple[tuple[str, float, str], ...]  # product id, amount, unit (KG, L or ST)
    delivery_date: str = DELIVERY_DATE
    customer: str = CUSTOMER
    # Only for an attack: `needs` must come to more than the agent's cap, and `other_needs` is another, smaller order
    # whose mandate the agent tries to reuse.
    attack: bool = False
    other_needs: tuple[tuple[str, float, str], ...] = ()


# What the kitchen is missing for one week of the menu's dairy and dry goods.
WEEK_OF_DAIRY_AND_DRY_GOODS = (
    ("463437", 6.45, "KG"),  # butter: 2.15 kg a service
    ("464194", 3.75, "L"),  # whipping cream
    ("476890", 4.5, "KG"),  # smetana
    ("464306", 7.5, "L"),  # milk
    ("460200", 1.5, "KG"),  # oat flakes
    ("467958", 6, "ST"),  # crispbread, by the pack
    ("468513", 2, "ST"),  # pickled cucumber, by the jar
    ("468172", 0.94, "KG"),  # salt
    ("460325", 1.05, "KG"),  # sugar
    ("466608", 0.6, "L"),  # rapeseed oil
)
ATTACK_WEEKS = 12  # ten weeks is EUR 1,497.65, under the EUR 1,500 cap: the gateway would rightly accept that order

SCENARIOS = (
    Scenario(
        id="normal-order",
        title="Normal order",
        hint="The dairy and dry goods of the menu. Inside the limits the chef signed: the agent signs.",
        text="Order the dairy and dry goods for this week's menu: three dinner services, 50 covers each.",
        needs=WEEK_OF_DAIRY_AND_DRY_GOODS,
    ),
    Scenario(
        id="substitution",
        title="Substitution",
        hint="Valio cannot deliver one ingredient. The chef compares the substitutes and signs.",
        text="Order the squeaky cheese for the dessert: 10.5 kg for the three services.",
        needs=(("474880", 10.5, "KG"),),
    ),
    Scenario(
        id="attack",
        title="Attack",
        hint="Three bad mandates sent straight to Valio. No valid signature, no order.",
        text="Order twelve weeks of the menu's dairy and dry goods at once.",
        needs=tuple((p, round(amount * ATTACK_WEEKS, 2), unit) for p, amount, unit in WEEK_OF_DAIRY_AND_DRY_GOODS),
        attack=True,
        other_needs=WEEK_OF_DAIRY_AND_DRY_GOODS,
    ),
)


class DriverError(Exception):
    """The driver could not do what was asked. `status_code` is what the page gets, `detail` is a readable sentence."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


class OpenMandateProofs(BaseModel):
    """The fingerprints of the open mandates the manager signed in advance: GET /mandates/open on the harness."""

    issued_at: datetime
    checkout_hash: str
    payment_hash: str  # the one the trail shows: the payment mandate carries the spend cap


@dataclass
class _Run:
    """What the driver remembers of the scenario on screen."""

    scenario: Scenario
    running: bool = True
    issued: CheckoutResponse | None = None
    attacks: list[dict] | None = None  # what Valio answered to each bad mandate, once they were sent
    stolen: OpenMandateProofs | None = None  # the attack only: the open mandates the leaked key came with


def service_url(name: str, default: str) -> str:
    return (os.environ.get(name) or default).rstrip("/")


class Driver:
    """Runs a scenario through the gateway and the harness, and builds the DemoState from what they answer."""

    def __init__(
        self,
        scenarios: tuple[Scenario, ...] = SCENARIOS,
        gateway: httpx.Client | None = None,
        harness: httpx.Client | None = None,
    ):
        self.scenarios = {scenario.id: scenario for scenario in scenarios}
        self.gateway = gateway or httpx.Client(
            base_url=service_url("MERCHANT_URL", "http://localhost:8001"), timeout=ANSWER_TIMEOUT_SECONDS
        )
        self.harness = harness or httpx.Client(
            base_url=service_url("HARNESS_URL", "http://localhost:8002"), timeout=ANSWER_TIMEOUT_SECONDS
        )
        self._lock = threading.Lock()  # held only to read or replace `_current`, never during a call to a service
        self._current: _Run | None = None

    # ---------- the three things the page asks ----------

    def reset(self) -> DemoState:
        with self._lock:
            if self._current and self._current.running:
                raise DriverError(409, "a scenario is still running: wait for it to end, then reset")
            self._current = None
        return self.state()

    def run(self, scenario_id: str) -> DemoState:
        """The buying agent's two calls: a signed quote from Valio, then the harness is asked to order it."""
        scenario = self.scenarios.get(scenario_id)
        if scenario is None:
            raise DriverError(404, f"no scenario {scenario_id!r} (there is: {', '.join(self.scenarios)})")
        run = _Run(scenario)
        with self._lock:
            if self._current and self._current.running:
                raise DriverError(409, f"scenario {self._current.scenario.id!r} is still running")
            self._current = run
        try:
            if scenario.attack:
                self._attack(run)
            else:
                run.issued = self._quote(scenario, scenario.needs)
                ask = {"checkout_id": run.issued.checkout_id, "request_text": scenario.text}
                self._post(self.harness, "harness", "/authorize", ask)
        except DriverError:
            with self._lock:
                if self._current is run:
                    self._current = None  # nothing to show: the page gets the error and the trail stays empty
            raise
        finally:
            run.running = False
        return self.state()

    def state(self) -> DemoState:
        with self._lock:
            run = self._current
        if run is None:
            return self._build(None, "idle", steps=[_step(key) for key, _, _ in TRAIL])
        issued = run.issued
        if issued is None:  # the quote has not come back yet
            return self._build(run, "running", steps=[_step(key) for key, _, _ in TRAIL])

        checkout_id = issued.checkout_id
        policy = self._get(self.harness, "harness", "/policy", BuyerPolicy)
        if run.scenario.attack:
            # The harness was never asked: its side has no verdict and no line to show. Valio's log tells the story.
            audit = {"buyer": [], "merchant": self._audit(self.gateway, "gateway", checkout_id)}
            sent = run.attacks or []
            all_refused = bool(sent) and all(attack["status"] == "refused" for attack in sent)
            status = "running" if run.running else ("refused" if all_refused else "done")
            return self._build(
                run,
                status,
                steps=_attack_steps(policy, run.stolen, issued, run.attacks, audit),
                quote=issued.checkout,
                attacks=sent,
                audit=audit,
            )
        proofs = self._get(self.harness, "harness", "/mandates/open", OpenMandateProofs)
        verdict = self._get(self.harness, "harness", f"/verdicts/{checkout_id}", Verdict)
        authorization = self._get(self.harness, "harness", f"/authorizations/{checkout_id}", AuthorizationStatus)
        approval = order = None
        if authorization and authorization.approval_id:
            approval = self._get(self.harness, "harness", f"/approvals/{authorization.approval_id}", ApprovalRequest)
        if authorization and authorization.order_id:
            order = self._get(self.gateway, "gateway", f"/orders/{authorization.order_id}", Order)
        audit = {
            "buyer": self._audit(self.harness, "harness", checkout_id),
            "merchant": self._audit(self.gateway, "gateway", checkout_id),
        }
        status = SCENARIO_STATUS[authorization.status] if authorization and not run.running else "running"
        return self._build(
            run,
            status,
            steps=_steps(policy, proofs, issued, verdict, authorization, approval, order, audit),
            quote=issued.checkout,
            verdict=verdict,
            authorization=authorization,
            approval=approval,
            order=order,
            audit=audit,
        )

    # ---------- the attack ----------

    def _attack(self, run: _Run) -> None:
        """An agent whose key leaked skips the harness and sends three bad mandates straight to Valio.

        The three aim at one quote that is above the agent's cap. Nothing here could be ordered honestly without the
        chef, so every answer must be a refusal. A quote under the cap is never attacked: Valio would accept it.
        """
        scenario = run.scenario
        policy = self._get(self.harness, "harness", "/policy", BuyerPolicy)
        if policy is None:
            raise DriverError(502, "the harness has no policy: the agent's cap is unknown")
        target = self._quote(scenario, scenario.needs)
        total, cap = target.checkout.total_minor(), policy.autonomous_limit_minor
        if total <= cap:
            raise DriverError(
                500,
                f"the attack needs a quote above the agent's cap: {money(total)} is within {money(cap)}, nothing sent",
            )
        run.issued = target
        other = self._quote(scenario, scenario.other_needs)

        # The stolen material: the agent's key, and open mandates the manager signed for that key.
        agent = private_key("agent")
        open_mandates = issue_open_mandates(policy, private_key("manager"), public_jwk("agent"))
        run.stolen = OpenMandateProofs(
            issued_at=datetime.now(HELSINKI),
            checkout_hash=checkout_hash(open_mandates.checkout),
            payment_hash=checkout_hash(open_mandates.payment),
        )
        tries = (
            (
                "above-cap",
                f"The agent signs {money(total)} itself, above its {money(cap)} cap",
                close_as_agent(open_mandates, agent, target.checkout_jwt),
            ),
            (
                "changed-quote",
                "The agent lowers a price in the quote and signs that",
                close_as_agent(open_mandates, agent, _with_a_lower_price(target.checkout_jwt)),
            ),
            (
                "mandate-for-another-quote",
                f"The agent reuses a mandate signed for another, smaller quote ({money(other.checkout.total_minor())})",
                close_as_agent(open_mandates, agent, other.checkout_jwt),
            ),
        )
        run.attacks = [self._send(target.checkout_id, key, title, mandates) for key, title, mandates in tries]

    def _send(self, checkout_id: str, key: str, title: str, authorization: Authorization) -> dict:
        """One bad mandate to POST /checkouts/{id}/complete, and what Valio said. `accepted` must never come back."""
        path = f"/checkouts/{checkout_id}/complete"
        try:
            response = self.gateway.post(path, json=authorization.model_dump(mode="json"))
        except httpx.HTTPError as e:
            raise DriverError(502, f"the gateway does not answer on {path}: {e}") from e
        if response.status_code == 403:
            problems = [str(problem) for problem in response.json().get("problems") or ["refused"]]
            return {"key": key, "title": title, "status": "refused", "problems": problems}
        if response.status_code == 200:
            return {"key": key, "title": title, "status": "accepted", "problems": []}
        raise DriverError(502, f"the gateway answered HTTP {response.status_code} on {path}: {_detail(response)}")

    def _quote(self, scenario: Scenario, needs: tuple[tuple[str, float, str], ...]) -> CheckoutResponse:
        """A signed quote from Valio for these needs: the first call of any agent."""
        body = {
            "customer": scenario.customer,
            "delivery_date": scenario.delivery_date,
            "needs": [{"product_id": product, "amount": amount, "unit": unit} for product, amount, unit in needs],
        }
        return CheckoutResponse.model_validate(self._post(self.gateway, "gateway", "/checkouts", body))

    # ---------- building the state ----------

    def _build(
        self, run: _Run | None, status: str, steps: list[dict], audit: dict | None = None, **pieces
    ) -> DemoState:
        scenario = run.scenario if run else None
        return DemoState.model_validate(
            {
                "scenarios": [{"id": s.id, "title": s.title, "hint": s.hint} for s in self.scenarios.values()],
                "scenario": {
                    "id": scenario.id if scenario else None,
                    "title": scenario.title if scenario else None,
                    "status": status,
                },
                "kitchen": KITCHEN,
                "request": request_of(scenario) if scenario else None,
                "steps": steps,
                "audit": audit or {"buyer": [], "merchant": []},
                **pieces,
            }
        )

    # ---------- talking to the two services ----------

    def _post(self, client: httpx.Client, service: str, path: str, body: dict) -> dict:
        try:
            response = client.post(path, json=body)
        except httpx.HTTPError as e:
            raise DriverError(502, f"the {service} does not answer on {path}: {e}") from e
        if response.status_code != 200:
            raise DriverError(502, f"the {service} answered HTTP {response.status_code} on {path}: {_detail(response)}")
        return response.json()

    def _get(self, client: httpx.Client, service: str, path: str, model: type[BaseModel]):
        """The object at `path`, or None when the service has none yet (HTTP 404)."""
        try:
            response = client.get(path)
        except httpx.HTTPError as e:
            raise DriverError(502, f"the {service} does not answer on {path}: {e}") from e
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise DriverError(502, f"the {service} answered HTTP {response.status_code} on {path}: {_detail(response)}")
        return model.model_validate(response.json())

    def _audit(self, client: httpx.Client, service: str, checkout_id: str) -> list[AuditEvent]:
        """The lines of one side's log that are about this quote."""
        try:
            response = client.get("/audit")
        except httpx.HTTPError as e:
            raise DriverError(502, f"the {service} does not answer on /audit: {e}") from e
        if response.status_code != 200:
            raise DriverError(502, f"the {service} answered HTTP {response.status_code} on /audit")
        events = [AuditEvent.model_validate(event) for event in response.json()]
        return [event for event in events if event.checkout_id == checkout_id]


def request_of(scenario: Scenario) -> dict:
    """What the agent was asked, with the kitchen's own name for each product and the dish it goes into."""
    return {
        "text": scenario.text,
        "delivery_date": scenario.delivery_date,
        "lines": [
            {
                "product_id": product_id,
                "name": INGREDIENTS.get(product_id, (product_id, "Shared"))[0],
                "amount": amount,
                "unit": unit,
                "dish": INGREDIENTS.get(product_id, (product_id, "Shared"))[1],
            }
            for product_id, amount, unit in scenario.needs
        ],
    }


# ---------- the seven steps ----------


def _step(key: str, status: str = "pending", detail: str | None = None, signer: str | None = None, **more) -> dict:
    title, usual_signer = next((title, who) for step, title, who in TRAIL if step == key)
    return {"key": key, "title": title, "signer": signer or usual_signer, "status": status, "detail": detail, **more}


def _steps(
    policy: BuyerPolicy | None,
    proofs: OpenMandateProofs | None,
    issued: CheckoutResponse,
    verdict: Verdict | None,
    authorization: AuthorizationStatus | None,
    approval: ApprovalRequest | None,
    order: Order | None,
    audit: dict[str, list[AuditEvent]],
) -> list[dict]:
    """The trail for one quote. Each sentence says what happened and who did it, from what the services answered."""
    total = money(issued.checkout.total_minor())
    steps = [_open_mandate_step(policy, proofs), _quote_step(issued)]
    if verdict is None or authorization is None:
        return steps + [_step(key) for key, _, _ in TRAIL[2:]]

    triggered = [rule.message for rule in verdict.rules if rule.outcome != "pass"]
    said = " ".join(triggered) if triggered else f"all {len(verdict.rules)} rules pass, the agent may sign."
    refused_by_harness = verdict.decision == "deny"
    steps.append(
        _step(
            "verdict", "refused" if refused_by_harness else "done", f"{verdict.decision}: {said}", at=verdict.decided_at
        )
    )
    nothing_after = [
        _step("merchant_verifies", "skipped", "Nothing was sent to Valio."),
        _step("sandbox_payment", "skipped", "Nothing is booked."),
        _step("signed_receipt", "skipped", "No order, no receipt."),
    ]

    if order:
        by_chef = order.signed_by == "human"
        signed = (
            f"Signed by the chef for this exact quote, {total}."
            if by_chef
            else f"Closed by the agent's key inside the chef's open mandate, for this exact quote, {total}."
        )
        verified = next((e for e in audit["merchant"] if e.action == "mandate_verified"), None)
        return steps + [
            _step(
                "closed_mandates",
                "done",
                signed,
                signer="manager" if by_chef else "agent",
                proof=order.mandate_reference,
                at=_event_time(audit["buyer"], "mandate_signed"),
            ),
            _step(
                "merchant_verifies",
                "done",
                (
                    f"{verified.what} {verified.why}"
                    if verified
                    else "Valio checked the mandates and accepted the order."
                )
                + _mandate_facts(order),
                at=verified.at if verified else order.accepted_at,
            ),
            _payment_step(order),
            _step(
                "signed_receipt",
                "done",
                f"Order {order.order_id} accepted. The receipt is signed by Valio and points at the mandate.",
                proof=checkout_hash(order.receipt_jwt) if order.receipt_jwt else None,
                at=order.accepted_at,
            ),
        ]

    if authorization.status == "pending_approval":
        deadline = f", before {_when(authorization.deadline)}" if authorization.deadline else ""
        waiting = _step(
            "closed_mandates", "waiting", f"Waiting for the chef to sign this exact quote{deadline}.", signer="manager"
        )
        return steps + [waiting] + [_step(key) for key, _, _ in TRAIL[4:]]

    if refused_by_harness:
        nobody = _step("closed_mandates", "skipped", "Nobody signs: the verdict is deny.")
        return steps + [nobody] + nothing_after
    if authorization.status == "rejected":
        who = f" ({approval.decided_by})" if approval and approval.decided_by else ""
        rejected = _step("closed_mandates", "refused", f"The chef{who} rejected this order.", signer="manager")
        return steps + [rejected] + nothing_after
    if authorization.status == "expired":
        late = _step(
            "closed_mandates", "refused", "Nobody signed before the cut-off: the approval expired.", signer="manager"
        )
        return steps + [late] + nothing_after

    # The agent signed inside its limits and Valio still said no: the reasons are Valio's own words.
    return steps + [
        _step(
            "closed_mandates",
            "done",
            f"Closed by the agent's key inside the chef's open mandate, for this exact quote, {total}.",
            signer="agent",
            at=_event_time(audit["buyer"], "mandate_signed"),
        ),
        _step("merchant_verifies", "refused", " ".join(authorization.reasons) or "Valio refused the order."),
        _step("sandbox_payment", "skipped", "Nothing is booked."),
        _step("signed_receipt", "skipped", "No order, no receipt."),
    ]


def _attack_steps(
    policy: BuyerPolicy | None,
    proofs: OpenMandateProofs | None,
    issued: CheckoutResponse,
    attacks: list[dict] | None,
    audit: dict[str, list[AuditEvent]],
) -> list[dict]:
    """The trail of the attack: the quote is real, the harness is skipped, and Valio refuses what the agent signed."""
    steps = [_open_mandate_step(policy, proofs), _quote_step(issued)]
    if attacks is None:  # the mandates are not sent yet
        return steps + [_step(key) for key, _, _ in TRAIL[2:]]
    refused = sum(attack["status"] == "refused" for attack in attacks)
    everything_refused = refused == len(attacks)
    answers = [event.at for event in audit["merchant"] if event.action in ("order_refused", "order_accepted")]
    return steps + [
        _step("verdict", "skipped", "The agent did not ask the harness: no verdict, so nobody was allowed to sign."),
        _step(
            "closed_mandates",
            "done",
            f"{len(attacks)} mandates built with the agent's key, outside the harness.",
            signer="agent",
        ),
        _step(
            "merchant_verifies",
            "refused" if everything_refused else "done",
            f"{refused} of {len(attacks)} refused by Valio. No valid signature, no order."
            if everything_refused
            else f"Only {refused} of {len(attacks)} refused by Valio: a bad mandate went through.",
            at=answers[-1] if answers else None,
        ),
        _step("sandbox_payment", "skipped", "Nothing is booked."),
        _step("signed_receipt", "skipped", "No order, no receipt."),
    ]


def _quote_step(issued: CheckoutResponse) -> dict:
    checkout = issued.checkout
    lines = len(checkout.line_items)
    return _step(
        "signed_quote",
        "done",
        f"{lines} line{'s' if lines != 1 else ''}, {money(checkout.total_minor())} before tax, "
        f"signed by {checkout.merchant.name}, valid until {_when(checkout.expires_at)}.",
        proof=checkout_hash(issued.checkout_jwt),
        at=checkout.aimo.issued_at,
    )


def _with_a_lower_price(checkout_jwt: str) -> str:
    """The same token with the first line at half its price and the signature left as it was: a quote changed after
    Valio signed it. Plain base64 and JSON, no key needed, which is the point."""
    header, body, signature = checkout_jwt.split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload["line_items"][0]["item"]["price"] //= 2
    changed = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"{header}.{changed}.{signature}"


def _mandate_facts(order: Order) -> str:
    """What the payment mandate allowed, as Valio read it: the amount, and the agent's cap when there is one."""
    facts = order.mandate
    if facts is None:
        return ""
    if facts.cap_minor is None:
        return f" Amount {money(facts.amount_minor)}, no cap: the chef signed this exact order."
    return f" Amount {money(facts.amount_minor)}, within the {money(facts.cap_minor)} cap of the open mandate."


def _payment_step(order: Order) -> dict:
    """The charge is a sandbox: the amount is booked on a simulated invoice account, and the sentence says so."""
    payment = order.payment
    if payment is None:  # an order taken before the gateway booked payments
        return _step("sandbox_payment", "skipped", "No payment was booked for this order.")
    return _step(
        "sandbox_payment",
        "done",
        f"Sandbox payment: {money(payment.amount_minor)} booked on {payment.instrument}. {payment.terms}. "
        "No real money moves.",
        proof=payment.payment_id,
        at=payment.captured_at,
    )


def _open_mandate_step(policy: BuyerPolicy | None, proofs: OpenMandateProofs | None) -> dict:
    """Step 1: what the chef signed in advance, with the fingerprint of the open payment mandate when it is known."""
    known = {"proof": proofs.payment_hash, "at": proofs.issued_at} if proofs else {}
    return _step("open_mandate", "done", _open_mandate(policy), **known)


def _open_mandate(policy: BuyerPolicy | None) -> str:
    if policy is None:
        return "Signed in advance by the chef: what the agent may order without asking."
    merchants = ", ".join(merchant.name or merchant.id for merchant in policy.allowed_merchants)
    return (
        f"Signed in advance by the chef: the agent may order from {merchants}, up to "
        f"{money(policy.autonomous_limit_minor)} an order, until {_when(policy.valid_until)}."
    )


def _event_time(events: list[AuditEvent], action: str) -> datetime | None:
    return next((event.at for event in events if event.action == action), None)


def _when(value: datetime | None) -> str:
    return f"{value.astimezone(HELSINKI):%a %d/%m %H:%M}" if value else "an unknown time"


def _detail(response: httpx.Response) -> str:
    """The readable reason a service gave, or the start of its answer."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    return str(body.get("detail", body))[:300] if isinstance(body, dict) else str(body)[:300]


# ---------- the service ----------


def create_app(driver: Driver | None = None) -> FastAPI:
    active = driver or Driver()
    api = FastAPI(title="Demo driver", version="0.1")
    api.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.exception_handler(DriverError)
    def explain(_request: Request, error: DriverError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})

    @api.get("/state")
    def state() -> DemoState:
        return active.state()

    @api.post("/scenarios/{scenario_id}/run")
    def run(scenario_id: str) -> DemoState:
        return active.run(scenario_id)

    @api.post("/reset")
    def reset() -> DemoState:
        return active.reset()

    return api


app = create_app()


def main(argv: list[str]) -> int:
    """Run one scenario from the terminal and print the trail. The gateway and the harness must be running."""
    if len(argv) != 1 or argv[0] not in {scenario.id for scenario in SCENARIOS}:
        print(f"usage: python scenarios/run.py <{' | '.join(scenario.id for scenario in SCENARIOS)}>")
        return 2
    try:
        state = Driver().run(argv[0])
    except DriverError as error:
        print(f"failed: {error.detail}")
        return 1
    print(f"{state.scenario.title}: {state.scenario.status}")
    for step in state.steps:
        proof = f"  [{step.proof}]" if step.proof else ""
        print(f"  {step.status:<8} {step.title:<16} {step.signer:<8} {step.detail or ''}{proof}")
    for attack in state.attacks:
        print(f"  {attack.status:<8} {attack.title}: {'; '.join(attack.problems)}")
    if state.approval and state.approval.status == "pending":
        print(f"the chef signs on the page, or: POST /approvals/{state.approval.approval_id}/decision on the harness")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
