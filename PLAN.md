# The plan: Trusted Trade Agents for Valio Aimo

Submission: **Sunday 15/11 at 10:00**. Three people, three lanes, no shared files. Read this page once, then open `team/<your-name>/START.md` and follow it.

## The idea in one sentence

**The harness verdict decides who signs.** An external buying agent can search and get quotes freely, but an order only exists if it carries a valid signature. Verdict `auto`: the agent's key signs, inside limits the human signed beforehand. Verdict `human`: the human signs this exact order. Verdict `deny`: nobody signs, and Valio Aimo refuses any order without a valid signature.

That one mechanism answers the two problems Valio asks about:
- **Trust protocol**: every quote is signed by Valio, and every fact in it (stock, price, origin, delivery reliability, carbon footprint) states its source, its date and how certain it is.
- **Guardrails model**: rules in code decide `auto`, `human` or `deny`. A separate model (Gemini Decision) only judges the fuzzy cases, and can only make the verdict stricter.

## How it fits together

```
BUYER SIDE (hotel chain)                                VALIO AIMO SIDE
Claude Desktop (external agent)
   │ MCP (5 tools, agent_mcp/)
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

## The demo in four acts

| Act | The human says | What happens | Verdict |
|---|---|---|---|
| 1 | "I need 1,000 litres of lactose-free milk by Monday." | Comparison table (price per litre, date, reliability, carbon, labels). 1,000 x 464306 at EUR 1.01, EUR 1,010. | `auto` |
| 2 | "Make it 2,000 litres." | EUR 2,020 is above the EUR 1,500 limit. Approval card with the order cut-off as a deadline. The human signs, or lets it expire. | `human` |
| 3 | "600 litres of the Arla one." | Only 384 in stock. The gateway ranks three substitutes. The Valio one (same allergens) goes through. The oat drink is 60% lower in carbon but changes the allergens. | `auto`, then `human` |
| 4 | Someone changes the price in a signed quote. | The signature no longer matches. A replayed mandate is refused too. | `deny` |

## What is already proven

Run on 14/11, scripts in `spikes/`:
- Real AP2 mandates on our case, 13 cases out of 13: a tampered quote, a substitute outside the signed list, a wrong quantity, another merchant, a forged mandate, another agent's key, two replays, an expired mandate and an order above the signed cap are all refused with a readable reason. A human-signed order verifies with the manager's key and fails with the agent's key.
- Our extra fields survive inside the signed quote. Signing and verifying take 1 to 2 ms.
- The stack installs together: Python 3.14, `ap2` (commit `e1ea56d`), `pydantic` 2.12.5, `fastapi` 0.162.7, `mcp` 2.3.0, `google-genai` 3.3.0, `uvicorn` 0.54.0. A stack test passes 8 checks out of 8 from this repo: MCP over stdio, FastAPI in a second process, MCP over HTTP.
- The catalog already lists substitutes for some products (field `substitutions`): 464306 lists 465039, 464398, 469363 and 464201.

Not proven yet, and the first thing two lanes check: Gemini Decision on our substitution case (Léon), Claude Desktop as the live agent (Colette).

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

## The first four hours

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

## After 17:00

| Time | What must be on `main` |
|---|---|
| Saturday 17:00 | Act 1 scripted across the real pieces, first backup video |
| Saturday 19:30 | Act 1 live from Claude Desktop. Acts 2 and 4 scripted: approval card with deadline, mandate signed by the human, tampered quote refused, two logs |
| Saturday 23:00 | Act 3: partial stock, ranked substitutes, Gemini judge. Otherwise the reduced version: rule only, judge shown on one example |
| Sunday 02:00 | All 4 acts from the page and Claude Desktop, attack buttons, replay mode complete |
| Sunday 06:00 | Feature freeze, fixes only |
| Sunday 06:00 to 08:00 | 3 rehearsals, final video, README and docs |
| Sunday 09:30 | Submission, 30 minutes of margin |

Cut order if things slip: the cumulative budget across split orders, the human-signed list of pre-accepted substitutes, judge calibration beyond 10 pairs, polish of the comparison table, Claude live on acts 3 and 4 (the scripted runner replaces it). Never cut: acts 1, 2 and 4 with real signatures and both logs.

## How the judges score, and where we answer

| Criterion | Weight | Our answer |
|---|---|---|
| Working end-to-end demo | 30% | The four acts on real Valio data, with a replay mode and a scripted fallback |
| Solving the user need | 20% | Litres converted to sales units in code, comparison on price, date, reliability and carbon |
| Autonomy and controls | 20% | The verdict decides who signs. Rules in code, a separate judge, two audit logs |
| Robustness to exceptions | 15% | Partial stock, ranked substitutes, allergen change, missing data, cut-off deadline |
| Openness, path to production | 15% | MCP, UCP Checkout, AP2 mandates, ES256, generated OpenAPI. `TECH-CHOICES.md` explains each choice |

## Rules for three people coding at once

- One step = one `feat/...` branch = one small PR. Never push to `main`.
- Before each step: `git switch main && git pull`.
- Before each PR: `uv run pytest` and `uv run ruff check` (once `pyproject.toml` exists).
- A PR is merged by its author once a teammate has clicked through it. Squash merge.
- Everything in the repo is in English. Keys live in `.env`, never in git.
- Write your results and open questions in `team/<name>/notes.md`, so the others can read them without asking.
