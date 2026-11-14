"""Gemini Decision judge for product substitutions (step L1).

Evaluates two independent yes/no ('noul') questions in a single pass with gemini-decision-1:
- within_preferences: whether the candidate product fits all stated buyer preferences
- same_use: whether the kitchen can use the candidate identically to the original product

Fails closed: missing API key, timeout (5s default), or any API/SDK error routes to 'human'
with probability=None and confidence=None.
"""

from __future__ import annotations

import inspect
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any

from google import genai

ROOT = Path(__file__).resolve().parent.parent
MODEL = "gemini-decision-1"
DEFAULT_AUTO_THRESHOLD = 0.85
DEFAULT_FLOOR = 0.15
DEFAULT_TIMEOUT_SECONDS = 5.0

QUESTIONS: dict[str, dict[str, str]] = {
    "within_preferences": {
        "type": "noul",
        "instructions": (
            "Does `candidate_product` respect every preference in `buyer_preferences` "
            "for autonomous ordering without requiring manager approval?"
        ),
    },
    "same_use": {
        "type": "noul",
        "instructions": (
            "Can the kitchen use `candidate_product` in the exact same way and for the exact same "
            "purpose as `original_product`, without changing anything?"
        ),
    },
}

ALLERGEN_LABELS: dict[str, str] = {
    "AM": "AM (milk)",
    "AW": "AW (cereals containing gluten)",
    "GO": "GO (oats)",
    "AP": "AP (peanuts)",
    "AN": "AN (tree nuts)",
    "ML": "ML (lactose)",
}


def _from_env_file(name: str, env_path: Path | None = None) -> str | None:
    """Read one variable from the repo's .env without exporting anything."""
    path = env_path or (ROOT / ".env")
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name and not key.lstrip().startswith("#"):
            cleaned = value.strip().strip("'\"")
            return cleaned or None
    return None


def _resolve_api_key(api_key: str | None = None) -> str | None:
    if api_key is not None:
        return api_key.strip() or None
    return os.environ.get("GEMINI_API_KEY", "").strip() or _from_env_file("GEMINI_API_KEY")


def _product_id(card: dict[str, Any]) -> str:
    return str(card.get("id") or card.get("product_id") or "")


def _format_allergens(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {"contains": [], "free_from": []}
    contains = [ALLERGEN_LABELS.get(code, str(code)) for code in raw.get("contains", [])]
    free_from = [ALLERGEN_LABELS.get(code, str(code)) for code in raw.get("free_from", [])]
    return {"contains": contains, "free_from": free_from}


def _structured_product(card: dict[str, Any]) -> dict[str, Any]:
    """Extract strictly structured catalog facts; never include marketing descriptions."""
    return {
        "id": _product_id(card),
        "name": card.get("name", ""),
        "brand": card.get("brand"),
        "category": card.get("category", ""),
        "allergens": _format_allergens(card.get("allergens")),
        "nutritional_claims": list(card.get("nutritional_claims", [])),
    }


def build_judge_input(original: dict[str, Any], candidate: dict[str, Any], preferences_text: str) -> str:
    """Serialize only structured product fields and the buyer's preference text."""
    payload = {
        "buyer_preferences": preferences_text,
        "original_product": _structured_product(original),
        "candidate_product": _structured_product(candidate),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _fail_closed_answers(
    original_id: str,
    candidate_id: str,
    auto_threshold: float,
    floor: float,
) -> list[dict[str, Any]]:
    return [
        {
            "question_key": key,
            "type": q["type"],
            "instructions": q["instructions"],
            "subject": {"original": original_id, "candidate": candidate_id},
            "probability": None,
            "confidence": None,
            "auto_threshold": auto_threshold,
            "floor": floor,
            "routed": "human",
            "model": MODEL,
        }
        for key, q in QUESTIONS.items()
    ]


def _call_decisions(
    client: Any,
    input_text: str,
    timeout_seconds: float,
) -> Any:
    create_fn = client.decisions.create
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "input": input_text,
        "questions": QUESTIONS,
    }
    try:
        sig = inspect.signature(create_fn)
        accepts_timeout = "timeout" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except (TypeError, ValueError):
        accepts_timeout = True

    if accepts_timeout:
        kwargs["timeout"] = timeout_seconds
    return create_fn(**kwargs)


def judge_substitution(
    original: dict[str, Any],
    candidate: dict[str, Any],
    preferences_text: str,
    *,
    auto_threshold: float = DEFAULT_AUTO_THRESHOLD,
    floor: float = DEFAULT_FLOOR,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    api_key: str | None = None,
    client: Any = None,
) -> list[dict[str, Any]]:
    """Judge a candidate substitute against the original product and buyer preferences.

    Returns two dicts matching contract.models.JudgeAnswer (within_preferences, same_use).
    Any missing key, timeout, or error fails closed with routed='human' and probability=None.
    """
    original_id = _product_id(original)
    candidate_id = _product_id(candidate)

    if client is None:
        resolved_key = _resolve_api_key(api_key)
        if not resolved_key:
            return _fail_closed_answers(original_id, candidate_id, auto_threshold, floor)
        try:
            timeout_ms = max(1, int(timeout_seconds * 1000))
            client = genai.Client(
                api_key=resolved_key,
                http_options={"api_version": "v1beta", "timeout": timeout_ms},
            )
        except Exception:  # noqa: BLE001 — fail closed on any client init error
            return _fail_closed_answers(original_id, candidate_id, auto_threshold, floor)

    input_text = build_judge_input(original, candidate, preferences_text)

    try:
        result = _call_decisions(client, input_text, timeout_seconds)
        answers_map = result.answers
        output: list[dict[str, Any]] = []
        for key, q in QUESTIONS.items():
            ans = answers_map[key]
            prob = round(float(ans.noul), 4)
            conf = round(float(ans.confidence), 4) if getattr(ans, "confidence", None) is not None else None
            routed = "auto" if prob >= auto_threshold else "human"
            output.append(
                {
                    "question_key": key,
                    "type": q["type"],
                    "instructions": q["instructions"],
                    "subject": {"original": original_id, "candidate": candidate_id},
                    "probability": prob,
                    "confidence": conf,
                    "auto_threshold": auto_threshold,
                    "floor": floor,
                    "routed": routed,
                    "model": MODEL,
                }
            )
        return output
    except Exception:  # noqa: BLE001 — fail closed on timeout, missing key, or API error
        return _fail_closed_answers(original_id, candidate_id, auto_threshold, floor)


def _load_demo_case() -> tuple[dict[str, Any], list[dict[str, Any]], str, float, float]:
    cards_path = ROOT / "contract" / "examples" / "product-cards.json"
    policy_path = ROOT / "contract" / "examples" / "policy.demo.json"
    cards = {card["id"]: card for card in json.loads(cards_path.read_text(encoding="utf-8"))}
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    sub = policy["substitution"]
    original = cards["469363"]
    candidates = [cards["464201"], cards["463380"], cards["464320"]]
    return original, candidates, sub["preferences_text"], sub["judge_auto_threshold"], sub["judge_floor"]


def _run_demo() -> None:
    original, candidates, preferences_text, auto_threshold, floor = _load_demo_case()

    print("=== Fail-closed check: missing API key ===")
    saved_env = os.environ.pop("GEMINI_API_KEY", None)
    try:
        no_key_res = judge_substitution(
            original,
            candidates[0],
            preferences_text,
            auto_threshold=auto_threshold,
            floor=floor,
            api_key="",
        )
    finally:
        if saved_env is not None:
            os.environ["GEMINI_API_KEY"] = saved_env
    print(json.dumps(no_key_res, indent=2))

    print("\n=== Fail-closed check: timeout (1 ms deadline) ===")
    timeout_res = judge_substitution(
        original,
        candidates[0],
        preferences_text,
        auto_threshold=auto_threshold,
        floor=floor,
        timeout_seconds=0.001,
    )
    print(
        f"Timeout result -> routed={[a['routed'] for a in timeout_res]}, "
        f"probability={[a['probability'] for a in timeout_res]}"
    )

    key = _resolve_api_key()
    if not key:
        print("\n[!] GEMINI_API_KEY is not set in environment or .env — skipping live API calls.")
        return

    print(f"\n=== Live Gemini Decision ({MODEL}) on 3 candidates ===")
    client = genai.Client(api_key=key, http_options={"api_version": "v1beta", "timeout": 5000})
    results_by_id: dict[str, list[dict[str, Any]]] = {}
    for cand in candidates:
        answers = judge_substitution(
            original,
            cand,
            preferences_text,
            auto_threshold=auto_threshold,
            floor=floor,
            client=client,
        )
        results_by_id[cand["id"]] = answers
        by_q = {a["question_key"]: a for a in answers}
        wp = by_q["within_preferences"]
        su = by_q["same_use"]
        print(
            f"- {cand['id']} ({cand['name']}): "
            f"within_preferences={wp['probability']} (conf={wp['confidence']}, routed={wp['routed']}), "
            f"same_use={su['probability']} (conf={su['confidence']}, routed={su['routed']})"
        )

    wp_scores = [
        next(a["probability"] for a in results_by_id[cid] if a["question_key"] == "within_preferences")
        for cid in ("464201", "463380", "464320")
    ]
    if all(s is not None for s in wp_scores):
        ordered = wp_scores[0] > wp_scores[1] > wp_scores[2]
        print(f"Order check (464201 > 463380 > 464320): {ordered} ({wp_scores})")

    print("\n=== Latency benchmark (10 live calls) ===")
    latencies_ms: list[float] = []
    for i in range(10):
        cand = candidates[i % len(candidates)]
        t0 = time.perf_counter()
        judge_substitution(
            original,
            cand,
            preferences_text,
            auto_threshold=auto_threshold,
            floor=floor,
            client=client,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)
        print(f"  call {i + 1:2d}/10 ({cand['id']}): {elapsed_ms:.1f} ms")

    print(
        f"Latency over 10 calls: median={statistics.median(latencies_ms):.1f} ms, "
        f"min={min(latencies_ms):.1f} ms, max={max(latencies_ms):.1f} ms"
    )


if __name__ == "__main__":
    _run_demo()
