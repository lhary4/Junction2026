# Team folders

One folder per person. Each holds two files:
- `START.md`: your steps, in order, with what you need, what to run and when a step is done.
- `notes.md`: yours to fill. Results, numbers, questions for the others.

## How to start a session

In a terminal, at the root of the repo:

```
git switch main
git pull
claude
```

Then type one line, with your own name:

```
Read PLAN.md and team/leon/START.md, then start at step L1.
```

When a step is done and its PR is merged, start the next one the same way (`then start at step L2`). A fresh session per step keeps things simple: one step, one branch, one PR.

## Who is where

| Person | Folder | Lane |
|---|---|---|
| Adrien | `team/adrien/` | Contract, signing library, Valio gateway |
| Léon | `team/leon/` | Harness: judge, rules, audit log, signer |
| Colette | `team/colette/` | Surface, agent tools, demo and pitch |
