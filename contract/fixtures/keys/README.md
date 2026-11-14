# Demo keys: DEMO ONLY, they protect nothing real

Three ES256 (P-256) private keys as JWK files, committed so the same signed fixtures verify on every laptop.

- `manager.json`: the buyer's manager. Signs the open mandates in advance, and signs an order directly when a human approves it.
- `agent.json`: the buying agent's key, held by the harness, never by the agent itself. Closes the open mandates for one quote.
- `merchant.json`: Valio Aimo's gateway. Signs quotes and receipts. Its public half is served at `/.well-known/jwks.json`.

Anyone with this repo can sign as any of the three. Real keys would never be in git.

`scripts/make_fixtures.py` creates a key only when its file is missing. Deleting a key and rerunning the script invalidates every recorded token signed with it.
