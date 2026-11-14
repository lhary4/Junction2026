"""The gateway's audit log: one line per thing Valio did, in state/merchant/audit.jsonl (ignored by git).

Each event carries the hash of the previous one, so an edited line shows. The chain makes tampering evident, it does
not prevent it: what anchors the log is that the buyer also holds the quote and the receipt Valio signed.

TEMPORARY: common/audit.py (Léon's step L2) is not on main yet, so this file chains the events itself. The gateway
only calls record() and events(): when the shared AuditLog is merged, the swap stays inside this file.
"""

import hashlib
import json
import threading
from pathlib import Path

from common import clock
from contract.models import AuditEvent
from merchant.catalog import HELSINKI
from merchant.store import state_dir

_lock = threading.Lock()  # two requests at once must not write the same `seq`


def record(
    action: str, what: str, why: str, checkout_id: str | None = None, checkout_hash: str | None = None
) -> AuditEvent:
    with _lock:
        previous = events()
        event = AuditEvent(
            seq=len(previous) + 1,
            at=clock.now().astimezone(HELSINKI),
            side="merchant",
            actor="merchant",
            action=action,
            checkout_id=checkout_id,
            checkout_hash=checkout_hash,
            what=what,
            why=why,
            prev_hash=previous[-1].hash if previous else None,
            hash="",
        )
        event.hash = digest(event)
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write(event.model_dump_json() + "\n")
        return event


def events() -> list[AuditEvent]:
    path = _path()
    if not path.exists():
        return []
    return [AuditEvent.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def digest(event: AuditEvent) -> str:
    """SHA-256 of the event as canonical JSON (sorted keys, no spaces), without its own `hash` field."""
    body = event.model_dump(mode="json", exclude={"hash"})
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _path() -> Path:
    return state_dir() / "audit.jsonl"
