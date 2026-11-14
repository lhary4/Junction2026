# Léon: the harness

Read `PLAN.md` first, then `docs/contract.md`. Your lane is the piece the pitch is built on: the code that decides whether an agent's order is signed by the agent, by a human, or by nobody.

What we kept from your spec, and why it moved, is in `docs/spec-v0/README.md`. Short version: your principles are the backbone (the LLM never decides a fact, `deny` beats `human` beats `auto`, submission is not acceptance, a hash-chained log). What changed is that we build on the real Valio APIs and that an approval is now a signature over the exact quote.

## What you own

- `harness/`, `common/audit.py`, `tests/test_harness_*.py`, `tests/test_audit.py`.
- Do not edit `contract/`, `trust/`, `merchant/`, `surface/`, `agent_mcp/`, `scenarios/`. If a model in `contract/` does not fit, tell Adrien.

## Before 13:15

- Install `uv` (https://docs.astral.sh/uv/).
- Create a key in Google AI Studio, put it in `.env` as `GEMINI_API_KEY`, share it in the team chat.
- `cp .env.example .env` and fill `VALIO_AIMO_API_KEY` from the team chat.

## Rules for every step

- One step = one branch = one small PR. Start from an up-to-date `main` (`git switch main && git pull`).
- Once `pyproject.toml` is on `main` (after 14:05): `uv sync`, `uv run pytest`, `uv run ruff check` before each PR.
- Write numbers and open questions in `team/leon/notes.md`.
- All code, comments and commit messages in English.

## L1. The Gemini judge on our real case (13:15 to 14:05)

Branch `feat/harness-judge`. Goal: know by 14:05 whether Gemini Decision can judge a substitution, with numbers.

Until `pyproject.toml` exists, run with `uv run --python 3.14 --with "google-genai>=3.3" python harness/judge.py`.

The call, from Google's docs:

```python
from google import genai

client = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
result = client.decisions.create(
    model="gemini-decision-1",
    input="...the facts, as text...",
    questions={"within_preferences": {"type": "noul", "instructions": "..."}},
)
answer = result.answers["within_preferences"]   # answer.noul is P(yes), from 0.01 to 0.99; answer.confidence
```

1. `harness/judge.py` with `judge_substitution(original: dict, candidate: dict, preferences_text: str) -> list[dict]`. It returns answers shaped like the `judge` list in `contract/examples/verdict.human.substitution.json`.
2. The input holds only structured fields from the product cards (name, category, allergens, nutritional claims, brand) and the buyer's preference sentence. Never marketing text: Google's docs warn that input text can argue for its own classification.
3. Two yes/no questions: `within_preferences` and `same_use`. The model never sees the key, so the whole question goes in `instructions`.
4. Run the real case from `contract/examples/product-cards.json`: original 469363, candidates 464201, 463380 and 464320, with `preferences_text` from `contract/examples/policy.demo.json`.
5. Fail closed: no key, a timeout (5 seconds) or any error returns `routed: "human"` with `probability: null`. Check it by removing the key.
6. In `team/leon/notes.md`: the six probabilities, the median latency over 10 calls, what the error looks like.

Expected order on `within_preferences`: 464201 above 463380 above 464320. If the order is wrong after two rewrites of the questions, or `client.decisions` is not available, say so at 14:05. The fallback is Gemini Flash with structured output behind the same function.

Done when: the numbers are in your notes and the function works. Open the PR once `main` has `pyproject.toml`, with a test that uses a fake client (no network).

## L2. The audit log (14:05 to 14:35)

Branch `feat/audit-log`. Goal: both services write the same kind of log, and anyone can check it was not edited. This is your hash chain.

1. `common/audit.py`: a class `AuditLog(path)` with `append(...)`, `read()` and `verify()`. One JSON object per line. Each event carries `prev_hash` and its own `hash`, the SHA-256 of the event's canonical JSON without the `hash` field. `verify()` returns the index of the first broken event, or `None`.
2. Fields: see `contract/examples/audit-events.json` and the `AuditEvent` model (the `hash` values in the example are shortened).
3. `append` accepts an optional `now`, because `common/clock.py` arrives with Adrien's A2.
4. Files go to `state/buyer/audit.jsonl` and `state/merchant/audit.jsonl` (`state/` is ignored by git).
5. `tests/test_audit.py`: three appends verify, then a line edited by hand is caught at the right index.

For the pitch, the honest wording: the chain makes tampering evident, it does not make it impossible. What anchors it is that each side also holds pieces signed by the other.

Done when: merged by 14:35. Tell Adrien, he uses it in A5.

## L3. The rules (14:35 to 15:55)

Branch `feat/harness-rules`. Goal: a pure function that turns a policy and a quote into a verdict. No network, no signature, no state.

1. `harness/policy.py`: `load_policy(path)` returns a `BuyerPolicy`. Colette will own `scenarios/policy.demo.json`. Until it exists, read `contract/examples/policy.demo.json`.
2. `harness/rules.py`: `evaluate(policy, checkout, now, signature, judge=None) -> Verdict`. `signature` is the `quote-signature` rule result, computed by the caller with `trust.verify_checkout`. `judge` is a function with the L1 signature, so tests can pass a fake.
3. The rules and their outcomes are the table in `docs/contract.md`. `deny` beats `human` beats `auto`. Every rule that ran appears in `Verdict.rules`, passed or not, so the log can show why.
4. Substitutions: a line with `substitute_for` is pre-accepted when the category and the `contains` list are the same as the replaced product. Different allergens give `human`. Not pre-accepted and same allergens goes to the judge.
5. `tests/test_harness_rules.py`, as a table: EUR 1,010 `auto`, EUR 2,020 `human`, missing allergen data `human`, blocked allergen `deny`, allergens changed by a substitute `human`, delivery later than requested `human`, expired quote `deny`, bad signature `deny`, two rules at once keep the stricter one, judge unreachable `human`.

The four example verdicts in `contract/examples/` are what your function should produce for the matching quotes.

Done when: tests pass and the PR is merged by 15:55.

## L4. The harness service (15:55 to 16:55)

Branch `feat/harness-service`. Goal: one call from the agent ends in an order, a pending approval, or a refusal. Routes are in `docs/contract.md`.

1. `harness/signer.py`: holds the agent's key and the open mandates. `sign_auto(checkout_jwt)` calls `trust.close_as_agent`, `sign_human(checkout_jwt)` calls `trust.close_as_human`. The manager's key lives on the buyer side. In the demo the Approve button triggers it. In production it would be a passkey on the approval page: say so in the pitch.
2. `harness/approvals.py`: a small store (memory plus a JSON file under `state/buyer/`). A request is bound to its `checkout_hash`. Its deadline is the quote's cut-off. Deciding after the deadline gives `expired`. A request can be decided once.
3. `harness/app.py`, FastAPI:
   - `POST /authorize`: fetch the quote from `MERCHANT_URL`, verify it with `trust.verify_checkout` against the gateway's JWKS, run `evaluate`. `auto`: sign, send to `POST /checkouts/{id}/complete`, verify the receipt, answer `ordered`. `human`: create the approval, answer `pending_approval`. `deny`: answer `denied`.
   - `POST /approvals/{id}/decision`: approve signs as the human and completes the order. Reject closes it.
   - `GET /authorizations/{checkout_id}`, `GET /approvals`, `GET /policy`, `GET /audit`.
   - Write an audit event at each step. Serve `surface/static` at `/`. Allow cross-origin calls from `localhost`.
4. Until the gateway is up (around 16:10), test with `contract/fixtures/checkout.valid.jwt` and a fake gateway.
5. `tests/test_harness_service.py` with FastAPI's test client and a fake gateway: `auto` gives an order, `human` then approve gives an order signed by the human, `human` then reject gives nothing, a tampered quote gives `denied`.

At 16:30, stop for five minutes with Adrien: fetch and verify one real quote from his gateway.

## 17:00 checkpoint

With Adrien and Colette, write `scenarios/run.py` on one screen: act 1 through the real pieces.

## Saturday evening: the 2-minute video (replaces "After 17:00")

Read the section "The demo: a 2-minute video, three buttons, one AP2 trail" in `PLAN.md` first. The demo runs on `scenarios/restaurant-case/`, not on milk. Adrien builds the demo driver (`scenarios/run.py`, port 8003) and the sandbox payment. Colette builds the page only, so the policy file and the words are yours tonight.

One step = one branch = one small PR, as before. Do not edit `merchant/`, `contract/`, `trust/`, `surface/` or `scenarios/run.py`.

### L5. The restaurant's policy and the judge on the candidates (by 20:45)

Branch `feat/restaurant-policy`. `scenarios/policy.demo.json` is Colette's file: tell her before you edit it.

1. Customer `demo-restaurant-helsinki`, approver `chef@demo-restaurant.example`. Keep the limit (EUR 1,500), the blocked allergens (AP, AN) and the thresholds.
2. Rewrite only the first line of `preferences_text` for this kitchen: a Nordic set menu, every dairy product is lactose free, no peanuts and no tree nuts. Keep the three lists.
3. Run the real judge on the candidates of the substitution scenario, with cards built the way the harness really builds them: the squeaky cheese 474880 to 467148 (same maker, frozen) and to 475072 (another maker, chilled), and the lingonberry jam 465815 to 462198. The full product file is needed (`uv run python scripts/fetch_data.py`, `VALIO_MODE=live`).
4. Probability, confidence and routing go in `team/leon/notes.md`. Tell Adrien the numbers: we want the case where the chef signs.

### L6. A message to the chef when an approval is created (by 22:00)

Branch `feat/harness-notify`. `harness/notify.py`: one Telegram message (Bot API `sendMessage`) with the reason in one sentence, the total, the deadline and the link to the approval page. Variables `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, added to `.env.example` without values. Timeout of 2 seconds, any failure is swallowed and logged: a message must never change or delay a verdict. No variable set means no call. The approval itself stays on the page, never in the chat. Test with a fake HTTP client. Add an entry to `TECH-CHOICES.md`.

### L7. The words (by 00:30)

Branch `feat/demo-script`.

1. `docs/demo-script.md`: the video second by second, 1:55 in total, on the beats of `PLAN.md`. For each beat: what is on screen, the sentence said, what to do if it fails. Say "mandate" for what is signed and "sandbox payment" for the charge.
2. `docs/pitch-deck.md`, five slides: the problem, the idea (the verdict decides who signs), the demo, the standards (MCP, UCP Checkout, AP2, ES256) and what we add to them, what comes next. Export it to PDF.

### L8. After Adrien's payment PR

Pull, run the harness tests, fix what the new `payment` field of `Order` breaks.

### Bonus, 90 minutes at most, only once L5 to L8 are merged

A WebAuthn passkey on "Approve and sign", with the quote hash as the challenge, verified by the harness before `sign_human`. Tell Colette first: it touches her button.
