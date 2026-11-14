# The plan: Trusted Trade Agents for Valio Aimo

Submission: **Sunday 15/11 at 10:00**. Three people, three lanes, no shared files. Read this page once, then open `team/<your-name>/START.md` and follow it.

## The idea in one sentence

**The harness verdict decides who signs.** An external buying agent can search and get quotes freely, but an order only exists if it carries a valid signature. Verdict `auto`: the agent's key signs, inside limits the human signed beforehand. Verdict `human`: the human signs this exact order. Verdict `deny`: nobody signs, and Valio Aimo refuses any order without a valid signature.

That one mechanism answers the two problems Valio asks about:
- **Trust protocol**: every quote is signed by Valio, and every fact in it (stock, price, origin, delivery reliability, carbon footprint) states its source, its date and how certain it is.
- **Guardrails model**: rules in code decide `auto`, `human` or `deny`. A separate model (Gemini Decision) only judges the fuzzy cases, and can only make the verdict stricter.

## How it fits together

```
BUYER SIDE (a restaurant)                               VALIO AIMO SIDE
Buying agent (the demo driver, or any agent through MCP)
   │ HTTP, or MCP (5 tools, agent_mcp/)
   ├──────────────────────────────────────────────────▶ merchant/  FastAPI :8001
   │                                                     search, ES256-signed quote, order,
   ▼                                                     mandate verification, signed receipt, audit
harness/  FastAPI :8002 ──── HTTP: reads the quote ───▶      │
 verifies the signature, rules in code,   sends the mandate  ▼
 Gemini Decision judge, signs or not,                   real Valio APIs (price, availability)
 approval queue, audit                                  + 3 data files, live or replay mode
   ▲
surface/ (static page): the human approves and signs, audit logs from both sides
```

1. The agent searches, then asks for a quote. The gateway converts "1,000 litres" into sales units, calls the real Valio APIs and returns a signed quote.
2. The agent asks the harness to authorize that quote. It only passes a short identifier, never a token.
3. The harness fetches the signed quote, checks signature and expiry, applies the rules, and calls the judge only for substitutions.
4. The verdict decides who signs: the agent's key, the human on the page, or nobody.
5. Valio verifies the signatures, the spend cap, the quote hash and single use, then answers with a signed receipt. Each side keeps the piece signed by the other, so the two audit logs back each other up.

Standards we stand on: MCP for the agent, UCP's `Checkout` object for the quote, AP2 v0.2 mandates for the authorization, ES256 signatures, OpenAPI generated from Pydantic models. Details: `docs/architecture.md` and `docs/contract.md`.

## The demo: a 2-minute video, three buttons, one AP2 trail

Decided on Saturday 14/11 at 19:30, after a talk with a Valio Aimo engineer (`contexte/mentor-notes.md`). What we hand in is a **video of 2:00 at most**, public on YouTube or Vimeo, plus a PDF deck. The four milk acts are dropped from the video. The demo runs on the restaurant case in `scenarios/restaurant-case/`: a 50-cover Helsinki restaurant, a Nordic set menu, 22 real catalog products.

The stage is one page that looks like a Valio Aimo customer portal, because that is where Valio expects the agent to live first. MCP stays as the second door, for customers whose ERP has its own agent.

```
+-------------------+---------------------------------+----------------------+
| SCENARIOS         | KITCHEN                         | AP2 TRAIL            |
| 1 Normal order    | menu, order lines, prices       | 1 Open mandate       |
| 2 Substitution    | substitution or approval card   | 2 Signed quote       |
| 3 Attack          | (the chef signs here)           | 3 Verdict            |
| Reset             |                                 | 4 Closed mandates    |
|                   |                                 | 5 Valio verifies     |
|                   |                                 | 6 Sandbox payment    |
|                   |                                 | 7 Signed receipt     |
+-------------------+---------------------------------+----------------------+
```

| Button | What runs | Expected end |
|---|---|---|
| 1 Normal order | The dairy and dry goods of the menu (butter, cream, smetana, milk, oat flakes, crispbread, pickled cucumber, salt, sugar, oil), about EUR 187 | `auto`: the agent's key signs, sandbox payment, signed receipt |
| 2 Substitution | One ingredient Valio cannot deliver. The gateway ranks substitutes, the judge reads the kitchen's preferences | `human`: the chef's phone buzzes, the chef compares and signs on the page, then payment and receipt |
| 3 Attack | The agent signs above its cap, a mandate over a changed quote, a replayed mandate | Three refusals by Valio, in red on the trail |

Fresh vegetables are left out of button 1 on purpose: they have no allergen data, and our rule sends unknown allergen data to a human.

**The ingredient of button 2** is picked by Adrien after running the candidates through the real gateway and harness in live mode. First choice: the squeaky cheese 474880 (fresh, lactose free, order cut-off passed), with two lactose-free replacements in stock, the same maker's frozen one (467148) and another maker's chilled one (475072). Fallback: the lingonberry jam 465815 (no delivery on any date), replaced by 462198. If the chosen case ends in `auto`, a fourth button "Above the limit" makes the chef sign once in the video.

**The AP2 trail** closes every scenario: seven steps, who signed each one (manager, agent, Valio), with the real hashes. **The payment step is a sandbox**: once the mandates verify, the gateway books the amount on a simulated invoice account. No real money moves, and the page says so. In the video we say "mandate" for what is signed and "sandbox payment" for the charge.

**The demo driver** (`scenarios/run.py`, port 8003, started by `scripts/dev.py`) plays the buying agent and feeds the page. `POST /scenarios/{id}/run` runs a scenario through the gateway and the harness with the same calls as the MCP tools. `GET /state` returns one JSON object, the `DemoState` of `contract/models.py`: the menu lines, the quote, the verdict, the approval, the order and the seven steps. The chef's decision goes from the page straight to the harness.

The video, target 1:55:

| Beat | Time | What we see |
|---|---|---|
| Hook | 0:00 to 0:12 | The portal of the restaurant, its menu. "Who signs?" |
| Normal order | 0:12 to 0:35 | Button 1. The trail lights up to the signed receipt |
| Substitution | 0:35 to 1:20 | Button 2. Ranked substitutes, the judge, the phone, the chef signs before the deadline |
| Attack | 1:20 to 1:40 | Button 3. Three refusals, both audit logs |
| What else it does | 1:40 to 1:52 | One sentence each: weekly reorder from stock and bookings, carbon comparison, the MCP door for ERP agents |
| Close | 1:52 to 2:00 | MCP, UCP, AP2, ES256. "The verdict decides who signs." |

The video is public and the challenge data must not be shown as real Valio data: the page carries a banner "Concept mock-up, Junction 2026, synthetic data".

## What is already proven

Run on 14/11, scripts in `spikes/`:
- Real AP2 mandates on our case, 13 cases out of 13: a tampered quote, a substitute outside the signed list, a wrong quantity, another merchant, a forged mandate, another agent's key, two replays, an expired mandate and an order above the signed cap are all refused with a readable reason. A human-signed order verifies with the manager's key and fails with the agent's key.
- Our extra fields survive inside the signed quote. Signing and verifying take 1 to 2 ms.
- The stack installs together: Python 3.14, `ap2` (commit `e1ea56d`), `pydantic` 2.12.5, `fastapi` 0.162.7, `mcp` 2.3.0, `google-genai` 3.3.0, `uvicorn` 0.54.0. A stack test passes 8 checks out of 8 from this repo: MCP over stdio, FastAPI in a second process, MCP over HTTP.
- The catalog already lists substitutes for some products (field `substitutions`): 464306 lists 465039, 464398, 469363 and 464201.

Proven since: Gemini Decision as the judge, on 61 labelled product pairs (PR #21). Dropped: Claude Desktop as the agent on screen. Our only test of a live agent took about 2 minutes for one round, on another client, and the video is 2 minutes long.

## Who owns what

One owner per folder. If you need a change in someone else's folder, say it out loud and let them do it.

| Folder | Owner | Content |
|---|---|---|
| `contract/`, `trust/`, `common/clock.py`, `pyproject.toml`, `scripts/` | Adrien | Pydantic models, AP2 signing library, freezable time, dependencies, data scripts |
| `merchant/` | Adrien | Valio gateway: search, quote, order, receipt |
| `harness/`, `common/audit.py` | Léon | Rules, Gemini judge, signer, approvals, hash-chained log |
| `surface/`, `agent_mcp/`, `scenarios/`, `docs/demo-script.md` | Colette | Page, MCP tools, demo policy, prompts, pitch |
| `team/<name>/` | Each person | `START.md` (your steps) and `notes.md` (your results and questions) |
| `tests/` | Everyone | One file per area: `test_merchant_*.py`, `test_harness_*.py`, `test_surface_*.py` |

Three exceptions for Saturday evening, so that Colette works on the page only: Adrien writes `scenarios/run.py` (the demo driver), Léon edits `scenarios/policy.demo.json` (the restaurant's policy) and writes `docs/demo-script.md` and the deck.

## The first four hours (done)

Start is 13:15, when this plan is merged. Each cell is one step in your `START.md`, and one small PR.

| Slot | Adrien | Léon | Colette |
|---|---|---|---|
| before 13:15 | Merge the plan PR. | AI Studio key, share `GEMINI_API_KEY`, install `uv`. | Install `uv` and Claude Desktop. Read the Junction submission form: what must be handed in? |
| 13:15 to 14:05 | **A1** contract as Pydantic models | **L1** Gemini judge on the real substitution case | **C1** MCP tools on example data, plugged into Claude Desktop |
| 14:05 to 14:45 | **A2** `trust/` library, demo keys, signed fixture quotes | **L2** hash-chained audit log (to 14:35), then **L3** rules | **C2** the page in mock mode (to 15:35) |
| 14:45 to 15:25 | **A3** data files and recorded fixtures | L3 continues (to 15:55) | C2 continues |
| 15:25 to 16:10 | **A4** gateway: real search and signed quotes | L3 ends, **L4** starts at 15:55 | **C3** words, no code: demo script, prompts, policy text, mentor questions, labelled pairs (15:35 to 16:15) |
| 16:10 to 16:55 | **A5** gateway: orders, mandate check, receipt | **L4** harness service: authorize, approvals, signer | **C4** switch the page and the tools to the live routes |

Sync points, five minutes, out loud:
- **13:15** plan merged, everyone pulls and starts a session.
- **14:05** contract merged. Léon gives the Gemini numbers, Colette the Claude Desktop timings. Two calls to make: Gemini Decision as the judge (fallback: Gemini Flash with structured output behind the same function), Claude Desktop as the live agent (fallback: the scripted runner).
- **14:45** `trust/` and signed fixtures merged.
- **16:30** first cross-call: the harness fetches and verifies a quote signed by the gateway.
- **17:00** checkpoint: act 1 across the real pieces, driven by `scenarios/run.py`, written together in 30 minutes. First backup video.

## Pulled forward on purpose

- **Recorded fixtures today.** For a Monday delivery the order cut-off is Sunday 17:00. Replay mode must be fed while the live answers are still good.
- **Submission requirements in the first 20 minutes**, so a required video or text is not discovered on Sunday at 9:00.
- **Mentor questions this afternoon**, while mentors are around.
- **Demo script, prompts, pitch outline** in hour 3.
- **A backup video at every milestone**, replaced by a better one each time.

## Saturday evening to Sunday 10:00

Where we stood at 19:30: the gateway and the harness work end to end, and nothing is visible on a page with the real services yet. That is the first thing to fix. Each person's steps are in the section "Saturday evening" of their `START.md`.

| Who | In order |
|---|---|
| Adrien | The `DemoState` model and its example files, the live probe and the choice of the substitution ingredient, the demo driver, the sandbox payment, the attacks, the menu products added to the replay recording. Then, if time is left, a customer token on the gateway and the MCP live mode |
| Léon | The restaurant's policy and the judge on the candidates, a Telegram message when an approval is created, the demo script and the deck. Bonus: a passkey on "Approve and sign" |
| Colette | The page only: the three zones on the example files, the cards and the animated trail, then the switch to the live state |

| Time | What must be true |
|---|---|
| Saturday 20:30 | Example state files on `main`, so the page can be built. Substitution ingredient chosen by 20:45 |
| Saturday 22:30 | Buttons 1 and 2 run the real flow on the page. First backup recording |
| Sunday 00:30 | Sandbox payment, full AP2 trail, attacks, Telegram message. Timed rehearsal. Backup video uploaded and project switched to FINAL (it stays editable until 10:00) |
| Sunday 02:00 | Replay recording complete. Code freeze |
| Sunday 06:30 | Recording in replay mode, then editing |
| Sunday 08:45 | Public video, PDF deck, form filled |
| Sunday 09:15 | Final check: the video opens in a private window, the project is in FINAL |

Cut order if things slip: the passkey, the customer token, the MCP live mode, the fourth button, the attacks beyond the first one. Never cut: buttons 1 and 2 on real signatures, the AP2 trail, the sandbox payment.

## How the judges score, and where we answer

| Criterion | Weight | Our answer |
|---|---|---|
| Working end-to-end demo | 30% | Three scenarios on a real menu and real Valio data, from the request to the signed receipt, with a replay mode |
| Solving the user need | 20% | A restaurant's own recipes and quantities, converted to sales units in code, and a substitute judged against the kitchen's stated preferences |
| Autonomy and controls | 20% | The verdict decides who signs. Rules in code, a separate judge, a spend cap Valio checks itself, two audit logs |
| Robustness to exceptions | 15% | A product Valio cannot deliver, ranked substitutes, missing allergen data, the order cut-off as a deadline, three attacks refused |
| Openness, path to production | 15% | MCP, UCP Checkout, AP2 mandates, ES256, generated OpenAPI. `TECH-CHOICES.md` explains each choice |

## Rules for three people coding at once

- One step = one `feat/...` branch = one small PR. Never push to `main`.
- Before each step: `git switch main && git pull`.
- Before each PR: `uv run pytest` and `uv run ruff check` (once `pyproject.toml` exists).
- A PR is merged by its author once a teammate has clicked through it. Squash merge.
- Everything in the repo is in English. Keys live in `.env`, never in git.
- Write your results and open questions in `team/<name>/notes.md`, so the others can read them without asking.
