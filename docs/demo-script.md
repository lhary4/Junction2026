# Demo Video Script — Trusted Trade Agents for Valio Aimo

- **Target runtime**: **1:55** (hard submission cap: **2:00**, leaving **5 seconds** of safety breathing room)
- **Voiceover pace**: **259 words** total (~135 wpm, leaving ~8 seconds of natural click and notification pauses)
- **Terminology lock**: Always say **"mandate"** for what is cryptographically signed and **"sandbox payment"** for the simulated invoice charge. Never present challenge data as production Valio data.
- **Compliance banner (visible from `0:00`)**: `"Concept mock-up, Junction 2026, synthetic data"`

---

## Pre-Flight Recording Checklist (2 Minutes Before Take)

1. **Start clean services (deterministic replay clock for filming, or live mode)**:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   VALIO_MODE=replay uv run python scripts/dev.py --fresh
   ```
   *(Starts Valio gateway on `:8001`, buyer harness + portal on `:8002`, and demo driver on `:8003` with empty `state/` and frozen recording clock `2026-11-14T13:29:15+02:00`.)*
2. **Browser setup**: Open `http://localhost:8002/` at `1920x1080` (100% zoom, notifications muted except Telegram PiP/phone). Verify the synthetic-data banner at the top and all three columns visible without horizontal scrolling (`SCENARIOS` | `KITCHEN` | `AP2 TRAIL`).
3. **Phone / Telegram check**: Confirm `.env` has `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` set so Beat 3 triggers the real Telegram push notification to the chef's phone.

---

## Beat Summary & Pacing Table

| # | Beat | Timestamp | Duration | Words | Pace | Verdict / Outcome Shown |
|---|---|---|---:|---:|---:|---|
| 1 | **Hook** | `0:00–0:12` | 12s | 27 | 135 wpm | Portal + 50-cover Nordic menu + *"Who signs?"* |
| 2 | **Normal order** | `0:12–0:35` | 23s | 50 | 130 wpm | `auto` -> agent closes open mandate -> sandbox payment -> ES256 receipt |
| 3 | **Substitution** | `0:35–1:20` | 45s | 95 | 127 wpm | `human` -> `gemini-decision-1` scores -> Telegram link -> chef signs before cut-off |
| 4 | **Attack** | `1:20–1:40` | 20s | 45 | 135 wpm | 3x HTTP 403 gateway refusals + dual SHA-256 hash-chained audit logs |
| 5 | **What else it does** | `1:40-1:52` | 12s | 26 | 130 wpm | Estimated carbon footprint on the order · weekly greener swap (butter → margarine, 40 % less) by chat or button · 5-tool MCP ERP door |
| 6 | **Close** | `1:52–2:00` | 8s *(ends `1:55`)* | 14 | ~130 wpm | MCP · UCP Checkout · AP2 · ES256 — *"The verdict decides who signs."* |
| | **Total** | **`0:00–1:55`** | **115s (+5s buffer)** | **257** | **~135 wpm** | |

---

## Second-by-Second Script

### Beat 1 — Hook
- **Timestamp**: `0:00–0:12 (12s)`
- **On screen**:
  - `0:00–0:04`: Full-screen Valio Aimo customer portal (`http://localhost:8002/`). Top banner clearly readable: **"Concept mock-up, Junction 2026, synthetic data"**.
  - `0:04–0:09`: Cursor sweeps across the center **`KITCHEN`** panel showing the 50-cover Helsinki restaurant's Nordic November set menu across 3 dinner services (Thu 19, Fri 20, Sat 21 Nov 2026): cured rainbow trout with horseradish smetana starter; sautéed reindeer with mashed almond potatoes and lingonberries main; warm squeaky cheese (`leipäjuusto`) with cloudberry jam, whipped cream, and oat crumble dessert — plus the kitchen policy badges (**100% lactose-free dairy**, **no peanuts `AP` / no tree nuts `AN`**, **EUR 1,500 autonomous cap**).
  - `0:09–0:12`: Cursor pauses on Step 1 (**`1 Open mandate`**) at the top of the right-hand **`AP2 TRAIL`**.
- **Spoken line** *(27 words)*:
  > "This fifty-cover Helsinki restaurant buys its Nordic set menu from Valio Aimo. An AI agent can search seventeen thousand products in seconds—but before money moves, who signs?"
- **If it fails on take**:
  - **Leftover state on screen**: Stop `scripts/dev.py`, run `VALIO_MODE=replay uv run python scripts/dev.py --fresh`, and hard-refresh `http://localhost:8002/`.
  - **Local backend port conflict**: Open `http://localhost:8002/?mock=1` for instant static fixture rendering while restarting services.

---

### Beat 2 — Normal Order (`auto`)
- **Timestamp**: `0:12–0:35 (23s)`
- **On screen**:
  - `0:12–0:15`: Click **`1 Normal order`** in the left **`SCENARIOS`** panel.
  - `0:15–0:21`: Center **`KITCHEN`** panel populates the 10 dairy and dry-goods lines that carry complete GS1 allergen data (lactose-free butter, whipping cream, smetana, semi-skimmed milk, wholegrain oat flakes, thin rye crispbread, pickled cucumber, sea salt, caster sugar, rapeseed oil), converted in deterministic code from recipe kilos and litres into Valio sales units — **~EUR 187 excl. VAT** *(fresh produce with missing allergen data is deliberately kept out of autonomous ordering)*.
  - `0:21–0:35`: Right **`AP2 TRAIL`** lights up green through all 7 steps in real time (`1–2 ms` per ES256 check):
    1. `1 Open mandate` (pre-signed once by restaurant manager, cap EUR 1,500)
    2. `2 Signed quote` (Valio ES256 UCP `Checkout` JWT + `checkout_hash`)
    3. `3 Verdict` -> **`auto`** (all 9 deterministic guardrail rules pass)
    4. `4 Closed mandates` (harness closes open mandate with the agent's key)
    5. `5 Valio verifies` (ES256 signature + EUR 1,500 spend cap + `checkout_hash` + single use)
    6. `6 Sandbox payment` (simulated wholesale invoice account booked)
    7. `7 Signed receipt` (Valio ES256 receipt verified by harness)
- **Spoken line** *(50 words)*:
  > "First, routine dairy and dry goods: a hundred and eighty-seven euros. Valio's gateway converts recipe quantities into sales units and signs a UCP Checkout quote. Every deterministic rule passes. Verdict: auto. The harness closes the manager's open mandate with the agent's key, Valio verifies, books a sandbox payment, and signs the receipt."
- **If it fails on take**:
  - **Live Valio API timeout / HTTP 503**: Switch immediately to `VALIO_MODE=replay uv run python scripts/dev.py --fresh` — replay mode runs the exact same ES256 signatures, Pydantic models, and AP2 mandate verification locally against recorded Valio payloads.
  - **Double-click race**: Click **`Reset`** in **`SCENARIOS`** (idempotent order check prevents duplicate charges anyway, and `Reset` clears the UI state cleanly).

---

### Beat 3 — Substitution (`human` — Chef Signs Before Cut-Off)
- **Timestamp**: `0:35–1:20 (45s)`
- **On screen**:
  - `0:35–0:39`: Click **`2 Substitution`** in **`SCENARIOS`**.
  - `0:39–0:51`: Center **`KITCHEN`** card flags dessert squeaky cheese `474880` (*Riitan Herkku*, fresh, lactose-free, 13.4 kg) as **past supplier cut-off**. Cursor highlights the ranked substitutes and `gemini-decision-1` evaluation (`~210 ms` median latency, reading only ES256-signed structured claims — never marketing copy or agent prompts):
    - *Why naive category/allergen rules fail*: cheapest lactose-free item in GS1 category `10640` is `474404` (*Nacho&Taco Cheddar cheese creme*) -> rejected at **1.4%** (`0.0135`, below `0.15` floor); same maker's **frozen** squeaky cheese `467148` -> rejected at **1.0%** (`0.0100`, *"NEVER ACCEPT: Frozen instead of fresh"*).
    - Chosen top substitute `475072` (*Haapalan lactose-free squeaky cheese 500 g*, chilled, Finnish Blue Swan): **`same_use = 91%` (`0.907`)**, **`within_preferences = 65%` (`0.648`)** — below the `0.85` auto threshold because brand and 500 g piece format differ -> **Verdict: `human`**.
  - `0:51–1:00`: **`AP2 TRAIL`** halts in amber at Step 3 (**`3 Verdict: human`**). Picture-in-picture phone screen (or phone beside monitor) buzzes with the **Telegram notification**: 1-sentence reason, order total, supplier cut-off countdown, and link to the portal — **no approve button in chat**.
  - `1:00–1:10`: On the portal's non-agentic approval card, cursor highlights the signed provenance & certainty badges (`measured` API price/cut-off, `declared` GS1 Synkka allergens/origin, one-use `checkout_hash` lock, live cut-off countdown) and clicks **`Approve and sign`**.
  - `1:10–1:20`: Manager's key signs closed AP2 mandates directly (`close_as_human`). Steps `4 Closed mandates` -> `5 Valio verifies` -> `6 Sandbox payment` -> `7 Signed receipt` turn green.
  - *(Filming fallback note: if recording against a fixture set where `474880` is unavailable for any reason, the secondary verified candidate is lingonberry jam `465815 -> 462198` Dronningholm 1 kg, scored by `gemini-decision-1` at `within_preferences = 0.22` / `same_use = 0.77` -> `human`.)*
- **Spoken line** *(95 words)*:
  > "Now an exception. Fresh lactose-free squeaky cheese missed its supplier cut-off. Naive category rules fail: the cheapest lactose-free match in that category is cheddar nacho sauce. Our isolated Gemini Decision judge rejects cheddar sauce and frozen cheese at one percent, and scores Haapalan chilled cheese at ninety-one percent same use, sixty-five percent preference fit—routing to human, with zero false auto approvals across sixty-one pairs. Telegram alerts the chef's phone with a portal link only. Checking Valio's signed certainty claims before cut-off, the chef clicks Approve and sign: a human-signed mandate, sandbox payment, and signed receipt."
- **If it fails on take**:
  - **Gemini API hiccup / missing key**: `harness/judge.py` fails closed to `routed: "human"` (`probability: null`) within 5 seconds so the approval card and signature flow never crash; verify `GEMINI_API_KEY` in `.env` if probabilities show `null` on camera.
  - **Telegram push delayed >2 seconds on venue Wi-Fi**: `harness/notify.py` enforces a hard 2-second timeout and swallows errors so the portal approval card renders immediately; drop the phone PiP overlay in editing or show the pre-received Telegram message on the unlocked phone screen.
  - **Approval expired during rehearsal pause**: Run `VALIO_MODE=replay uv run python scripts/dev.py --fresh` (freezes clock prior to cut-off) and re-click Button 2.

---

### Beat 4 — Cryptographic Attacks Refused (`deny` / HTTP 403)
- **Timestamp**: `1:20–1:40 (20s)`
- **On screen**:
  - `1:20–1:23`: Click **`3 Attack`** in **`SCENARIOS`**.
  - `1:23–1:33`: Three forged/invalid authorization attempts fire straight at Valio's gateway (`POST /checkouts/{id}/complete`), simulating a bypassed or compromised buyer harness. **`AP2 TRAIL`** lights up Step 5 (**`5 Valio verifies`**) in **crimson (`HTTP 403`)** for all three:
    1. **Over-cap agent mandate**: agent-signed closed mandate above the manager's signed **EUR 1,500** `AmountRange` cap -> **Refused (HTTP 403)**.
    2. **Tampered quote**: valid mandate presented against a modified cart (`checkout_hash` mismatch) -> **Refused (HTTP 403)**.
    3. **Replayed mandate**: previously used mandate re-submitted against a second quote (`nonce` / `checkout_hash` mismatch) -> **Refused (HTTP 403)**.
  - `1:33–1:40`: Expand/scroll to the side-by-side **Buyer & Merchant Audit Logs** drawer at the bottom of the portal, showing matching `order_refused` entries and intact `prev_hash -> hash` SHA-256 chains on both `state/buyer/audit.jsonl` and `state/merchant/audit.jsonl`.
- **Spoken line** *(45 words)*:
  > "What if the agent or buyer harness is bypassed? Button three sends three attacks straight to Valio: an agent mandate above the fifteen-hundred-euro cap, a tampered quote, and a replayed mandate. Valio's gateway refuses all three with HTTP 403, anchored in both hash-chained audit logs."
- **If it fails on take**:
  - **Audit log too long to read cleanly on 1080p**: Restart with `scripts/dev.py --fresh` and run Buttons `1 -> 2 -> 3` once in order so the log contains only those crisp, contiguous events.
  - **Static emergency fallback**: Navigate to `http://localhost:8002/?mock=1&state=deny` if a local process was accidentally killed.

---

### Beat 5 — What Else It Does
- **Timestamp**: `1:40–1:52 (12s)`
- **On screen**:
  - Setup, off camera: `Reset`, then **1 Normal order**, confirm the recipes and the stock. The page is on step 3 "Ready to order", nothing sent yet.
  - `1:40-1:44` *(4s)*: Step 3 shows the **estimated carbon footprint** under the order (`145.9 kg CO2e`) and the **Weekly greener check** card beside it: butter → lactose-free margarine, `42.8 → 25.9 kg CO2e, 40% less`.
  - `1:44-1:49` *(5s)*: The chef types in the chat *"Is there a more eco-friendly option for the butter? If so, switch it."* (paste it, Gemini answers in about a second). The butter line becomes the margarine with a **Greener swap** tag, the footprint drops to `129 kg CO2e`, `16.9 kg CO2e less`. Same result with the **Greener option** button on the butter line, then **Switch**: use the button if the chat is slow on the take.
  - `1:49-1:52` *(3s)*: Clean overlay card showing `agent_mcp/server.py` exposing the **5 MCP tools** connected to the same `:8001` and `:8002` services, for chains with an ERP agent.
- **Spoken line** *(26 words, three sentences)*:
  > "Every order carries an estimated carbon footprint. Weekly, Valio offers a greener swap: margarine for butter, forty percent less CO2e. Five MCP tools connect ERP agents."
- **Facts behind the line**: the footprint is weight x the product group average of the challenge's carbon file, marked as an estimate and never signed. The swap is offered only when it saves at least 25 %, adds no allergen and keeps the menu lactose free. Ordered, the swapped cart is also cheaper: EUR 176.10 against EUR 186.89 (recorded in `contract/examples/demo-state.normal-order.greener.json`).
- **If it fails on take**:
  - **Never launch a live MCP chat client during this 12s beat** (live MCP chat rounds take ~120s); use a clean 3-second slide/code overlay for the 5 MCP tools so timing stays rock-solid.
  - **No greener card**: the page needs the demo driver for the footprint, or replays the two estimates recorded in `contract/examples/footprint.*.json`, which only match the normal order's quantities. Reset and do not change a quantity before this beat.

---

### Beat 6 — Close
- **Timestamp**: `1:52–2:00 (8s — voiceover finishes at 1:55, leaving 5s breathing room before 2:00)`
- **On screen**:
  - `1:52–1:55`: Clean closing lockup over the verified portal / architecture banner:
    **`MCP` · `UCP Checkout` · `Google AP2 v0.2 Mandates` · `ES256`**
    Headline: **"The verdict decides who signs."**
    Footer: *"Concept mock-up for Junction 2026 — uses challenge synthetic data."*
  - `1:55–1:58`: Hold silent lockup for 3 seconds and cut cleanly before `1:58` (strictly `<= 2:00`).
- **Spoken line** *(14 words)*:
  > "Built on MCP, UCP Checkout, Google AP2 mandates, and ES256. The verdict decides who signs."
- **If it fails on take**:
  - **Exported video > `1:59.0`**: Trim 1–2 seconds of silent mouse travel in Beats 2 and 4 rather than time-warping voiceover. Verify final duration with `ffprobe` (`<= 118s`) and test playback in a private/incognito browser window before submitting.

---

## Full Uninterrupted Voiceover Read-Through (259 Words — Stopwatch Check: `1:55`)

> **[0:00]** This fifty-cover Helsinki restaurant buys its Nordic set menu from Valio Aimo. An AI agent can search seventeen thousand products in seconds—but before money moves, who signs?
>
> **[0:12]** First, routine dairy and dry goods: a hundred and eighty-seven euros. Valio's gateway converts recipe quantities into sales units and signs a UCP Checkout quote. Every deterministic rule passes. Verdict: auto. The harness closes the manager's open mandate with the agent's key, Valio verifies, books a sandbox payment, and signs the receipt.
>
> **[0:35]** Now an exception. Fresh lactose-free squeaky cheese missed its supplier cut-off. Naive category rules fail: the cheapest lactose-free match in that category is cheddar nacho sauce. Our isolated Gemini Decision judge rejects cheddar sauce and frozen cheese at one percent, and scores Haapalan chilled cheese at ninety-one percent same use, sixty-five percent preference fit—routing to human, with zero false auto approvals across sixty-one pairs. Telegram alerts the chef's phone with a portal link only. Checking Valio's signed certainty claims before cut-off, the chef clicks Approve and sign: a human-signed mandate, sandbox payment, and signed receipt.
>
> **[1:20]** What if the agent or buyer harness is bypassed? Button three sends three attacks straight to Valio: an agent mandate above the fifteen-hundred-euro cap, a tampered quote, and a replayed mandate. Valio's gateway refuses all three with HTTP 403, anchored in both hash-chained audit logs.
>
> **[1:40]** Every order carries an estimated carbon footprint. Weekly, Valio offers a greener swap: margarine for butter, forty percent less CO2e. Five MCP tools connect ERP agents.
>
> **[1:52]** Built on MCP, UCP Checkout, Google AP2 mandates, and ES256. The verdict decides who signs. **[1:55]**
