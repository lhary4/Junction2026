"""Hash-chained JSONL audit log shared by the buyer harness and the merchant gateway (step L2).

Each line is one AuditEvent JSON object carrying `prev_hash` and its own `hash`
(SHA-256 of the event's canonical JSON without `hash`). The chain makes tampering
evident; what anchors it across trust boundaries is that each side also holds
pieces cryptographically signed by the other.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from common import clock
from contract.models import AuditEvent

ROOT = Path(__file__).resolve().parent.parent
HELSINKI = ZoneInfo("Europe/Helsinki")

Side = Literal["buyer", "merchant"]
Actor = Literal["agent", "harness", "human", "merchant"]

# One lock per resolved file path so separate `AuditLog(path)` objects created across
# concurrent web requests never race and write the same `seq` number to one `.jsonl` file.
_REGISTRY_LOCK = threading.Lock()
_PATH_LOCKS: dict[Path, threading.Lock] = {}


def _lock_for_path(path: Path) -> threading.Lock:
    resolved = path.resolve()
    with _REGISTRY_LOCK:
        lock = _PATH_LOCKS.get(resolved)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[resolved] = lock
        return lock


def default_log_path(side: Side) -> Path:
    """Default JSONL path: state/buyer/audit.jsonl or state/merchant/audit.jsonl."""
    base = Path(os.environ.get("AIMO_STATE_DIR") or ROOT / "state")
    return base / side / "audit.jsonl"


def digest(event: AuditEvent) -> str:
    """SHA-256 hex digest of canonical JSON (sorted keys, compact separators) excluding `hash`.

    Sorting keys and stripping spaces guarantees that the exact same event produces
    the exact same 64-character fingerprint on every laptop and operating system.
    """
    body = event.model_dump(mode="json", exclude={"hash"})
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class AuditLog:
    """Append-only hash-chained audit log backed by a JSON Lines (`.jsonl`) file.

    One line = one JSON event. Each event stores the previous line's `hash` in `prev_hash`,
    forming a chain so any edited, deleted, or re-ordered line breaks verification.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        # Share one lock per file path so concurrent AuditLog(path) instances stay serialized.
        self._lock = _lock_for_path(self.path)

    def append(
        self,
        side: Side,
        actor: Actor,
        action: str,
        what: str,
        why: str,
        *,
        checkout_id: str | None = None,
        checkout_hash: str | None = None,
        rule: str | None = None,
        now: datetime | None = None,
    ) -> AuditEvent:
        """Append one event chained to the previous event's hash and return it."""
        # Use the shared freezable clock by default so replay-mode logs match recorded demo times.
        timestamp = clock.now().astimezone(HELSINKI) if now is None else now
        if timestamp.tzinfo is None:
            raise ValueError("AuditLog.append requires a timezone-aware `now` datetime")

        with self._lock:
            existing = self.read()
            # First line in the file has `prev_hash=None`; every line after points to the previous line's hash.
            prev_hash = existing[-1].hash if existing else None
            event = AuditEvent(
                seq=len(existing) + 1,
                at=timestamp,
                side=side,
                actor=actor,
                action=action,
                checkout_id=checkout_id,
                checkout_hash=checkout_hash,
                what=what,
                why=why,
                rule=rule,
                prev_hash=prev_hash,
                hash="",
            )
            # Compute the fingerprint over all fields above (excluding `hash`), then save one JSON line.
            event.hash = digest(event)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
            return event

    def read(self) -> list[AuditEvent]:
        """Read all events from the log file (returns an empty list if the file does not exist)."""
        if not self.path.exists():
            return []
        lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [AuditEvent.model_validate_json(line) for line in lines]

    def verify(self) -> int | None:
        """Verify every event's hash, sequence number, and `prev_hash` link.

        Returns the 0-based index of the first broken event, or None if the log is intact.
        """
        if not self.path.exists():
            return None

        lines = [line for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        expected_prev: str | None = None

        for idx, line in enumerate(lines):
            try:
                event = AuditEvent.model_validate_json(line)
            except (ValidationError, ValueError):
                # Corrupt JSON or missing required fields on this line.
                return idx

            # 1) Line numbering must be 1, 2, 3... with no gaps (catches deleted lines).
            if event.seq != idx + 1:
                return idx
            # 2) `prev_hash` must match the previous line's `hash` (catches edited or swapped lines).
            if event.prev_hash != expected_prev:
                return idx
            # 3) Recomputing `digest(event)` must match `event.hash` (catches in-place edits).
            if event.hash != digest(event):
                return idx

            expected_prev = event.hash

        return None
