# Colette's notes

Results, numbers and open questions for the others. Newest first.

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
