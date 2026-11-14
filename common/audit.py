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


def default_log_path(side: Side) -> Path:
    """Default JSONL path: state/buyer/audit.jsonl or state/merchant/audit.jsonl."""
    base = Path(os.environ.get("AIMO_STATE_DIR") or ROOT / "state")
    return base / side / "audit.jsonl"


def digest(event: AuditEvent) -> str:
    """SHA-256 hex digest of canonical JSON (sorted keys, compact separators) excluding `hash`."""
    body = event.model_dump(mode="json", exclude={"hash"})
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class AuditLog:
    """Append-only hash-chained audit log backed by a JSON Lines file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

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
        timestamp = clock.now().astimezone(HELSINKI) if now is None else now
        if timestamp.tzinfo is None:
            raise ValueError("AuditLog.append requires a timezone-aware `now` datetime")

        with self._lock:
            existing = self.read()
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
                return idx

            if event.seq != idx + 1:
                return idx
            if event.prev_hash != expected_prev:
                return idx
            if event.hash != digest(event):
                return idx

            expected_prev = event.hash

        return None
