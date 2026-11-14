"""Buyer-side state store for approvals, authorizations, verdicts, and verified quote tokens (step L4).

Keeps state in memory synced to JSON files under `state/buyer/` (or `$AIMO_STATE_DIR/buyer/`).
Each ApprovalRequest is bound to its `checkout_hash`, expires at the quote's cut-off deadline,
and can be decided at most once.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from common import clock
from contract.models import ApprovalRequest, AuthorizationStatus, Verdict

ROOT = Path(__file__).resolve().parent.parent
HELSINKI = ZoneInfo("Europe/Helsinki")

ApprovalStatusFilter = Literal["pending", "approved", "rejected", "expired"]


class ApprovalNotFoundError(LookupError):
    """Raised when an approval_id does not exist."""


class ApprovalAlreadyDecidedError(RuntimeError):
    """Raised when attempting to approve or reject a request that was already decided."""


def buyer_state_dir() -> Path:
    return Path(os.environ.get("AIMO_STATE_DIR") or ROOT / "state") / "buyer"


def expired_reason(deadline: datetime | None) -> str:
    if deadline is None:
        return "Approval deadline passed. Nothing was ordered."
    local_deadline = deadline.astimezone(HELSINKI)
    return f"No answer before the order cut-off ({local_deadline:%Y-%m-%d %H:%M}). Nothing was ordered."


class ApprovalStore:
    """Thread-safe store persisted under `<state_dir>/buyer/`."""

    def __init__(self, directory: Path | None = None) -> None:
        self._explicit_dir = directory
        self._lock = threading.Lock()
        self._loaded_dir: Path | None = None
        self._approvals: dict[str, ApprovalRequest] = {}
        self._authorizations: dict[str, AuthorizationStatus] = {}
        self._verdicts: dict[str, Verdict] = {}
        self._checkout_jwts: dict[str, str] = {}

    def _dir(self) -> Path:
        return self._explicit_dir if self._explicit_dir is not None else buyer_state_dir()

    def _ensure_loaded(self) -> Path:
        folder = self._dir()
        if self._loaded_dir != folder:
            self._approvals = {}
            self._authorizations = {}
            self._verdicts = {}
            self._checkout_jwts = {}
            self._load_from_disk(folder)
            self._loaded_dir = folder
        return folder

    def _load_from_disk(self, folder: Path) -> None:
        approvals_file = folder / "approvals.json"
        if approvals_file.exists():
            raw = json.loads(approvals_file.read_text(encoding="utf-8"))
            self._approvals = {k: ApprovalRequest.model_validate(v) for k, v in raw.items()}

        auth_file = folder / "authorizations.json"
        if auth_file.exists():
            raw = json.loads(auth_file.read_text(encoding="utf-8"))
            self._authorizations = {k: AuthorizationStatus.model_validate(v) for k, v in raw.items()}

        verdicts_file = folder / "verdicts.json"
        if verdicts_file.exists():
            raw = json.loads(verdicts_file.read_text(encoding="utf-8"))
            self._verdicts = {k: Verdict.model_validate(v) for k, v in raw.items()}

        jwts_file = folder / "checkout_jwts.json"
        if jwts_file.exists():
            self._checkout_jwts = dict(json.loads(jwts_file.read_text(encoding="utf-8")))

    def _flush(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "approvals.json").write_text(
            json.dumps(
                {k: v.model_dump(mode="json") for k, v in self._approvals.items()},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (folder / "authorizations.json").write_text(
            json.dumps(
                {k: v.model_dump(mode="json") for k, v in self._authorizations.items()},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (folder / "verdicts.json").write_text(
            json.dumps(
                {k: v.model_dump(mode="json") for k, v in self._verdicts.items()},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (folder / "checkout_jwts.json").write_text(
            json.dumps(self._checkout_jwts, indent=2) + "\n",
            encoding="utf-8",
        )

    def _expire_due_unlocked(self, now: datetime) -> list[ApprovalRequest]:
        newly_expired: list[ApprovalRequest] = []
        for approval_id, approval in list(self._approvals.items()):
            if approval.status == "pending" and approval.deadline is not None and approval.deadline <= now:
                updated = approval.model_copy(update={"status": "expired"})
                self._approvals[approval_id] = updated
                self._authorizations[approval.checkout_id] = AuthorizationStatus(
                    status="expired",
                    checkout_id=approval.checkout_id,
                    decision="human",
                    signed_by=None,
                    order_id=None,
                    reasons=[expired_reason(approval.deadline)],
                    approval_id=approval.approval_id,
                    approval_url=None,
                    deadline=approval.deadline,
                )
                newly_expired.append(updated)
        return newly_expired

    def expire_due(self, now: datetime | None = None) -> list[ApprovalRequest]:
        """Transition any pending approvals past their deadline to `expired`."""
        ts = (now or clock.now()).astimezone(HELSINKI)
        with self._lock:
            folder = self._ensure_loaded()
            expired_list = self._expire_due_unlocked(ts)
            if expired_list:
                self._flush(folder)
            return expired_list

    def create_approval(
        self,
        verdict: Verdict,
        request_text: str,
        *,
        checkout_jwt: str,
        approval_url_base: str,
        now: datetime | None = None,
    ) -> tuple[ApprovalRequest, AuthorizationStatus]:
        """Create a pending ApprovalRequest bound to `verdict.checkout_hash`."""
        ts = (now or clock.now()).astimezone(HELSINKI)
        approval_id = f"apr_{uuid.uuid4().hex[:8]}"
        triggered_rules = [r for r in verdict.rules if r.outcome != "pass"]
        approval = ApprovalRequest(
            approval_id=approval_id,
            checkout_id=verdict.checkout_id,
            checkout_hash=verdict.checkout_hash,
            status="pending",
            total_minor=verdict.total_minor,
            currency=verdict.currency,
            reasons=triggered_rules,
            judge=verdict.judge,
            request_text=request_text,
            requested_at=ts,
            deadline=verdict.deadline,
            decided_by=None,
            decided_at=None,
            order_id=None,
        )
        status = AuthorizationStatus(
            status="pending_approval",
            checkout_id=verdict.checkout_id,
            decision="human",
            signed_by=None,
            order_id=None,
            reasons=[f"{r.rule_id}: {r.message}" for r in triggered_rules],
            approval_id=approval_id,
            approval_url=f"{approval_url_base.rstrip('/')}/#/approvals/{approval_id}",
            deadline=verdict.deadline,
        )
        with self._lock:
            folder = self._ensure_loaded()
            self._approvals[approval_id] = approval
            self._authorizations[verdict.checkout_id] = status
            self._verdicts[verdict.checkout_id] = verdict
            self._checkout_jwts[verdict.checkout_id] = checkout_jwt
            self._flush(folder)
        return approval, status

    def save_outcome(
        self,
        verdict: Verdict,
        status: AuthorizationStatus,
        *,
        checkout_jwt: str | None = None,
    ) -> None:
        with self._lock:
            folder = self._ensure_loaded()
            self._verdicts[verdict.checkout_id] = verdict
            self._authorizations[verdict.checkout_id] = status
            if checkout_jwt is not None:
                self._checkout_jwts[verdict.checkout_id] = checkout_jwt
            self._flush(folder)

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            self._ensure_loaded()
            return self._approvals.get(approval_id)

    def list_approvals(self, status: ApprovalStatusFilter | None = None) -> list[ApprovalRequest]:
        with self._lock:
            self._ensure_loaded()
            items = list(self._approvals.values())
            if status is not None:
                items = [a for a in items if a.status == status]
            return items

    def get_checkout_jwt(self, checkout_id: str) -> str | None:
        with self._lock:
            self._ensure_loaded()
            return self._checkout_jwts.get(checkout_id)

    def get_authorization(self, checkout_id: str) -> AuthorizationStatus | None:
        with self._lock:
            self._ensure_loaded()
            return self._authorizations.get(checkout_id)

    def list_authorizations(self) -> list[AuthorizationStatus]:
        with self._lock:
            self._ensure_loaded()
            return list(self._authorizations.values())

    def get_verdict(self, checkout_id: str) -> Verdict | None:
        with self._lock:
            self._ensure_loaded()
            return self._verdicts.get(checkout_id)

    def check_ready_for_decision(
        self,
        approval_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ApprovalRequest, AuthorizationStatus | None, bool]:
        """Validate whether `approval_id` can be decided at `now`.

        Returns `(approval, expired_status_or_none, newly_expired)`.
        Raises ApprovalNotFoundError if unknown, or ApprovalAlreadyDecidedError if already approved/rejected.
        """
        ts = (now or clock.now()).astimezone(HELSINKI)
        with self._lock:
            folder = self._ensure_loaded()
            approval = self._approvals.get(approval_id)
            if approval is None:
                raise ApprovalNotFoundError(approval_id)

            if approval.status in ("approved", "rejected"):
                raise ApprovalAlreadyDecidedError(
                    f"Approval {approval_id} was already {approval.status} by {approval.decided_by}"
                )

            newly_expired = False
            if approval.status == "pending" and approval.deadline is not None and approval.deadline <= ts:
                approval = approval.model_copy(update={"status": "expired"})
                self._approvals[approval_id] = approval
                self._authorizations[approval.checkout_id] = AuthorizationStatus(
                    status="expired",
                    checkout_id=approval.checkout_id,
                    decision="human",
                    signed_by=None,
                    order_id=None,
                    reasons=[expired_reason(approval.deadline)],
                    approval_id=approval.approval_id,
                    approval_url=None,
                    deadline=approval.deadline,
                )
                self._flush(folder)
                newly_expired = True

            if approval.status == "expired":
                return approval, self._authorizations[approval.checkout_id], newly_expired

            return approval, None, False

    def record_rejected(
        self,
        approval_id: str,
        decided_by: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ApprovalRequest, AuthorizationStatus]:
        ts = (now or clock.now()).astimezone(HELSINKI)
        with self._lock:
            folder = self._ensure_loaded()
            approval = self._approvals[approval_id]
            if approval.status != "pending":
                raise ApprovalAlreadyDecidedError(f"Approval {approval_id} is {approval.status}")
            updated = approval.model_copy(
                update={
                    "status": "rejected",
                    "decided_by": decided_by,
                    "decided_at": ts,
                }
            )
            status = AuthorizationStatus(
                status="rejected",
                checkout_id=approval.checkout_id,
                decision="human",
                signed_by=None,
                order_id=None,
                reasons=["The approver rejected the request."],
                approval_id=approval_id,
                approval_url=None,
                deadline=None,
            )
            self._approvals[approval_id] = updated
            self._authorizations[approval.checkout_id] = status
            self._flush(folder)
            return updated, status

    def record_approved(
        self,
        approval_id: str,
        decided_by: str,
        order_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[ApprovalRequest, AuthorizationStatus]:
        ts = (now or clock.now()).astimezone(HELSINKI)
        with self._lock:
            folder = self._ensure_loaded()
            approval = self._approvals[approval_id]
            if approval.status != "pending":
                raise ApprovalAlreadyDecidedError(f"Approval {approval_id} is {approval.status}")
            updated = approval.model_copy(
                update={
                    "status": "approved",
                    "decided_by": decided_by,
                    "decided_at": ts,
                    "order_id": order_id,
                }
            )
            status = AuthorizationStatus(
                status="ordered",
                checkout_id=approval.checkout_id,
                decision="human",
                signed_by="human",
                order_id=order_id,
                reasons=[f"{r.rule_id}: {r.message}" for r in approval.reasons],
                approval_id=approval_id,
                approval_url=None,
                deadline=None,
            )
            self._approvals[approval_id] = updated
            self._authorizations[approval.checkout_id] = status
            self._flush(folder)
            return updated, status
