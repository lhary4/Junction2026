# Valio Aimo: what the resource portal actually gives us

Explored on 13-14/11/2026 from https://junction26.valioaimo.fi/ (event password in the team chat) and tested against the live mock APIs. Read this before designing anything: it changes what we have to build.

## TLDR
- Two **read-only** mock APIs (price, availability) plus four static files (product data, its JSON schema, delivery reliability, carbon footprint).
- **There is no order API.** Quote, order, approval rules and audit log are ours to build. That is exactly what the judges score (autonomy and controls 20%, exceptions 15%).
- The API doc forbids querying the whole catalog: search the static product file first, call the APIs only on a shortlist. Undisclosed rate limits apply.
- The brief's example works: the catalog has 32 lactose-free milk products, including 10 L Novobox formats.
- The portal home page holds no rules, FAQ or judging notes: it only lists the materials, the data caveats and the API access (checked again on 14/11/2026). Rules and criteria live in the brief, `contexte/challenge-1-valio-aimo.md`.

## What the portal home page says (14/11/2026)
- The challenge material is six items: pricing API, availability API, product data file, its JSON schema, delivery reliability file, carbon footprint file.
- **Data licence caveat**: the data is "inspired by real world" but "does not contain fully accurate product information and must not be used for anything outside of this challenge". Do not reuse it in other projects, and do not present it as real Valio Aimo data in a public demo.
- Product data quality varies by maker: factory-made meals with a GTIN usually have precise nutrition and allergen data, fruit and vegetables often do not.
- Delivery reliability and carbon footprint do not cover every product. Carbon is the average of the product group, not a measure of the product.
- **The files do not change during the challenge** unless announced separately (OpenAPI description). Cache them locally and do not re-download on every run.
- In the real world, prices and availability are customer specific and change constantly (OpenAPI description). This is the official reason the APIs must only be called on a shortlist: say it in the pitch as a design choice, not a workaround.
- `GET /api/ping` exists as a health check (needs the API key). Use it to test the key before debugging anything else.

## APIs
Base URL `https://junction26.valioaimo.fi/api`. Every call needs the header `X-API-Key: $VALIO_AIMO_API_KEY` (key on the Junction platform dashboard, put it in `.env`). Without it: HTTP 401. Docs: `/docs` (Swagger), `/redoc`, `/openapi.json`.

Both POST endpoints take the same body:

```json
{ "customer": "demo", "requestedDate": "2026-11-17", "products": ["463038", "464179", "462775"] }
```

`products` holds 1 to 1,000 product codes (more is HTTP 422). `customer` has no effect in the mock, any string works.

### `POST /api/availability`
| Field | Meaning |
|---|---|
| `closingTime` | Order cut-off: order before this to receive goods on `availableDate`. |
| `salesBlock` | If true, the product cannot be ordered right now. |
| `logisticModel` | `Stock`: Valio Aimo holds it and knows the quantity. `Terminal`: shipped from the supplier's warehouse, quantity unknown. |
| `scheduleLines[]` | One entry if available, empty if it cannot be delivered on any date. |
| `scheduleLines[].availableAmount` | Quantity in `salesUnit`. Always `999999` for Terminal products (unknown). `0` means not available. |
| `scheduleLines[].availableDate` | Earliest date the amount is available. **Can differ from the requested date.** |

### `POST /api/price`
Per product: `catalogPrice` (before tax, plus `valueWithTax`), `priceWithTax`, `comparisonPrice` per `comparisonUnit` (`KG` or `L` only, use it to compare pack sizes), `tax` (`taxRate`, `taxValue`), `listPrice` (before customer discount), `validFrom`/`validTo`, `netPriceFound` (customer-specific price found or not), `error` (no price found). Currency EUR.

### What the live test showed (requested date 17/11/2026, called on 14/11 at 00:04)
| Code | Product | Model | Available | Unit price excl. tax | Per litre |
|---|---|---|---|---|---|
| 463038 | Valio Eila semi-skimmed lactose free 10 l Novobox | Terminal | 999999 `KI`, on 16/11 | 31.31 € | 1.57 € |
| 464179 | Arla 10 L Novobox lactose free ESL | Terminal | 999999 `ST`, on 16/11 | 27.22 € | 2.72 € |
| 462775 | Arla milk drink 1 L lactose free UHT | Stock | 51 `ST`, on 16/11 | 2.57 € | 2.57 € |

Things we learned from it:
- **`validTo` is `9999-12-31`** on all three. The price validity period is not a quote expiry: if we want time-bound quotes, we define the expiry ourselves.
- **Sales units hide the real quantity.** 31.31 € at 1.57 €/L means one `KI` of the Valio Novobox is about 20 L, not 10 L. Converting "1,000 litres" into units to order needs `units[].sizeInBaseUnits` from the product file plus the comparison price, and must be tested.
- **`closingTime` was already in the past** (12/11) for the two Terminal products while `availableDate` was 16/11. Unclear whether that is mock behaviour or a real signal. Question for the mentors.
- Stock products give a real quantity (51 here), which is enough to demo partial availability.

## Static files
Download links are on the portal home page (behind the event password) and through `/api/products/download`, `/api/delivery-reliability/download`, `/api/carbon-footprint/download`. Do not commit them: the product file is 86 MB. Fetch them at setup.

| File | Content | Coverage |
|---|---|---|
| Product data (JSON, 86 MB) | 17,546 products, 648 vendors, 349 categories | see below |
| Product data schema (JSON Schema) | Describes the product file | |
| Delivery reliability (CSV `productId,deliveryReliability`) | Share of ordered quantity historically delivered, 0 to 1 | 4,425 products; 2,490 at 1.0, 291 below 0.9, 94 below 0.7 |
| Carbon footprint (CSV `productId,AVG kg CO2-eq/kg`) | Average for the **product group**, not the product | 11,033 products |

### Product record
Top-level fields: `id` (the code used by the APIs), `salesUnitGtin`, `salesUnit`, `baseUnit`, `category`, `allowedLotSize`, `deleted`, `temperatureCondition`, `vendorName`, `countryOfOrigin`, `units` (pallet, carton, unit with `gtin` and `sizeInBaseUnits`), `deposits`, `synkkaData`.

`synkkaData` (GS1 Synkka product data) holds names in `fi`, `en`, `sv`, marketing texts, ingredients, storage and preparation instructions, brand, VAT code, min and max temperature, and `classifications`:
- `allergen` and `nonAllergen`: GS1 allergen codes with `CONTAINS` or `FREE_FROM` (for example `AM` milk, `AE` egg).
- `nutritionFact`, `gda`, `vitamin`, `mineral`, `composition`: values per 100 g (lactose is `LACS`).
- `nutritionalClaim`, `packaging`, `packagingMarkedLabel`.

Data quality varies by product: factory-made meals are complete, fruit and vegetables often are not.
- Allergen data present for 9,436 products (54%). **46% have none: for an allergen-safe kitchen, "unknown" must never count as "free from".**
- Nutrition present for 12,244 products.

Most frequent labels (`packagingMarkedLabel`), useful for the sustainability comparison: Goods from Finland blue swan (2,057), Made in Finland key flag (1,772), Finnish heart symbol (826), EU organic (456), Svanen (362), Rainforest Alliance (234), EU Ecolabel (195), MSC (104), Fairtrade (92), ASC (51), KRAV (26).

## What this means for the design
- **Search locally, price remotely.** Build a local index of the product file (names, category, allergens, labels, units) for search and filtering, then call price and availability only on the shortlist.
- **Order, quote, approval and audit are ours.** Nothing in the mock places or stores an order.
- **Exceptions are already in the data.** Use them in the demo:
  - `closingTime` makes an approval that comes too late miss the delivery, so the guardrail has a deadline.
  - Terminal products have unknown stock: combine with delivery reliability to express how much the buyer can trust the promise.
  - Missing allergen data has to route to a human, never to auto-substitution.
  - `availableDate` later than requested, or partial stock, means split the order or rank substitutes (price per litre, labels, carbon).

## Open questions for the mentors
- What does a `closingTime` in the past mean when `availableDate` is in the future?
- Are the `999999` Terminal quantities ever really constrained in the mock, or always unlimited?
- Do they expect us to model a customer (contract prices, approval roles), given that `customer` has no effect?
