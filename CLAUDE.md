# Junction 2026 (hackathon, Helsinki)

Team project for Junction, November 2026. Repo owned by Léon: github.com/lhary4/Junction2026 (private).

## Language
- Everything in this repo is written in English: code, comments, commit messages, branch names, PRs, issues, docs. Even when a teammate talks to Claude in French.

## Team
- Adrien, Léon, Colette. Everyone codes, with Claude Code as a pair. Nobody is a seasoned developer: explain choices, keep the code simple, prefer boring, well-documented tools.

## Challenge
- Two candidates, decision pending. Full briefs in `contexte/`:
  - `contexte/challenge-1-valio-aimo.md`: Trusted Trade Agents (Valio Aimo).
  - `contexte/challenge-2-meta-glasses.md`: AI Glasses for Everyone, Everyday (Meta).
- Once the team decides, write the choice here and delete nothing from `contexte/`.

## Where things live
- `contexte/`: raw challenge context (briefs, rules, API docs, judging criteria, mentor notes). Never put secrets there.
- Code goes at the root once the challenge and stack are chosen.

## Git rules (three people coding at once)
- `main` always works. Nobody pushes directly to `main`, and nobody uses "Commit directly to main" on github.com. The repo is private on a free plan, so GitHub cannot enforce it: it is a team rule.
- One task = one `feat/...` branch = one small PR, merged fast (aim for one every one to two hours). Long-lived branches create painful conflicts.
- Before starting a task: update `main` (`git switch main && git pull`), then create the branch from it.
- Each person owns an area of the code. If two people must edit the same file, say it out loud first.
- After someone merges, everyone brings `main` into their branch (`git merge main`) before continuing.
- A PR is merged by its author once it builds and a teammate has clicked through it. Squash merge.

## Secrets
- API keys and passwords live in `.env` (ignored by git), shared through the team chat. `.env.example` lists the variable names without values.
