# Requirements Document

## Introduction

This document specifies the requirements for **Trusted Trade Agents**, the interface and operating model through which an external, autonomous AI purchasing agent interacts with Valio Aimo's (mocked) systems. These requirements are derived from the approved design document (`design.md`) in a design-first workflow, so they describe the behavior the design already commits to and must stay consistent with it.

The system lets an external agent discover products, retrieve authoritative price and availability, rank offers transparently, obtain human approval when required, place orders at fixed prices, and leave an auditable trail. Valio Aimo keeps control of permissions, pricing, order acceptance, and the audit log at all times. The governing principle is a hard split between **LLM reasoning** (the agent decides *what* to ask for and explains *why*) and **deterministic business validation** (the backend decides what is *true* and what is *allowed*).

Scope is the hackathon MVP built around the central demo scenario — *"I need 1,000 litres of lactose-free milk by Monday"* — running end to end, plus the budget-exceeded exception path (with partial availability as a stretch). The build is split into three parallel streams (Backend/policy, AI Agent, Dashboards) coding against one shared contract. The team is three non-expert developers, so the solution favors boring, well-documented tooling, and all repository content is in English. All data is synthetic; no real or confidential Valio Aimo systems are touched.

Requirements are grouped by stream and cross-cutting concern:
- Requirements 1–2: cross-cutting — authentication/authorization and the trust boundary.
- Requirements 3–9: Stream 1 — backend (discovery, pricing, policy engine, order lifecycle, audit).
- Requirements 10–12: Stream 2 — AI purchasing agent (ranking/explanation, safety invariants, control loop).
- Requirements 13–14: Stream 3 — dashboards (customer approval, Aimo control/audit).
- Requirement 15: exception handling subset.
- Requirement 16: delivery constraints and team/openness constraints.

## Glossary

- **System**: The complete Trusted Trade Agents solution (backend, agent, dashboards) acting together, used when a requirement is not specific to one component.
- **Aimo_API**: The mock Valio Aimo REST backend exposing the OpenAPI contract. The trust boundary of the system; the only way the agent can act.
- **Policy_Engine**: The deterministic authorization component inside the backend that decides AUTONOMOUS, REQUIRES_APPROVAL, or DENIED. It runs only in the trusted backend, never in the LLM.
- **Order_Manager**: The backend component responsible for order submission, acceptance, idempotency, and duplicate prevention.
- **Audit_Log**: The append-only, hash-chained record of every decision and action in the system.
- **Purchasing_Agent**: The external, autonomous AI agent (Stream 2) that extracts intent, calls backend tools, ranks offers, and reports outcomes. Treated as untrusted.
- **LLM**: The large-language-model provider used by the Purchasing_Agent for intent extraction, ranking rationale, and prose reports. Treated as untrusted.
- **Approval_Dashboard**: The buyer-facing Customer Approval Dashboard (Stream 3) where a human approves or rejects pending requests.
- **Control_Dashboard**: The Aimo-facing Control/Audit Dashboard (Stream 3) for monitoring registered agents and viewing the audit log.
- **Customer**: A Valio Aimo professional customer (e.g. a hotel chain) on whose behalf an agent acts.
- **Purchasing_Policy**: The customer-owned, backend-enforced ruleset defining autonomous spend limit, allowed categories, blocked allergens, and substitution preferences.
- **Quote**: An authoritative price-and-availability response (`quote_id`, `valid_until`) produced by the backend; the only source of prices, stock, and delivery the agent may report.
- **Fixed_Price**: A price taken directly from an Aimo-issued Quote, not a negotiated offer.
- **Decision**: One of AUTONOMOUS, REQUIRES_APPROVAL, or DENIED returned by the Policy_Engine.
- **Approval_Request**: A pending request for human sign-off created when a Decision is REQUIRES_APPROVAL.
- **Idempotency_Key**: A client-supplied key on order submission ensuring at most one order is created for repeated submissions.
- **Bearer_Token**: An opaque authentication token issued to a registered agent, scoped to one customer.

## Requirements

### Requirement 1: Agent Authentication and Delegated Authorization

**User Story:** As Valio Aimo, I want external agents to authenticate with a customer-scoped token, so that every agent action is tied to an authorized customer and can be trusted and traced.

#### Acceptance Criteria

1. WHEN a registered agent submits a valid agent identifier and API key, THE Aimo_API SHALL issue a Bearer_Token associated with that agent's Customer within 2 seconds, where the Bearer_Token remains valid for a configured lifetime of 3600 seconds.
2. IF an agent submits an unknown or revoked API key, THEN THE Aimo_API SHALL reject the request with an UNAUTHENTICATED error, SHALL NOT issue a Bearer_Token, and SHALL return an error indication that does not disclose whether the agent identifier exists.
3. IF an agent submits a token issuance request missing the agent identifier or the API key, THEN THE Aimo_API SHALL reject the request with an UNAUTHENTICATED error and SHALL NOT issue a Bearer_Token.
4. WHEN an agent calls any endpoint other than token issuance without a Bearer_Token, with a malformed Bearer_Token, or with an expired Bearer_Token, THE Aimo_API SHALL reject the request with an UNAUTHENTICATED error and SHALL NOT perform the requested action.
5. WHEN an authenticated agent requests its account information, THE Aimo_API SHALL return the Customer identity and the Purchasing_Policy under which the agent operates.
6. WHERE an agent is linked to a given Customer, IF the agent requests data or actions scoped to a different Customer, THEN THE Aimo_API SHALL reject the request with an authorization error and SHALL NOT return data or perform actions outside that agent's Customer.

### Requirement 2: Trust Boundary and Server-Side Enforcement

**User Story:** As Valio Aimo, I want the API to be the single trust boundary, so that an untrusted external agent can never produce authoritative facts or bypass controls.

#### Acceptance Criteria

1. WHEN THE Aimo_API receives a request, THE Aimo_API SHALL validate the request body against the published JSON Schema before performing any processing or state change.
2. IF a request body fails schema validation, THEN THE Aimo_API SHALL reject the request with a VALIDATION_ERROR response indicating which field(s) failed and SHALL NOT change any stored state.
3. THE Aimo_API SHALL compute prices, stock levels, and order acceptance status exclusively within the trusted backend, and SHALL ignore any such values supplied in an incoming request body.
4. THE System SHALL exclude secrets, Bearer_Tokens, and API keys from all content sent to the LLM.
5. WHEN an authorization decision is required, THE Policy_Engine SHALL make that decision in the deterministic backend rather than in the LLM.
6. IF a request body contains fields representing prices, stock levels, or order acceptance status, THEN THE Aimo_API SHALL disregard those fields and SHALL use only backend-computed values.

### Requirement 3: Product Discovery and Catalog Search

**User Story:** As a purchasing agent, I want a structured way to search the catalog, so that I can find products that match the buyer's stated need.

#### Acceptance Criteria

1. WHEN an authenticated agent submits a product search with a non-empty query string of 1 to 200 characters and optional filters, THE Aimo_API SHALL return a structured list of matching products, where each result includes a product identifier, name, category, unit, allergens, and certifications.
2. WHEN a product search returns more than 50 matching products, THE Aimo_API SHALL return at most 50 results per response and SHALL include a pagination indicator for retrieving subsequent results.
3. THE Aimo_API SHALL exclude customer-specific prices from all product search results and product detail responses.
4. IF an authenticated agent submits a product search with an empty query string or a query string exceeding 200 characters, THEN THE Aimo_API SHALL respond with a VALIDATION error indicating the query length is invalid and SHALL NOT return a product list.
5. WHEN an authenticated agent requests the details of a product by its identifier, THE Aimo_API SHALL return that product's full attributes, including product identifier, name, category, unit, allergens, and certifications.
6. IF an agent requests a product identifier that does not exist, THEN THE Aimo_API SHALL respond with a NOT_FOUND error indicating the product identifier was not found.
7. WHEN a product search matches no products, THE Aimo_API SHALL return an empty result list with no error.

### Requirement 4: Price and Availability Inquiry at Fixed Prices

**User Story:** As a purchasing agent, I want authoritative price and availability for specific items on a requested delivery date, so that I can compare offers and order at fixed prices.

#### Acceptance Criteria

1. WHEN an authenticated agent submits between 1 and 100 items, each with a quantity between 1 and 999,999 and a requested delivery date on or after the current date, THE Aimo_API SHALL return a Quote containing, for each item, the Fixed_Price as a non-negative decimal, an ISO 4217 currency code, the available quantity, the requested quantity, an availability status of one of fully_available, partially_available, or unavailable, and the delivery details for the requested delivery date.
2. THE Aimo_API SHALL include in every Quote a unique quote identifier and an expiry timestamp that is later than the Quote creation timestamp.
3. WHERE the available quantity of an item is less than the requested quantity and greater than zero, THE Aimo_API SHALL set that item's availability status to partially_available and SHALL report the available quantity.
4. WHERE the available quantity of an item is zero, THE Aimo_API SHALL set that item's availability status to unavailable and SHALL report an available quantity of zero.
5. THE Aimo_API SHALL base each returned Fixed_Price on fixed customer-specific pricing rather than a negotiated quote.
6. IF a submitted item identifier is unknown, the requested quantity is outside the range of 1 to 999,999, or the requested delivery date is before the current date, THEN THE Aimo_API SHALL reject the inquiry with an error response indicating the specific invalid input and SHALL NOT return a Quote.
7. WHEN the Aimo_API returns a Quote, THE Aimo_API SHALL record one price-inquiry AuditEvent; IF the inquiry is rejected for invalid input, THEN THE Aimo_API SHALL record one price-inquiry AuditEvent indicating the rejection.

### Requirement 5: Deterministic Policy Evaluation

**User Story:** As a customer, I want the backend to decide deterministically what an agent may do autonomously versus what needs my sign-off, so that control stays with me and Valio Aimo and not with the LLM.

#### Acceptance Criteria

1. WHEN an agent submits a cart for order validation, THE Policy_Engine SHALL return exactly one Decision with a value of AUTONOMOUS, REQUIRES_APPROVAL, or DENIED.
2. WHEN multiple rules are triggered for a single cart, THE Policy_Engine SHALL apply precedence in the order DENIED over REQUIRES_APPROVAL over AUTONOMOUS and SHALL return the highest-precedence Decision.
3. IF any item in the cart belongs to a category outside the customer's allowed categories, THEN THE Policy_Engine SHALL return DENIED.
4. IF any item in the cart contains an allergen listed in the customer's blocked allergens, THEN THE Policy_Engine SHALL return DENIED.
5. IF the cart total is strictly greater than the customer's autonomous spend limit AND no rule that yields DENIED is triggered, THEN THE Policy_Engine SHALL return REQUIRES_APPROVAL.
6. IF the cart contains a substitution outside the customer's substitution preferences AND no rule that yields DENIED is triggered, THEN THE Policy_Engine SHALL return REQUIRES_APPROVAL.
7. WHEN the Policy_Engine returns REQUIRES_APPROVAL or DENIED, THE Policy_Engine SHALL include at least one reason that identifies each triggering rule.
8. WHEN no rule is triggered for a cart, THE Policy_Engine SHALL return AUTONOMOUS.
9. WHILE evaluating a policy, THE Policy_Engine SHALL produce no side effects and SHALL NOT create or modify any order.
10. WHEN the Policy_Engine is called two or more times with identical Purchasing_Policy, cart, and context, THE Policy_Engine SHALL return an identical Decision and identical reasons on every call.
11. IF the Purchasing_Policy or product metadata required to evaluate a cart cannot be loaded from the backend, THEN THE Policy_Engine SHALL return DENIED and SHALL include a reason indicating that policy or product metadata was unavailable.
12. THE Policy_Engine SHALL load the Purchasing_Policy and product metadata from the backend rather than from agent-supplied input.

### Requirement 6: Order Submission and Acceptance Lifecycle

**User Story:** As Valio Aimo, I want order submission to be separate from acceptance, so that acceptance remains Valio Aimo's decision and no agent can declare an order accepted.

#### Acceptance Criteria

1. WHEN an agent submits an order that passes all validation checks, THE Order_Manager SHALL create the order with status submitted and SHALL NOT set the status to accepted within the same submission call.
2. THE Order_Manager SHALL permit a transition to status accepted only for transitions initiated within the trusted backend, and IF a transition to accepted is requested from any agent-supplied input, THEN THE Order_Manager SHALL reject the transition with a FORBIDDEN error and SHALL retain the order's current status.
3. WHEN an order transitions to status accepted, THE Order_Manager SHALL return an order identifier, an order total as a monetary amount in the range 0.01 to 999,999,999.99, and a transaction containing a confirmation code with a length between 1 and 64 characters.
4. WHEN an agent submits an order whose Policy_Engine validation result is REQUIRES_APPROVAL, THE Order_Manager SHALL transition the order to status accepted only if a matching Approval_Request has status approved.
5. IF an agent submits an order whose validation result is REQUIRES_APPROVAL and no matching Approval_Request with status approved exists, THEN THE Order_Manager SHALL reject the submission with a FORBIDDEN error, SHALL NOT create an order, and SHALL return an error indication identifying that an approved Approval_Request is required.
6. WHEN an order is submitted, THE Order_Manager SHALL re-run the Policy_Engine server-side and SHALL complete the transition to status accepted only after the server-side Policy_Engine result is a passing validation.
7. WHEN an agent requests an order by its identifier, THE Aimo_API SHALL return the order's current status and transaction.
8. IF an agent requests an order by an identifier that does not correspond to an existing order, THEN THE Aimo_API SHALL reject the request with a NOT_FOUND error and SHALL NOT return order status or transaction data.

### Requirement 7: Idempotency and Duplicate Prevention

**User Story:** As a purchasing agent, I want order submission to be idempotent, so that a retried request never creates a duplicate order.

#### Acceptance Criteria

1. WHEN two or more order submissions carry the same Idempotency_Key, THE Order_Manager SHALL create exactly one order and SHALL persist that order with the Idempotency_Key associated to it.
2. WHEN a submission carries an Idempotency_Key that matches a previously persisted order AND the request payload is identical to the original, THE Order_Manager SHALL return the original order unchanged and SHALL NOT create a new order.
3. IF a submission carries an Idempotency_Key that matches a previously persisted order AND the request payload differs from the original, THEN THE Order_Manager SHALL reject the submission, SHALL return an error indicating an idempotency key conflict, and SHALL leave the original order unchanged.
4. WHERE an order submission fails with a transient network error, THE Purchasing_Agent SHALL retry the submission a maximum of 3 times, reusing the same Idempotency_Key on each retry.
5. IF an order submission fails with a non-transient error, THEN THE Purchasing_Agent SHALL NOT retry the submission.
6. THE Order_Manager SHALL treat each Idempotency_Key as valid for duplicate detection for a minimum of 24 hours after the original order is persisted.

### Requirement 8: Price Freshness at Commit

**User Story:** As Valio Aimo, I want prices re-checked when an order is committed, so that no order is placed on a stale or changed price.

#### Acceptance Criteria

1. WHEN an agent submits an order referencing a Quote, THE Order_Manager SHALL re-validate the referenced Quote at submission time by confirming the Quote exists, has not expired, and belongs to the submitting customer, within 2 seconds of receiving the submission.
2. IF the referenced Quote has expired at submission time, THEN THE Order_Manager SHALL reject the submission with a PRICE_CHANGED error indicating the price is no longer valid AND SHALL NOT create an order.
3. IF the price in the submitted order differs from the price recorded in the referenced Quote, THEN THE Order_Manager SHALL reject the submission with a PRICE_CHANGED error indicating the price has changed AND SHALL NOT create an order.
4. IF the referenced Quote does not exist or belongs to a customer other than the submitting customer, THEN THE Order_Manager SHALL reject the submission with an error indicating the Quote is invalid AND SHALL NOT create an order.
5. WHEN an order is rejected for a price change, THE Order_Manager SHALL record an order-rejected AuditEvent with the reason PRICE_CHANGED within 2 seconds of the rejection.

### Requirement 9: Append-Only Audit Trail

**User Story:** As a customer and as Valio Aimo, I want a human-readable, tamper-evident record of what the agent did and why, so that every purchasing decision is traceable and explainable.

#### Acceptance Criteria

1. WHEN a price inquiry, approval request, approval decision, order submission, order acceptance, or order rejection occurs, THE Audit_Log SHALL append exactly one AuditEvent for that occurrence.
2. THE Audit_Log SHALL record each AuditEvent with a timestamp in ISO 8601 UTC format, an actor identifier, an action type drawn from the set {price inquiry, approval request, approval decision, order submission, order acceptance, order rejection}, a subject identifier, and a human-readable details field of 1 to 2000 characters.
3. IF any required field of an AuditEvent (timestamp, actor, action, subject identifier, or details) is absent or empty, THEN THE Audit_Log SHALL reject the append operation and SHALL leave the existing audit trail unchanged.
4. THE Audit_Log SHALL compute each AuditEvent's hash from the event's own fields combined with the previous AuditEvent's hash, such that each event is linked to its predecessor in a hash chain.
5. WHEN the Audit_Log is verified, IF any AuditEvent's stored hash does not match the hash recomputed from its fields and its predecessor's hash, THEN THE Audit_Log SHALL report the verification as failed and SHALL identify the first AuditEvent at which the mismatch occurs.
6. THE Audit_Log SHALL reject any operation that modifies or deletes an existing AuditEvent and SHALL preserve the existing audit trail unchanged.
7. WHEN a buyer-scoped token requests audit events, THE Aimo_API SHALL return only AuditEvents belonging to that token's Customer and SHALL exclude AuditEvents belonging to any other Customer.
8. WHERE an Aimo-admin token requests audit events, THE Aimo_API SHALL return AuditEvents across all customers.

### Requirement 10: Transparent Good-Better-Best Ranking and Explanation

**User Story:** As a buyer, I want the agent to rank options transparently and explain its choice, so that I understand the trade-offs behind a recommendation.

#### Acceptance Criteria

1. WHEN the Purchasing_Agent receives a Quote containing two or more candidate offers, THE Purchasing_Agent SHALL assign each offer exactly one of the tiers "good", "better", or "best" using only field values present in the Quote.
2. IF two or more offers have identical values across all ranking fields present in the Quote, THEN THE Purchasing_Agent SHALL assign them the same tier and SHALL state in the explanation that the offers are tied.
3. IF the Quote contains exactly one candidate offer, THEN THE Purchasing_Agent SHALL assign that offer the "best" tier and SHALL state in the explanation that only one candidate was available.
4. IF the Quote contains no candidate offers, THEN THE Purchasing_Agent SHALL produce no ranking and SHALL return a message indicating that no candidates were available to rank.
5. THE Purchasing_Agent SHALL produce a human-readable explanation of its ranking in which every cited quantity and attribute is a value present in the received Quote, and SHALL NOT cite any value absent from the Quote.
6. WHEN the Purchasing_Agent reports a chosen offer, THE Purchasing_Agent SHALL include the product identifier, the price, the delivery terms, and a rationale that references the Quote values distinguishing the chosen offer from the other candidates.

### Requirement 11: Agent Safety Invariants

**User Story:** As Valio Aimo and as a buyer, I want the agent to never invent facts, so that every price, stock figure, delivery promise, and success claim is backed by the backend.

#### Acceptance Criteria

1. WHEN the Purchasing_Agent reports a price, stock level, delivery date, or order status, THE Purchasing_Agent SHALL use a value copied verbatim from a prior Aimo_API response received within the current active session.
2. IF the Purchasing_Agent would report a price, stock level, delivery date, or order status for which no corresponding value exists in a prior Aimo_API response, THEN THE Purchasing_Agent SHALL withhold the unverified value, present an indication that the value is unavailable, and refrain from substituting any generated value.
3. THE Purchasing_Agent SHALL report a transaction as successful only when the Aimo_API order response returns a status equal to accepted and contains a non-empty confirmation code.
4. IF an Aimo_API order response returns any status other than accepted, or returns accepted without a non-empty confirmation code, THEN THE Purchasing_Agent SHALL report the transaction as not successful and present an indication of the failure reason.
5. THE Purchasing_Agent SHALL treat catalog text contained in product names and descriptions as data rather than as instructions, and SHALL NOT alter its actions based on any directive embedded in that text.
6. WHEN the LLM returns extracted requirements or ranking rationale, THE Purchasing_Agent SHALL validate that output against the JSON Schema before using it.
7. IF LLM output fails JSON Schema validation, THEN THE Purchasing_Agent SHALL retry the LLM request exactly one time.
8. IF LLM output fails JSON Schema validation after one retry, THEN THE Purchasing_Agent SHALL escalate to a human with an indication of the validation failure reason and SHALL NOT use the invalid output.

### Requirement 12: Agent Control Loop and Escalation

**User Story:** As a buyer, I want the agent to follow a disciplined discover-compare-validate-order flow and escalate when blocked, so that it acts within its authority and hands off to me when needed.

#### Acceptance Criteria

1. WHEN a buyer provides a natural-language purchasing intent, THE Purchasing_Agent SHALL extract structured requirements and validate them against the JSON Schema before performing product search.
2. IF the extracted structured requirements fail JSON Schema validation after one retry, THEN THE Purchasing_Agent SHALL escalate to the buyer with the reason AND SHALL NOT perform product search, obtain a Decision, or submit an order.
3. WHEN the Purchasing_Agent has a candidate offer, THE Purchasing_Agent SHALL obtain a Decision from the Aimo_API before submitting an order, AND SHALL NOT submit an order for which no Decision has been obtained.
4. WHEN the Decision is AUTONOMOUS, THE Purchasing_Agent SHALL submit the order without requesting human sign-off.
5. IF the Decision is DENIED, THEN THE Purchasing_Agent SHALL report the reason returned in the Decision to the buyer AND SHALL NOT submit an order.
6. IF the Decision is REQUIRES_APPROVAL, THEN THE Purchasing_Agent SHALL create an Approval_Request AND SHALL submit the order only after the matching Approval_Request has status approved AND SHALL NOT submit an order while the Approval_Request remains pending or has status rejected.
7. WHEN product search returns no candidates, THE Purchasing_Agent SHALL report to the buyer that no matching products were found AND SHALL NOT obtain a Decision or submit an order.

### Requirement 13: Customer Approval Dashboard

**User Story:** As a kitchen manager, I want to review and approve or reject pending agent requests, so that I keep sign-off authority over purchases that exceed the agent's autonomy.

#### Acceptance Criteria

1. WHEN an Approval_Request is created, THE Approval_Dashboard SHALL display the Approval_Request within 3 seconds, showing the cart summary (each line item name, quantity, and unit price), the cart total, and the agent's explanation text.
2. WHEN a Customer approves a pending Approval_Request, THE Aimo_API SHALL set that Approval_Request's status to approved and record the deciding Customer identifier and the decision timestamp.
3. WHEN a Customer rejects a pending Approval_Request, THE Aimo_API SHALL set that Approval_Request's status to rejected and record the deciding Customer identifier and the decision timestamp.
4. IF a Customer submits an approve or reject decision on an Approval_Request whose status is not pending, THEN THE Aimo_API SHALL reject the decision, leave the existing status and recorded decision unchanged, and return an error indicating the Approval_Request has already been decided.
5. WHEN an Approval_Request decision is recorded, THE Audit_Log SHALL append an approval-decided AuditEvent containing the Approval_Request identifier, the outcome (approved or rejected), the deciding Customer identifier, and the decision timestamp.
6. THE Approval_Dashboard SHALL display the Customer's own approval history and order history, ordered from most recent to oldest.

### Requirement 14: Aimo Control and Audit Dashboard

**User Story:** As Valio Aimo, I want a dashboard to monitor registered agents and inspect the audit trail, so that I can oversee autonomous activity across customers.

#### Acceptance Criteria

1. WHEN an Aimo operator opens the Control_Dashboard, THE Control_Dashboard SHALL display each registered agent with its status, where status is one of active, suspended, or revoked.
2. IF no agents are registered, THEN THE Control_Dashboard SHALL display an empty-state message indicating that no agents exist.
3. WHEN an Aimo operator opens the audit viewer, THE Control_Dashboard SHALL display AuditEvents retrieved from the Aimo_API in human-readable form, showing for each event its timestamp, associated agent identifier, event type, and outcome.
4. IF the Aimo_API request for AuditEvents fails or returns no response within 10 seconds, THEN THE Control_Dashboard SHALL display an error message indicating that the audit trail could not be loaded and SHALL retain any previously displayed AuditEvents.
5. WHEN new AuditEvents are recorded during a purchasing flow, THE Control_Dashboard SHALL reflect the updated audit trail within 5 seconds of the AuditEvent being available from the Aimo_API, ordered with the most recent AuditEvent first.

### Requirement 15: Exception Handling

**User Story:** As a buyer, I want the system to handle failures and edge cases predictably, so that it stays safe and transparent beyond the happy path.

#### Acceptance Criteria

1. WHEN a Quote reports an item with zero available quantity, THE System SHALL report that item to the buyer as unavailable with its available quantity shown as zero AND SHALL NOT include that item in any submitted order.
2. WHERE an item is partially available AND the Purchasing_Policy allows substitutions, THE Purchasing_Agent SHALL propose a partial fulfilment covering the available quantity plus a substitute product for the remaining quantity AND SHALL report the available quantity, the substitute product, and the reason for the substitute.
3. IF the Policy_Engine returns DENIED with a blocked-allergen reason, THEN THE Purchasing_Agent SHALL report the blocked-allergen reason to the buyer AND SHALL NOT submit an order.
4. IF the Policy_Engine returns DENIED with a category-outside-allowed-categories reason, THEN THE Purchasing_Agent SHALL report the disallowed-category reason to the buyer AND SHALL NOT submit an order.
5. WHEN a human rejects a pending Approval_Request, THE Purchasing_Agent SHALL report to the buyer that no order was placed AND THE Order_Manager SHALL NOT create an order for that Approval_Request.
6. IF no approval decision is recorded within 300 seconds of the Approval_Request being created, THEN THE Purchasing_Agent SHALL report to the buyer that the order is awaiting approval and was not placed, AND THE Approval_Request SHALL retain status pending.
7. WHEN an order submission carries an Idempotency_Key that already produced an order, THE System SHALL report that single existing order unchanged rather than a second order.
8. IF an item in an order submission has zero available quantity at submission time, THEN THE Order_Manager SHALL reject the submission with an OUT_OF_STOCK error, SHALL NOT create an order, AND SHALL record one order-rejected AuditEvent with the reason OUT_OF_STOCK.

### Requirement 16: Delivery, Team, and Openness Constraints

**User Story:** As the project team, I want the solution to respect the delivery scenario and our team constraints, so that it is demoable, maintainable by non-experts, and credible as an open standard.

#### Acceptance Criteria

1. WHEN a buyer requests a delivery date for one or more quoted items, THE Aimo_API SHALL return, for each quoted item, a delivery date, a lead time expressed in whole days, and a reliability value expressed as a percentage from 0 to 100.
2. IF a requested quoted item has no available delivery date, THEN THE Aimo_API SHALL return an indicator for that item identifying it as unavailable while still returning results for all other requested items.
3. WHEN the central demo scenario of ordering 1,000 litres of lactose-free milk for delivery by the next Monday end of day is executed, THE System SHALL complete the scenario end to end from discovery through confirmed acceptance without manual intervention between stages.
4. THE System SHALL expose its interface through an OpenAPI contract document that defines every request and response the System accepts and returns.
5. THE System SHALL use synthetic data only AND SHALL NOT issue requests to, or read data from, real or confidential Valio Aimo systems.
6. THE System SHALL use English for all code, comments, and documentation stored in the repository.
