# Adrien's notes

Results, numbers and open questions for the others. Newest first.

## A11: the menu in the replay recording (14/11, 22:25)

**The three buttons now run in replay mode**, which is the mode the video is recorded in. Before this, a run in replay answered HTTP 502: the menu's products were not among the recorded answers, and the restaurant asks for delivery on 19/11 where the recording was for 16/11.

- **A second recording**, in `contract/fixtures/valio/2026-11-19/`: 47 products, asked on 14/11 at 22:19:22 for delivery on 19/11. The 22 products of the menu, and the 25 other products of the squeaky cheese's category, so that replay ranks the candidates live ranked. `uv run python scripts/record_fixtures.py restaurant` records it again.
- **The first recording is untouched**: 157 products, 13:29:07, the frozen clock. A test holds it.
- **A quote reads the recording of its delivery date, and only that one.** I first put the two recordings together, and nine tests of the milk case failed for a good reason: a Greek cheese "from cow's milk" joined the lactose-free milks, with no price for 16/11, shown as "not found". A search, which has no date, reads both.
- **The clock stays at 13:29 for everything in replay.** Each price keeps the time Valio really gave it: a restaurant quote is issued "at 13:29" with facts "as of 22:19".
- **Size**: the two recordings are 0.90 MB together, the limit is 1 MB.

**Checked.**

| Button, replay mode | In the tests, real gateway and harness | On the page in Chrome, three real processes |
|---|---|---|
| 1 Normal order | `done`, 10 lines, EUR 186.89, `auto` | seven steps lit, "valid until Sun 15 Nov, 13:29" |
| 2 Substitution | `waiting_for_human`, 475072 the only alternative, then `done` once approved | judge 0.64, "Approve and sign", then "Signed by chef, Sat 14 Nov, 13:29" and the sandbox payment |
| 3 Attack | `refused`, EUR 1,783.15, three refusals | "No order was placed", the three sentences in plain words |

**To know before recording the video.**

- Every time on screen is 13:29 in replay: the quote, the signature, the receipt. That is the frozen clock, and the page shows it as it is.
- The judge is not recorded. In replay the harness still asks Gemini, so button 2 needs the network and `GEMINI_API_KEY`. Without them the judge fails closed and the verdict is still `human`. For Colette: in that case the judge's answers carry `probability: null`, and the page turns that into "0%" on the two bars, which reads as a score the judge never gave.
- The quote is valid until Sunday 15/11 at 13:29 in replay (24 hours after the frozen clock), where live says 17:00 (the cut-off).

## Refusals in plain words, and the hash of step 1 (14/11, 22:15)

**What Valio answers when it refuses is now written to be read on the page.** The words of the AP2 SDK are translated in `trust/mandates.py`. Amounts are in euros, a quote is named by its id, and a problem the code does not know is passed on unchanged.

| Before | Now |
|---|---|
| "Amount 178315 exceeds maximum 150000" | "The amount, EUR 1,783.15, is above the EUR 1,500.00 the agent may sign alone." |
| "Checkout checkout_hash mismatch: expected 7byP…, got QY-b…" | "The mandate does not match the quote Valio Aimo signed: the quote was changed, or it is another one." |
| "mandate rejected: ValueError: KB-SD-JWT nonce mismatch: expected 'chk_a', got 'chk_b'" | "The mandate was signed for another quote (chk_b), not for this one (chk_a)." |
| "mandate rejected: InvalidJWSSignature: Verification failed for all signatures…" | "A signature on the mandate does not verify: it was not signed with the expected key." |
| "amount 101000 exceeds what is left on the invoice account (49000 of 150000)" | "EUR 1,010.00 does not fit on the invoice account: EUR 490.00 left of EUR 1,500.00." |

The full list is in `docs/contract.md`, "The order". The harness looks for the word "expired" in Valio's problems to close an approval that came too late: both expiry sentences keep that word.

**Step 1 of the trail has its hash.** Léon added `GET /mandates/open` to the harness (PR #33). The driver shows its `payment_hash` and its `issued_at` on the open mandate step.

**The examples are recorded again**, with the restaurant policy that is now on `main`: the cheese is at 0.64 and 0.93.

For Léon: `docs/demo-script.md` describes the third attack as a "previously used mandate re-submitted against a second quote". What the driver sends is a mandate signed for another quote and never used. The reason is in the A10 section below.

## A10: button 3, the attack (14/11, 22:00)

The driver has its third scenario. It plays an agent whose key leaked: it asks Valio for a quote above the cap, never asks the harness, and sends three bad mandates straight to the gateway. The gateway needed no change: it already refused all three.

| What the agent tries | What Valio answers (live, on the restaurant case) |
|---|---|
| Signs EUR 1,783.15 itself, above its EUR 1,500 cap | "Amount 178315 exceeds maximum 150000" |
| Halves a price in the quote and signs that | "Checkout checkout_hash mismatch", and two more problems |
| Reuses a mandate signed for another, smaller quote (EUR 186.89) | "mandate rejected: ValueError: KB-SD-JWT nonce mismatch" |

- **The quote** is twelve weeks of the normal order at once. Ten weeks is EUR 1,497.65, under the cap, and Valio would rightly accept the agent's mandate for it. So the driver checks the total against the cap first and sends nothing when the quote is under it.
- **The third attack is not a replay of a used mandate.** Sending the same mandate twice on its own quote is not an attack for Valio: it answers the same order again, so that a lost answer never orders twice. What it refuses is a mandate used on another quote, and that is what the driver sends. The smaller quote is asked for and never ordered.
- **Nothing is ordered, nothing is booked**, and the buyer's audit side is empty: the harness never heard of it. Valio's log has one line per refusal.
- **Checked** on the page in Chrome, live, three services: three buttons, "No order was placed", the trail red on "Valio verifies", the three refusals with Valio's sentences.
- **The example file** `demo-state.attack.json` is now recorded by `scripts/record_demo_states.py` like the four others.

To decide for the video: Valio's sentences are the SDK's own words. They are true and they are on screen as they are. If the pitch wants plain words ("the quote was changed after Valio signed it"), the place is `trust/mandates.py`, where the problems are written, not the page.

## A9: the sandbox payment (14/11, 21:55)

Once the mandates verify, the gateway books the order's amount on a simulated invoice account, and the order comes back with its payment. No real money moves, and every sentence about it says "sandbox".

- **The order has two more objects** (`contract/models.py`, both `null` on an order taken before this step): `mandate` is what the payment mandate allowed as Valio read it (the agent's cap, or `null` when the chef signed, the amount, the instrument), `payment` is the booking (`payment_id`, `status: "captured"`, `amount_minor`, `instrument`, `terms`, `sandbox: true`, `captured_at`).
- **The account** is one file per customer in `state/merchant/accounts/`: credit limit, amount used, one line per payment. `dev.py --fresh` empties it. A mandate sent twice books once. A refused order books nothing.
- **One more refusal**: an order that does not fit on the account is refused with HTTP 403, like one above the cap. A mandate that names another customer's account is refused too.
- **The trail**: step 6 is `done`, its sentence starts with "Sandbox payment" and its proof is the payment id. Step 5 now ends with the amount and the cap Valio read in the mandate. One more audit line on Valio's side, `payment_captured`.
- **Checked** on the page in Chrome, live, three services: button 1 lights the seven steps, and the receipt card reads "Sandbox payment: EUR 186.89 booked on invoice-account:demo-restaurant-helsinki. Invoice at 14 days (simulated). No real money moves."

**Two values are made up for the sandbox**, and the code and `TECH-CHOICES.md` say so: the credit limit, EUR 20,000 a customer, and the terms, "Invoice at 14 days (simulated)". Valio's real ones are not in the challenge data. Change them in `merchant/payments.py` if the pitch needs other words.

**Rehearsals.** With EUR 20,000 the account takes about a hundred demo orders. Past that, orders are refused with "exceeds what is left on the invoice account". Start with `uv run python scripts/dev.py --fresh` before a rehearsal or a recording.

**The example files are now recorded by a script**, `scripts/record_demo_states.py`: it runs the driver through the gateway and the harness in live mode and writes what `GET /state` answers. The four files it writes (idle, normal order, substitution pending and approved) carry the payment. Step 1 has no hash in them any more: the first recording took it from inside the harness, which the driver cannot do. The attack file is the older one, until A10.

For Colette: nothing to change on the page. It already reads the payment line from step 6.

## A8: the demo driver, buttons 1 and 2 (14/11, 21:45)

`scenarios/run.py`, port 8003. `uv run python scripts/dev.py` now starts three services, and the page is on `http://localhost:8002/portal.html` (the harness serves it, with `kitchen/` and the example files: checked, HTTP 200 for the three).

**How I checked.** Three real processes on spare ports, `VALIO_MODE=live`, called over HTTP the way the page calls them, with `main`'s policy file (still the hotel's, limit EUR 1,500).

| Button | Time | End | What the state says |
|---|---|---|---|
| 1 Normal order | 1.3 s | `done` | 10 lines, EUR 186.89, verdict `auto`, signed by the agent, receipt |
| 2 Substitution | 1.0 s | `waiting_for_human` | bread cheese 475072 for the squeaky cheese, EUR 114.87, judge 0.52 and 0.89 |
| 2, after `POST /approvals/{id}/decision` on the harness | | `done` | signed by the chef, receipt |

`GET /state` answers in 1 ms when idle and 5 ms after a run. The page waits 1.5 s at most.

With the hotel policy the judge gives 0.52. With Léon's restaurant policy it gave 0.64 (A7). Both end `human`. The number on screen changes when his policy is merged.

**The page, clicked through in Chrome against the three services** (`portal.html` served by the harness, live mode, 21:42). The strip says "driver live, harness live". Button 1: recipes, stock, "Agent order", then the quote table with its ten lines, the trail lit to the receipt, the receipt card. Button 2: the verdict card, the card with both cheeses side by side, "Approve and sign", then "Signed by chef" and the receipt. No error from the page in the console.

Three things show on screen and are not the driver's to fix:

- "Delivery Mon 16 Nov" next to "Needed by Thu 19 Nov". The quote's `delivery_date` is the day Valio can deliver. To decide before the video.
- The account name, top right, is `kitchen.name`: "Demo Restaurant Helsinki", still a placeholder.
- The payment line of the receipt card reads "No payment is booked yet: the sandbox payment is not built." Right for tonight, gone with A9. Do not record the final video before A9.

**For Colette, answers to your questions.**

- Lines sent to `POST /scenarios/{id}/run`: not tonight. A scenario sends its own lines, a test holds them equal to the example files your stock files are built on. Letting the chef change a line means the request no longer matches a recorded run, and the video is recorded in replay.
- Recipes, stock and bookings in `DemoState`: not tonight, they stay your files. The same test keeps the request and your "to order" lines from drifting apart: if I change a scenario's lines, it fails.
- A rejected approval: it works live. The state ends `refused`, step 4 says "The chef rejected this order", steps 5 to 7 are `skipped`. No example file for it yet.
- The harness serves `portal.html` and `kitchen/` as they are: yes.
- In live mode the page shows two buttons, because `state.scenarios` has two. The attack comes with A10.
- If the gateway or the harness is down, a run answers HTTP 502 with a sentence that names the service. Your page shows it under "Something did not answer".

**Two steps of the trail are incomplete in the live state.**

- Step 1 has no hash. For Léon: the harness holds the open mandates and shows them nowhere. One route would do, for example `GET /mandates/open` answering the hash of each token and the time they were issued, or one audit line when they are issued.
- Step 6 is `skipped` and says "No payment is booked yet". It turns `done` with A9.

**What the driver cannot do yet.** Replay mode: the menu's products are not in the recorded answers (A11), so in replay a run answers HTTP 502 with the gateway's sentence. The tests run the flow on the recorded milk instead.

## A7: the live probe, the ranking fix and the ingredient of button 2 (14/11, 21:00)

How I looked: this branch on `main` at `b4f70de`, `VALIO_MODE=live`, delivery on 2026-11-19, the real `merchant.app` behind the real harness, the real Gemini judge, and Léon's restaurant policy taken unchanged from `feat/leon-saturday-evening` (it is not on `main` yet: limit EUR 1,500, thresholds 0.85 and 0.15).

**What the gateway proposed, before and after the fix.** Each need in kilos, as the kitchen states it. No `substitute_with`: this is the gateway's own pick.

| Need | Why it is short | Pick before (cheapest of the tier) | Pick now (closest name, then price) | Judge on the pick now | Verdict |
|---|---|---|---|---|---|
| Squeaky cheese 474880, 10.5 kg | `late_delivery`, cut-off passed on 11/11 | 474404 Nacho&Taco cheddar cheese creme, judge 0.01 | 475072 Haapalan lactose-free bread cheese 500 g, 21 pieces, EUR 114.87 | `within_preferences` 0.64, `same_use` 0.93 | `human`: "The judge is unsure about this substitute (0.64, threshold 0.85): a human must sign." |
| Lingonberry jam 465815, 4.5 kg | `out_of_stock`, no delivery on any date | 475860 Saarioinen apple filling, judge 0.01 | 462198 Dronningholm lingonberry jam 1 kg, 5 tubs, EUR 32.70 | 0.31 and 0.75 | `human`, same sentence with 0.31 |

The scores are the ones Léon measured in L5, to the fourth decimal.

**The pick for button 2: the squeaky cheese.** Both cases end with the chef signing, so the fourth button "Above the limit" is not needed. The cheese is the first choice of the plan, it is the dessert's main ingredient, and its two scores tell a clear story: the same use (0.93), but another maker and 500 g pieces instead of 670 g (0.64). The jam stays the fallback, it works the same way.

**What changed in the gateway (`merchant/quotes.py`).**

- Inside a tier: Valio's listed substitutes first, then the closest product name, then the cheapest. Closest is the number of name words the two names share, pack sizes left out, and a word may sit inside a longer one ("lingonberry" and "jam" both count against "lingonberryjam"). Nothing changes in replay: the 201 tests of `main` pass unchanged.
- A product with no `comparisonPrice` in Valio's price API no longer answers HTTP 500. The caster sugar 460325 is the one on the menu. The quote works the price per kilo out from the price and the size in the product file.

**Button 1, live.** The ten dairy and dry goods lines: EUR 186.89, verdict `auto`, signed by the agent, receipt verified.

**Button 3, live.** Twelve weeks of the normal order at once, EUR 1,783.15, above the EUR 1,500 cap: the three bad mandates are refused. Ten weeks is EUR 1,497.65, under the cap, and the gateway accepted that agent mandate, as it should. The sentences Valio answers are the SDK's own ("KB-SD-JWT nonce mismatch"): true, hard to read in a video.

**The example files are recorded again** (`contract/examples/demo-state.*.json`) from these runs. The cheddar cream is gone from the substitution files.

**Not done, and why.**

- The frozen squeaky cheese 467148 is not offered. Its category, 41770, also holds ice cubes, coffee and banana leaves: declaring it "related" to cheese would offer those too. Léon measured it at 0.01 anyway ("frozen instead of fresh"). So the card shows one substitute, not two.
- The list of alternatives has one entry: one per tier, and only `best` has a candidate.

**Open, for the three of us.**

- For Colette: `state.quote` is the `AimoCheckout` itself (`state.quote.line_items`, `state.quote.aimo`), not a `CheckoutResponse` as your brief says. `linesTable(state.quote)` works as it is. The token is left out on purpose. `request.lines[].dish` is "Starter", "Main", "Dessert" or "Shared".
- For Colette and Léon: `kitchen.name` is still "Demo Restaurant Helsinki", made from the customer id. I found no name for the restaurant in the repo. Tell me the name and I record the files again.
- For Léon, for A8: the driver cannot read the open mandate over HTTP. To show its hash on step 1 of the trail, the harness needs a small route or an audit line when it issues the open mandates.
- The order's `delivery_date` is 16/11, the day Valio can deliver, while the kitchen asked for 19/11. To decide before the video: show the date asked, or say "from 16/11".

## After PR #21 (Léon's harness hardening): what is closed, what is left (14/11, evening)

How I looked: `main` at `12bded1`, replay mode, the real `merchant.app` behind the real harness, and the real Gemini judge this time (about 70 calls, under one cent). `uv run pytest` gives 189 passed. The sections below this one describe the harness before PR #21.

**Closed.**

- Finding 1, the judge that was never asked. The shortcut now opens only for the gateway's own top pick, when the signed quote says the catalog lists it as a replacement and no origin, label or dietary claim is lost. A substitute named by the agent (`substitute_with`) always goes to the judge. Replayed: the coffee milk 463380 for 469363 gets 0.17 and goes to a human. Before, it was ordered on `auto` with no judge call.
- The cards the judge reads. The harness now fetches brand, nutritional claims and pack size from `GET /products/search`. So I drop the two things I had offered: nutritional claims in the quote (a contract PR), and writing `ML` in `free_from` for a product that is lactose free by its claim (a gateway PR). Replayed: 464201 named by the agent gets 0.94 and is ordered on `auto`. It got 0.37 when I measured the judge on the quote's cards this afternoon.
- Finding 2, the deadline. The approval card closes when the quote expires (15/11 at 13:29:07 in replay).
- Finding 3, network failures, and the lock of the audit log. Fixed in the code and covered by Léon's new tests. I did not replay them. My own lock in `merchant/audit.py` is now redundant: I leave it until after the demo, it costs nothing.

**Act 3 through the real pieces** (600 L of 469363, 384 in stock). The two scores are `within_preferences` and `same_use`. `auto` needs both at 0.85 or more.

| Substitute | Chosen by | Who answers | Verdict |
|---|---|---|---|
| 464306 Valio Eila semi skimmed, chilled | the gateway | the shortcut, judge not asked | `auto`, ordered |
| 464306, the same product | the agent | judge, 0.75 and 0.72 | `human` |
| 464201 Valio semi skimmed UHT | the agent | judge, 0.94 and 0.97 | `auto`, ordered |
| 463380 Arla Cafè milk | the agent | judge, 0.17 and 0.51 | `human` (at 600 L it is also over the EUR 1,500 limit) |
| 468465 Oddlygood oat drink | the agent | allergen rule, and judge, 0.09 and 0.69 | `human` |

**The 61 labelled pairs with the judge as it is now.** One call per pair, with the gateway's full product card on both sides, which is what the harness ends up with. For the pairs outside the demo order, the first line of the policy text (it names the order) is replaced by the pair's own use.

- 57 of 61 agree with the label (56 this afternoon).
- No `ask` or `no` pair on `auto`: 0 of 50. The highest of them is at 0.31, far from 0.85. All 17 `no` pairs are under the floor.
- 7 of the 11 `ok` pairs on `auto` (6 this afternoon). The four sent to a human for nothing: 464306 to 465039 (0.74), 463380 to 464768 (0.14), 471323 to 465250 (0.39), 467286 to 474934 (0.16).
- 27 of the 33 `ask` pairs are under the floor too. So the floor does not tell `ask` from `no`. Do not turn it into a refusal (I raised that idea in the section below): it would refuse most of the cases Colette wants a human to see.

**Still open 1, for Colette and Léon: the default act 3 goes against one line of the policy text.**

- Valio's own pick for the UHT milk 469363 is the chilled milk 464306 (`temperature_condition` 4 against 8 in the product data).
- The policy text sends "a UHT or shelf-stable product replaced by a chilled one" to a human. The judge agrees when it is asked: 0.72 through the running harness (Léon's notes say 0.61, same verdict). The shortcut orders it on `auto`, because the catalog lists it.
- Three ways. Keep it as it is. Or add one sentence to the policy text, "a replacement listed in Valio's catalog is accepted without asking", so the text and the product agree, then run the 61 pairs again (one minute). Or set `"pre_accepted": "none"`: act 3 becomes `human`, unless the agent asks for 464201, which passes at 0.94.
- My pick is the sentence. Nothing has to change in the gateway.

**Still open 2: the narrowed shortcut can still accept two `ask` pairs.** Read from the catalog, not replayed. Of the 61 pairs, 7 pass the new conditions if the gateway picks them itself (listed in the catalog, same category, same allergens, nothing lost). 5 are `ok`, and for 3 of those the shortcut is what gets them through, since the judge alone asks a human. 2 are `ask`: 469079 to 462718 (a cooking yoghurt for a table yoghurt) and 472312 to 469498 (a brioche bun for a potato bun). It was 24 of 50 before PR #21.

**Two sentences to correct in `TECH-CHOICES.md`.** They are in Léon's entries, so I did not touch them.

- "the quote's own 15-minute expiry" and "a quote expires in 15 minutes", in the entry "Buyer harness". The gateway's quotes are valid for 24 hours at most, or until the cut-off (`MAX_VALIDITY` in `merchant/quotes.py`).
- "storage temperature" in the list of facts sent to the judge, in the entry "Models". `_structured_product` in `harness/judge.py` does not pass `temperature_condition`. Either add it, and the judge can see the UHT to chilled case by itself, or drop the two words.

**Two things in the gateway that the harness now relies on.** The shortcut reads the exact words "listed as a substitute in the catalog" in the `why` of the chosen alternative (`_tier` in `merchant/quotes.py`). The judge's cards come from `GET /products/search?q=<product name>&limit=20`, where the harness keeps the card with the right id. Both are held by `test_real_gateway_act3_coffee_milk_calls_judge_and_deadline_matches_quote_expiry` in `tests/test_harness_service.py`, which runs the real gateway: it fails if I reword the sentence, or if the search stops returning these products for their own name. Outside that test, a missed search is silent: the judge gets a thinner card, the scores drop and a human is asked.

The picture of all this, for the three of us: the page "Substitution Decision Map" (ask me for the link, it is private until I share it).

## For Léon: three things seen while running the harness against the real gateway (14/11, after PR #17)

Status on 14/11, evening: all three are fixed by PR #21, and so is the lock of the audit log. See the section above.

How I looked: `main` after #17, replay mode, the real `merchant.app` behind the real harness, and a stand-in judge that records its calls (there is no Gemini key on my machine). What works: acts 1 and 2, act 3 both ways (Valio's own pick 464306 goes `auto`, `"substitute_with": "468465"` goes `pending_approval`), and a quote whose price was changed outside the token is denied with a clear reason. A fourth point, the lock of the audit log, is in the next section.

**1. The judge never changes a verdict, and a coffee milk goes through on `auto`. To decide together: it is a product choice.**

- Measured: a quote for 500 L of 469363 with `"substitute_with": "463380"` (Arla Cafè milk), then `POST /authorize`. Answer: `ordered`, signed by the agent, EUR 1,259.72, judge called 0 times.
- Why: `_is_pre_accepted` in `harness/rules.py` accepts any substitute of the same category with the same `contains` list, before the judge is asked. 463380 is in category 10400 and contains milk, like the original.
- What it contradicts: the demo policy says "No flavoured milk and no coffee creamers", and `TECH-CHOICES.md` says the judge sends this product to a human at 23%. In the five quotes I tried, the judge was only called for the oat drink 468465, which `allergen-unchanged-on-substitution` already sends to a human.
- Where it comes from: the `pre_accepted` rule of the contract (PR #7), not your code.
- First proposal (no longer enough, see the update below): pre-accept only what Valio picked. The signed quote carries `aimo.requested[].substitute_with`: when it is filled, the agent picked the substitute, so ask the judge. About five lines in `harness/rules.py`. The default act 3 stays `auto` with no network, the coffee milk goes to the judge, and 464201 picked by the agent lets the judge say yes (0.96 in your L1 test).
- The other way, with no code: `"pre_accepted": "none"` in the policy. Every substitute then goes to the judge, so the `auto` of act 3 depends on Gemini answering on stage.
- Not measured: what the judge answers on what the harness really sends. `rules.py` builds the two cards from the quote, which has no brand and no nutritional claims, and the `labels` it adds are dropped by `_structured_product` in `harness/judge.py` (it reads `nutritional_claims`). Your L1 scores were measured on the full product cards. One difference the judge will see: 469363 has `free_from: ["ML"]`, while 464306 and 464201 have an empty `free_from` (their lactose-free claim is only a nutritional claim). If the judge needs the claims, I can add `nutritional_claims` to `LineClaims` and `SubstituteFor` in a small contract PR: tell me.

Update after PR #20 (Colette's demo policy and labelled pairs), same day:

- Nothing changes in the mechanism: `scenarios/policy.demo.json` keeps `"pre_accepted": "same_category_and_same_allergens"`. Run again on `main` with that policy: the coffee milk is still `ordered` on `auto`, judge called 0 times.
- The new preference text makes the gap wider. It is written for a judge that reads every substitute, and most of its "A human decides" cases stay inside one category with the same allergens (less fat, another use, another format, a label lost). That is exactly what the shortcut lets through before the judge is asked.
- Measured on the 61 labelled pairs, with the full product file: the shortcut accepts 34 of them without the judge, and only 10 of those 34 are labelled `ok` (16 `ask`, 8 `no`). Counting only the pairs that also pass the gateway's own checks on the product (allergen data, free-from promises, lactose free kept): 28, of which 14 `ask` and 4 `no`. Examples: fat-free milk for semi-skimmed, cooking cream for whipping cream, vanilla coffee milk for plain, beef and pork mince for beef.
- So my first proposal is not enough. Valio's own pick is the cheapest product of the same category with the same allergens, and that can be one of the `ask` cases.
- What I would do now: `"pre_accepted": "none"` in `scenarios/policy.demo.json`, one word, so the judge reads every substitute and the text is really applied. Two things first, or the `auto` of act 3 is at risk. One: the judge must see the nutritional claims. The text says a human decides when the candidate's data says nothing about a promise of the original, and in the quote 464306 is lactose free only by its name. I add the claims, and the labels of the replaced product, to the quote as soon as you say yes (a small contract PR), and you pass them to the judge. Two: measure the judge on the 61 pairs through the cards `rules.py` builds, not on the full product cards.
- In replay mode the demo is not affected today. For 469363, the recorded data lets only two of the ten labelled candidates through (466016 and 461174, both plant-based, both sent to a human). The coffee milk 463380 is the one leak I found.
- One more thing in the new text: it has a "Never accept" list, but a judge answer can only send to a human, and that human can still approve. Worth one sentence in the pitch, or a refusal below `judge_floor` if we want the list to mean what it says.

**2. The approval deadline is later than the quote's expiry. One line to change.**

- `evaluate` sets `deadline = checkout.aimo.closing_time or checkout.expires_at`. The gateway signs `expires_at` as the earlier of the cut-off and 24 hours after the quote. In replay mode the quote expires on 15/11 at 13:29:07 and the card says 15/11 at 17:00.
- Measured with `AIMO_FROZEN_NOW=2026-11-15T15:00:00+02:00`: the approval is still `pending`, Approve answers HTTP 403 `quote expired at 2026-11-15T13:29:07+02:00`, and the approval stays `pending`.
- Proposal: `deadline = checkout.expires_at`. It is never later than the cut-off, and the four verdict examples still come out the same (the two times are equal in them).
- Until then, to show "the human lets it expire", freeze the clock after 17:00, for example `2026-11-15T17:05:00+02:00`.

**3. A network failure gives a bare HTTP 500, or a wrong `denied`. Unlikely on one laptop: limits to know, not to fix tonight.**

- Gateway not reachable: `POST /authorize` answers HTTP 500 "Internal Server Error", because `httpx` errors are not caught in `harness/app.py`. The agent has nothing to tell the buyer. An HTTP 502 with a readable `detail` would be enough.
- Answer lost after the gateway accepted the order: on the retry the harness signs a new mandate, the gateway refuses it (`quote chk_... was already ordered as ord_... with another mandate`), and the harness stores `denied` while Valio holds an accepted order. The gateway gives the same order back only when the same mandate comes back. Fix on your side: keep the `Authorization` you sent and send it again on a retry.
- The `checkout` object next to the token with a field missing: HTTP 500, because the `ValidationError` of `AimoCheckout.model_validate(raw_checkout)` in `_verify_quote_token` is not caught. A changed price in that object is handled well: denied, `quote-signature`.

## The gateway's log uses `common/audit.py`, and `dev.py --fresh` (14/11, PR #18)

For everyone: `uv run python scripts/dev.py --fresh` empties the local state (quotes, orders, approvals, both audit logs), then starts both services. Use it before a rehearsal or the demo. Why: in replay mode the clock is frozen at the recording time, so an approval left pending never reaches its cut-off and stays on the approval page. It removes nothing while a service still answers on 8001 or 8002, and says so: the harness keeps its approvals in memory and would write the old ones back.

Checked over real HTTP with both services: act 2 leaves 1 pending approval, 4 lines in the buyer's log and 1 in the gateway's. A plain restart keeps all of it. A restart with `--fresh` shows 0, 0 and 0.

`merchant/audit.py` no longer chains its own lines: `record()` and `events()` call the shared `AuditLog`. Same file (`state/merchant/audit.jsonl`), same lines, same fingerprints. `GET /audit` on 8001 answers as before.

For Léon, one thing in `common/audit.py` that I worked around and did not change, because it is your file: the lock of an `AuditLog` belongs to the object, and `harness/app.py` builds a new object on every request (`_audit()`), so two requests at the same moment are not kept apart. Measured: 8 threads writing 200 lines through separate objects break the chain at the second line (`verify()` returns 1). Through one shared object the chain stays whole. This is why the gateway holds one lock of its own in `merchant/audit.py`. Two ways to fix it on your side: one lock per file path inside `common/audit.py` (then the gateway's lock can go), or one `AuditLog` kept for the life of the harness.

## Lookup: `GET /offers`, prices and availability before any quote (14/11, PR #16)

The brief's first must-have ("product, price and availability lookup") had no route. Now: `GET /offers?q=&delivery_date=&amount=&unit=&limit=` on the gateway (8001). Fields and rules: `docs/contract.md`, section "The lookup". Example: `contract/examples/offers.act1.json`.

Try it: `uv run python scripts/dev.py`, then open `http://localhost:8001/offers?q=lactose-free%20milk&delivery_date=2026-11-16&amount=1000&unit=L&limit=5`.

What it answers to the brief's sentence, in replay mode and in live mode on 14/11 at 15:32 (same five rows; live: 70 products matched in the full catalog, 70 priced, 2 seconds):

| Product | Per litre | 1,000 L, excl. tax | Stock | Cut-off |
|---|---|---|---|---|
| 464306 Valio Arki Eila semi skimmed 1 l | EUR 1.01 | EUR 1,010 | available, count not given | Sun 15/11 17:00 |
| 464401 Valio Arki Eila skimmed 1 l | EUR 1.10 | EUR 1,100 | available, count not given | Sun 15/11 17:00 |
| 464237 Valio coffee milk 1 l UHT | EUR 1.30 | EUR 1,300 | available, count not given | Sun 15/11 17:00 |
| 477050 Valio Eila skimmed sour milk 1 l | EUR 1.35 | EUR 1,350 | available, count not given | Sun 15/11 17:00 |
| 463335 Valio Eila 3 % milk drink 1 l | EUR 1.40 | EUR 1,400 | available, count not given | Sun 15/11 17:00 |

With `limit=25` you also get the other cases: 469363 (384 units counted, `stock_covers: false` for 1,000 L) and the offers that cannot be ordered, for example 463038, the 10 l Novobox (`orderable: false`, `reason: "late_delivery"`, its cut-off was 12/11).

The answer is **not signed** and says so (`"binding": false`). The signed quote stays the only thing the harness, a mandate or a receipt refers to.

For Colette, three things to plug (I do not touch `agent_mcp/` or `surface/`):

1. **A sixth MCP tool, `lookup_offers`.** Arguments: `query`, `delivery_date` (ISO date), optional `amount` with `unit` (`L`, `KG` or `ST`), `limit` (5 is enough for a chat). It calls `GET {MERCHANT_URL}/offers` and returns the JSON as it is. In example mode it returns `contract/examples/offers.act1.json`. The gateway answers HTTP 422 with a readable `detail` when the request has to change, HTTP 503 when Valio's API does not answer.
2. **Rule 2 of `SERVER_INSTRUCTIONS` in `agent_mcp/server.py`.** Today it says to call `search_products`, then `request_quote` "for the best matching option", but nothing in a search result says which option is best: there is no price in it. Proposed text: "When the buyer specifies what they need, how much, and by when, complete the workflow without asking unnecessary questions: call `lookup_offers` with their words, the delivery date, the amount and its unit. Pick the first offer with `orderable: true` that fits what the buyer asked (offers are sorted: orderable first, then enough counted stock, then cheapest per litre or kilo). Never pick an offer with `orderable: false`: say its `reason` instead. Then call `request_quote` for that product, and `authorize_checkout` so the buyer's harness applies policy."
3. **Rule 1 and the `search_products` description** say a price may only be stated after `request_quote`. With the lookup: "Prices from `lookup_offers` are indicative: state them as indicative, with their `as_of` time. A price or a total only commits Valio once it is in the signed quote from `request_quote`." Two more signals worth a sentence: `stock_covers: false` means the quote will take what there is and propose substitutes for the rest, and `matched` larger than `priced` means the words were too broad.

Answer to your question "The comparison table has one price in act 1": neither one quote per candidate, nor more prices inside the quote. The table reads `GET /offers` (`offers.act1.json` in mock mode): each row has its price per litre, delivery date, cut-off and stock, next to the reliability, carbon and labels already on the card. Label these rows "indicative, not signed" (the answer carries `binding: false`), and keep "signed by Valio" for the lines of the quote. The quote keeps pricing only what is ordered.

Also in your notes: the delivery date had no certainty level. In the lookup, `available_date` and `closing_time` are claims now (`declared` and `measured`, source `aimo_availability_api`). In the signed quote they are still plain values, so keep the "certainty not stated" badge there for now.

`GET /products/search` keeps its shape, but its results change: hyphens, punctuation and case no longer count ("lactose-free milk" found nothing before), and every category is returned, closest names first. In the full catalog a search for "lactose-free milk" now also returns a lactose-free milk chocolate. That is why the agent should compare through `lookup_offers`, where a product sold by the kilo is marked `unit_mismatch` when litres are asked.

For Léon: nothing changes for the harness. One new value in the list of claim sources, `aimo_availability_api`.

Seen while testing, not changed here: 463779 answers a stock of 666,666,666 units. It looks like a second "plenty" value of the mock, next to 9,999,999,999, but the gateway reads it as a real count (`measured`), in quotes too.

## A5: the gateway takes orders (14/11, 14:50)

Start it: `uv run python scripts/dev.py` (gateway on 8001, and the harness on 8002 once `harness/app.py` exists). Routes and cases: `docs/contract.md`, section "The order".

Checked in replay mode, with mandates built by `trust/` exactly as the harness will build them. The first three rows also ran over real HTTP against `scripts/dev.py`, the others run in `tests/test_merchant_orders.py`:

| Case | Answer |
|---|---|
| Act 1, 1,000 L, mandate closed by the agent | 200, order `accepted`, `signed_by: agent`, the receipt verifies against the gateway's JWKS |
| Act 2, 2,000 L, mandate closed by the agent | 403, `Amount 202000 exceeds maximum 150000` |
| Act 2, 2,000 L, mandates signed by the manager | 200, `signed_by: human` |
| Act 4, mandate built over a quote whose price was changed | 403, `Checkout checkout_hash mismatch` and `payment mandate is for another quote` |
| Same mandate sent twice | 200, same order, same receipt, one order on disk |
| A second mandate for an ordered quote | 403, `already ordered as ord_...` |

For Léon (16:30 cross-call):
- After `POST /checkouts/{id}/complete`, HTTP 200 is an `Order`, HTTP 403 is `{"problems": [...]}`, HTTP 404 is an unknown quote. Verify `order.receipt_jwt` with `trust.verify_receipt` and the JWKS from `GET /.well-known/jwks.json`, then compare its `reference` with `order.mandate_reference`.
- `common/audit.py` was not on `main` when I wrote A5, so the gateway chains its own lines in `merchant/audit.py` (same fields as `AuditEvent`, SHA-256 of the event as JSON with sorted keys and no spaces, without `hash`). When yours is merged I switch that one file to it. Tell me if your canonical JSON differs, so both logs verify with the same function.

For Colette (C4): `GET /audit` on 8001 returns the gateway's lines, oldest first. Actions: `quote_issued`, `mandate_verified`, `order_accepted`, `order_replayed`, `order_refused`.

Open question: the gateway does not ask Valio for stock again when the order arrives. The quote holds until it expires (24 hours at most, or the cut-off). Say so if a mentor asks.
