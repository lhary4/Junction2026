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

## Open choices (to decide, then move up)
Each line becomes a full entry once the team decides. Order is roughly the order we need the answer in.
- **Challenge**: Valio Aimo (ordering agents) or Meta (AI glasses).
- **Stack**: language and framework for the app (for example a Next.js web app, or a Python backend with a simple web page).
- **Models and hosting**: which AI model the agent uses, who runs it (a provider's API or a model we host ourselves), and what it costs per demo.
- **Protocols**: how agents talk to each other and to the supplier (for example MCP, OpenAPI, Google's UCP), and whether we follow one standard or build our own simple format.
- **Guardrails**: the rules the agent cannot break on its own (budget limits, allergens, delivery dates) and when it must ask a human.
- **Signatures and trust**: how a buyer can prove an order or a quote really came from its agent and was not changed (for example signed messages with JWS).
- **Data**: how we store and search the 17,546 products (a local index built from the product file, never committed to git because it weighs 86 MB).
- **Audit log**: where we record what each agent did and why, so a human can check it afterwards.
- **Payments (bonus)**: whether agents pay for real (x402 on a test network, Nevermined) or we only simulate payment.
- **Hosting the demo**: where the app runs during judging (a laptop, Vercel, another host).

## Choices we dropped
Nothing yet.
