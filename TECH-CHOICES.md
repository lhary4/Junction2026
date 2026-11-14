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
- What it changes for us: unknown is a real value, shown as "unknown" and never read as "fine". Missing allergen data goes to a human. Missing stock does not: when Valio gives no count (a product it cannot count, or "plenty"), both pages say it under the quote ("Stock not confirmed on 6 of 10 lines: Valio gave no count. This does not stop the order.") and the order still goes ahead. The signature proves Valio promised, not that the stock exists. Whether an unknown stock should ever go to a human is an open question for the mentors.
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
- What it changes for us: the agent only passes short identifiers, never a signed token. The human approves on a separate page, not in the chat. A Valio Aimo engineer told us the agent will first live inside their own customer portal, and that MCP is for the customers whose ERP has its own agent (`contexte/mentor-notes.md`). So in the video the two services are called by a small demo driver behind a portal page, and MCP is shown as the second door to the same services.
- Live MCP (trying it): the five tools now call the real services instead of reading example files. Quotes and authorizations go through the demo driver, so an order asked in Claude's chat shows on the kitchen page as the "Chat order", with the human's own sentence. The server runs on stdio for Claude Desktop, or over HTTP on port 8005 for chats that live in the cloud (claude.ai, ChatGPT), reached through a temporary tunnel. Anyone who has the tunnel address can place sandbox orders, with the demo keys: close the tunnel after recording. Any catalog product works in live mode; in replay mode only the recorded products do. A sixth tool, `get_kitchen`, gives the agent the restaurant's recipes, bookings and stock count, with what is short already worked out by the kitchen's own data, so "order what is missing for this week" in a chat asks for the same lines as button 1 and the agent computes no quantity itself. It reads the stock file, not the corrections the chef types on the page. A seventh tool, `lookup_offers`, prices every product matching a few words in one call, sorted orderable first then cheapest per kilo or litre. Before it, "the three cheapest potatoes" made the agent ask one signed quote per product: ten calls, and a wrong answer, because it only quoted the first matches. Its prices are indicative and unsigned; only the quote commits Valio. When a service refuses, the agent now reads why ("460577 out of stock"): the MCP library hides the message of any error it does not recognise as expected, so the agent used to see only "Error executing tool".
- If we change it: only `agent_mcp/` changes, plus the two `/agent/...` routes of the driver.
- Alternatives we looked at: our own agent loop; a chat-only demo (the brief says this is not about a chatbot, and an agent could approve itself).
- Decided in: PR #7, 14/11/2026. Portal first, MCP as the second door: PR #23, 14/11/2026. Live MCP through the driver: PR to come, 14/11/2026.

## Models: Claude as the buying agent, Gemini Decision as the judge
- Status: decided
- What it is: any assistant that speaks MCP, Claude for example, can play the outside buying agent. In the video the agent's steps are played by a scripted demo driver (see "Demo format"). A second, different model (Google's Gemini Decision) answers two yes-or-no questions with a probability, for one thing only: when a substitute is not pre-accepted automatically, does it fit the buyer's preferences and can the kitchen use it the same way?
- Why: a judge that is not the agent is harder to fool. Tested on our real milk case, it ranked the plain lactose-free milk above 93% (`auto`), the coffee milk around 17–25% (`human`) and the oat drink below 16% (`human`), in about a fifth of a second per call (0.10 USD per million input tokens, free tier for prototyping, per Google's announcement of 11/11/2026, linked in `docs/architecture.md`). Tested across all 61 labelled product pairs in `scenarios/`, zero out of 50 "ask a human" or "reject" pairs were wrongly approved automatically, and all 17 "reject" pairs scored below the 15% floor.
- What it changes for us: a substitute skips the judge only when Valio's signed quote marks it as a catalog-listed replacement in the top tier, the agent did not force a specific substitute, and no origin, quality label or dietary promise is lost; every other substitute goes to the judge. Every structured fact the judge reads (name, brand, category, storage temperature, origin, quality labels, nutritional claims, pack sizes and all 29 standard allergen codes) travels inside Valio's ES256-signed quote for both the original product and its replacement, so the harness makes no unsigned search lookup, and we never send marketing descriptions or the agent's own request sentence so neither can talk the judge into saying yes. The judge gives no explanation, so we log both questions, the probabilities and the thresholds ourselves. It can only make a verdict stricter: if the key is missing, the network fails or an answer takes more than five seconds, a human decides.
- If we change it: one function in `harness/judge.py`, and the pre-acceptance check in `harness/rules.py`.
- Alternatives we looked at: Gemini Flash with structured output (our fallback if the ranking had failed); rules only (cannot read a buyer's plain-English note like "no coffee creamers"); pre-accepting every substitute in the same category and allergen group (dropped: it waved coffee milk and vanilla milk through without calling the judge); fetching missing nutritional claims from the unsigned search route at evaluation time (dropped in favour of signing them directly inside the quote).
- Decided in: PR #7, 14/11/2026. Tested on the milk case: PR #17, 14/11/2026. Hardened and tested across 61 product pairs: PR #21, 14/11/2026. Signed substitution claims and explicit catalog-listed flag in the quote: PR #25, 14/11/2026.

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
- What it is: everything that needs "now" asks `common/clock.py`. In replay mode it answers the moment the Valio answers were recorded (14/11 at 13:29) and never moves. In live mode it answers the real time. `AIMO_FROZEN_NOW` sets any other fixed time, in both modes.
- Why: replay mode serves answers recorded on 14/11. Their deadlines only make sense if the clock says 14/11 too. The recorded order cut-off is Sunday 15/11 at 17:00: on the real clock, replay mode could not quote anything after it.
- What it changes for us: replay mode works at any hour, on any day, with no setting. Quote expiry, approval deadlines and receipt times follow the frozen clock, so in replay mode every line of the logs carries the same time and nothing expires on its own: to show an expiry, set `AIMO_FROZEN_NOW` to a time after the deadline. The gateway and the harness must run in the same mode (`VALIO_MODE`), or their clocks disagree. The permissions themselves keep the real time, because the AP2 toolkit stamps the real time when it signs. They are valid until the end of 16/11, so this holds for the whole weekend.
- If we change it: a ticking frozen clock (starting at the recorded time) would be one function to change.
- Alternatives we looked at: passing the time everywhere by hand (easy to forget one place); keeping the real clock in replay mode unless someone sets `AIMO_FROZEN_NOW` (what we had first: the demo would have stopped quoting on Sunday at 17:00).
- Decided in: PR #9, 14/11/2026. Replay mode freezing the clock by itself: PR #15, 14/11/2026.

## Data: local files, live calls on a shortlist, and a replay mode
- Status: decided
- What it is: the product file and the two small tables (delivery reliability, carbon footprint) are downloaded once and never committed. Prices and stock are asked from Valio only for a shortlist. A replay mode serves answers recorded on 14/11 with a frozen clock.
- Why: Valio's API forbids querying the whole catalog. The order cut-off for a Monday delivery is Sunday 17:00, so a live-only demo would break.
- What it changes for us: `VALIO_MODE=live` or `replay`. The recorded answers are a small subset saved in the repo. In live mode, when Valio's API is unreachable, answers with an error or takes more than 30 seconds, the gateway says so in plain words ("try again", HTTP 503) instead of crashing, and keeps "your request is wrong" (HTTP 422) for requests that really are.
- If we change it: without replay, the demo depends on the time of day.
- Alternatives we looked at: live only; committing the full product file (86 MB, not allowed).
- Decided in: PR #7, 14/11/2026.

## Recorded answers: 157 products, raw API answers, trimmed product records
- Status: decided
- What it is: `contract/fixtures/valio/` holds what Valio answered on 14/11 at 13:29 for a Monday 16/11 delivery: all lactose-free milks and plant-based drinks, plus the substitutes Valio lists for our five demo products. Prices and stock are kept exactly as the API sent them. The product records keep names, brand, origin, allergens, labels and ingredients, and drop marketing texts, pictures and instructions.
- Why: the full records of these products weigh 1.3 MB, the limit we set for the repo is 1 MB. Keeping the raw API answers means replay mode and live mode read the same shapes.
- What it changes for us: replay mode only knows these 157 products. A test checks that the demo facts still hold on them (464306 in stock with a Sunday 17:00 cut-off, 469363 with only 384 units). Rerunning `scripts/record_fixtures.py` replaces the recording and fails loudly if a demo fact no longer holds.
- The restaurant's menu, a second recording: the video runs on the restaurant case, whose products are not among the 157 and whose delivery is on Thursday 19/11. So a second set of answers was recorded on 14/11 at 22:19 for that date, in its own folder (`contract/fixtures/valio/2026-11-19/`): the 22 products of the menu and the 25 other products of the squeaky cheese's category, 47 in all. The first recording was left as it is, because the tests and the frozen clock stand on it. A quote reads the recording made for its delivery date, and only that one. The clock stays frozen at 13:29 for both, and each recorded price says when Valio really gave it. The two recordings weigh 0.90 MB together, under the 1 MB limit. Tests run the three buttons of the demo on the second recording.
- If we change it: a new recording changes prices or stock in the demo, so tell everyone before merging one.
- Alternatives we looked at: recording only the five demo products (too few for a real search and for substitutes); adding the menu's products to the first recording (it changed what the milk case finds: a cheese "from cow's milk" joined the lactose-free milks, and Valio has no answer for it on 16/11); asking the restaurant's delivery for 16/11 in replay (the page says "needed by Thursday 19").
- Decided in: PR #10, 14/11/2026. The restaurant's recording: PR #35, 14/11/2026.

## Pack sizes: read in the product name, and the price per litre has the last word
- Status: decided
- What it is: the buyer asks for litres or kilos, Valio sells cartons, boxes and bottles. When the product file does not say how much one sales unit holds, the gateway reads it in the product's name: "5 dl", "100x2 cl", "2,5dlx12". A pack count written next to the size counts ("100x2 cl" is 2 litres), unless the product file already lists a unit of that many pieces (for "12x375g" sold by the box, 12 boxes to a carton, one box is 375 g).
- Why: the product file counts 94% of the catalog in pieces, not in litres or kilos (16,440 products out of 17,546), so the name is the only place that gives a size. Before the pack count was read, a carton of 100 portions of 2 cl showed as 0.02 litre.
- What it changes for us: the size on a product card is a reading of the name, and says how it was read. In a quote it is checked against Valio's own numbers (price divided by price per litre): within 2% the name is confirmed, otherwise the price wins, because Valio invoices on it. Checked on the 157 recorded products: the three that carry a pack count now match the price. On the whole catalog the rule changes about 1,100 cards and gives a size to 160 that had none. It only makes sizes bigger, never smaller.
- If we change it: `size_per_sales_unit` in `merchant/catalog.py`, and its tests in `tests/test_merchant_robustness.py`.
- Alternatives we looked at: the name's size alone (wrong for every multipack sold as one unit); trusting only the price per litre (not there before a quote, so a product card would show no size).
- Decided in: PR #11, 14/11/2026 (reading the name). The pack count: PR #15, 14/11/2026.

## Lookup: prices and availability for a shortlist, informative and not signed
- Status: decided
- What it is: one question to Valio's gateway, "what do you have for these words, on this date, for this amount?" (`GET /offers`). The answer lists products with their price, price per litre or kilo, stock, delivery date and order cut-off, says for each one whether it can be ordered and why not, and works out how many units the amount needs and what they cost. Products that can be ordered come first, cheapest first. Valio does not sign this answer.
- Why: the brief's first requirement is a "product, price and availability lookup", and its example asks for "an option based on price and availability". Before this, the agent picked a product without seeing any price, and only a quote revealed that an order was already too late. We do not sign the answer because a signature means "Valio commits to this". Two kinds of signed pieces would blur which one an order may rest on. The quote stays the only one.
- What it changes for us: the agent compares first, then asks a signed quote for the product it picked. The lookup says in its own data that it commits nobody (`binding: false`), and every fact in it still states its source and how sure it is. Valio is only asked about the 100 products whose names are closest to the words, in one call for prices and one for stock: its API forbids pricing the whole catalog and does not say how many calls it tolerates. The answer says how many products matched and how many were priced, so the agent knows when to use more precise words.
- If we change it: signing the lookup would need an expiry and a rule on what a signed price list allows. A smaller shortlist is one number in `merchant/offers.py`, but 50 is already too few: in the full catalog the brief's sentence matches 70 products and the cheapest one is the 51st closest name.
- Alternatives we looked at: one signed quote per candidate (five signed commitments to compare five prices, and five times the calls); prices inside the search results (every search would call Valio, even to read a label); a signed lookup (see above).
- Decided in: PR #16, 14/11/2026.

## Search: plain words on product names, every category kept
- Status: decided
- What it is: search looks for the words of the request in the English and Finnish product names. Capital letters, hyphens and punctuation do not count, Finnish letters (ä, ö) do. Names that contain the words as whole words come first, then the names with the fewest other words.
- Why: "lactose-free milk", the exact words of the brief, found nothing because the names write "lactose free". The search also kept only the kind of product that matched most often, so "butter" answered with butter buns and hid the butter.
- What it changes for us: nothing is hidden any more, so a broad word brings mixed results (butter, peanut butter, butter buns). Each result says its kind of product, and the lookup shows price and availability, so the agent narrows with one more word.
- If we change it: one function in `merchant/catalog.py`. The lookup and the search route both use it.
- Alternatives we looked at: guessing one kind of product from the words (no rule we tried got "butter", "cream" and "cheese" right); a search engine with synonyms and typos (too much for the weekend).
- Decided in: PR #16, 14/11/2026.

## Substitutes: the gateway proposes, ranked in three tiers, and never breaks a free-from promise
- Status: decided (the ranking inside a tier is open: Colette may change what counts first)
- What it is: when stock is short, Valio's gateway takes what there is and proposes up to three replacements: `best` (same kind of product, same allergens), `better` (same kind, other allergens), `good` (a related kind, plant-based drinks for milk). Inside a tier, the substitutes Valio itself lists come first, then the product whose name is closest to the original's, then the cheapest per litre or kilo. The best one goes into the quote automatically. The agent may ask for another one from the list, never one the gateway did not offer.
- Why: the agent never decides a fact, so it cannot invent a substitute. A lactose-free kitchen must never receive normal milk because it was cheaper, even if the allergen codes look the same: the data often lists milk but forgets lactose. The name counts before the price because Valio's categories are wide: on the restaurant menu, the cheapest product of the category was a cheddar cream for a squeaky cheese and an apple filling for a lingonberry jam. The judge sent both to a human, but the quote should not propose them in the first place.
- What it changes for us: a substitute must arrive on time, cover the whole missing quantity, have complete allergen data, and keep every "free from" of the original. The harness still checks allergens and asks the judge, this is a first filter on Valio's side. Most stock counts from the mock are "plenty" (9,999,999,999): the quote says "available, count not given" instead of showing that number. Inside one quote the same stock is never promised twice: a second line for the same product, or a second shortfall covered by the same substitute, only gets what the first one left.
- If we change it: `merchant/quotes.py` only. The related kinds of product are one line in it.
- Alternatives we looked at: listing every candidate and letting the agent choose (the agent would pick facts); only Valio's listed substitutes (469363, the act 3 product, lists none); the cheapest of the tier first (what we had until the live run on the restaurant menu); a frozen version as a related kind (the frozen squeaky cheese sits in a category with ice cubes and coffee, so the category says nothing).
- Decided in: PR #11, 14/11/2026. Name before price: PR #27, 14/11/2026.

## Delivery date: the day the buyer asked, unless a product cannot come before
- Status: decided
- What it is: a quote says the goods arrive on the day the buyer asked for. Only when one product cannot be ready by then does the quote move to that product's first possible day, and the harness then sends it to a human or refuses it (late delivery).
- Why: Valio's availability answer gives `availableDate`, the earliest day a product can come, not the day it will come. The mock answers 16/11 whatever date is asked. Taking that day as the delivery made a quote asked for Thursday 19/11 say "delivery Monday 16/11", and the harness wrote "Delivery on 2026-11-16, as requested".
- What it changes for us: the quote, the order and the page show 19/11 for the restaurant. Each line still keeps Valio's own earliest day (`available_date`). The order cut-off stays the one Valio gives (Sunday 15/11 17:00): it is the cut-off for its earliest day, so it may be earlier than needed for a later delivery, never later. The demo examples were recorded again in live mode: only the dates changed.
- If we change it: one line in `merchant/quotes.py`, then record the demo examples again (`scripts/record_demo_states.py`).
- Alternatives we looked at: keeping Valio's earliest day (wrong day on the page and in the chat); moving the cut-off later by the same number of days (that would be a fact Valio never gave).
- Decided in: PR #42, 14/11/2026.

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
- What it is: `uv run python scripts/dev.py` starts Valio's gateway (port 8001) and the buyer's harness (port 8002), and stops both with Ctrl+C. It hands the values of `.env` to both. With `--fresh` it first empties what earlier runs left in `state/`: quotes, orders, approvals and both audit logs.
- Why: three people on macOS and Windows should not have to remember two commands and export keys by hand. And a rehearsal must not leave things on the screen of the next one.
- What it changes for us: a value typed in the terminal wins over `.env`. A service that is not in the repo yet is skipped. If one service dies, the other is stopped and the error is shown. Start a rehearsal or the demo with `--fresh`: in replay mode the clock does not move, so an approval nobody answered never reaches its cut-off and stays on the approval page. `--fresh` removes nothing while a service is still running, and says so.
- If we change it: only this script.
- Alternatives we looked at: a shell script (does not run on Windows); Docker (one more tool to install during a hackathon); a separate clean-up script (the harness keeps its approvals in memory, so run under a live harness it would empty the files and the harness would write the old approvals back).
- Decided in: PR #13, 14/11/2026. `--fresh`: PR #18, 14/11/2026.

## Buyer harness: rules in plain code, one-use approvals with a cut-off, and receipt verification
- Status: decided
- What it is: the buyer's web service (port 8002) takes a quote id from the agent, fetches the signed quote directly from Valio, checks Valio's signature first, runs every guardrail rule, and either signs as the agent, opens a one-use approval card for a human, or refuses. After sending a signed permission to Valio, it checks Valio's signed receipt before calling the order confirmed.
- Why: the agent must never touch a quote token or a signing key, and "sending an order" is not the same thing as "Valio accepted the order". Running every rule instead of stopping at the first problem lets the approval card show every reason at once (for example, over the spend limit and a substitute at the same time).
- What it changes for us: an unsigned or edited quote stops right away before any rule reads its numbers. Every substitute line in a quote is checked, and if stock is short with no substitute covering the missing amount, a human must sign before a partial delivery is ordered. Human approval cards sit in `state/buyer/` tied to that quote's exact fingerprint, expire at whichever comes first between the quote's own 24-hour expiry and the supplier's order cut-off, and can only be answered once (a second click is refused). Before sending a signed permission to Valio, the harness saves that exact permission locally so a retry after a network drop replays the identical permission instead of getting refused, and if Valio's gateway is unreachable the harness returns a clean "gateway unavailable" answer (HTTP 502) instead of crashing. In the demo, clicking Approve signs with the manager's key kept on the buyer side; in real life, that click would use a passkey in the browser. The harness also serves the approval page directly at `http://localhost:8002/`.
- If we change it: `harness/` only. Valio's gateway still checks every signature and spend cap on its own side.
- Alternatives we looked at: stopping at the first failed rule (hides other warnings from the approver); letting the agent pass the quote data to the harness (the agent could alter numbers); trusting HTTP 200 without checking the receipt signature; setting the approval deadline to the order cut-off alone (a quote expires in at most 24 hours, which can fall before a later cut-off).
- Decided in: PR #17, 14/11/2026. Hardened for multi-line quotes, shortfalls, quote-expiry deadlines and network retries: PR #21, 14/11/2026.

## Audit log: one chained file on each side
- Status: decided
- What it is: the buyer's harness and Valio's gateway each write one line per decision (`state/buyer/audit.jsonl` and `state/merchant/audit.jsonl`): what, why, which rule, who. Each line includes a fingerprint of the previous one, so an edited, deleted or swapped line is caught at its exact line number.
- Why: the brief asks for a readable record for both the buyer and Valio.
- What it changes for us: the chain shows tampering, it does not prevent it. The stronger proof is that each side also keeps pieces signed by the other. Both logs are written and checked by the same code, so one check works on both files. One shared lock per file path makes simultaneous web requests write strictly one after the other even when they open separate log objects, so two lines never get the same number.
- If we change it: only `common/audit.py`. The buyer's harness uses it directly. Valio's gateway uses it through `merchant/audit.py`, which only says where the gateway's file is.
- Alternatives we looked at: a database table; a single shared log.
- Decided in: PR #7, 14/11/2026. Shared verifier in `common/audit.py`: PR #17, 14/11/2026. Gateway moved to the shared code: PR #18, 14/11/2026. Shared per-file lock inside `common/audit.py`: PR #21, 14/11/2026.

## Payments: a sandbox, the order is booked on a simulated invoice account and no real money moves
- Status: decided
- What it is: wholesale orders are invoiced on the customer's account, so the "payment instrument" in the AP2 payment mandate is that invoice account, and the mandate carries the maximum amount the agent may commit. Once Valio's gateway has verified the mandates, it books the order's amount on a pretend account it keeps in a file: a credit limit, what is used so far, one line per payment. The order comes back with that payment, marked `sandbox`.
- Why: the video has to show the end of the chain, a charge after the signatures. AP2 is a payment protocol, and stopping at "mandate verified" left its last step invisible. A sandbox shows it without a bank, a card network or a payment provider's account.
- What it changes for us: every screen and every log line about the payment says "sandbox", and the page carries the banner "Concept mock-up". In the video we say "mandate" for what is signed and "sandbox payment" for the charge. The credit limit (EUR 20,000 a customer) and the terms ("Invoice at 14 days") are made up, because Valio's real ones are not in the challenge data. An order that does not fit on the account is refused, like one above the spend cap. Starting the services with `--fresh` empties the accounts.
- If we change it: real payment would add AP2's other roles (credential provider, payment processor) and a real provider's test mode. Only `merchant/payments.py` and the payment step of the trail would change.
- Alternatives we looked at: no payment at all (what we had until Saturday evening: the trail stopped at the receipt); a payment provider's test mode such as Stripe (one more account and one more integration for a step the brief does not ask for); x402, Nevermined (named in the brief as context, not required).
- Decided in: PR #7, 14/11/2026 (the spend cap in the mandate). Sandbox payment: PR #31, 14/11/2026.

## Approval page: three plain files, with a mock mode that reads the examples
- Status: decided
- What it is: the page where a human approves is three files (`surface/static/`), opened in a browser. With `?mock=1` in the address it reads the example files in `contract/examples/` instead of the running services. Every screen of the demo has its own link (for example `&state=expired`), and `&now=...` starts the page's clock at a chosen time.
- Why: the page could be built and rehearsed before the gateway and the harness exist, and it stays as a safety net if a service fails on stage.
- What it changes for us: the page never works out a fact itself. A price only appears if it is in a signed quote, a missing value reads "unknown", and "verified" is only written when the harness said so. Anything the agent wrote is shown as plain text, so it cannot add a button to an approval card. In mock mode nothing is really checked or signed, and the page says so.
- If we change it: only `surface/` changes. If an example file is renamed, a test fails.
- Alternatives we looked at: React (a build step, dropped earlier); the harness serving ready-made pages (the page could not be built before the harness).
- Decided in: PR for step C2 (`feat/surface-mock`), 14/11/2026.

## Demo format: a 2-minute video on a portal page with scenario buttons
- Status: decided
- What it is: what we hand in is a video of 2 minutes at most, not a live demo. It is recorded on one page that looks like a Valio Aimo customer portal for one restaurant. There is one button per scenario: a normal order, a substitution, an attack. A click runs the real flow. The page shows the seven steps of the authorization (the AP2 trail) and who signed each one. How the page is laid out is the next entry. A small service, the demo driver, plays the buying agent: it sends the same requests an MCP agent would send, and gives the page everything it shows as one piece of data (the demo state). For the attack button it plays an agent whose key was stolen: it skips the guardrails and sends three bad authorizations straight to Valio, which refuses all three.
- Why: Junction asks for a video, strictly 2 minutes. A scripted driver makes every take the same, where a live assistant took about 2 minutes for one round in our only test. One piece of data for the page lets the page be built on example files before the services are wired.
- What it changes for us: the demo runs on the restaurant case (`scenarios/restaurant-case/`), not on the milk example of the brief. The page carries a banner "Concept mock-up, Junction 2026, synthetic data", because the video is public and the challenge data must not be shown as real Valio data. The video is recorded in replay mode, so the menu's products must be in the recorded answers. For an order the driver holds no key. For the attack it uses the demo keys that sit in the repo, marked "DEMO ONLY": that is what a leaked key looks like, and it is why the attack proves Valio's own checks and not the guardrails.
- If we change it: a live pitch would use the same page and the same buttons. Showing a real assistant instead of the driver needs the MCP live mode.
- Alternatives we looked at: Claude Desktop on screen (too slow, and a chat is what the brief says this is not); an automation tool showing its steps (n8n: one more tool, and the trail already shows the real steps); the four milk acts of the first plan.
- Decided in: PR #23, 14/11/2026. The driver: PR #30. The attack button: PR #32, 14/11/2026.

## Demo page: the chef's order in three steps, with a replay of recorded runs
- Status: trying it
- What it is: `surface/static/portal.html` is the page of the video. The chef goes through three steps, like a checkout: the recipes, the stock (what is needed, what the last count found, what is missing), then the order, sent by one button. The signing steps stay in a panel on the left and light up one after the other in about three seconds. A panel on the right is the conversation with Aimo Personal Assistant. The scenario buttons are in a dark strip at the bottom, drawn so that nobody takes them for part of the customer's page.
- Why: the first screen showed products as shop cards and did not show how an order comes to exist. A kitchen thinks in recipes and stock, so the page starts there, and the order is the last step.
- What it changes for us:
  - The page reads four sources. The demo driver gives the demo state. The harness gives the spending limit and takes the chef's signature. The assistant service answers the chat. The kitchen's recipes, stock count and bookings are three small files in `surface/static/kitchen/`.
  - The kitchen files are synthetic: they stand in for the restaurant's own system, which Valio told us we may mock. They are written so that what is missing is exactly what each recorded scenario orders, and a test checks it.
  - When the demo driver does not answer, or cannot run a scenario, the page replays the runs recorded in `contract/examples/demo-state.*.json` and says so. The strip at the bottom has a light for each service. The video can be recorded this way if a service fails.
  - The chef can change the stock count and the quantity to order, in the table or through the chat. The page sends these lines to the demo driver with the order. The driver plays each scenario's own lines, so when the chef's lines differ the quote is not for them, and the page says so in a red line above the quote. After a refused order (the attack), the chef corrects the quantities and orders again.
  - The page shows eight steps. Seven are the AP2 trail of the demo state. The eighth, "Delivery scheduled", is read by the page from the order Valio accepted. It is not in the contract: the contract still has seven steps.
  - Words are the chef's. The buying agent and the judge are both called Aimo Personal Assistant, and each rule of the harness has a plain sentence written in the page ("The total is within your spending limit"). The harness's own sentences stay as they are, in a tooltip. A test fails if the harness gets a rule the page has no words for.
  - A signature is asked twice: the button, then a window that shows exactly what is signed. Reject stays at the top of the work area, Approve and sign is at the bottom of the card.
  - The spending limit can be opened and changed on the page, but the change is sent to the harness, which has no route for it yet. The page never keeps a limit of its own, because only the harness enforces it.
  - The look follows the Valio Aimo web shop: its colours and its logo. Its two fonts are commercial and we have no licence, so the page ships the closest free fonts (Sofia Sans Extra Condensed and Figtree, under the SIL Open Font License) and no internet is needed.
- If we change it: only `surface/` changes. If the demo state changes shape, this page changes with it. If the scenarios order other lines, the kitchen files must follow, and the test says so. If the harness renames a rule, the page's sentence for it must be renamed too.
- Alternatives we looked at: product cards as in the shop (too big, and it is not a shop); the three-zone screen of the first plan, with the buttons on the left (the buttons looked like part of the product); the signing steps in a row at the top (the team found them hard to follow, and they scrolled away); adding the eighth step to the contract (it would change `DemoState` for everyone on the last evening).
- Decided in: PR #28 (branch `feat/surface-portal-v1`), then the PR for the branch `feat/surface-portal-v2`, 14/11/2026.

## Chat on the page: Gemini, behind a small service that checks what it may change
- Status: trying it
- What it is: the chef can write to Aimo Personal Assistant on the order page. A small service, `surface/assistant.py` on port 8004, passes the message to Gemini (model `gemini-3.5-flash-lite`) with what the page shows at that moment, and returns the answer. The same service serves the page.
- Why: the team wanted the stock to be changed "by hand in the table and with the agent", and a chat that really answers. The key cannot sit in the page, where anyone could read it, so a service holds it. We already have a Gemini key for the judge, and this model answers in about one second, which a live demo needs.
- What it changes for us:
  - The chat only repeats what the page shows. It is told never to state a price, a stock or an allergen that is not there, and to say "I do not know yet" instead. This keeps the rule "the agent never decides a fact".
  - The chat never signs, approves, rejects or orders. The chef signs on the page with a button, never in the conversation. This keeps the rule "a human approves on the page".
  - The chat may change two numbers when the chef asks: the kitchen's stock count and the quantity to order. Both are the kitchen's own data, not Valio's. The service checks each change again (a known product, zero or more, no order open), and the page writes under the answer what really changed, so a wrong sentence of the model cannot hide a change.
  - It fails closed: no key, a timeout or an unreadable answer gives an error, never an invented reply. The table can still be changed by hand.
  - The service serves three folders and nothing else from the repo, so `.env` cannot be read through it. Before, the page was served by a plain file server on the whole repo.
  - One more command to start: `uv run uvicorn surface.assistant:app --port 8004`. `scripts/dev.py` does not start it yet.
  - Cost: one short Gemini call for each message, on the team's key.
- If we change it: another model is one line (`ASSISTANT_MODEL` in `.env`). Another provider means rewriting one function. Without the service the page still works, with the chat field switched off.
- Alternatives we looked at: no model, only the scripted lines of V1 (the team asked for a real chat); calling Gemini from the page (the key would be public); letting the chat call the gateway and the harness itself (that is the buying agent's job, done by the demo driver and the MCP tools, and it would put a second agent in the product); Claude as the model (no key for it in the project).
- Decided in: PR for the branch `feat/surface-portal-v2`, 14/11/2026.

## Chef notification: one Telegram alert when an approval is waiting, never an approval in chat
- Status: decided
- What it is: when the harness decides that a human must review an order, it sends one short message to the chef on Telegram with the reason in one sentence, the total in euros, the Helsinki deadline, and a link to the approval page.
- Why: a chef in service is not watching a browser tab, so the phone needs to buzz right away. Telegram's bot service is free, arrives right away on a phone, and needs only a bot key and a chat number, unlike paid text message services or slow email setup.
- What it changes for us: the two Telegram settings in the local environment file are optional; when either one is empty, the harness makes no network call at all. When set, the alert has a strict two-second time limit, and any failure is written to the warning log without revealing the bot key, so a broken notification never changes, blocks, or delays a verdict. Asking to authorize the same pending quote a second time does not send a second message. Above all, the chef never approves inside Telegram: the link opens the web page, which is the only place that shows and signs the exact quote.
- If we change it: only harness/notify.py changes. Nothing in the rules, the signatures, or Valio's gateway depends on it.
- Alternatives we looked at: approving directly inside Telegram chat (dropped because chat has no browser passkey or quote-fingerprint signing boundary); email or SMS text messages (slower on stage or require paid sender setup).
- Decided in: PR #33, 14/11/2026.

## Chef notification: one Telegram alert when an approval is waiting, never an approval in chat
- Status: decided
- What it is: when the harness decides that a human must review an order, it sends one short message to the chef on Telegram with the reason in one sentence, the total in euros, the Helsinki deadline, and a link to the approval page.
- Why: a chef in service is not watching a browser tab, so the phone needs to buzz right away. Telegram's bot service is free, arrives right away on a phone, and needs only a bot key and a chat number, unlike paid text message services or slow email setup.
- What it changes for us: the two Telegram settings in the local environment file are optional; when either one is empty, the harness makes no network call at all. When set, the alert has a strict two-second time limit, and any failure is written to the warning log without revealing the bot key, so a broken notification never changes, blocks, or delays a verdict. Asking to authorize the same pending quote a second time does not send a second message. Above all, the chef never approves inside Telegram: the link opens the web page, which is the only place that shows and signs the exact quote.
- If we change it: only harness/notify.py changes. Nothing in the rules, the signatures, or Valio's gateway depends on it.
- Alternatives we looked at: approving directly inside Telegram chat (dropped because chat has no browser passkey or quote-fingerprint signing boundary); email or SMS text messages (slower on stage or require paid sender setup).
- Decided in: Branch feat/harness-notify, 14/11/2026.

## Open choices (to decide, then move up)
- **Hosting the demo**: where the services run during judging (one laptop, or a small server so the three of us can use the same instance).
- **Customer token on the gateway** (planned, after the demo flow): today anyone who can reach the gateway can ask a quote for any customer. Valio told us prices are per customer, so a token must say who is asking.

## Choices we dropped
- **Our own agent loop**: an outside assistant through MCP does the job and is closer to the brief's "external agent".
- **An invented Valio API with seed data** (first spec): the real APIs and files exist and the judges want the demo on them.
- **A hand-written API description (OpenAPI)**: FastAPI generates it from the models.
- **Login tokens (bearer) as the trust mechanism**: a token says who is calling, not that a human allowed this order.
- **React, Vite and SQLite**: a plain page and files are enough and need no build.
- **Ed25519 signatures**: AP2 does not allow them for quotes.
- **Running the whole demo inside the chat**: the brief says this is not a chatbot, and approval must happen where the agent cannot reach.
- **No payment step at all** ("Payments: none"): the trail stopped at the signed receipt, and a video about a payment protocol never showed a charge. Replaced by the sandbox payment.
- **Claude Desktop as the agent on screen**: our only test of a live assistant took about 2 minutes for one round (on another client, Claude Desktop itself could not run on that laptop), and the video is 2 minutes long. A scripted demo driver sends the same requests.
- **Search results limited to the most common kind of product**: it hid the right answer whenever another kind matched more often ("butter" returned butter buns only). Every kind is returned now.
- **Pre-accepting every substitute in the same category and allergen group**: coffee milk and sweetened vanilla milk sit in the same category and allergen group as plain milk, so only catalog-listed replacements in the top tier that lose no origin, label or dietary promise skip the judge now.
