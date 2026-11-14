# Spec v0 (kept for reference, do not build from it)

These three files are Léon's first spec, written on 14/11/2026 before the team had looked at the real Valio portal together. They moved here when the plan in `PLAN.md` replaced them. Nothing was deleted.

Do not build from these files: they describe an API and a catalog that we invented at the time. The current references are `PLAN.md`, `docs/architecture.md` and `docs/contract.md`.

## What we kept

The backbone of the current design comes from here:

| From spec v0 | Where it lives now |
|---|---|
| The LLM never decides a fact. Prices, stock and acceptance come from the backend only (`requirements.md`, requirements 2 and 11) | The agent only passes identifiers. Facts come in a quote signed by the gateway |
| One deterministic policy engine, with `DENIED` over `REQUIRES_APPROVAL` over `AUTONOMOUS` (`design.md` B.2, requirement 5) | `harness/rules.py`, verdicts `deny`, `human`, `auto`, same precedence |
| Submission is not acceptance: only Valio accepts an order (`design.md` B.3, requirement 6) | The order exists only with Valio's signed receipt |
| The same request sent twice gives one order (requirement 7) | The gateway records each mandate and returns the same order on a replay |
| An expired quote cannot be ordered (requirement 8) | `quote-not-expired` in the harness, and the same check in the gateway |
| An append-only, hash-chained audit log (requirement 9) | `common/audit.py`, one log on each side |
| A customer approval screen and a Valio-side audit view (requirements 13 and 14) | `surface/`, one page with both |
| Three streams coding against one shared contract, with example files as stubs (`tasks.md`) | `contract/examples/`, one owner per folder, steps in `team/` |
| Correctness properties as tests (`design.md`, properties 2 to 7) | The test tables in `team/leon/START.md` and `team/adrien/START.md` |

## What changed, and why

| In spec v0 | Now | Why |
|---|---|---|
| An invented API (`/v1/products/search`, `/v1/price-availability`) and a seed catalog | The real Valio price and availability APIs and the real product file | They exist, and 30% of the score is a demo on the mocked environment Valio provides |
| An approval checked by its status only | An approval is a signature over the hash of the exact quote | Otherwise an agent could get one cart approved and order another |
| A blocked allergen is refused; an empty allergen list passes | Missing allergen data goes to a human | 46% of the catalog has no allergen data |
| The agent sends `unit_price` in the order | The agent sends an identifier, the price is in the signed quote | The spec's own requirement 2 says to ignore prices from the agent |
| Trust rests on a login token | Signed quotes, AP2 mandates, signed receipts | The challenge is called Trusted Trade Agents; a token says who calls, not that a human allowed this order |
| Partial stock and substitution are optional tasks | They are act 3 of the demo | 15% of the score is robustness to exactly these cases, and the real data gives them almost for free |
| The demo price was adjusted to cross the limit | The limit is a product choice (EUR 1,500) and the real prices decide | Easier to defend in front of the judges |
| Our own LLM agent with a fixed control loop | An outside assistant (Claude Desktop) through MCP, plus a scripted runner | Less to build, and it is a real external agent |
| React and Vite, SQLite, hand-written OpenAPI, `hypothesis` tests | A plain page, files, OpenAPI generated from the models, plain table tests | Less to learn in one weekend |
