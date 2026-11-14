# Restaurant case: a Nordic November menu, 50 covers a service

A Helsinki restaurant runs one set menu (starter, main, dessert) for 50 covers a dinner service. It orders from Valio Aimo for three services: Thursday 19, Friday 20 and Saturday 21 November 2026, delivered on Thursday 19.

Every ingredient is a real product of the challenge catalog. The machine-readable order, with every product fact, is in [order.json](order.json). Facts in this page come from that file: the data files (names, allergens, labels, carbon, reliability) and the live mock API called on 14/11/2026 with requested date 19/11/2026 (price before VAT, availability). Prices and stock change: re-run the calls before a demo.

The kitchen keeps one promise for the whole menu: **every dairy product is lactose free.** The menu uses no peanuts and no tree nuts.

## The menu

| Course | Dish |
|---|---|
| Starter | Cured rainbow trout, roasted Finnish beetroot, horseradish smetana, rye crisp, dill |
| Main | Sautéed reindeer (poronkäristys), butter-mashed almond potatoes, lingonberries, pickled cucumber |
| Dessert | Warm squeaky cheese (leipäjuusto), cloudberry jam, whipped cream, oat crumble |

### Allergens, as the data states them

GS1 codes: AF fish, AM milk, AW cereals containing gluten, NR rye, GO oats, AS sesame. "Unknown" means the product file has no allergen data for that product. Unknown is never read as safe.

| Dish | Contains (declared) | May contain (declared) | Products with no allergen data |
|---|---|---|---|
| Starter | AF (trout), AM (smetana), AW, NR (crispbread) | AS (crispbread) | red and yellow beetroot, fresh horseradish, dill |
| Main | AM (milk, butter) | none | reindeer strips, almond potatoes, onions |
| Dessert | AM (cheese, cream, butter), AW, GO (oat flakes) | none | cloudberry jam (Valio 2.5 kg) |

## Recipes, for 50 covers

Quantities are for one service. The order quantities for three services, rounded to what can be bought, are in the shopping list below.

### Starter: cured rainbow trout, beetroot, horseradish smetana

| Ingredient | Product | Per service |
|---|---|---|
| Rainbow trout fillet A | 461921 | 3.3 kg raw (about 58 g a plate once trimmed) |
| Fine sea salt (cure) | 468172 | 130 g |
| Caster sugar (cure) | 460325 | 130 g |
| Dill | 460395 | 1 bunch in the cure, 1 bunch to garnish |
| Red beetroot | 460837 | 4 kg |
| Yellow beetroot | 460810 | 1.5 kg |
| Rapeseed oil | 466608 | 0.2 l |
| Smetana, lactose free | 476890 | 1.5 kg |
| Fresh horseradish | 460727 | 150 g |
| Thin rye crispbread | 467958 | 2 packs of 300 g |

1. Two days before the first service, cure the whole 10 kg box at once: mix 40 g salt and 40 g sugar per kg of fish with chopped dill, cover the fillets, press, chill 36 hours. Rinse, pat dry, wrap. Cured trout keeps four days chilled.
2. Roast the beetroot whole in foil at 200 °C, 60 to 75 minutes. Peel warm, cut in wedges, dress with rapeseed oil and salt. Keep red and yellow apart so the colours do not bleed.
3. Grate the horseradish finely into the smetana, season with salt. Make it the day of service.
4. Plate: slices of trout, beetroot wedges, a spoon of horseradish smetana, a shard of rye crispbread, dill tips.

### Main: sautéed reindeer, mashed almond potatoes, lingonberries

| Ingredient | Product | Per service |
|---|---|---|
| Reindeer strips for sautéing, frozen | 465607 | 7.5 kg (150 g a plate) |
| Butter, lactose free, salted | 463437 | 0.75 kg for the reindeer, 1 kg for the mash |
| Onions | 460195 | 1.5 kg |
| Fine sea salt | 468172 | 75 g reindeer, 60 g mash |
| Ground black pepper | 461009 | 10 g |
| Almond potatoes | 460078 | 11 kg raw (about 200 g mash a plate) |
| Lactose-free semi-skimmed milk | 464306 | 2.5 l |
| Lingonberry jam | 465815 | 1.5 kg (30 g a plate) |
| Pickled cucumbers | 468513 | about 1.25 kg drained (25 g a plate) |

1. Thaw the reindeer overnight in the cold room. Break the strips apart.
2. In wide pans, melt butter, brown the reindeer in small batches so it fries and does not boil. Add sliced onion, then water to just cover. Simmer covered 40 minutes, until tender. Season with salt and pepper at the end.
3. Peel the almond potatoes, boil in salted water until soft, drain well. Mash with hot milk and butter. Keep warm, covered.
4. Plate: mash, reindeer with its juices, a spoon of lingonberry jam, slices of pickled cucumber.

### Dessert: warm squeaky cheese, cloudberry jam, whipped cream, oat crumble

| Ingredient | Product | Per service |
|---|---|---|
| Squeaky cheese (leipäjuusto), lactose free | 474880 | 3.5 kg (70 g a plate) |
| Butter, lactose free, salted | 463437 | 150 g for the cheese, 250 g for the crumble |
| Cloudberry jam | 469044 | 1.5 kg (30 g a plate) |
| Whipping cream, lactose free | 464194 | 1.25 l |
| Wholegrain oat flakes | 460200 | 500 g |
| Caster sugar | 460325 | 200 g |

1. Crumble, in the afternoon: toss oat flakes with melted butter and sugar, bake at 175 °C for 12 to 15 minutes, stirring once, until golden. Cool, keep dry.
2. Whip the cream to soft peaks just before service. Keep chilled.
3. Cut the cheese in wedges. To order, warm it in a buttered pan or under the salamander until it browns and softens.
4. Plate: warm cheese, a spoon of cloudberry jam, whipped cream, crumble on top.

## Shopping list for the three services

Prices are before VAT, from the live API on 14/11/2026. Order quantities are in the product's sales unit.

| Product | Name | Order | Unit price | Line |
|---|---|---|---|---|
| 461921 | Kalavapriikki rainbow trout fillet A | 10 kg | 16.48 | 164.80 |
| 460837 | Red beetroot washed, Finland | 12 kg | 1.00 | 12.00 |
| 460810 | Yellow beetroot washed, Finland | 5 kg | 1.92 | 9.60 |
| 476890 | Valio smetana 2 kg lactose free | 3 tubs | 13.06 | 39.18 |
| 460727 | Horseradish, Hungary | 0.5 kg | 15.32 | 7.66 |
| 460395 | Dill bunch 100 g, Finland | 6 | 2.12 | 12.72 |
| 467958 | Vaasan thin rye crispbread 300 g | 6 | 1.70 | 10.20 |
| 465607 | Rönkä reindeer strips 5 kg, frozen | 5 packs | 158.71 | 793.55 |
| 460078 | Almond potatoes washed | 33 kg | 0.93 | 30.69 |
| 464306 | Valio Eila semi-skimmed milk 1 l lactose free | 8 | 1.01 | 8.08 |
| 460195 | Onions 10 kg, Finland | 1 sack | 15.34 | 15.34 |
| 465815 | Marjex lingonberry jam 3 kg | 2 | 19.92 | 39.84 |
| 468513 | Myrttisen pickled cucumber 4.5 kg | 2 | 17.22 | 34.44 |
| 474880 | Riitan Herkku squeaky cheese lactose free | 13.4 kg | 12.86 | 172.32 |
| 469044 | Valio cloudberry jam 2.5 kg | 2 | 30.80 | 61.60 |
| 464194 | Valio whipping cream 1 l UHT lactose free | 4 | 3.91 | 15.64 |
| 460200 | Elovena wholegrain oat flakes 1 kg | 2 | 2.76 | 5.52 |
| 463437 | Valio Eila butter 500 g salted lactose free | 13 | 3.31 | 43.03 |
| 468172 | Meira fine sea salt 800 g | 2 | 1.34 | 2.68 |
| 460325 | Dansukker caster sugar 1 kg | 2 | 1.55 | 3.10 |
| 461009 | Meira ground black pepper 480 g | 1 | 16.50 | 16.50 |
| 466608 | Apetit rapeseed oil 10 l | 1 | 25.02 | 25.02 |
| | **Total before VAT** | | | **1,523.51** |

## What the live data shows on this order

Facts only. What to do with each one is the team's decision: write it in the last column, or in `policy.demo.json`.

| # | Line | What the data says | Candidates in the catalog | Decision |
|---|---|---|---|---|
| 1 | Whole order | Total 1,523.51 EUR before VAT. The demo policy's autonomous limit is 1,500 EUR. | | |
| 2 | Yellow beetroot 460810 | Cannot be delivered on any date (no schedule line). | Chioggia beetroot 460787: cannot be delivered either. Red beetroot 460837: 76 kg in stock. | |
| 3 | Lingonberry jam 465815 (3 kg) | Cannot be delivered on any date. | 462198 Dronningholm 1 kg: 276 in stock, allergen data present (none declared), 6.54 EUR/kg. 460157 Saarioinen 500 g: 300 in stock, no allergen data, 7.24 EUR/kg. 460748 Saarioinen 6 kg: not deliverable. | |
| 4 | Cloudberry jam 469044 (Valio 2.5 kg, chilled) | Cannot be delivered on any date. No allergen data. | 466574 Kalas 1.5 kg: 401 in stock, origin Sweden, ambient, no allergen data, 16.19 EUR/kg. 463569 Meritalo 310 g: 11 cases of 8 in stock, Finland, allergen data present (none declared), 21.31 EUR/kg, order cut-off 13/11 already past, delivery reliability 0.898. | |
| 5 | Squeaky cheese 474880 (fresh) | Terminal product (stock unknown), order cut-off 11/11 already past, available date 16/11. Lot size 6.7 kg. | 467148 same maker, **frozen**: 177 kg in stock, 12.69 EUR/kg. 475072 Haapalan 500 g pieces, chilled, lactose free: 100 in stock, 10.94 EUR/kg, no carbon data. | |
| 6 | Reindeer 465607 | Terminal product, order cut-off 12/11 already past, available date 16/11. No allergen data. 793.55 EUR, more than half the order. | 465853 same product, other code: 149.12 a pack, same cut-off. 465887 3 kg packs: 32.38 EUR/kg, same cut-off. All without allergen data. | |
| 7 | Rainbow trout 461921 | Terminal product, order cut-off 12/11 already past. Origin Norway. Lot size 10 kg. | 462016 trout fillet C, Finland: 40 kg in stock, 15.77 EUR/kg, no allergen data. 461868 Benella whole trout: not deliverable. | |
| 8 | Black pepper 461009 | Terminal product, order cut-off 12/11 already past. | | |
| 9 | Fresh produce | Beetroot, horseradish, dill, potatoes, onions, reindeer: no allergen data, as the portal warns for fruit, vegetables and raw meat. | | |

Things worth knowing before using this case:
- The "cut-off already past, available on 16/11" pattern is the open question in `contexte/valio-aimo-resources.md`. Ask the mentors before building a demo act on it.
- `availableAmount` of 9999999999 on Stock products reads as "plenty" in the mock. `order.json` stores it as null (unknown), like the 999999 of Terminal products.
- Carbon figures are averages of the product group, not of the product. The reindeer group is 3.49 kg CO2e/kg frozen and 9.21 chilled; the trout group 6.375.
- Some products list Valio's own substitutes (`substitutions` field): butter 463437 lists 462421 and 464076, cream 464194 lists 463837 and 469346, milk 464306 lists the four from the demo.
