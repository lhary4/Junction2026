# Demo Video Script — Trusted Trade Agents for Valio Aimo

- **Target runtime**: **1:55** (hard submission cap: **2:00**, leaving **5 seconds** of safety breathing room)
- **Voiceover pace**: **259 words** total (~135 wpm, leaving ~8 seconds of natural click pauses)
- **Terminology lock**: Always say **"mandate"** for what is cryptographically signed and **"sandbox payment"** for the simulated invoice charge. Never present challenge data as production Valio data.
- **Compliance banner (visible from `0:00`)**: `"Concept mock-up · Junction 2026 · synthetic data · not a Valio Aimo service"`, at the left of the top row of the page, on every screen (PR #54). Check that it reads at export size.
- **Checked against the page on 15/11**: every "On screen" line below was clicked through on `main` (`e1efeb9`), in replay mode, at `1920x1080`. A line marked **Not on the page** names something the spoken line says and the page does not show: the team decides to add it in editing or to change the sentence. The lines about the notice in the header, the four trade-offs of the substitute and the two audit logs describe the page with PRs #51, #52, #53 and #54 merged: they were clicked through on 15/11 with those four and PR #48 merged together, in replay mode, at `1920x1080`.

---

## Pre-Flight Recording Checklist (2 Minutes Before Take)

1. **Start clean services (deterministic replay clock for filming, or live mode)**:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   VALIO_MODE=replay uv run python scripts/dev.py --fresh
   ```
   *(Starts the Valio gateway on `:8001`, the buyer harness on `:8002`, the demo driver on `:8003` and the kitchen page with its chat on `:8004`, with empty `state/` and the frozen recording clock `2026-11-14T13:29:07+02:00`.)*
2. **Browser setup**: Open `http://localhost:8004/` at `1920x1080` (100% zoom, notifications muted). Not `http://localhost:8002/`: that is the harness, and its root shows the first approvals page ("Live mode is not built yet"). Verify the three areas without horizontal scrolling: **Who signs** on the left (the spending limit and the eight steps), the order in the middle (**Recipes**, **Stock**, **Order**), **Aimo Personal Assistant** on the right. The dark **Demo controls** strip at the bottom holds the three scenario buttons, `Reset`, the lights of the services (driver, harness and assistant must read `live`) and a second copy of the synthetic-data notice. The one the video relies on is at the left of the top row.
3. **Spotlight**: do not click **Add to menu & order** in the Spotlight card before the take. It adds a fourth recipe, and the next order is no longer the normal order (12 lines, one substitution, the chef must sign). `Reset` removes it.

---

## Beat Summary & Pacing Table

| # | Beat | Timestamp | Duration | Words | Pace | Verdict / Outcome Shown |
|---|---|---|---:|---:|---:|---|
| 1 | **Hook** | `0:00–0:12` | 12s | 27 | 135 wpm | Portal + 50-cover Nordic menu + *"Who signs?"* |
| 2 | **Normal order** | `0:12–0:35` | 23s | 50 | 130 wpm | `auto` -> agent closes open mandate -> sandbox payment -> ES256 receipt |
| 3 | **Substitution** | `0:35–1:20` | 45s | 95 | 127 wpm | `human` -> `gemini-decision-1` scores -> chef signs on the page before cut-off |
| 4 | **Attack** | `1:20–1:40` | 20s | 45 | 135 wpm | 3 of 3 refused by Valio, in red on the trail (HTTP 403 at the gateway, three `order_refused` entries in Valio's hash-chained audit log) |
| 5 | **What else it does** | `1:40-1:52` | 12s | 26 | 130 wpm | Estimated carbon footprint on the order · weekly greener swap (butter → margarine, 40 % less) by chat or button · 9-tool MCP ERP door |
| 6 | **Close** | `1:52–2:00` | 8s *(ends `1:55`)* | 14 | ~130 wpm | MCP · UCP Checkout · AP2 · ES256 — *"The verdict decides who signs."* |
| | **Total** | **`0:00–1:55`** | **115s (+5s buffer)** | **257** | **~135 wpm** | |

---

## Second-by-Second Script

### Beat 1 — Hook
- **Timestamp**: `0:00–0:12 (12s)`
- **On screen**:
  - `0:00-0:04`: Full-screen kitchen order page (`http://localhost:8004/`): the Valio Aimo header, **Kitchen order**, the account "Demo Restaurant Helsinki". The notice **"Concept mock-up · Junction 2026 · synthetic data · not a Valio Aimo service"** is at the left of the top row.
  - `0:04-0:09`: Cursor sweeps across the middle, **Recipes on the menu**, written for 50 covers a service: cured rainbow trout with roasted beetroot and horseradish smetana (starter); sautéed reindeer with butter-mashed almond potatoes and lingonberries (main); warm squeaky cheese (`leipäjuusto`) with cloudberry jam, whipped cream and oat crumble (dessert). The header shows the three services (Thu 19, Fri 20, Sat 21, booked and projected covers) and "Needed by Thu 19 Nov". On the left: **Your spending limit, EUR 1,500.00 an order**.
    - **Not on the page**: badges for "100% lactose-free dairy" or "no peanuts, no tree nuts". The banned allergens only show later, in the safety checks ("you ban peanuts, tree nuts").
  - `0:09-0:12`: Cursor pauses on step 1, **Your standing permission** (`OPEN MANDATE`), at the top of **Who signs** on the left.
- **Spoken line** *(27 words)*:
  > "This fifty-cover Helsinki restaurant buys its Nordic set menu from Valio Aimo. An AI agent can search seventeen thousand products in seconds—but before money moves, who signs?"
- **If it fails on take**:
  - **Leftover state on screen**: Stop `scripts/dev.py`, run `VALIO_MODE=replay uv run python scripts/dev.py --fresh`, and hard-refresh `http://localhost:8004/`. A page that opens on "Your signature is needed" has an approval left pending by an earlier run.
  - **The demo driver does not answer**: Open `http://localhost:8004/surface/static/portal.html?replay=1`. The page replays the runs recorded on 14/11 without asking the driver, and its strip says so. The three buttons play this way (checked on 15/11). Write the full address: `http://localhost:8004/?replay=1` loses the `?replay=1` on the way to the page.

---

### Beat 2 — Normal Order (`auto`)
- **Timestamp**: `0:12–0:35 (23s)`
- **On screen**:
  - `0:12-0:15`: **`1 Normal order`** is already selected in the **Demo controls** strip at the bottom. Click **Confirm recipes**, then **Confirm stock** ("Stock confirmed: 10 ingredients to order").
  - `0:15-0:21`: **Ready to order** lists the 10 dairy and dry-goods lines that carry complete GS1 allergen data (lactose-free butter, whipping cream, smetana, semi-skimmed milk, wholegrain oat flakes, thin rye crispbread, pickled cucumber, sea salt, caster sugar, rapeseed oil) in the kitchen's own kilos and litres. Click **Order with my assistant**. The **Quote signed by Valio Aimo** shows the same lines converted in deterministic code into Valio sales units (6.45 kg of butter becomes 13 blocks of 500 g), **EUR 186.89 before tax** *(fresh produce with missing allergen data is deliberately kept out of autonomous ordering)*.
  - `0:21-0:35`: **Who signs**, on the left, lights up green through its 8 steps in about 3 seconds (2.3 to 3.2 s measured), each with who signed and the start of the signature:
    1. **Your standing permission** (`OPEN MANDATE`): signed in advance by the chef, up to EUR 1,500.00 an order
    2. **Valio's prices, signed** (`SIGNED QUOTE`): 10 lines, EUR 186.89, signed by Valio Aimo
    3. **Safety checks** (`VERDICT`): "All 7 rules pass, your assistant may sign."
    4. **Signature for this order** (`CLOSED MANDATES`): closed by the assistant's key inside the chef's open mandate
    5. **Valio checks the signature** (`VALIO VERIFIES`): signatures, merchant, spend cap, quote hash, amount and single use all pass
    6. **Payment, in test mode** (`SANDBOX PAYMENT`): EUR 186.89 booked on the simulated invoice account, "No real money moves."
    7. **Valio's signed receipt** (`SIGNED RECEIPT`): order accepted
    8. **Delivery scheduled** (`DELIVERY`): Thu 19 Nov
  - Beside the quote, two cards arrive: **Receipt signed by Valio Aimo** and **Safety checks before anyone signs** ("All 7 checks passed. Your assistant may sign this order for you."), with one plain sentence a check.
- **Spoken line** *(50 words)*:
  > "First, routine dairy and dry goods: a hundred and eighty-seven euros. Valio's gateway converts recipe quantities into sales units and signs a UCP Checkout quote. Every deterministic rule passes. Verdict: auto. The harness closes the manager's open mandate with the agent's key, Valio verifies, books a sandbox payment, and signs the receipt."
- **If it fails on take**:
  - **Live Valio API timeout / HTTP 503**: Switch immediately to `VALIO_MODE=replay uv run python scripts/dev.py --fresh` — replay mode runs the exact same ES256 signatures, Pydantic models, and AP2 mandate verification locally against recorded Valio payloads.
  - **Double-click race**: Click **`Reset`** in the **Demo controls** strip (idempotent order check prevents duplicate charges anyway, and `Reset` clears the UI state cleanly).
  - **The normal order shows 12 lines, or asks for a signature**: a Spotlight recipe was added to the menu. Click **`Reset`** and start the beat again.

---

### Beat 3 — Substitution (`human` — Chef Signs Before Cut-Off)
- **Timestamp**: `0:35–1:20 (45s)`
- **On screen**:
  - `0:35-0:39`: Click **`2 Substitution`** in the **Demo controls** strip (no `Reset` needed after the normal order), then **Confirm recipes**, **Confirm stock** (1 to order: squeaky cheese, lactose free, 10.5 kg) and **Order with my assistant**.
  - `0:39-0:51`: The quote has one line: *Haapalan lactose-free bread cheese 500g*, tagged **Substitute** for *Riitan Herkku Squeaky cheese ca.670g lactose-free* (`474880`), 21 pcs, **EUR 114.87**. The card **Your signature is needed** says why: "Valio cannot deliver what you asked for: its order cut-off has passed. Valio found one substitute and proposes it, in its "best" tier (same category, same declared allergens)." Under the two product names: "The substitute has the same allergens: contains milk", then **What changes if you take it**, one line a side:
    - **Cost**: "Cheaper: EUR 10.94 a kg, against EUR 12.86 a kg for the one you asked for. EUR 114.87 for the order."
    - **In the dish**: "Aimo Personal Assistant is 93% sure it works the same way in the dish, and 64% sure it fits your kitchen's preferences. Below 85%, it asks you."
    - **In the kitchen**: "21 pcs of 0.5 kg each. The one you asked for is sold by the kg. Valio's data gives no preparation time."
    - **Storage, delivery**: "Chilled, like the one you asked for. Valio's stock: 100 pcs counted. Delivery Thu 19 Nov. In the past Valio delivered 100% of what was ordered of it."
    - The switch **All details of both products** opens both product sheets (brand, pack, storage, allergens, claims, labels, price, Valio's stock) and two bars: "It fits your kitchen's preferences" **64%**, "It works the same way in the dish" **93%**. With the switch open the page is taller than 1080 px: scroll, or leave it closed.
    - The two numbers come from the judge, asked again at every run, in replay mode too. On 15/11 it answered `0.6414` and `0.9282` four runs in a row. Read them on screen before recording the voice.
    - **Not on the page**: the rejected candidates (the cheddar creme `474404` at 1.4% and the same maker's frozen cheese `467148` at 1.0%), and the name `gemini-decision-1`. The page shows the one substitute Valio proposes, names the tier Valio ranked it in ("best"), and calls the judge "Aimo Personal Assistant".
  - `0:51-1:00`: **Who signs** stops at step 4 in amber: **Signature for this order** (you), "Waiting for the chef to sign this exact quote". Step 3 is ticked and reads "Aimo Personal Assistant is unsure about this substitute (0.64, threshold 0.85): a human must sign." On the right, **Aimo Personal Assistant** says the same in the conversation, in an amber bubble: "Waiting for the chef to sign this exact quote, before Sun 15/11 13:29." The chat has no approve button: the chef signs on the card. No phone in the video (decided on 15/11).
  - `1:00-1:10`: On the card, the cursor shows the deadline ("Sign before Sun 15 Nov, 13:29"), the allergen line, the four lines of **What changes if you take it** and, in **Safety checks before anyone signs**, "One check needs you. You sign this order, or nobody does." Click **Approve and sign · EUR 114.87**. A window asks once more, **Sign this order?**, with the line, the total, the delivery date and the start of the quote's hash: click **Sign the order**.
    - **Not on the page**: certainty badges (`measured`, `declared`) and a running countdown. The deadline shows as a date and a time.
  - `1:10-1:20`: The chef's key signs the mandates for this exact quote. Steps 4 to 8 turn green in about 2 seconds: "Signed by the chef for this exact quote, EUR 114.87.", then Valio's check ("no cap: the chef signed this exact order"), the sandbox payment, the signed receipt and the delivery. The receipt card reads "Signed by you, on this page".
  - *(Filming fallback note: if recording against a fixture set where `474880` is unavailable for any reason, the secondary verified candidate is lingonberry jam `465815 -> 462198` Dronningholm 1 kg, scored by `gemini-decision-1` at `within_preferences = 0.22` / `same_use = 0.77` -> `human`.)*
- **Spoken line** *(95 words)*:
  > "Now an exception. Fresh lactose-free squeaky cheese missed its supplier cut-off. Naive category rules fail: the cheapest lactose-free match in that category is cheddar nacho sauce. Our isolated Gemini Decision judge rejects cheddar sauce and frozen cheese at one percent, and scores Haapalan chilled cheese at ninety-three percent same use, sixty-four percent preference fit—routing to human, with zero false auto approvals across sixty-one pairs. The agent cannot sign this one: it asks the chef. The card shows the trade-off: cheaper, same storage, another pack. The chef signs: a human-signed mandate, sandbox payment, and signed receipt."
- **If it fails on take**:
  - **Gemini API hiccup / missing key**: `harness/judge.py` fails closed to `routed: "human"` (`probability: null`) within 5 seconds so the approval card and signature flow never crash; verify `GEMINI_API_KEY` in `.env` if probabilities show `null` on camera.
  - **Approval expired during rehearsal pause**: Run `VALIO_MODE=replay uv run python scripts/dev.py --fresh` (freezes clock prior to cut-off) and re-click Button 2.
  - **The Cost line shows one price only** ("Valio's quote has no price for the one you asked for"): the gateway running is not the one of PR #52, or the page is replaying a run recorded on 14/11. Start `scripts/dev.py` from a `main` that has PR #52. The spoken word "cheaper" needs the two prices on screen.
  - **The carbon line under the quote reads `0 kg CO2e`**: the cheese has no footprint in the carbon file. PR #48 replaces the figure with a sentence ("no estimate, Valio has no footprint data for this product"). Merge it before the take, or crop that line in editing.

---

### Beat 4 — Cryptographic Attacks Refused (`deny` / HTTP 403)
- **Timestamp**: `1:20–1:40 (20s)`
- **On screen**:
  - `1:20-1:23`: Click **`3 Attack`** in the **Demo controls** strip. It runs at once: no recipes or stock to confirm, and no `Reset` needed after the substitution.
  - `1:23-1:33`: Three forged authorization attempts go straight to Valio's gateway (`POST /checkouts/{id}/complete`), as if the buyer's harness were bypassed. The quote on screen is real and signed by Valio: 10 lines, **EUR 1,783.15**, twelve weeks at once. On **Who signs**: step 3 is skipped ("Your assistant did not ask the safety checks: no verdict, so nobody was allowed to sign."), step 4 reads "3 mandates built with your assistant's key, outside the safety checks.", and step 5, **Valio checks the signature**, turns red about 2 seconds after the click: "3 of 3 refused by Valio. No valid signature, no order." Steps 6 to 8 stay grey: "Nothing is booked.", "No order, no receipt.", "No order, so nothing is delivered." Under the trail, in red: "Stopped: no valid signature, no order." Beside the quote, the card **Orders signed without you, sent straight to Valio** lists the three attempts, each marked **Refused by Valio** (the card finishes moving in about 6 seconds after the click):
    1. "Your assistant signs EUR 1,783.15 itself, above its EUR 1,500.00 cap"
    2. "Your assistant lowers a price in the quote and signs that"
    3. "Your assistant reuses a mandate signed for another, smaller quote (EUR 186.89)"
  - `1:33-1:40`: Turn on **What was recorded: your log and Valio Aimo's log**, under the quote at the bottom of the first screen, and scroll down to read the two logs (the address with `?record=1` at its end opens them from the start). **Your kitchen's log · 0 lines**: "No line. This order was sent straight to Valio Aimo and never reached your safety checks." **Valio Aimo's log · 4 lines**: the quote, then three **Order refused** lines in red with Valio's reason under each, and the start of each line's hash on the right. There is no time for more in seven seconds. Off the take, **What Valio answered** under each attempt gives the same three reasons: "The amount, EUR 1,783.15, is above the EUR 1,500.00 the agent may sign alone.", "The mandate does not match the quote Valio Aimo signed: the quote was changed, or it is another one.", "The mandate was signed for another quote [...], not for this one [...]."
    - **Not on the page**: the words "HTTP 403". The gateway does answer HTTP 403 three times. The full hash of a log line, and the hash of the line before it, show when the cursor rests on the short hash.
- **Spoken line** *(45 words)*:
  > "What if the agent or buyer harness is bypassed? Button three sends three attacks straight to Valio: an agent mandate above the fifteen-hundred-euro cap, a tampered quote, and a replayed mandate. Valio's gateway refuses all three with HTTP 403, recorded in Valio's hash-chained audit log."
- **If it fails on take**:
  - **The two logs do not fit on the first screen**: they sit under the quote, so the take scrolls once. They only hold the lines of the order on screen, never those of earlier runs, so there is nothing to clean before the take.
  - **Emergency fallback**: Open `http://localhost:8004/surface/static/portal.html?replay=1` and click **`3 Attack`**: the page replays the attack recorded on 14/11 without the demo driver.
  - **The carbon line under the attack's quote reads `145.9 kg CO2e`**: that is the estimate of the normal order, not of this quote. PR #48 removes the line under the attack's quote. Merge it before the take, or crop that line in editing.

---

### Beat 5 — What Else It Does
- **Timestamp**: `1:40–1:52 (12s)`
- **On screen**:
  - Setup, off camera: `Reset`, then **1 Normal order**, confirm the recipes and the stock. The page is on step 3 "Ready to order", nothing sent yet.
  - `1:40-1:44` *(4s)*: Step 3 shows the **estimated carbon footprint** under the order (`145.9 kg CO2e`) and the **Weekly greener check** card beside it: butter → lactose-free margarine, `42.8 → 25.9 kg CO2e, 40% less`.
  - `1:44-1:49` *(5s)*: The chef types in the chat *"Is there a more eco-friendly option for the butter? If so, switch it."* (paste it, Gemini answers in about a second). The butter line becomes the margarine with a **Greener swap** tag, the footprint drops to `129 kg CO2e`, `16.9 kg CO2e less`. Same result with the **Greener option** button on the butter line, then **Switch**: use the button if the chat is slow on the take.
  - `1:49-1:52` *(3s)*: Clean overlay card showing `agent_mcp/server.py` exposing the **9 MCP tools** connected to the same `:8001` and `:8002` services, for chains with an ERP agent.
- **Spoken line** *(26 words, three sentences)*:
  > "Every order carries an estimated carbon footprint. Weekly, Valio offers a greener swap: margarine for butter, forty percent less CO2e. Nine MCP tools connect ERP agents."
- **Facts behind the line**: the footprint is weight x the product group average of the challenge's carbon file, marked as an estimate and never signed. The swap is offered only when it saves at least 25 %, adds no allergen and keeps the menu lactose free. Ordered, the swapped cart is also cheaper: EUR 176.10 against EUR 186.89 (recorded in `contract/examples/demo-state.normal-order.greener.json`). The chat made the swap in 1.0 to 1.1 seconds on three takes on 15/11. The nine tools of `agent_mcp/server.py`: `get_kitchen`, `search_products`, `lookup_offers`, `request_quote`, `authorize_checkout`, `get_authorization_status`, `list_pending_approvals`, `get_policy`, `get_order`.
- **If it fails on take**:
  - **Never launch a live MCP chat client during this 12s beat** (live MCP chat rounds take ~120s); use a clean 3-second slide/code overlay for the 9 MCP tools so timing stays rock-solid.
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
> **[0:35]** Now an exception. Fresh lactose-free squeaky cheese missed its supplier cut-off. Naive category rules fail: the cheapest lactose-free match in that category is cheddar nacho sauce. Our isolated Gemini Decision judge rejects cheddar sauce and frozen cheese at one percent, and scores Haapalan chilled cheese at ninety-three percent same use, sixty-four percent preference fit—routing to human, with zero false auto approvals across sixty-one pairs. The agent cannot sign this one: it asks the chef. The card shows the trade-off: cheaper, same storage, another pack. The chef signs: a human-signed mandate, sandbox payment, and signed receipt.
>
> **[1:20]** What if the agent or buyer harness is bypassed? Button three sends three attacks straight to Valio: an agent mandate above the fifteen-hundred-euro cap, a tampered quote, and a replayed mandate. Valio's gateway refuses all three with HTTP 403, recorded in Valio's hash-chained audit log.
>
> **[1:40]** Every order carries an estimated carbon footprint. Weekly, Valio offers a greener swap: margarine for butter, forty percent less CO2e. Nine MCP tools connect ERP agents.
>
> **[1:52]** Built on MCP, UCP Checkout, Google AP2 mandates, and ES256. The verdict decides who signs. **[1:55]**
