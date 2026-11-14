# Colette's notes

Results, numbers and open questions for the others. Newest first.

## C2: the page in mock mode

- Done: `surface/static/` shows the three areas from `contract/examples/`. How to run it and one link per screen: `surface/README.md`.
- Checked in headless Chrome on 14/11: the four offers screens, both approval cards in their four states, both buttons, a card expiring when the countdown reaches zero, the audit page, and that HTML typed into the agent's sentence stays plain text.
- Live mode is not built: without `?mock=1` the page says so. That is step C4.

Questions for Adrien (examples and contract):
- **The comparison table has one price in act 1.** Product cards carry no price, and the act 1 quote only prices 464306, so the four other rows read "unknown, not in this quote". For a full price comparison in act 1, either the agent asks one quote per candidate, or a quote lists the prices of the other candidates. Which one do we want?
- There is no example quote for `chk_act3_oat_demo` (the oat drink order of `verdict.human.substitution.json`). The substitution card shows "lines not in the example files" and takes the total from the verdict. An example `checkout.act3-oat.json` would complete it.
- There is no `ApprovalRequest` example for a substitution. The page builds one from the verdict (rules that did not pass become the reasons). Is that what the harness will send?
- Two facts have no certainty level in the contract: the delivery date of a line (`available_date`) and the price of an alternative (`aimo.alternatives[].comparison_price_minor`). The page shows them with a "certainty not stated" badge instead of guessing.
- `chk_act3_demo` has no verdict in the examples, so its signature line reads "not checked yet".

Question for Léon:
- `approval_url` in the examples is `http://localhost:8002/#/approvals/apr_...` (the harness's port). The page understands `#/approvals/<id>`, but it is served on port 8003. Will the harness serve `surface/static/`, or should the link point to 8003?

## What Junction asks us to hand in

- Deadline: **Sunday 15/11/2026 at 10:00** (strict auto-close, no late submissions; must switch project status from **DRAFT** to **FINAL** before 10:00 — FINAL projects can still be edited until 10:00).
- Video (length, format): **2-minute video pitch — strictly NOT A SECOND LONGER THAN 2:00** (aim for ~1:50–1:55). Uploaded to YouTube or Vimeo and set to public ("available for everyone").
- Text (length): Project name, punchline, description, Challenge selected, Technologies used (no character limit stated on the summary screen, check field counters when filling DRAFT).
- Slides: **Pitch deck (PDF)** required.
- Repo link or access: Demo link + Source code link + Source code publicity choice + Credit preference.
- Contact fields required: Team members' phone numbers + Discord username.
- Pitch length and format: Top teams are contacted before the Closing Ceremony for live pitching; the primary judged pitch for everyone is the **strictly <= 2:00 video + PDF deck** (so our 4 demo acts must fit comfortably inside ~90 seconds of the 2-minute video!).

## C1: Claude Desktop as the agent

- MCP server (`agent_mcp/server.py`) connects in **380 ms** and answers `tools/list` in **3 ms** (verified in `~/Library/Logs/Claude/mcp-server-valio-aimo.log` and 9/9 stdio integration checks).
- Claude Desktop chat was not usable on Colette's laptop/account, so prompts were tested in Antigravity with the same MCP server:

| Round | Time from the sentence to the final answer |
|---|---|
| 1 | ~2 min (120 s) |
| 2 | > 6 min (no answer / hung) |
| 3 | Skipped (already failed the < 30 s gate) |

Does Claude ask questions before acting?
- Not testable on Claude Desktop on Colette's machine; Antigravity IDE agent is way too slow (> 2 min, hung on round 2, partly due to full repo + 83 MB data tabs in IDE context).
- Recommendation: either test `feat/agent-mcp-mock` for 2 minutes on Adrien/Léon's Claude Desktop, or switch to the planned fallback (`scenarios/run.py` scripted runner), which also fits the strict **<= 2:00** submission video rule.

Does it order on its own?
- Automated MCP stdio flow (`search_products` -> `request_quote` -> `authorize_checkout`) returns `status: "ordered"`, `decision: "auto"`, `signed_by: "agent"`, `order_id: "ord_4b9d2a10"` for 1,000 L.

What does it say when an approval is pending?
- For 2,000 L (`chk_act2_demo`), `authorize_checkout` returns `status: "pending_approval"`, `deadline: "2026-11-15T17:00:00+02:00"`, and `approval_url: "http://localhost:8002/#/approvals/apr_7c1e0b52"`.
