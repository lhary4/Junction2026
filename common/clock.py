"""The one clock the gateway and the harness read, so a demo can run at a recorded time.

Replay mode (VALIO_MODE=replay, the default) answers the time the Valio answers were recorded, read from
contract/fixtures/valio/frozen_now.txt. Their order cut-off is Sunday 15/11 at 17:00: on the real clock, nothing
recorded could be quoted after it. Live mode answers the real time.
AIMO_FROZEN_NOW, an ISO time with its offset (e.g. 2026-11-14T13:15:00+02:00), wins in both modes.
A frozen clock does not tick: every call returns that exact time.
"""

import os
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

RECORDED_AT = Path(__file__).resolve().parent.parent / "contract" / "fixtures" / "valio" / "frozen_now.txt"


def now() -> datetime:
    frozen = os.environ.get("AIMO_FROZEN_NOW") or (_recorded_at() if _replay() else None)
    if not frozen:
        return datetime.now(UTC)
    value = datetime.fromisoformat(frozen)
    if value.tzinfo is None:
        raise ValueError(f"the frozen time needs a UTC offset, got {frozen!r}")
    return value


def _replay() -> bool:
    """Same default as merchant.catalog.mode(): no VALIO_MODE means replay."""
    return os.environ.get("VALIO_MODE", "replay") == "replay"


@cache
def _recorded_at() -> str:
    return RECORDED_AT.read_text(encoding="utf-8").strip()
