"""The one clock the gateway and the harness read, so a demo can run at a recorded time.

Set AIMO_FROZEN_NOW to an ISO time with its offset (replay mode), e.g. 2026-11-14T13:15:00+02:00.
The frozen clock does not tick: every call returns that exact time.
"""

import os
from datetime import UTC, datetime


def now() -> datetime:
    frozen = os.environ.get("AIMO_FROZEN_NOW")
    if not frozen:
        return datetime.now(UTC)
    value = datetime.fromisoformat(frozen)
    if value.tzinfo is None:
        raise ValueError(f"AIMO_FROZEN_NOW needs a UTC offset, got {frozen!r}")
    return value
