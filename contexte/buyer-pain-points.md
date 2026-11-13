# Buyer pain points and objections to purchasing agents (Valio Aimo challenge)

Desk research done on 14/11/2026 to answer one question: what do professional kitchen buyers actually struggle with when ordering, and what makes them (and wholesalers) wary of agents that order on their behalf? Use it to choose the demo scenario and to prepare the pitch and the questions for the mentors.

## TLDR
- The recurring pain is not "searching the catalog", it is **what happens after the order**: substitutions nobody agreed to, short deliveries, price on the invoice different from the quote, credits never applied.
- Chefs cannot accept "the closest product": menus and recipes are fixed, so a substitution has to be judged against the dish, not the SKU.
- Buyers and analysts agree on the guardrails an agent needs: spend limits, an approved supplier list, human sign-off on risky decisions, and a timestamped trail of what was decided and why.
- Wrong orders are the problem of whoever deployed the agent, which is why the approval model and the audit log are not optional.
- Valio Aimo already has an AI assistant (A.I.mo) in its My Aimo portal, so a plain chatbot on top of the webshop will not stand out. The brief says the same.

## How reliable is this
- **No real forum voices.** Reddit is blocked for our search tool and for the Chrome extension, ChefTalk returned HTTP 409 to our browser, and RestaurantOwner.com only surfaced consultant articles and templates. Hacker News was the only forum we could read.
- Most sources are trade press and vendor blogs, which have a commercial interest. Numbers from vendors are marked as such. Treat everything below as hypotheses to test with a mentor or a real chef, not as findings.
- Not verified, do not cite: a 2024 lawsuit about an AI ordering system that wrongly confirmed a dish as peanut-safe (one compliance page, no corroboration), and a "4 to 10% of purchased food is wasted by over-ordering" figure (attributed to the National Restaurant Association, original not found).

## 1. What hurts buyers today
- **Substitutions they did not choose.** Operators describe substitutions without warning, items repeatedly out of stock, deliveries split over several days and products arriving close to their use-by date ([Restaurant Business](https://www.restaurantbusinessonline.com/financing/10-things-you-need-know-about-your-distributor)). Some substitutes are a cheaper off-brand item with no change on the invoice, so the advice is to name acceptable substitutes for key products in advance.
- **Menus are hardcoded.** A UX case study on Sysco's substitution flow notes that a chef cannot just take the next closest thing the way a consumer would ([case study](https://nathanportfolio.pages.dev/substitutions-case-study.html)).
- **Quote versus invoice.** A quoted price that differs from the invoiced price is the most cited early warning to switch supplier, and the advice is to log shortages and substitutions by date: two shorts in three weeks is a pattern ([Nine Guides](https://nineguides.pages.dev/suppliers/switching-food-distributors)).
- **Credits never applied.** Short deliveries often never get credited, and signing the delivery receipt makes the receiver responsible for what was actually delivered ([Restaurant Business](https://www.restaurantbusinessonline.com/financing/10-things-you-need-know-about-your-distributor)). One line item mismatch can get a whole invoice rejected and start a dispute that lasts weeks ([SDCExec](https://www.sdcexec.com/home/article/22965872/recvue-how-inefficient-billing-processes-increase-risk-in-food-logistics)).
- **Errors cost the relationship.** Rekki says restaurants typically start looking for another supplier after two mistakes in two months ([Rekki](https://rekki.com/article/the-hidden-cost-of-order-errors-why-food-wholesalers-need-to-rethink-their-process)). This is a vendor figure with no published method.
- **Standing orders drift.** They fire on a schedule and do not see stock on hand, so surplus builds up week after week. The usual fix is to generate them as drafts that a human reviews before they go to the supplier ([Supy](https://supy.io/blog/learn-standing-orders-vs-manual-reordering)).
- **Comparing and ordering takes time.** One ChefTalk thread excerpt mentions people spending 6 to 8 hours a week comparing prices and talking to sales reps ([thread](https://www.cheftalk.com/threads/how-do-you-order-supplies.116110/)). We could only read the search excerpt, so this is a single anecdote.

## 2. Objections to agents that order alone
- **Low risk tolerance in B2B.** The likely direction is agents supporting human decision makers, with strong guardrails and shared responsibility, not full automation ([PYMNTS](https://www.pymnts.com/news/b2b-payments/2025/agentic-ai-needs-to-solve-for-trust-before-conquering-b2b/)). A Bain figure cited by TechRepublic says only 24% of consumers are comfortable letting AI complete a purchase (consumers, not B2B, so a proxy at best) ([TechRepublic](https://www.techrepublic.com/article/agentic-commerce/)).
- **Agents without business context fail in predictable ways**: recommending unavailable stock, ignoring approval requirements, breaking procurement policy. Accuracy and trust matter more than speed in B2B ([HCL](https://proda.hcl-software.com/blog/commerce/agentic-ai-in-b2b-commerce-is-different-from-b2c)).
- **Agents do not ask clarifying questions.** They need structured, explicit data or they move on ([Elastic Path](https://www.elasticpath.com/blog/everyone-is-fighting-over-the-wrong-part-of-agentic-commerce)). This supports the brief's idea of a structured, verifiable interface.
- **Who is liable for a wrong order.** The consensus in Hacker News threads is that whoever authorizes the agent carries the liability, which is why companies set spending limits and an approved vendor list instead of approving every purchase ([SaySigned thread](https://news.ycombinator.com/item?id=46989782)). eBay banned "buy for me" agents partly over wrong orders at scale, and one commenter says a marketplace would need a way to pause, inspect and assign responsibility at execution time ([eBay thread](https://news.ycombinator.com/item?id=46711574)). These are commenters' views, not legal advice.
- **Allergens.** A supplier switching an oil or an ingredient silently changes a dish's allergen profile, and recipe data goes stale. Advice is to treat AI output as a suggestion and have a second pair of eyes check a modified dish ([Hostie](https://www.hostie.ai/resources/voice-ai-allergy-dietary-questions-menu-aware-bots-2025)).
- **Wholesalers fear losing the customer.** Brands that give data ownership to an agent platform risk losing pricing power and the direct client relationship ([Starr Conspiracy](https://www.thestarrconspiracy.com/insights/newsfeed/the-real-risk-in-agentic-commerce-14e404)). This is analyst commentary, not a survey. It is the "who owns the customer relationship" worry in the brief.
- **Guardrail patterns people suggest**: approval thresholds that are tuned as the agent earns trust, and decisions logged with a timestamp and reproducible logic instead of "trust me" ([Cleverence](https://www.cleverence.com/amp/articles/business-blogs/2026-b2b-procurement-15t-shifts-to-ai-agents-5721/)). Computing cites a Gartner forecast that agents could mediate 90% of B2B buying by 2028, and frames governance as the next question for CIOs ([Computing](https://www.computing.co.uk/news-network/2026/agentic-procurement-is-moving-from-theory-to-reality-are-cios-ready-to-govern-it)).

## 3. Valio Aimo today
- Customers order through a webshop that needs a customer number, through VALO Tilauspalvelu, or at cash and carry (open to any business customer).
- The My Aimo portal already includes an AI assistant called A.I.mo, with human Aimo experts reachable by message ([My Aimo](https://www.valioaimo.fi/en/become-a-customer/my-aimo.md)).
- We found nothing public on a Valio Aimo marketplace, on third-party sellers, or on agents that buy or sell for customers, and no customer reviews of the webshop.
- Small mismatch to keep in mind: the brief says 25,000 product names, the Valio Aimo site says more than 20,000 products, and the product file has 17,546 records.

## What it means for our design
These are ideas for the team to decide, not decisions. They line up with the judging criteria (autonomy and controls 20%, exceptions 15%, working end-to-end demo 30%).
1. **Ranked substitution** (good, better, best) judged against the request, never automatic when the allergen profile changes or the allergen data is missing. This reuses the rule already in `valio-aimo-resources.md`.
2. **"Promised versus delivered" record**: prices are fixed in the brief, so the remaining gap is short or partial delivery. Log what the agent was promised (`availableDate`, amount) so a credit can be claimed.
3. **Approval thresholds** by amount and by decision type, with a decision log that both the buyer and Valio Aimo can read.
4. **Standing orders as drafts** with drift detection before sending, which is one of the example scenarios in the brief.

## Questions to ask a mentor or a real chef
1. When a supplier substitutes a product, what do you check before accepting it, and what makes you reject it?
2. How do you find out about a short delivery, and what does it take to get the credit?
3. Which orders would you let an agent place alone, and what is the spend limit before you want to see it?
4. Who in your kitchen signs off on an order, and what would you need to see in a log to trust it?
5. For a school or hospital kitchen: what allergen checks are mandatory on a substitution?

## Sources not opened
- ChefTalk threads that looked relevant but returned HTTP 409: [Comparing Suppliers' Prices](https://www.cheftalk.com/threads/comparing-suppliers-prices.78550/) and [signature item not available](https://www.cheftalk.com/threads/what-happens-when-you-propose-a-menu-and-the-signiture-item-is-not-available.64950/). If one of us can open them in a normal browser, paste them into this file.
