# Mentor notes: a talk with a Valio Aimo engineer

A conversation during the hackathon, written up on Saturday 14/11/2026. The person works on the technology side: the web shop, the customer portal (which they helped build over the last two years) and the AI features. Summary of a recorded conversation, in our words. The recording itself is not in the repo.

## What they said

**Where the agent lives**
- In the short term, the buying agent would most likely be part of Valio Aimo's own web store and customer portal.
- Some customers have an agent inside their own ERP and would like it to buy from Valio Aimo. For them, an MCP-style interface is one option.
- Most customers, by number, have no ERP. Bigger restaurant chains and hotels may have one. For the others, inventory is often a spreadsheet and recipes are in a notebook.

**Two constraints on any technical interface**
- The customer must be identified, with an authentication token or something similar, because **prices and the catalog are specific to each customer**. One customer does not see the same prices as another.
- **Part of the intelligence should stay on Valio Aimo's side.** If they only expose plain data APIs, they depend on each customer building a good agent, and they cannot do anything when it works badly.

**Recipes, stock and history**
- The customer portal already lets customers manage their recipes and their inventory, if they want to. An agent in the portal could read them there.
- We cannot know their real data structures: we may mock recipes and stock.
- Kitchens count their stock by hand, about weekly. Orders are placed weekly or a few times a week.
- The portal has reports on past purchases. That history is not shared for the challenge, but we may assume it exists and generate synthetic data.
- Pick a customer we can relate to: restaurant, hotel or hospital makes no difference to them.

**Substitution**
- Price against culinary quality: "it depends" on the use and on the customer. A product used as an ingredient in a sauce can be flexible. For baking it can be very strict: only that exact product works.
- Letting the customer set general preferences, or building a profile that is applied to every order, is a good idea.

**What they have today**
- An AI assistant in the customer portal that answers questions from the purchase reports, for example how many kilograms of a product the customer bought on a given day last year.

**The competition**
- This is one of the most chosen challenges of the event, so there will be many submissions. To do well, a team needs something no one else will show, and must put it front and centre.

## What we do with it

| What they said | What we do |
|---|---|
| The agent first lives in the portal, MCP is for customers with an ERP | The demo page looks like a customer portal. MCP stays as the second door, with the same gateway behind it |
| Prices are per customer, a token must identify the customer | Today the gateway has no authentication and the `customer` field comes from the request. A customer token on the gateway is on Adrien's list for Saturday evening, after the demo flow |
| Intelligence stays on Valio's side | Already our design: the gateway converts units, ranks substitutes and signs the quote. Say it in the pitch |
| Substitution depends on the use, a preference profile is a good idea | The buyer's policy holds the kitchen's preferences in plain words, and the judge reads them for every substitute |
| Recipes and stock can be mocked | The restaurant case in `scenarios/restaurant-case/` |
| Many teams, show a difference up front | Real signatures: the verdict decides who signs, and Valio refuses an order without a valid mandate |

## Still open

The three questions at the end of `contexte/valio-aimo-resources.md` were not asked in this talk: what an order cut-off in the past means when the available date is in the future, whether the `999999` quantities are ever constrained, and whether they expect us to model a customer.
