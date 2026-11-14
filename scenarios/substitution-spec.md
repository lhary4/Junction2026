# Kitchen preferences: substitution rules by use, settings the restaurant tunes, one priority

Status: **partly decided**, 14/11/2026. Owner: Colette (`scenarios/`). Checked against `main` after PR #33 (Léon's restaurant policy is merged).
Words only: nothing decided here is in code or in `scenarios/policy.demo.json` yet. What is still open is listed in section 11.
Case: the Helsinki restaurant of `scenarios/restaurant-case/` (50 covers, Nordic set menu, 22 catalog products).

Every `?` is a product decision not taken yet. A cell marked `ok`, `ask` or `no` only repeats what `scenarios/policy.demo.json` or the labelled pairs (`scenarios/pairs*.csv`) already say. Decisions taken in this spec are marked **Decided** with the date.

Words used below:
- `ok`: the substitute goes through without a human (the kitchen would not notice).
- `ask`: the chef decides on the approval page.
- `no`: never `auto`. A `no` candidate is offered only when every candidate is a `no`: then the best of them by the restaurant's priority goes to the chef (decision C3).

## 1. Why this spec

The demo policy applies one set of rules to every product, whatever the kitchen does with it. On the menu the same difference does not weigh the same:
- 500 g pieces of squeaky cheese instead of 670 g: a wedge on the dessert plate, cut differently. Decided `ok` (B19).
- Salted butter instead of unsalted: in the reindeer sauté nobody notices; in a crumble or a pastry dough the recipe changes.
- Red beetroot instead of yellow: the starter is plated red and yellow, the menu says "keep red and yellow apart so the colours do not bleed".

The spec adds three things:
1. **The use of the line** decides which rules apply.
2. **Settings the restaurant tunes** (tolerances, price cap, strictness per use, autonomy and budget), shown on the page under "Kitchen preferences".
3. **One priority, plus a tie-break**, chosen by the restaurant (price, carbon, quality, closest for the recipe, packaging and logistics). It orders the substitutes the rules allow.

## 2. The three layers

| Layer | What it decides | Who can change it | Where it runs |
|---|---|---|---|
| A. Safety rules | allergens, dietary promises (every dairy product lactose free), unknown data, food vs non-food | Nobody can make them looser. The restaurant can only make them stricter (`human` to `deny`). | deterministic code, `harness/rules.py` and the gateway |
| B. Rules by use | whether a difference is `ok`, `ask` or `no` for this use | the restaurant, from our defaults | the judge reads them; deterministic checks where the data is plain |
| C. Priority | which allowed substitute comes first | the restaurant | ranking of the candidates, before the quote is signed |

A priority never changes a verdict. It only orders candidates that layers A and B allow.

## 3. Layer A: safety rules

Already in code:
- A blocked allergen in the order (peanuts `AP`, tree nuts `AN`): `deny`.
- Allergen data missing: `human`, never `auto`. On this menu: reindeer, beetroot, horseradish, dill, potatoes, onions, cloudberry jam.
- The substitute's allergens differ from the original's: `human`.
- The gateway never offers a substitute that breaks a free-from promise of the original (lactose free stays lactose free), arrives late, does not cover the shortfall, or has no allergen data.

Proposed additions:
- A1. Food never replaced by non-food, nor the other way round: `?`
- A2. A dietary promise the original makes and the candidate's data does not prove: today `ask` in the text. Keep it in the judge's text, or make it a deterministic rule: `?`

## 4. Layer B: the uses

| Code | Use | What matters most | On this menu |
|---|---|---|---|
| `served` | Served as it is, the guest sees and tastes it | look, taste, variety, origin shown on the menu | cured rainbow trout (decided 14/11), beetroot, horseradish smetana, dill, rye crisp, lingonberry and cloudberry jam, pickled cucumber, squeaky cheese wedge |
| `cooked` | Cooked in a dish, hidden in it | how it behaves when cooked | reindeer sauté, onions, butter and milk in the mash, the salt and sugar of the trout cure (decided 14/11) |
| `baking` | Pastry, bakery, and fixed formulas | exact composition: fat, salt, sugar, water | oat crumble (oats, butter, sugar), whipped cream |
| `drink` | In a drink | foaming, taste in coffee | none on this menu (coffee milk in the labelled pairs) |
| `non_food` | Not eaten | fits the dispenser, food contact, safety data | none on this menu |

Decided on 14/11:
- Q1. Is this list right? **Decided 14/11:** the trout line (461921) is `served`; the salt and sugar of the cure (40 g of each per kg of fish) are `cooked`, not `baking`.
- Q1b. **One product, several uses.** Butter 463437 goes into the reindeer (`cooked`), the mash (`cooked`) and the crumble (`baking`); sugar 460325 into the cure (`cooked`) and the crumble (`baking`). **Decided 14/11:** the line follows the strictest of its uses (on this menu: `baking` for the butter and the sugar).
- Q1c. When the use is not known: apply the strictest column, or send every substitute to the chef. **Decided 14/11 (Colette left this choice to Claude; change it if it does not suit):** every substitute on a line with no known use goes to the chef, never `auto`. It follows the product rule "unknown is never read as safe". Consequence: until the use reaches the harness (section 9, step 1), every substitution goes to the chef.

Colette's principle for `baking`: very strict on ingredients. Seven of its cells are decided in section 5; the others still wait for her yes or no.

## 5. Layer B: the rules by use

"Today" is the rule in `policy.demo.json`, which applies to every use. A cell repeats it only where a labelled pair decided it for that use; `?` everywhere else.

| # | Difference | Today | served | cooked | baking | drink |
|---|---|---|---|---|---|---|
| B1 | Only the maker or brand changes | ok | ok (milk) | ok (chicken) | ok (whipping cream) | ? |
| B2 | A different kind of product (another fruit, another cheese, pork in beef) | no | no (fruit, parmesan) | no (mince) | **Decided 14/11:** no (coconut or jam sugar for caster sugar, oat flakes with wheat bran for oat flakes) | ? |
| B3 | Flavoured or sweetened instead of plain | no | no (coffee drink) | ? | ? | no (vanilla coffee milk) |
| B4 | Frozen instead of fresh. **Decided 14/11:** the default is `ask` for every use, and the kitchen can change it in its preferences (section 7) | no | ask (squeaky cheese) | ask (the chicken pair is labelled `no`: see C9) | ask | ask |
| B5 | Chilled replaced by UHT or ambient | ok | ok (milk) | ? | ? | ? |
| B6 | UHT or ambient replaced by chilled | ask | ? | ? | ? | ask (coffee milk) |
| B7 | Plant-based instead of dairy, same use | ask | ask (oat drink) | ? | ask (plant fat for butter) | ask (barista oat) |
| B8 | A label or stated origin lost: organic, Fairtrade, MSC, Finnish | ask | ask (yoghurt, tomato). **Decided 14/11:** the country of origin changes and the original carries no origin label: ok (cloudberry jam, Finland to Sweden) | ask (pork) | ? | ask (coffee) |
| B9 | Composition the dish would show: clearly less fat, another milk type | ask | ask (milk type) | ask (cream 15 to 10 %, mince 17 to 10 %) | ? | ? |
| B10 | Clearly salted (over 1 %) instead of unsalted | ask | ? | ? | ask (butter) | ? |
| B11 | Small change, or richer of the same type | ok | ? | ok (cooking cream 10 to 15 %) | ok (whipping cream 38 to 36 %) | ok (milk in coffee) |
| B12 | Lightly salted (under 1 %) instead of natural | ok | ? | ok (chicken) | ? | ? |
| B13 | Cheese ageing: within 6 months / more than 6 months | ok / ask | ok / ask (parmesan) | ? | ? | ? |
| B14 | Made for another use | ask | ask (cooking yoghurt for table yoghurt) | ? | ask (cooking cream for whipping cream) | **Decided C1:** drinking milk for coffee milk is ok with as much fat or more, ask with less |
| B15 | Another variety of the same product (beetroot colour, pepper colour, bun) | ask | ask (pepper, mozzarella). **Decided 14/11:** ask for beetroot colour | ask (bun) | **Decided 14/11:** ask (granulated sugar for caster sugar, big or instant oat flakes for wholegrain oat flakes) | ? |
| B16 | Another flavour of the same flavoured product | ok | ok (yoghurt) | ? | ? | ? |
| B17 | The format changes the kitchen's work (10 l box, portion packs, shredded for whole) | ask | ask (rolls, 10 l box) | ask (shredded cabbage) | **Decided 14/11:** ask (butter in 5 kg blocks for 500 g packs) | ask (10 l box) |
| B18 | The same product in another case size, same delivered quantity | ok | ok (diced paprika). **Decided 14/11:** jam in 1 kg tubs for 3 kg is this rule, not B17 | **Decided 14/11:** ok (reindeer in 3 kg packs for 5 kg) | **Decided 14/11:** ok (butter in 200 g packs for 500 g, whipping cream in 2 dl cartons for 1 l) | ? |
| B19 | Another piece or portion size (squeaky cheese 670 g to 500 g, croissant 60 to 70 g) | no rule | **Decided 14/11:** ok (squeaky cheese 670 g to 500 g; croissant) | ? | **Decided 14/11:** ask | ? |
| B20 | A lower quality grade (trout fillet A to fillet C) | no rule | **Decided 14/11:** ok (trout fillet A to C) | ? | **Decided 14/11:** ok | ? |

## 6. The menu's substitution cases, and what the rules give today

Facts from `scenarios/restaurant-case/menu.md` and the live runs in `team/adrien/notes.md` (A7) and Léon's L5 notes. "What the rules give" applies the rules above; `?` where no rule decides.

| Line, use | Why short | Candidate | Differences | What the rules give | Judge today |
|---|---|---|---|---|---|
| Squeaky cheese 474880, `served` (dessert) | cut-off passed, available 16/11 | **475072** Haapalan 500 g, chilled, lactose free, 10.94 EUR/kg (12.86 before), no carbon data. The gateway's pick, chosen for button 2 | other maker (B1), 500 g pieces (B19), low sodium claim added | B1 `ok`, B19 `ok` (decided 14/11) | 0.64 and 0.93: `human` |
| Squeaky cheese 474880 | same | 467148 same maker, frozen, 12.69 EUR/kg | frozen (B4) | B4 `ask` (the default for every use, decided 14/11) | 0.01: `human` (not offered by the gateway: other category) |
| Lingonberry jam 465815 3 kg, `served` (main) | out of stock | **462198** Dronningholm 1 kg, 6.54 EUR/kg. The fallback of button 2 | other maker (B1), 1 kg tubs for 3 kg (B18, decided 14/11) | B1 `ok`, B18 `ok` (decided 14/11: 1 kg tubs for 3 kg is another case size, not a format change) | 0.31 and 0.75: `human` |
| Lingonberry jam 465815 | same | 475860 Saarioinen apple filling 6 kg (the cheapest, before PR #27) | another fruit (B2) | `no` | 0.01: `human` |
| Cloudberry jam 469044, `served` (dessert) | not deliverable | 466574 Kalas 1.5 kg, Sweden, ambient, no allergen data | other maker (B1), origin Finland to Sweden with no origin label on the original (B8), chilled to ambient (B5), 1.5 kg for 2.5 kg (B18) | layer A: `human` (no allergen data); B1 `ok`, B5 `ok`, B18 `ok`, origin change without a label `ok` (decided 14/11) | not run |
| Yellow beetroot 460810, `served` (starter) | not deliverable | 460837 red beetroot | another variety (B15) | B15 `ask` (decided 14/11); layer A: `human` (no allergen data) | not run |
| Rainbow trout fillet A 461921, `served` (starter, decided 14/11) | cut-off passed | 462016 fillet C, Finland, no allergen data | grade A to C (B20), origin Norway to Finland with no origin label on the original (B8) | layer A: `human` (no allergen data); B20 `ok` (decided 14/11), origin change without a label `ok` (decided 14/11) | not run |
| Reindeer 465607, `cooked` | cut-off passed | 465853 same product, other code; 465887 3 kg packs | none, or pack size (B18) | layer A: `human` (no allergen data); B18 `ok` in `cooked` (decided 14/11) | not run |

Valio's own listed substitutes on the menu: butter 463437 (500 g, salted) lists 462421 (the same butter in 200 g) and 464076 (the same butter in 5 kg blocks); whipping cream 464194 (1 l, 38 % fat) lists 463837 (Valio Keittiön, 2 dl) and 469346 (Arla Pro, 1 l, 36 % fat).

**What the decisions change for button 2.** With B1 and B19 both `ok`, the rules now give `ok` for the squeaky cheese candidate 475072, and B1 with B18 give `ok` for the lingonberry jam 462198. The judge still answers `human` for both today (0.64 and 0.31), because it reads the policy text, which has not changed. Once these rules are written into `policy.demo.json`, either case may end in `auto`: run button 2 again before recording. `PLAN.md` holds the fallback (a fourth button, "Above the limit"). The low sodium claim that 475072 adds is covered by no rule.

## 7. Settings the restaurant tunes ("Kitchen preferences")

**Decided 14/11:** the restaurant can tune four families of settings. The priorities keep the Q5 choice (a main priority and a tie-break, no weights). On the page the settings are **shown, not edited**: the values change in the file.

| Setting | Today | Default | Applied by |
|---|---|---|---|
| Spend limit for `auto` | `autonomous_limit_minor`, EUR 1,500 | already set | `harness/rules.py`, exact |
| Judge threshold for `auto` | `judge_auto_threshold`, 0.85 | already set; lowest allowed `?` | `harness/rules.py`, exact |
| Most a substitute may cost more, per litre or kilo, before the chef decides | none (gap C8) | `?` % | `harness/rules.py`, exact: the price per unit of both products is in the signed quote |
| Fat tolerance | "clearly less fat" | `?` points | the judge, through its text: fat is not in the product cards. The product file states fat and salt per 100 g (butter 464076: fat 80 g, salt 0.8 g), so both could be checked in code if the cards carried them |
| Salt tolerance | 1 % | `?` | the judge, through its text |
| Cheese ageing tolerance | 6 months | `?` | the judge, through its text |
| Frozen instead of fresh (B4) | `no` for every use | **Decided 14/11:** `ask` for every use; the kitchen can change it | the judge, through its text; in code once step 4 of section 9 is done (`temperature_condition` is in the data) |
| Strictness per use (`served`, `cooked`, `baking`, `drink`, `non_food`) | one level for all | `?` each | the judge: the use must first reach the harness (section 9, step 1) |
| Main priority and tie-break | gateway order: Valio's listed, then closest name, then cheapest | `?` and `?` | the ranking (section 8) |

Say it plainly in the pitch: the settings the judge reads are instructions to a model, not guarantees. The ones applied in code are exact.

### Where the settings live: Adrien's "strict models" rule, challenged

Our models refuse any field they do not know (`TECH-CHOICES.md`, "Data contract: strict models"). Adding a block of settings straight into `policy.demo.json` makes the harness refuse the policy. We checked whether the rule should go:
- **It should stay.** A setting with a typo (`max_price_increse_pct`) would be dropped without a word: the restaurant believes a cap exists and nothing applies it. With settings shown on the page, we would display a setting that does nothing.
- Accepting unknown fields would not make a setting work anyway: the harness still has to read it.
- A declared field carries its bounds (for example a judge threshold never under a floor we choose), and the page can read those bounds from the generated JSON Schema.

So the settings become a typed block of the policy model in `contract/models.py` (Adrien), read by `harness/rules.py` and the judge's text (Léon). Shape, values to fix:

```json
"tuning": {
  "max_price_increase_pct": "?",
  "fat_tolerance_points": "?",
  "salt_tolerance_pct": "?",
  "cheese_ageing_tolerance_months": "?",
  "frozen_for_fresh": "ask",
  "strictness": {"served": "?", "cooked": "?", "baking": "?", "drink": "?", "non_food": "?"},
  "priority": {"main": "?", "tie_break": "?"}
}
```

Until then, the page shows what the policy holds today (`GET /policy` on the harness, `contract/examples/policy.demo.json` in mock mode).

## 8. Layer C: the priority

**Decided 14/11 (Q5):** the policy holds one main priority and a second one used only to break ties. Which pair the restaurant uses: `?`

| Priority | Ranks by | Data and certainty | Limit to say out loud |
|---|---|---|---|
| Price | price per litre or kilo | `comparison_price_minor`, signed in the quote: measured | none |
| Carbon | kg CO2-eq per kg | `carbon_footprint`: estimated | the average of the product group: two jams get the same number. It separates groups (dairy vs oat, chilled vs frozen reindeer: 9.21 vs 3.49), and those substitutes often go to the chef anyway. 475072 has no carbon data. |
| Quality | the labels, origin and grade the restaurant values | `labels`, `origin`, the name (fillet A or C): declared | no quality score in Valio's data: the restaurant names what counts. `?` |
| Closest for the recipe | how close the candidate is for this use | Valio's listed substitutes (declared), then the closest name (what the gateway does since PR #27), then the judge's `same_use` | ranking by the judge means one judge call per candidate |
| Packaging and logistics | same pack size and storage as the original, stock counted, delivery reliability | `pack_sizes`, `temperature_condition`, `logistic_model`, `delivery_reliability` | packaging material is in the product file, not in our cards |

**Decided 14/11 (C3):** first the candidates the rules allow (`ok`, then `ask`), each group ordered by the priority. A `no` is offered only if every candidate is a `no`, and then the best `no` goes to the chef, never `auto`.

Today the gateway ranks, within a tier: Valio's listed substitutes, then the closest name, then the cheapest (`merchant/quotes.py`, PR #27). That is already "closest for the recipe" with price as the tie-break. Another priority means changing that order (Adrien), or the agent picking among the tiers with `substitute_with` (Colette).

## 9. How it fits Léon's judge

What runs on `main` today (`harness/rules.py`, `harness/judge.py`, PRs #21, #25, #27, checked again after PR #33):
1. Rules in code first: signature, expiry, order cut-off, merchant, allergens, unknown data, allergens changed by a substitute, delivery date, spend limit, uncovered shortfalls, expired policy.
2. A narrow shortcut: no judge call only when the substitute is the gateway's own pick, the signed quote says Valio's catalog lists it (`catalog_listed`), the agent did not name it, and no origin, label or dietary claim is lost. None of the substitutes for the menu's short lines is listed, so the judge always runs in the video.
3. Otherwise Gemini Decision (`gemini-decision-1`) answers two yes/no questions with a probability: `within_preferences` and `same_use`. It reads `preferences_text` and two cards: name, brand, category, allergens, origin, labels, nutritional claims, pack and unit sizes. It does not read the price, the carbon, the agent's sentence or the dish.
4. Both answers at 0.85 or more: `auto`. Otherwise the chef. Under 0.15 only the message changes ("outside the stated preferences"), which matches C3.
5. Measured by Léon on the 61 labelled pairs: no `ask` or `no` pair reached `auto`; every `no` pair scored 0.133 or less.

What this spec changes:

| Step | Change | Owner | Needs |
|---|---|---|---|
| 1 | The use of each line reaches the harness. The demo state already knows the dish of each line (`request.lines[].dish`); the quote request does not. | Adrien (contract, gateway), Colette (agent tools) | a field on `Need`, copied into the signed quote |
| 2 | The judge's text is built from the rules of that use and the restaurant's settings, instead of one long text | Léon | the rules as a file (`scenarios/substitution-rules.json`, written once section 5 is decided) |
| 3 | The settings block in the policy model | Adrien | contract PR, section 7 |
| 4 | Rules the data states plainly move into code: price cap, frozen vs fresh and chilled vs ambient (`temperature_condition`), food vs non-food | Léon | a few lines each in `rules.py` |
| 5 | The ranking follows the restaurant's priority | Adrien, or Colette through `substitute_with` | |

The judge keeps the fuzzy questions: a different kind of product, made for another use, another variety, a composition change the dish would show.

## 10. Contradictions with the demo policy

**Decided 14/11 by Colette:**
- **C1. Coffee milk replaced by whole drinking milk.** The label `ok` in `pairs.csv` (463380 to 464768) stands; the rule adapts: drinking milk for coffee milk is `ok` with as much fat or more, `ask` with less. **Not written in `policy.demo.json` yet.** Léon's restaurant policy is merged (PR #33), so nothing blocks it any more. Léon edits this file on Saturday evening (`PLAN.md`): he writes C1 and C9 together, then runs button 2 again (section 6).
- **C2. The shortcut.** Decided: no shortcut (`"pre_accepted": "none"`). Since then PR #21 narrowed the shortcut to Valio-listed picks that lose nothing, and the milk act it would have broken is out of the video. On this menu no substitute is listed, so the judge runs either way. **Decided 14/11:** keep the narrow shortcut. Where it meets Q1c (a Valio-listed pick on a line with no known use), Q1c applies: `human` beats `auto`.
- **C3. "Never" cannot refuse.** Decided: see section 8.

Raised by this spec:
- **C4. Rules written for every use that depend on the use:** richer is `ok` (B11), chilled to UHT `ok` (B5), another flavour `ok` (B16). Decided since: frozen (B4, see C9) and another case size (B18: `ok` in `served`, `cooked` and `baking`).
- **C5. The policy holds an order.** `preferences_text` starts with a line about this order (Léon's version: "a 50-cover Nordic set menu, every dairy product is lactose free..."). The promise belongs in the policy; the use belongs to the order line.
- **C6. Piece size.** No rule speaks of it (B19). It is the button 2 case: squeaky cheese in 500 g pieces. **Decided 14/11:** `ok` for `served`, `ask` for `baking`. `cooked` and `drink` are still open.
- **C7. Non-food "the most similar item: ok".** Says nothing of dispenser fit, food contact or chemicals. Not on this menu.
- **C8. Price.** No rule stops a much dearer substitute (section 7, price cap).
- **C9. Frozen instead of fresh.** **Decided 14/11:** the default is `ask` for every use, and the kitchen can change it in its preferences. `policy.demo.json` still says "NEVER ACCEPT: frozen instead of fresh", and the chicken pair in `pairs.csv` is labelled `no`. Not written in `policy.demo.json` yet (see C1). The chicken label: keep it as that kitchen's own setting, or relabel it `ask`: `?`

## 11. Open questions

Answered on 14/11, written in their sections: Q1, Q1b, Q1c (section 4), Q2 (C2), and for Q4 the menu's cases of section 6 plus B2, B4, B15, B17, B18, B19 and B20 in `baking`.

Still open, all Colette's to decide:
- Q4: each `?` left in section 5, starting with the rest of the `baking` column.
- A1 and A2: the two proposed safety rules (section 3).
- C9: the chicken pair labelled `no` for frozen instead of fresh (section 10).
- Q5b: the restaurant's main priority and tie-break.
- Q6: the default of each setting (section 7).
- Q7: for "quality", which labels count, and are origin and grade part of it.

To do once decided, by their owners: C1 and C9 in `policy.demo.json` (Léon), the settings block and the use of each line in the contract (Adrien), the rules file `scenarios/substitution-rules.json` (Colette). Section 9 has the detail.
