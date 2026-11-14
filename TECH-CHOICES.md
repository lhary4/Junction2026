# Tech choices, in plain words

None of us is a seasoned developer. This file explains every technical choice in the project in simple language: what we picked, why, and what it changes for us. If you can read this file and nothing else, you should understand how the product works and what would break if we changed something.

## How to keep this file up to date
- Every PR that adds, changes or removes a technical choice updates this file **in the same PR**. When the PR is merged, `main` and this file stay in sync. Nobody edits it directly on `main`.
- A PR that changes no technical choice says so in its description ("Tech choices: no change").
- Write it for a teammate who was asleep: no jargon without a one-line explanation, no code, short sentences.
- When a choice is replaced, do not delete it: move it to "Choices we dropped" at the bottom with one line on why.
- Each choice uses the template below.

### Template
```
## <Topic>: <what we chose>
- Status: decided | trying it | open
- What it is: one or two sentences a non-developer understands.
- Why: the reason we picked it over the alternatives.
- What it changes for us: what it allows, what it forbids, what it costs (money, time, risk).
- If we change it: what breaks or has to be redone.
- Alternatives we looked at: name + one line each.
- Decided in: PR link, date.
```

## Current choices

## Secrets: API keys live in a local `.env` file
- Status: decided
- What it is: passwords and API keys sit in a file called `.env` on each laptop. Git ignores it, so it never reaches GitHub. `.env.example` lists the names of the keys without their values.
- Why: a key pushed to GitHub can leak and be abused, even in a private repo.
- What it changes for us: each teammate copies `.env.example` to `.env` and pastes the keys shared in the team chat. Code reads keys from there, never from a value written in the code.
- If we change it: nothing breaks, but any key that ever lands in git must be considered leaked and regenerated.
- Alternatives we looked at: none, this is the standard practice.
- Decided in: PR #1, 13/11/2026.

## Challenge: Valio Aimo, Trusted Trade Agents
- Status: decided
- What it is: we build the way an outside buying agent can search, get a quote and order from Valio Aimo, with rules about what it may do alone.
- Why: the brief names two problems we want to solve, a trust protocol and a guardrails model, and the data is real enough to demo on.
- What it changes for us: pure software, built on Valio's two read-only APIs and three data files. Quote, order, approval and audit are ours to build.
- If we change it: everything restarts.
- Alternatives we looked at: Meta's AI glasses challenge (brief kept in `contexte/`).
- Decided in: PR #7, 14/11/2026.

## Guardrails: the verdict decides who signs
- Status: decided
- What it is: before any order, a piece of code on the buyer's side (the harness) gives a verdict. `auto`: the agent's key signs. `human`: a person signs this exact order on a separate page. `deny`: nobody signs. Valio refuses any order without a valid signature.
- Why: a rule that only lives in the agent can be talked around. A missing signature cannot.
- What it changes for us: the rules are plain code (spend limit, allergens, delivery date, expiry). `deny` beats `human`, `human` beats `auto`. The agent never holds a key.
- If we change it: the harness, the approval page and the order check in the gateway are all built on it.
- Alternatives we looked at: rules written in the agent's prompt (not enforceable); an approval flag in a database (not tied to the exact cart).
- Decided in: PR #7, 14/11/2026.

## Trust protocol: every fact states its source and how sure it is
- Status: decided
- What it is: in a quote, stock, price, origin, delivery reliability and carbon footprint each come with where the value comes from, when, and a certainty level: measured, declared, estimated or unknown.
- Why: a signature proves Valio said it and nobody changed it. It does not prove it is true. The certainty level is what lets an agent decide without a manual check.
- What it changes for us: unknown is a real value, shown as "unknown" and never read as "fine". Missing allergen data goes to a human.
- If we change it: the quote format, the rules and the comparison table change.
- Alternatives we looked at: signing the quote only, without sources.
- Decided in: PR #7, 14/11/2026.

## Quote format: UCP's Checkout object, signed
- Status: decided
- What it is: the quote Valio sends back uses an existing open format for a shopping cart (the Checkout object of the Universal Commerce Protocol). Our own facts sit in one extra field called `aimo`. Valio signs the whole thing.
- Why: the AP2 toolkit already understands this format, and judges score open standards over home-made ones.
- What it changes for us: we do not rename its fields. Money is counted in cents.
- If we change it: the mandates stop verifying, because they check this exact format.
- Alternatives we looked at: our own quote format (what the first spec had).
- Decided in: PR #7, 14/11/2026.

## Authorization: AP2 mandates
- Status: decided
- What it is: AP2 is Google's open protocol for letting an agent buy on someone's behalf. A mandate is a signed permission. The manager signs an open one in advance (which merchant, how much). Each order then carries a closed one, tied to one quote.
- Why: it is exactly our guardrail, already specified, with a working Python toolkit. We tested it on our case: 13 situations out of 13 behave as expected.
- What it changes for us: the spend limit is checked twice, by the harness and by Valio itself. An approval cannot be reused for another cart. We install the toolkit from GitHub at a fixed version.
- If we change it: `trust/` is rewritten, the rest keeps working because nobody else calls the toolkit.
- Alternatives we looked at: plain signed messages with our own field names; an approval id checked in a database.
- Decided in: PR #7, 14/11/2026.

## Signatures: ES256, demo keys in the repo
- Status: decided
- What it is: ES256 is a standard way to sign data. Three keys exist: Valio's, the manager's and the agent's. The demo keys are saved in the repo so the same examples verify on every laptop.
- Why: AP2 forbids the other common scheme (Ed25519) for quotes. Shared demo keys save hours of "works on my machine".
- What it changes for us: these keys protect nothing real and are labelled "DEMO ONLY". Real keys would never be in git.
- If we change it: all recorded example tokens must be regenerated.
- Alternatives we looked at: Ed25519 (not allowed by AP2 for quotes); keys generated on each laptop.
- Decided in: PR #7, 14/11/2026.

## How the agent talks to us: MCP on top of two small web services
- Status: decided
- What it is: MCP is the standard plug that lets an AI assistant use outside tools. Our agent gets five tools. Behind them run two small web services, one for Valio, one for the buyer's harness.
- Why: we do not have to write the agent, and it is a real outside agent, as in the brief. The services also work without MCP, for any other client.
- What it changes for us: the agent only passes short identifiers, never a signed token. The human approves on a separate page, not in the chat.
- If we change it: only `agent_mcp/` changes.
- Alternatives we looked at: our own agent loop; a chat-only demo (the brief says this is not about a chatbot, and an agent could approve itself).
- Decided in: PR #7, 14/11/2026.

## Models: Claude as the buying agent, Gemini Decision as the judge
- Status: trying it (decision at the 14:05 sync on 14/11)
- What it is: Claude Desktop plays the outside buying agent. A second, different model (Google's Gemini Decision) answers yes or no questions with a probability, for one thing only: is this substitute within what the buyer asked for?
- Why: a judge that is not the agent is harder to fool. It is fast and cheap (0.10 USD per million input tokens, free tier for prototyping, per Google's announcement of 11/11/2026, linked in `docs/architecture.md`).
- What it changes for us: the judge gives no explanation, so we log the question, the probability and the threshold ourselves. It can only make a verdict stricter. If it does not answer, a human decides.
- If we change it: one function in `harness/judge.py`.
- Alternatives we looked at: Gemini Flash with structured output (our fallback); rules only.
- Decided in: PR #7, 14/11/2026.

## Stack: Python 3.14 with uv, FastAPI, Pydantic, a plain web page
- Status: decided
- What it is: Python for everything. `uv` installs the same Python and the same libraries on every laptop. FastAPI makes the web services. Pydantic describes each piece of data once. The page is plain HTML, CSS and JavaScript.
- Why: the AP2 toolkit is Python and Pydantic. This exact set of versions was installed and run together.
- What it changes for us: one command to install (`uv sync`), one to test (`uv run pytest`). No build step for the page.
- If we change it: version pins live in `pyproject.toml`. Changing Python or Pydantic versions risks breaking the AP2 toolkit.
- Alternatives we looked at: a Next.js app; React for the page.
- Decided in: PR #7, 14/11/2026.

## Data contract: examples first, then models
- Status: decided
- What it is: `contract/examples/` holds one example of every message the pieces exchange. `contract/models.py` turns them into checked models, and a test proves the examples still fit.
- Why: three people can code at once only if they agree on the shapes first.
- What it changes for us: `contract/` changes only through a small, announced PR.
- If we change it: every lane is affected, so say it out loud first.
- Alternatives we looked at: a hand-written API description file.
- Decided in: PR #7, 14/11/2026.

## Data contract: strict models, generated schemas
- Status: decided
- What it is: our models refuse any field they do not know. A misspelled field name is an error, not a value silently dropped. The signed quote also checks that every line has its facts under `aimo.lines`, and the other way round. `scripts/export_schemas.py` writes one JSON Schema file per model into `contract/schemas/`, for tools and readers that are not Python.
- Why: in a signed quote, a dropped field is a fact that disappears without anyone noticing. An error at the first test is cheaper than a wrong order in the demo.
- What it changes for us: when you add a field, add it to `contract/models.py` first, or the other lanes' code will refuse your messages. Fields that can be empty default to empty, so a quote stored without its empty fields still loads. Never edit `contract/schemas/` by hand: rerun the script.
- If we change it: switching to "accept unknown fields" is one line in `contract/models.py`, but typos would then pass the tests.
- Alternatives we looked at: accepting unknown fields like the AP2 SDK does.
- Decided in: PR #8, 14/11/2026.

## Trust library: one small package signs and checks everything
- Status: decided
- What it is: `trust/` is the only code that talks to the AP2 toolkit. The gateway and the harness call a handful of functions: sign or check a quote, give the agent its permissions, close them for one quote, check them, sign or check a receipt.
- Why: if the toolkit changes, one folder changes. Nobody else has to learn it.
- What it changes for us: each permission is tied to one quote three ways: addressed to Valio, carrying the quote's id, and carrying the quote's fingerprint. A permission cannot be reused for another quote or another seller. Valio also checks that the amount promised is exactly the quote's total, because the toolkit alone would accept a smaller one. When a human approves, the manager's key signs the order directly, with no permission from the agent involved. When a quote fails, the error says which rule it breaks (bad signature or expired), so the harness can report the right reason.
- If we change it: the gateway's order check and the harness's signer change with it.
- Alternatives we looked at: calling the toolkit directly from the gateway and the harness (two copies of the same tricky code).
- Decided in: PR #9, 14/11/2026.

## Time: one clock that can be frozen
- Status: decided
- What it is: everything that needs "now" asks `common/clock.py`. When `AIMO_FROZEN_NOW` is set, it answers that exact time and never moves.
- Why: replay mode serves answers recorded on 14/11. Their deadlines only make sense if the clock says 14/11 too.
- What it changes for us: quote expiry, approval deadlines and receipt times follow the frozen clock. The permissions themselves keep the real time, because the AP2 toolkit stamps the real time when it signs. They are valid until the end of 16/11, so this holds for the whole weekend.
- If we change it: a ticking frozen clock (starting at the recorded time) would be one function to change.
- Alternatives we looked at: passing the time everywhere by hand (easy to forget one place).
- Decided in: PR #9, 14/11/2026.

## Data: local files, live calls on a shortlist, and a replay mode
- Status: decided
- What it is: the product file and the two small tables (delivery reliability, carbon footprint) are downloaded once and never committed. Prices and stock are asked from Valio only for a shortlist. A replay mode serves answers recorded on 14/11 with a frozen clock.
- Why: Valio's API forbids querying the whole catalog. The order cut-off for a Monday delivery is Sunday 17:00, so a live-only demo would break.
- What it changes for us: `VALIO_MODE=live` or `replay`. The recorded answers are a small subset saved in the repo.
- If we change it: without replay, the demo depends on the time of day.
- Alternatives we looked at: live only; committing the full product file (86 MB, not allowed).
- Decided in: PR #7, 14/11/2026.

## Recorded answers: 157 products, raw API answers, trimmed product records
- Status: decided
- What it is: `contract/fixtures/valio/` holds what Valio answered on 14/11 at 13:29 for a Monday 16/11 delivery: all lactose-free milks and plant-based drinks, plus the substitutes Valio lists for our five demo products. Prices and stock are kept exactly as the API sent them. The product records keep names, brand, origin, allergens, labels and ingredients, and drop marketing texts, pictures and instructions.
- Why: the full records of these products weigh 1.3 MB, the limit we set for the repo is 1 MB. Keeping the raw API answers means replay mode and live mode read the same shapes.
- What it changes for us: replay mode only knows these 157 products. A test checks that the demo facts still hold on them (464306 in stock with a Sunday 17:00 cut-off, 469363 with only 384 units). Rerunning `scripts/record_fixtures.py` replaces the recording and fails loudly if a demo fact no longer holds.
- If we change it: a new recording changes prices or stock in the demo, so tell everyone before merging one.
- Alternatives we looked at: recording only the five demo products (too few for a real search and for substitutes).
- Decided in: PR #10, 14/11/2026.

## Substitutes: the gateway proposes, ranked in three tiers, and never breaks a free-from promise
- Status: decided (the ranking inside a tier is open: Colette may change what counts first)
- What it is: when stock is short, Valio's gateway takes what there is and proposes up to three replacements: `best` (same kind of product, same allergens), `better` (same kind, other allergens), `good` (a related kind, plant-based drinks for milk). Inside a tier, the substitutes Valio itself lists come first, then the cheapest per litre. The best one goes into the quote automatically. The agent may ask for another one from the list, never one the gateway did not offer.
- Why: the agent never decides a fact, so it cannot invent a substitute. A lactose-free kitchen must never receive normal milk because it was cheaper, even if the allergen codes look the same: the data often lists milk but forgets lactose.
- What it changes for us: a substitute must arrive on time, cover the whole missing quantity, have complete allergen data, and keep every "free from" of the original. The harness still checks allergens and asks the judge, this is a first filter on Valio's side. Most stock counts from the mock are "plenty" (9,999,999,999): the quote says "available, count not given" instead of showing that number.
- If we change it: `merchant/quotes.py` only. The related kinds of product are one line in it.
- Alternatives we looked at: listing every candidate and letting the agent choose (the agent would pick facts); only Valio's listed substitutes (469363, the act 3 product, lists none).
- Decided in: PR #11, 14/11/2026.

## Orders: one per quote, and a repeated request gets the same order back
- Status: decided
- What it is: to order, the harness sends the signed permissions for one quote to Valio's gateway. The gateway checks three things in a fixed order: the quote is one it signed and has not expired, the permissions are valid for exactly this quote and this amount, and the quote has not been ordered yet. If all three pass, it creates the order and signs a receipt.
- Why: "no signature, no order" has to be enforced by the seller, not only by the buyer's software. And a network hiccup must never create two orders.
- What it changes for us: sending the same permission twice returns the same order, with the same receipt. A second, different permission for a quote that is already ordered is refused. A refusal lists every problem in readable sentences and creates nothing. The spend cap is checked by Valio too: an order signed by the agent above the cap is refused even if the buyer's harness were bypassed. Valio knows the manager's public key in advance (in real life, from the day the customer account is opened; in the demo, from the keys folder).
- If we change it: `merchant/orders.py` and the harness's reading of a refusal. The gateway does not ask Valio's stock again when the order arrives: the quote's price and stock hold until it expires.
- Alternatives we looked at: refusing any repeated request (a retry after a lost answer would look like an attack); checking stock again at order time (one more live call, and the brief asks for prices that hold).
- Decided in: PR #13, 14/11/2026.

## Running it locally: one command starts both services
- Status: decided
- What it is: `uv run python scripts/dev.py` starts Valio's gateway (port 8001) and the buyer's harness (port 8002), and stops both with Ctrl+C. It hands the values of `.env` to both.
- Why: three people on macOS and Windows should not have to remember two commands and export keys by hand.
- What it changes for us: a value typed in the terminal wins over `.env`. A service that is not in the repo yet is skipped. If one service dies, the other is stopped and the error is shown.
- If we change it: only this script.
- Alternatives we looked at: a shell script (does not run on Windows); Docker (one more tool to install during a hackathon).
- Decided in: PR #13, 14/11/2026.

## Audit log: one chained file on each side
- Status: decided
- What it is: the buyer's harness and Valio's gateway each write one line per decision: what, why, which rule, who. Each line includes a fingerprint of the previous one, so an edited line is detected.
- Why: the brief asks for a readable record for both the buyer and Valio.
- What it changes for us: the chain shows tampering, it does not prevent it. The stronger proof is that each side also keeps pieces signed by the other.
- If we change it: only `common/audit.py`. Until that shared file is merged, Valio's gateway chains its own lines in `merchant/audit.py`, which is the one place to switch over.
- Alternatives we looked at: a database table; a single shared log.
- Decided in: PR #7, 14/11/2026.

## Payments: none, the spend cap travels in an AP2 payment mandate
- Status: decided
- What it is: no money moves. Wholesale orders are invoiced on the customer's account, so the "payment instrument" in the mandate is that invoice account. The mandate carries the maximum amount the agent may commit.
- Why: payment is outside the brief, but the mandate is where AP2 puts the spend limit, and it lets Valio check the limit itself.
- What it changes for us: nothing to integrate with a bank or a network.
- If we change it: real payment would add AP2's other roles (credential provider, payment processor).
- Alternatives we looked at: x402, Nevermined (named in the brief as context, not required).
- Decided in: PR #7, 14/11/2026.

## Approval page: three plain files, with a mock mode that reads the examples
- Status: decided
- What it is: the page where a human approves is three files (`surface/static/`), opened in a browser. With `?mock=1` in the address it reads the example files in `contract/examples/` instead of the running services. Every screen of the demo has its own link (for example `&state=expired`), and `&now=...` starts the page's clock at a chosen time.
- Why: the page could be built and rehearsed before the gateway and the harness exist, and it stays as a safety net if a service fails on stage.
- What it changes for us: the page never works out a fact itself. A price only appears if it is in a signed quote, a missing value reads "unknown", and "verified" is only written when the harness said so. Anything the agent wrote is shown as plain text, so it cannot add a button to an approval card. In mock mode nothing is really checked or signed, and the page says so.
- If we change it: only `surface/` changes. If an example file is renamed, a test fails.
- Alternatives we looked at: React (a build step, dropped earlier); the harness serving ready-made pages (the page could not be built before the harness).
- Decided in: PR for step C2 (`feat/surface-mock`), 14/11/2026.

## Open choices (to decide, then move up)
- **Hosting the demo**: where the services run during judging (one laptop, or a small server so the three of us can use the same instance).

## Choices we dropped
- **Our own agent loop**: an outside assistant through MCP does the job and is closer to the brief's "external agent".
- **An invented Valio API with seed data** (first spec): the real APIs and files exist and the judges want the demo on them.
- **A hand-written API description (OpenAPI)**: FastAPI generates it from the models.
- **Login tokens (bearer) as the trust mechanism**: a token says who is calling, not that a human allowed this order.
- **React, Vite and SQLite**: a plain page and files are enough and need no build.
- **Ed25519 signatures**: AP2 does not allow them for quotes.
- **Running the whole demo inside the chat**: the brief says this is not a chatbot, and approval must happen where the agent cannot reach.
