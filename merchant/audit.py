"""The gateway's audit log: one line per thing Valio did, in state/merchant/audit.jsonl (ignored by git).

Each event carries the hash of the previous one, so an edited line shows. The chain makes tampering evident, it does
not prevent it: what anchors the log is that the buyer also holds the quote and the receipt Valio signed.

The chaining, the file format and the check (AuditLog.verify) live in common/audit.py, shared with the buyer's harness.
This file only says where the gateway's log is, and that every line in it is Valio's.
"""

import threading

from common.audit import AuditLog, default_log_path
from contract.models import AuditEvent

# Two requests at once must not write the same `seq`. An AuditLog only locks its own object, and the gateway makes a
# new one per call because the state folder can change (AIMO_STATE_DIR): so the gateway holds one lock for all of them.
_lock = threading.Lock()


def record(
    action: str, what: str, why: str, checkout_id: str | None = None, checkout_hash: str | None = None
) -> AuditEvent:
    with _lock:
        return _log().append(
            "merchant", "merchant", action, what, why, checkout_id=checkout_id, checkout_hash=checkout_hash
        )


def events() -> list[AuditEvent]:
    with _lock:
        return _log().read()


def _log() -> AuditLog:
    return AuditLog(default_log_path("merchant"))
