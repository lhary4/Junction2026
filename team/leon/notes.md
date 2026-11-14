# Léon's notes

Results, numbers and open questions for the others. Newest first.

## L1: Gemini Decision on the substitution case

Model: `gemini-decision-1` (`v1beta`), original `469363` (*Arla Semi skimmed milkdrink 1 L UHT lactose free Suomesta*), `auto_threshold = 0.85`, `floor = 0.15`.

| Candidate | `within_preferences` | `same_use` | Routing (`within_preferences` / `same_use`) |
|---|---|---|---|
| 464201 Valio semi skimmed UHT lactose free | **0.9645** (conf 0.9645) | **0.9772** (conf 0.9772) | `auto` / `auto` |
| 463380 Arla Cafè milk UHT lactose free | **0.2272** (conf 0.7728) | **0.4815** (conf 0.5185) | `human` / `human` |
| 464320 Oatly iKaffe oat drink | **0.0190** (conf 0.9810) | **0.0892** (conf 0.9108) | `human` / `human` |

Order check (`464201 > 463380 > 464320`): passed on both `within_preferences` (`0.9645 > 0.2272 > 0.0190`) and `same_use` (`0.9772 > 0.4815 > 0.0892`) on the first phrasing.

Median latency over 10 calls: **245.4 ms** (min **189.9 ms**, max **487.9 ms**; two `noul` questions evaluated in parallel per call).

What happens without a key or on a timeout:
- Missing `GEMINI_API_KEY`: skips network call and immediately returns two `JudgeAnswer`-shaped dicts with `routed: "human"`, `probability: null`, `confidence: null`.
- Timeout (default 5.0 s, verified live with a 1 ms deadline) or any SDK/HTTP error: catches the exception and fails closed with `routed: "human"`, `probability: null`, `confidence: null`.
