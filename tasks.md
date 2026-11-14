# Implementation Plan: Trusted Trade Agents (Valio Aimo)

## Overview

This plan turns the design into small, mergeable coding tasks for three non-expert developers working in parallel on three machines. It is organized as four phases that map to the three-stream work split in the design (Part C):

- **Phase 0 — Shared Contract** is done FIRST by whoever is free, ideally pairing the whole team for an hour. It is the single integration point (OpenAPI contract, shared data model, example JSON fixtures, repo skeleton). Nothing heavy in Streams 1–3 should start until Phase 0 is agreed and merged.
- **Phase 1 — Stream 1 (Backend)**, **Phase 2 — Stream 2 (Agent)**, and **Phase 3 — Stream 3 (Dashboards)** run in parallel. Each is owned by one person, touches its own files, and can stub against the Phase 0 fixtures so it never has to wait on another stream.
- **Phase 4 — Integration & Demo** wires the three streams against the real backend and runs the demo scenario plus one exception path.

Stack (from design Part D, boring and non-expert friendly): Python + FastAPI backend, in-memory/SQLite seed data, plain LLM tool-calling agent with an `httpx` typed client, plain React (Vite) or single-file HTML/JS dashboards. English everywhere. One `feat/` branch per task.

**How to read the stream notes:** each stream phase begins with a short note stating the files it owns, what it can stub early, and its dependency on the shared contract. Pick a phase, create a `feat/` branch per task, and merge small PRs often.

## Tasks

- [ ] 1. Phase 0 — Shared Contract (do FIRST, unblocks all three streams)
  - **Owned by:** whole team pairs for ~1 hour, then one person finalizes. These are co-owned files; change them only via a small PR with a heads-up (git rule).
  - **Files/dirs:** `openapi.yaml`, `contract/examples/`, `backend/models.py` (data model lives here), repo top-level layout (`backend/`, `agent/`, `frontend/`), `.env.example`, `README.md` run instructions.
  - **Depends on:** nothing. **Blocks:** everything else.

  - [ ] 1.1 Create repo skeleton and run instructions
    - Create the three stream directories (`backend/`, `agent/`, `frontend/`) with a one-line `README` in each saying who owns it and how to run it.
    - Add the shared `.env.example` variable names (LLM provider key, agent API keys, backend base URL) with no values.
    - Add root `README.md` section: how to start the backend, run the agent CLI, and open each dashboard.
    - _Requirements: 16.5, 16.6_

  - [ ] 1.2 Define the shared data model
    - In `backend/models.py`, write Pydantic models for the entities in design §A.6 used by the MVP: Customer, PurchasingPolicy, Product, Price, Availability, DeliveryOption, Quote, ProductOffer, ApprovalRequest, Order, OrderItem, Transaction, AuditEvent.
    - Keep field names exactly as the agent and frontend will consume them.
    - _Requirements: 16.4_

  - [ ] 1.3 Write the OpenAPI contract
    - In `openapi.yaml` (OpenAPI 3.1), define every endpoint from design §B.1 (auth/token, account, products/search, products/{id}, price-availability, orders/validate, approval-requests, approval-requests/{id}/decision, approval-requests/{id}, orders, orders/{id}, audit) with request/response schemas and the standard error shape + error codes.
    - This is the source of truth all three streams code against.
    - _Requirements: 16.4, 2.1_

  - [ ] 1.4 Save example JSON fixtures
    - Copy the request/response examples from design §B.1 into `contract/examples/` as one JSON file per endpoint (happy path + the budget-exceeded `REQUIRES_APPROVAL` validate response + a `DENIED` response).
    - Streams 2 and 3 build against these before the backend is live.
    - _Requirements: 16.4_

- [ ] 2. Phase 1 — Stream 1: Backend (Mock Aimo API + Policy + Orders + Audit)
  - **Owned by:** one developer (e.g. Adrien). **Files/dirs:** `backend/app.py`, `backend/routes/*`, `backend/policy/engine.py`, `backend/orders/lifecycle.py`, `backend/audit/log.py`, `backend/data/seed.py`, plus `backend/tests/`.
  - **Can stub early:** nothing needed — Stream 1 is fully standalone and should ship a live endpoint + seed data on day one so Streams 2 & 3 can point at it instead of fixtures.
  - **Depends on:** Phase 0 (`openapi.yaml` + `backend/models.py`).

  - [ ] 2.1 Scaffold FastAPI app and seed synthetic data
    - Create `backend/app.py` with a FastAPI app, health route, and startup that loads `backend/data/seed.py`.
    - Seed synthetic customers, one purchasing policy, the lactose-free milk catalog, customer-specific prices, availability, and delivery options (design Part E, §A.6). Make seed resettable between demo runs.
    - _Requirements: 16.3, 16.5_

  - [ ] 2.2 Implement auth/token issuance and the account endpoint
    - `POST /v1/auth/token`: exchange registered `agent_id` + `api_key` for an opaque bearer token scoped to one customer, 3600s lifetime; reject unknown/revoked keys and missing fields with `UNAUTHENTICATED` without disclosing whether the agent id exists.
    - `GET /v1/account`: return the token's customer identity and its purchasing policy.
    - Add a bearer-token dependency that rejects missing/malformed/expired tokens on all other endpoints.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 2.3 Write unit tests for auth and customer scoping
    - Test valid issuance, unknown/revoked key, missing fields, missing/expired token on a protected route, and that a customer-A token cannot read customer-B data.
    - **Property 9: Customer isolation** — **Validates: Requirements 1.6, 9.7**
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

  - [ ] 2.4 Implement request validation and server-side-only facts
    - Add JSON Schema / Pydantic validation on every request body before any processing; return `VALIDATION_ERROR` naming the bad field(s) with no state change.
    - Ignore any price/stock/acceptance-status values supplied in request bodies; always use backend-computed values.
    - _Requirements: 2.1, 2.2, 2.3, 2.6_

  - [ ] 2.5 Implement product search and product details
    - `POST /v1/products/search`: validate query length 1–200, return matches with product id/name/category/unit/allergens/certifications, no prices; page at 50 with a pagination indicator; empty list on no match.
    - `GET /v1/products/{id}`: full attributes or `NOT_FOUND`.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ] 2.6 Implement price + availability inquiry (Quote)
    - `POST /v1/price-availability`: validate 1–100 items, quantity 1–999,999, delivery date not in the past; return a Quote with `quote_id`, `valid_until` (later than creation), per-item fixed customer-specific price, currency, available vs requested quantity, availability status (fully/partially/unavailable), and delivery details.
    - Record one `price_inquiry` audit event on success and on invalid-input rejection.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 16.1, 16.2_

  - [ ] 2.7 Implement the deterministic Policy_Engine
    - In `backend/policy/engine.py`, implement `evaluatePolicy` and `substitutionWithinPreferences` from design §B.2: hard-deny on disallowed category or blocked allergen, `REQUIRES_APPROVAL` on spend over limit or substitution outside prefs, else `AUTONOMOUS`; precedence DENIED > REQUIRES_APPROVAL > AUTONOMOUS; always include reasons when not AUTONOMOUS; load policy + product metadata server-side (never from agent input); return DENIED if that metadata cannot load. No side effects.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.11, 5.12_

  - [ ] 2.8 Wire the order-validation endpoint
    - `POST /v1/orders/validate`: load the referenced quote + policy, call `evaluatePolicy`, return the Decision + total + reasons without creating an order.
    - _Requirements: 5.1, 5.7_

  - [ ]* 2.9 Write unit tests for the Policy_Engine
    - Table-driven tests: AUTONOMOUS, REQUIRES_APPROVAL (spend), REQUIRES_APPROVAL (substitution), DENIED (category), DENIED (allergen), precedence when multiple rules fire, missing-metadata → DENIED.
    - _Requirements: 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.11_

  - [ ]* 2.10 Write property tests for policy determinism and hard-deny
    - Use `hypothesis` with random policies/carts.
    - **Property 2: Deterministic policy** (same input → same Decision, no side effects) — **Validates: Requirements 5.9, 5.10**
    - **Property 3: Hard deny wins** (any category/allergen violation → DENIED regardless of spend) — **Validates: Requirements 5.2, 5.3, 5.4**
    - _Requirements: 5.9, 5.10, 5.2, 5.3, 5.4_

  - [ ] 2.11 Implement the append-only hash-chained Audit_Log
    - In `backend/audit/log.py`: append-only `AuditEvent` with ISO 8601 UTC timestamp, actor, action from the allowed set, subject id, and 1–2000 char details; reject appends missing a required field; compute each hash from the event's fields + predecessor's hash; provide a verify function that reports the first mismatched event; reject any modify/delete.
    - `GET /v1/audit`: buyer token sees only its customer's events; admin token sees all.
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

  - [ ]* 2.12 Write property tests for the Audit_Log
    - **Property 8: Audit completeness** (each logged action appends exactly one event; hash chain unbroken under verify) — **Validates: Requirements 9.1, 9.4**
    - _Requirements: 9.1, 9.4, 9.5_

  - [ ] 2.13 Implement the order lifecycle (submission ≠ acceptance, price freshness, idempotency)
    - In `backend/orders/lifecycle.py` implement `submitOrder` (design §B.3): idempotency lookup first; re-validate the quote exists, not expired, belongs to the customer, price unchanged (`PRICE_CHANGED` otherwise, no order, audit `order_rejected`); re-run the Policy_Engine server-side and require an approved Approval_Request when REQUIRES_APPROVAL; stock re-check (`OUT_OF_STOCK`); create as `submitted`, then backend-only transition to `accepted` with a confirmation code; reject any agent-supplied acceptance with `FORBIDDEN`.
    - `POST /v1/orders` (with `Idempotency-Key` header) and `GET /v1/orders/{id}` (status + transaction, `NOT_FOUND` otherwise).
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 7.1, 7.2, 7.3, 7.6, 8.1, 8.2, 8.3, 8.4, 8.5, 15.8_

  - [ ]* 2.14 Write unit + property tests for the order lifecycle
    - Unit: submitted→accepted transition, approval-gate enforced, expired-quote rejection, OUT_OF_STOCK rejection, agent-supplied acceptance rejected.
    - Property tests with `hypothesis`:
      - **Property 4: Approval gate** — **Validates: Requirements 6.4, 6.5**
      - **Property 5: Submission is not acceptance** — **Validates: Requirements 6.1, 6.2**
      - **Property 6: Idempotency** (same key twice → one order, second returns the first) — **Validates: Requirements 7.1, 7.2**
      - **Property 7: Price freshness** (expired quote → PRICE_CHANGED, no order) — **Validates: Requirements 8.2, 8.3**
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 7.1, 7.2, 8.2, 8.3_

  - [ ] 2.15 Implement approval-request endpoints
    - `POST /v1/approval-requests` (create pending, log `approval_requested`), `POST /v1/approval-requests/{id}/decision` (approve/reject only when pending, record decider + timestamp, log `approval_decided`, reject re-decision), `GET /v1/approval-requests?status=pending` and `GET /v1/approval-requests/{id}`.
    - _Requirements: 13.2, 13.3, 13.4, 13.5_

- [ ] 3. Checkpoint — backend standalone
  - Ensure all backend tests pass and the seeded demo data loads. Ask the user if questions arise.

- [ ] 4. Phase 2 — Stream 2: AI Purchasing Agent
  - **Owned by:** one developer (e.g. Léon). **Files/dirs:** `agent/main.py`, `agent/client.py`, `agent/tools.py`, `agent/extract.py`, `agent/ranking.py`, `agent/report.py`, `agent/prompts/`, plus `agent/tests/`.
  - **Can stub early:** point `agent/client.py` at the Phase 0 `contract/examples/` fixtures (or a tiny local mock) so ranking, control loop, and report logic are built and tested with no backend and no live LLM. The LLM is isolated behind `extract.py`/`report.py`.
  - **Depends on:** Phase 0 (`openapi.yaml` + fixtures). Does NOT depend on Stream 1 or 3 to start.

  - [ ] 4.1 Build the typed HTTP client (the portal swap point)
    - In `agent/client.py`, write a thin `httpx` client with one method per endpoint, reading base URL + bearer token from `.env`. Default it to the fixtures so it works offline.
    - _Requirements: 2.4, 16.5_

  - [ ] 4.2 Define the agent tools over the client
    - In `agent/tools.py`, define one tool per endpoint the agent uses (search_products, get_price_availability, validate_order, request_approval, check_approval, submit_order, get_order) wrapping `client.py`.
    - _Requirements: 12.3_

  - [ ] 4.3 Implement LLM intent extraction with schema validation
    - In `agent/extract.py`, send the buyer intent to the LLM, parse structured requirements, validate against the JSON Schema; retry exactly once on failure; never put secrets/tokens in the prompt.
    - _Requirements: 11.6, 11.7, 11.8, 2.4, 12.1_

  - [ ] 4.4 Implement deterministic good-better-best ranking
    - In `agent/ranking.py`, sort candidate offers using only Quote field values; assign good/better/best; one candidate → best; zero candidates → no ranking + "no candidates" message; ties get the same tier and are flagged.
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ] 4.5 Implement the fact-injecting outcome report
    - In `agent/report.py`, build the ranking explanation and outcome report from templates that inject prices/stock/delivery/order-status copied verbatim from tool responses; if a value has no backing response, mark it unavailable instead of generating one; report success only when order status is `accepted` with a non-empty confirmation code.
    - Treat catalog text as data, not instructions.
    - _Requirements: 10.5, 10.6, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 4.6 Write property test for no-fabricated-facts
    - Use `hypothesis`: for any tool response, the generated report contains only values present in that response.
    - **Property 1: No fabricated facts** — **Validates: Requirements 11.1, 11.2, 10.5**
    - _Requirements: 11.1, 11.2, 10.5_

  - [ ] 4.7 Implement the control loop and escalation
    - In `agent/main.py`, implement `runPurchase` (design §B.4): extract → search → price → rank → validate → (approval) → order → report. No Decision → no order; DENIED → report reason, no order; REQUIRES_APPROVAL → create approval request, poll with a 300s timeout, submit only when approved; no candidates → report and stop. Retry submission only on transient errors (max 3) reusing the idempotency key.
    - _Requirements: 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 7.4, 7.5_

  - [ ]* 4.8 Write unit tests for the control loop
    - Mock the client with fixtures: AUTONOMOUS path submits directly; DENIED path stops; REQUIRES_APPROVAL path waits then submits; approval-rejected and approval-timeout paths place no order; transient error retries with the same idempotency key, non-transient does not.
    - _Requirements: 12.4, 12.5, 12.6, 7.4, 7.5, 15.5, 15.6_

- [ ] 5. Checkpoint — agent against fixtures
  - Ensure the agent runs end to end against the fixtures and all agent tests pass. Ask the user if questions arise.

- [ ] 6. Phase 3 — Stream 3: Dashboards / Frontend
  - **Owned by:** one developer (e.g. Colette). **Files/dirs:** `frontend/approval/`, `frontend/control/`, `frontend/api.js`, `frontend/components/`.
  - **Can stub early:** render against the Phase 0 `contract/examples/` fixtures / a local mock server so the approve/reject UI and audit viewer are built before the backend persists anything.
  - **Depends on:** Phase 0 (`openapi.yaml` + fixtures). Does NOT depend on Stream 1 or 2 to start.

  - [ ] 6.1 Build the shared frontend API wrapper
    - In `frontend/api.js`, write `fetch` wrappers for the approval, decision, audit, and order endpoints using the contract shapes, with a base URL that defaults to fixtures/mock.
    - _Requirements: 16.5_

  - [ ] 6.2 Build the Customer Approval Dashboard
    - In `frontend/approval/`: list pending approval requests showing per-line name/quantity/unit price, cart total, and the agent's explanation; approve and reject buttons calling the decision endpoint; an approval + order history view ordered newest-first.
    - _Requirements: 13.1, 13.6, 15.5_

  - [ ] 6.3 Build the Aimo Control / Audit Dashboard
    - In `frontend/control/`: list registered agents with status (active/suspended/revoked) and an empty-state message when none; an audit viewer showing timestamp, agent id, event type, and outcome per event, newest-first; error message if audit fails or no response within 10s while keeping previously shown events; refresh new events within ~5s.
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

- [ ] 7. Checkpoint — dashboards against fixtures
  - Ensure both dashboards render and behave correctly against fixtures. Ask the user if questions arise.

- [ ] 8. Phase 4 — Integration & Demo
  - **Owned by:** whole team (each repoints their stream's base URL at the live backend). **Files/dirs:** `agent/client.py` config, `frontend/api.js` config, `tests/integration/`.
  - **Depends on:** Phases 1, 2, 3 complete.

  - [ ] 8.1 Point agent and dashboards at the live backend
    - Switch `agent/client.py` and `frontend/api.js` base URLs from fixtures to the running backend via `.env`; confirm auth/token flow works end to end.
    - _Requirements: 16.3, 16.5_

  - [ ] 8.2 Write the end-to-end demo integration test (happy path with approval)
    - In `tests/integration/`, drive the full central scenario against the live backend: search → price (1,000 L lactose-free milk, delivery next Monday) → validate (REQUIRES_APPROVAL, over budget) → approve → order (accepted) → assert the audit trail contains the expected chain.
    - _Requirements: 16.3, 6.4, 13.2, 9.1_

  - [ ]* 8.3 Write the exception integration test (budget-exceeded, approval rejected)
    - Drive validate (REQUIRES_APPROVAL) → human rejects → assert no order is created and the audit records the rejection.
    - _Requirements: 15.5, 13.3, 13.4_

  - [ ]* 8.4 (Optional / stretch) Partial availability with substitution
    - Backend returns `partially_available`; agent proposes partial fulfilment + a substitute for the remainder (when policy allows), reporting available quantity, substitute, and reason.
    - _Requirements: 15.1, 15.2, 4.3_

  - [ ]* 8.5 (Optional / stretch) Price-changed-at-commit re-quote and sustainability tie-break
    - Agent re-quotes and re-validates when a commit returns `PRICE_CHANGED`; ranking adds a sustainability/reliability tie-break using certification fields already in the Quote.
    - _Requirements: 8.3, 10.1_

- [ ] 9. Final checkpoint — full demo
  - Reset seed data, run the happy path then the exception path, and show both dashboards updating live. Ensure all tests pass. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional (tests and stretch features) and can be skipped for a faster MVP; the unmarked tasks form the critical path. Core implementation tasks are never marked optional.
- **Parallelism:** after Phase 0 merges, Stream 1 (tasks 2.x), Stream 2 (tasks 4.x), and Stream 3 (tasks 6.x) run fully in parallel on three machines with no shared files. Streams 2 and 3 use the Phase 0 fixtures until the backend is live, then Phase 4 just repoints base URLs.
- Each task references the requirement clauses it satisfies for traceability; property-test tasks also reference the design's Correctness Properties (P1–P9) and the requirements each property validates.
- Property-based tests use `hypothesis`; unit tests cover the deterministic Policy_Engine and order lifecycle; one end-to-end integration test covers the demo scenario.
- Checkpoints give each stream a natural stop to merge and verify before integration.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "4.1", "6.1"] },
    { "id": 3, "tasks": ["2.2", "2.4", "2.5", "4.2", "4.3", "4.4", "6.2", "6.3"] },
    { "id": 4, "tasks": ["2.3", "2.6", "2.7", "4.5", "4.7"] },
    { "id": 5, "tasks": ["2.8", "2.9", "2.10", "2.11", "4.6", "4.8"] },
    { "id": 6, "tasks": ["2.12", "2.13", "2.15"] },
    { "id": 7, "tasks": ["2.14", "8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3", "8.4", "8.5"] }
  ]
}
```
