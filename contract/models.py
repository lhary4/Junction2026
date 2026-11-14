"""The contract as Pydantic models. Everyone imports these; docs/contract.md explains every field.

Field names match contract/examples/ exactly, and tests/test_contract.py proves every example validates.
Our own models refuse unknown fields (extra="forbid"), so a typo fails loudly instead of being dropped.
Every field that can be null defaults to None, so a payload dumped with exclude_none=True validates again.
"""

from datetime import date
from typing import Any, Literal, get_args

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contract.ap2 import Checkout, Merchant


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- Shared vocabulary ----------

Certainty = Literal["measured", "declared", "estimated", "unknown"]
ClaimSource = Literal[
    "aimo_stock_count",
    "supplier_warehouse",
    "aimo_availability_api",
    "aimo_price_api",
    "gs1_synkka",
    "aimo_delivery_history",
    "product_group_average",
    "none",
]
BuyerUnit = Literal["L", "KG", "ST"]
Decision = Literal["auto", "human", "deny"]
Signer = Literal["agent", "human"]
RuleId = Literal[
    "quote-signature",
    "quote-not-expired",
    "merchant-allowed",
    "allergen-not-blocked",
    "allergen-data-known",
    "allergen-unchanged-on-substitution",
    "delivery-on-time",
    "spend-limit",
    "substitution-within-preferences",
]
Escalation = Literal["human", "deny"]


class Claim(ContractModel):
    """One fact Valio states, with where it comes from and how sure it is. `value` is null when unknown."""

    value: int | float | str | None = None
    unit: str
    source: ClaimSource
    as_of: AwareDatetime
    certainty: Certainty

    @model_validator(mode="after")
    def unknown_has_no_value(self):
        if (self.certainty == "unknown") != (self.value is None):
            raise ValueError("value must be null exactly when certainty is 'unknown'")
        return self


class AllergenInfo(ContractModel):
    """GS1 allergen codes. data='missing' never means 'free from'."""

    contains: list[str] = []
    free_from: list[str] = []
    data: Literal["complete", "missing"]


# ---------- Search: GET /products/search ----------


class SizePerSalesUnit(ContractModel):
    value: float | None = None
    unit: str | None = None
    how: str


class PackSize(ContractModel):
    unit_id: str
    size_in_base_units: int


class ProductCard(ContractModel):
    id: str
    name: str
    category: str
    vendor: str | None = None
    brand: str | None = None
    sales_unit: str
    base_unit: str
    size_per_sales_unit: SizePerSalesUnit
    pack_sizes: list[PackSize] = []
    temperature_condition: int | None = None
    allergens: AllergenInfo
    nutritional_claims: list[str] = []
    labels: list[str] = []
    origin: Claim
    delivery_reliability: Claim
    carbon_footprint: Claim
    catalog_substitutes: list[str] = []


class SearchResponse(ContractModel):
    query: str
    count: int
    products: list[ProductCard]


# ---------- Lookup: GET /offers ----------

OfferProblem = Literal["late_delivery", "out_of_stock", "not_found", "unit_mismatch"]


class OffersRequest(ContractModel):
    """The query parameters of GET /offers. `amount` and `unit` go together: what the buyer needs, in their unit."""

    q: str = Field(min_length=2)
    delivery_date: date
    amount: float | None = Field(None, gt=0)
    unit: BuyerUnit | None = None
    limit: int = Field(10, ge=1, le=50)

    @model_validator(mode="after")
    def amount_comes_with_its_unit(self):
        if (self.amount is None) != (self.unit is None):
            raise ValueError("amount and unit go together: give both, or neither")
        return self


class OfferQuantity(ContractModel):
    """The amount the buyer asked for, as whole sales units of one product (rounded up), and what they cost."""

    quantity: int = Field(gt=0)
    base_quantity: float
    base_unit: BuyerUnit
    total_minor: int
    how: str
    # False: Valio counted fewer units than `quantity`, a quote would split the need. None: no count to compare with.
    stock_covers: bool | None = None


class Offer(ContractModel):
    """One product that matches a lookup, with its price and whether it can be ordered for the date asked.

    Informative: nothing here commits Valio or the buyer. Only a signed quote (POST /checkouts) does.
    """

    product: ProductCard
    orderable: bool
    reason: OfferProblem | None = None
    logistic_model: Literal["Stock", "Terminal"] | None = None
    price: Claim
    comparison_price: Claim
    comparison_unit: str | None = None
    stock: Claim
    available_date: Claim
    closing_time: Claim
    to_order: OfferQuantity | None = None

    @model_validator(mode="after")
    def reason_says_why_not(self):
        if self.orderable != (self.reason is None):
            raise ValueError("reason must be null exactly when orderable is true")
        return self


class OffersResponse(ContractModel):
    query: str
    delivery_date: date
    amount: float | None = None
    unit: BuyerUnit | None = None
    as_of: AwareDatetime
    binding: Literal[False] = False
    matched: int
    priced: int
    count: int
    offers: list[Offer]


# ---------- Quote request: POST /checkouts ----------


class Need(ContractModel):
    """What the buyer asked for, in their own unit (litres, kilos or sales units)."""

    product_id: str
    amount: float = Field(gt=0)
    unit: BuyerUnit
    # To cover a shortfall with one of the alternatives the gateway offered in an earlier quote, instead of its own pick.
    substitute_with: str | None = None


class QuoteRequest(ContractModel):
    customer: str
    delivery_date: date
    needs: list[Need] = Field(min_length=1)
    allow_alternatives: bool = True


# ---------- The signed quote: AimoCheckout ----------


class SubstituteFor(ContractModel):
    """The product a substitute line replaces, signed with the quote so the harness can compare."""

    product_id: str
    name: str
    category: str
    allergens: AllergenInfo
    brand: str | None = None
    sales_unit: str | None = None
    base_unit: str | None = None
    size_per_sales_unit: SizePerSalesUnit | None = None
    temperature_condition: int | None = None
    nutritional_claims: list[str] = []
    labels: list[str] = []
    origin: Claim | None = None


class LineClaims(ContractModel):
    """Our facts for one line item, under aimo.lines[<line item id>]."""

    product_id: str
    category: str
    brand: str | None = None
    sales_unit: str
    base_quantity: float
    base_unit: BuyerUnit
    size_per_sales_unit: SizePerSalesUnit | None = None
    temperature_condition: int | None = None
    comparison_price_minor: int
    comparison_unit: str
    substitute_for: SubstituteFor | None = None
    logistic_model: Literal["Stock", "Terminal"]
    available_date: date | None = None
    closing_time: AwareDatetime | None = None
    stock: Claim
    price: Claim
    origin: Claim
    allergens: AllergenInfo
    delivery_reliability: Claim
    carbon_footprint: Claim
    nutritional_claims: list[str] = []
    labels: list[str] = []


class Shortfall(ContractModel):
    product_id: str
    requested_base_quantity: float
    available_base_quantity: float
    missing_base_quantity: float
    base_unit: BuyerUnit
    reason: Literal["partial_stock", "out_of_stock", "late_delivery", "not_found"]


class Alternative(ContractModel):
    for_product_id: str
    product_id: str
    tier: Literal["best", "better", "good"]
    comparison_price_minor: int
    comparison_unit: str
    why: str
    chosen: bool
    catalog_listed: bool = False


class AimoExtension(ContractModel):
    """Everything of ours, under the one extra top-level key `aimo` that UCP's Checkout allows."""

    customer: str
    issued_at: AwareDatetime
    totals_exclude_tax: bool = True
    requested: list[Need]
    requested_delivery_date: date
    delivery_date: date
    closing_time: AwareDatetime | None = None
    lines: dict[str, LineClaims]
    shortfalls: list[Shortfall] = []
    alternatives: list[Alternative] = []


class AimoCheckout(Checkout):
    """UCP's Checkout as typed by the AP2 SDK, plus our `aimo` key. No SDK field is renamed or removed."""

    model_config = ConfigDict(extra="forbid")

    aimo: AimoExtension

    @model_validator(mode="after")
    def lines_match_line_items(self):
        item_ids = [line.id for line in self.line_items]
        if sorted(item_ids) != sorted(self.aimo.lines):
            raise ValueError(f"aimo.lines keys {sorted(self.aimo.lines)} must match line item ids {sorted(item_ids)}")
        for line in self.line_items:
            if self.aimo.lines[line.id].product_id != line.item.id:
                raise ValueError(f"aimo.lines[{line.id}].product_id does not match line item {line.id}")
        return self

    def total_minor(self) -> int:
        total = next((t.amount for t in self.totals if t.type == "total"), None)
        if total is None:
            raise ValueError("checkout totals missing 'total' entry")
        return total


class CheckoutResponse(ContractModel):
    """What POST /checkouts and GET /checkouts/{id} return."""

    checkout_id: str
    checkout_jwt: str
    checkout: AimoCheckout


# ---------- Buyer policy ----------


class SubstitutionPolicy(ContractModel):
    allowed: bool
    pre_accepted: Literal["same_category_and_same_allergens", "none"]
    preferences_text: str
    judge_auto_threshold: float = Field(ge=0, le=1)
    judge_floor: float = Field(ge=0, le=1)


class BuyerPolicy(ContractModel):
    policy_id: str
    customer: str
    agent_id: str
    approver: str
    allowed_merchants: list[Merchant]
    currency: str
    autonomous_limit_minor: int = Field(ge=0)
    blocked_allergens: list[str] = []
    unknown_allergen_data: Escalation
    allergen_change_on_substitution: Escalation
    late_delivery: Escalation
    substitution: SubstitutionPolicy
    valid_until: AwareDatetime


# ---------- Verdict ----------


class RuleResult(ContractModel):
    rule_id: RuleId
    outcome: Literal["pass", "human", "deny"]
    message: str
    evidence: dict[str, Any] = {}


class JudgeSubject(ContractModel):
    original: str
    candidate: str


class JudgeAnswer(ContractModel):
    """What we asked the judge and what came back. The model gives no explanation, so we keep the question."""

    question_key: str
    type: str
    instructions: str
    subject: JudgeSubject
    probability: float | None = None
    confidence: float | None = None
    auto_threshold: float
    floor: float
    routed: Literal["auto", "human"]
    model: str


class Verdict(ContractModel):
    decision: Decision
    checkout_id: str
    checkout_hash: str
    total_minor: int
    currency: str
    signer: Signer | None = None
    deadline: AwareDatetime | None = None
    decided_at: AwareDatetime
    rules: list[RuleResult]
    judge: list[JudgeAnswer] = []


# ---------- Approval and authorization (harness) ----------


class AuthorizeRequest(ContractModel):
    """Body of POST /authorize on the harness."""

    checkout_id: str
    request_text: str


class ApprovalDecision(ContractModel):
    """Body of POST /approvals/{id}/decision on the harness."""

    decision: Literal["approve", "reject"]
    decided_by: str


class ApprovalRequest(ContractModel):
    approval_id: str
    checkout_id: str
    checkout_hash: str
    status: Literal["pending", "approved", "rejected", "expired"]
    total_minor: int
    currency: str
    reasons: list[RuleResult]
    judge: list[JudgeAnswer] = []
    request_text: str
    requested_at: AwareDatetime
    deadline: AwareDatetime | None = None
    decided_by: str | None = None
    decided_at: AwareDatetime | None = None
    order_id: str | None = None


class AuthorizationStatus(ContractModel):
    status: Literal["ordered", "pending_approval", "denied", "rejected", "expired"]
    checkout_id: str
    decision: Decision
    signed_by: Signer | None = None
    order_id: str | None = None
    reasons: list[str] = []
    approval_id: str | None = None
    approval_url: str | None = None
    deadline: AwareDatetime | None = None


class Authorization(ContractModel):
    """The two AP2 mandate chains the harness sends to the gateway. Never shown to the agent."""

    signed_by: Signer
    checkout_mandate: str
    payment_mandate: str


# ---------- Order (gateway) ----------


class Receipt(ContractModel):
    """Decoded payload of the receipt JWT the gateway signs."""

    status: Literal["Success", "Error"]
    iss: str
    iat: int
    reference: str
    order_id: str | None = None
    error: str | None = None
    error_description: str | None = None

    @model_validator(mode="after")
    def status_fields_present(self):
        if self.status == "Success" and not self.order_id:
            raise ValueError("Success receipt requires order_id")
        if self.status == "Error" and (not self.error or not self.error_description):
            raise ValueError("Error receipt requires error and error_description")
        return self

    def model_dump(self, **kwargs):
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


class MandateFacts(ContractModel):
    """What the payment mandate allows, as Valio read it once the signatures verified."""

    # The agent's spend cap, from the open mandate the manager signed. Null when the manager signed this exact order.
    cap_minor: int | None = None
    amount_minor: int
    currency: str
    instrument: str


class Payment(ContractModel):
    """The sandbox charge: the order's amount booked on a simulated invoice account. No real money moves."""

    payment_id: str
    status: Literal["captured"]
    amount_minor: int
    currency: str
    instrument: str
    terms: str
    sandbox: Literal[True] = True
    captured_at: AwareDatetime


class Order(ContractModel):
    order_id: str
    status: Literal["accepted"]  # a refused order is HTTP 403 with {"problems": [...]}, never an Order
    checkout_id: str
    checkout_hash: str
    mandate_reference: str
    signed_by: Signer
    total_minor: int
    currency: str
    delivery_date: date
    created_at: AwareDatetime
    accepted_at: AwareDatetime | None = None
    receipt_jwt: str | None = None
    receipt: Receipt | None = None
    mandate: MandateFacts | None = None
    payment: Payment | None = None


# ---------- Audit ----------


class AuditEvent(ContractModel):
    """One line of a hash-chained audit log. Each side keeps its own chain."""

    seq: int = Field(ge=1)
    at: AwareDatetime
    side: Literal["buyer", "merchant"]
    actor: Literal["agent", "harness", "human", "merchant"]
    action: str
    checkout_id: str | None = None
    checkout_hash: str | None = None
    what: str
    why: str
    rule: str | None = None
    prev_hash: str | None = None
    hash: str


# ---------- Demo state: GET /state on the demo driver (scenarios/run.py, port 8003) ----------

ScenarioStatus = Literal["idle", "running", "waiting_for_human", "done", "refused"]
StepKey = Literal[
    "open_mandate",
    "signed_quote",
    "verdict",
    "closed_mandates",
    "merchant_verifies",
    "sandbox_payment",
    "signed_receipt",
]
StepSigner = Literal["manager", "agent", "merchant", "none"]
StepStatus = Literal["pending", "done", "waiting", "refused", "skipped"]
AttackStatus = Literal["pending", "refused", "accepted"]


class DemoScenario(ContractModel):
    """One button of the page."""

    id: str
    title: str
    hint: str


class DemoScenarioRun(ContractModel):
    """The scenario on screen. After a reset nothing has run: `id` and `title` are null and `status` is idle."""

    id: str | None = None
    title: str | None = None
    status: ScenarioStatus

    @model_validator(mode="after")
    def idle_means_no_scenario(self):
        if (self.status == "idle") != (self.id is None):
            raise ValueError("id must be null exactly when status is 'idle'")
        return self


class MenuCourse(ContractModel):
    course: str
    dish: str


class DemoKitchen(ContractModel):
    """The restaurant whose portal the page shows."""

    customer: str
    name: str
    covers_per_service: int = Field(gt=0)
    services: list[str]
    menu: list[MenuCourse]


class DemoRequestLine(ContractModel):
    """One ingredient the kitchen needs, in the kitchen's unit. The quote says how many sales units that makes."""

    product_id: str
    name: str
    amount: float = Field(gt=0)
    unit: BuyerUnit
    dish: str


class DemoRequest(ContractModel):
    """What the buying agent was asked: the sentence the harness receives, and the needs sent to the gateway."""

    text: str
    delivery_date: date
    lines: list[DemoRequestLine] = Field(min_length=1)


class DemoAttack(ContractModel):
    """One bad mandate sent straight to the gateway. `accepted` must never happen: it would mean Valio let it through."""

    key: str
    title: str
    status: AttackStatus
    problems: list[str] = []


class DemoStep(ContractModel):
    """One step of the AP2 trail: who signed it, and a hash or an identifier that proves it."""

    key: StepKey
    title: str
    signer: StepSigner
    status: StepStatus
    detail: str | None = None
    proof: str | None = None
    at: AwareDatetime | None = None


class DemoAudit(ContractModel):
    """The lines both sides wrote about the quote on screen: the harness's log and the gateway's log."""

    buyer: list[AuditEvent] = []
    merchant: list[AuditEvent] = []


class DemoState(ContractModel):
    """Everything the page shows, in one object. The page never rebuilds a fact: it renders what is here."""

    scenarios: list[DemoScenario]
    scenario: DemoScenarioRun
    kitchen: DemoKitchen
    request: DemoRequest | None = None
    quote: AimoCheckout | None = None
    verdict: Verdict | None = None
    authorization: AuthorizationStatus | None = None
    approval: ApprovalRequest | None = None
    order: Order | None = None
    attacks: list[DemoAttack] = []
    steps: list[DemoStep]
    audit: DemoAudit

    @model_validator(mode="after")
    def trail_has_its_seven_steps(self):
        expected = list(get_args(StepKey))
        if [step.key for step in self.steps] != expected:
            raise ValueError(f"steps must be the seven steps of the AP2 trail, in this order: {', '.join(expected)}")
        return self

    @model_validator(mode="after")
    def scenario_is_one_of_the_buttons(self):
        if self.scenario.id is not None and self.scenario.id not in [s.id for s in self.scenarios]:
            raise ValueError(f"scenario {self.scenario.id!r} is not in scenarios")
        return self
