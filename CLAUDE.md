# Junction 2026 (hackathon, Helsinki)

Team project for Junction, November 2026. Repo owned by Léon: github.com/lhary4/Junction2026 (private).

## Language
- Everything in this repo is written in English: code, comments, commit messages, branch names, PRs, issues, docs. Even when a teammate talks to Claude in French.

## Team
- Adrien, Léon, Colette. Everyone codes, with Claude Code as a pair. Nobody is a seasoned developer: explain choices, keep the code simple, prefer boring, well-documented tools.

## Challenge
- **Decided on 14/11/2026: Valio Aimo, Trusted Trade Agents.** Brief: `contexte/challenge-1-valio-aimo.md`. What the APIs and data files really contain: `contexte/valio-aimo-resources.md`. What professional buyers struggle with and what makes them wary of ordering agents (desk research, no real forum voices): `contexte/buyer-pain-points.md`.
- The other candidate, `contexte/challenge-2-meta-glasses.md` (Meta), was not chosen. Delete nothing from `contexte/`.
- Submission: Sunday 15/11/2026 at 10:00.

## Start here
- `PLAN.md`: the idea, the architecture, the four acts of the demo, who owns what, the timeline.
- `team/<your-name>/START.md`: your steps, in order. Start a session with `Read PLAN.md and team/<your-name>/START.md, then start at step ...`.
- `docs/contract.md` and `contract/examples/`: the messages the pieces exchange. Code against them.

## Where things live
- `contexte/`: raw challenge context (briefs, rules, API docs, judging criteria, mentor notes). Never put secrets there.
- `TECH-CHOICES.md`: every technical choice and its consequences, in plain words. Read it first when you join or come back after a break.
- `docs/spec-v0/`: the first spec, kept for reference. It describes an invented API: do not build from it. `docs/spec-v0/README.md` says what was kept.
- `spikes/`: small scripts that proved a choice works. Not product code.
- `data/` and `state/` are created locally and ignored by git.

One owner per folder. Do not edit a folder you do not own: ask its owner.

| Folder | Owner | Content |
|---|---|---|
| `contract/`, `trust/`, `common/clock.py`, `pyproject.toml`, `scripts/` | Adrien | Pydantic models, AP2 signing library, freezable time, dependencies, data scripts |
| `merchant/` | Adrien | Valio gateway: search, quote, order, receipt |
| `harness/`, `common/audit.py` | Léon | Rules, Gemini judge, signer, approvals, hash-chained log |
| `surface/`, `agent_mcp/`, `scenarios/`, `docs/demo-script.md` | Colette | Page, MCP tools, demo policy, prompts, pitch |
| `team/<name>/` | Each person | `START.md` and `notes.md` |
| `tests/` | Everyone | One file per area, named after it |

`contract/` and `trust/` are shared by everyone: they change only through a small PR announced out loud.

## Rules the product must keep
- The agent never decides a fact. Prices, stock, allergens and totals come from the gateway, in a signed quote.
- The agent never holds a key and never sees a token. It passes short identifiers.
- No signature, no order. `deny` beats `human`, `human` beats `auto`.
- Unknown is never read as safe: missing allergen data goes to a human.
- A human approves on the page in `surface/`, never in the chat.

## Git rules (three people coding at once)
- `main` always works. Nobody pushes directly to `main`, and nobody uses "Commit directly to main" on github.com. The repo is private on a free plan, so GitHub cannot enforce it: it is a team rule.
- One task = one `feat/...` branch = one small PR, merged fast (aim for one every one to two hours). Long-lived branches create painful conflicts.
- Before starting a task: update `main` (`git switch main && git pull`), then create the branch from it.
- Each person owns an area of the code. If two people must edit the same file, say it out loud first.
- After someone merges, everyone brings `main` into their branch (`git merge main`) before continuing.
- A PR is merged by its author once it builds and a teammate has clicked through it. Squash merge.

## Tech choices file (mandatory on every PR)
- `TECH-CHOICES.md` explains every technical choice in plain words (guardrails, signatures, protocols, models and hosting, data, payments...) and what it changes for us. It exists because none of us is a seasoned developer: anyone must be able to read it and understand how the product works.
- Every PR that adds, changes or removes a technical choice updates `TECH-CHOICES.md` in the same PR, so the file is up to date the moment the PR is merged. A PR that changes no choice writes "Tech choices: no change" in its description.
- Claude: before opening or merging a PR, check whether the diff introduces a choice (a new library, a model, a protocol, a rule the agent follows, a hosting decision, a data format). If it does and the file is not updated, update it first. Follow the template at the top of the file, simple words, no code.
- A teammate reviewing a PR checks this file too: if they cannot understand the new entry, the PR is not ready.

## Secrets
- API keys and passwords live in `.env` (ignored by git), shared through the team chat. `.env.example` lists the variable names without values.
