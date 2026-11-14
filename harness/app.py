"""Buyer-side guardrails harness service on port 8002 (step L4).

Run: uv run uvicorn harness.app:app --port 8002
(or start both gateway and harness together with `uv run python scripts/dev.py`).

Routes (docs/contract.md):
- POST /authorize
- GET  /authorizations
- GET  /authorizations/{checkout_id}
- GET  /verdicts/{checkout_id}
- GET  /approvals
- GET  /approvals/{approval_id}
- POST /approvals/{approval_id}/decision
- GET  /policy
- GET  /mandates/open
- GET  /audit
- /    serves `surface/static` (and `/contract/examples` for rehearsal mock links)
"""

from __future__ import annotations

import base64
import inspect
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from common import clock
from common.audit import AuditLog, default_log_path
from contract.models import (
    AimoCheckout,
    ApprovalDecision,
    ApprovalRequest,
    AuditEvent,
    Authorization,
    AuthorizationStatus,
    AuthorizeRequest,
    BuyerPolicy,
    Order,
    RuleResult,
    Verdict,
)
from harness.approvals import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    ApprovalStatusFilter,
    ApprovalStore,
    expired_reason,
)
from harness.judge import judge_substitution
from harness.notify import NotifyFn, notify_approval
from harness.policy import load_policy
from harness.rules import JudgeFn, evaluate
from harness.signer import HarnessSigner
from trust import TrustError
from trust.checkout import checkout_hash, read_checkout, verify_checkout
from trust.receipts import verify_receipt

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
HELSINKI = ZoneInfo("Europe/Helsinki")
SURFACE_STATIC = ROOT / "surface" / "static"
CONTRACT_EXAMPLES = ROOT / "contract" / "examples"


def _from_env_file(name: str) -> str | None:
    env = ROOT / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name and not key.lstrip().startswith("#"):
            return value.strip() or None
    return None


def merchant_url() -> str:
    return (os.environ.get("MERCHANT_URL") or _from_env_file("MERCHANT_URL") or "http://localhost:8001").rstrip("/")


def harness_url() -> str:
    return (os.environ.get("HARNESS_URL") or _from_env_file("HARNESS_URL") or "http://localhost:8002").rstrip("/")


def _jwt_kid(token: str) -> str | None:
    try:
        raw_header = token.split(".")[0]
        padded = raw_header + "=" * (-len(raw_header) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
        kid = header.get("kid")
        return str(kid) if kid is not None else None
    except Exception:  # noqa: BLE001
        return None


def _audit() -> AuditLog:
    return AuditLog(default_log_path("buyer"))


def _record_expired_audits(expired_items: list[ApprovalRequest], now: datetime) -> None:
    if not expired_items:
        return
    log = _audit()
    for item in expired_items:
        log.append(
            "buyer",
            "harness",
            "approval_expired",
            f"Approval {item.approval_id} expired at cut-off.",
            expired_reason(item.deadline),
            checkout_id=item.checkout_id,
            checkout_hash=item.checkout_hash,
            now=now,
        )


def _verify_quote_token(
    checkout_jwt: str,
    raw_checkout: dict[str, Any] | None,
    jwks: dict[str, Any],
    now: datetime,
) -> tuple[AimoCheckout, RuleResult]:
    """Verify the merchant's ES256 signature on `checkout_jwt` and return `(checkout, signature_rule)`."""
    kid = _jwt_kid(checkout_jwt)
    try:
        verified = verify_checkout(checkout_jwt, jwks, now)
        if raw_checkout is not None:
            try:
                outer = AimoCheckout.model_validate(raw_checkout)
            except ValidationError as val_err:
                raise TrustError(
                    f"outer checkout payload is invalid: {val_err.error_count()} validation error(s)",
                    rule="quote-signature",
                ) from val_err
            if outer != verified:
                raise TrustError("outer checkout payload differs from signed checkout_jwt", rule="quote-signature")
        sig_rule = RuleResult(
            rule_id="quote-signature",
            outcome="pass",
            message=f"Quote signed by {verified.merchant.id} with key {kid}.",
            evidence={"kid": kid} if kid else {},
        )
        return verified, sig_rule
    except TrustError as err:
        if err.rule == "quote-not-expired":
            # Signature verified cleanly; let `evaluate` record `quote-not-expired` alongside all other rules.
            parsed = read_checkout(checkout_jwt)
            sig_rule = RuleResult(
                rule_id="quote-signature",
                outcome="pass",
                message=f"Quote signed by {parsed.merchant.id} with key {kid}.",
                evidence={"kid": kid} if kid else {},
            )
            return parsed, sig_rule

        # Bad signature or tampered quote: decode unverified payload only to report id/total in Verdict.
        untrusted = _fallback_untrusted_checkout(checkout_jwt, raw_checkout)
        merchant_name = untrusted.merchant.name or untrusted.merchant.id
        evidence: dict[str, Any] = {"error": str(err)}
        if kid:
            evidence["kid"] = kid
        sig_rule = RuleResult(
            rule_id="quote-signature",
            outcome="deny",
            message=(
                f"The quote does not match {merchant_name}'s signature: it was changed after signing. "
                "Nothing is signed, nothing is ordered."
            ),
            evidence=evidence,
        )
        return untrusted, sig_rule


def _fallback_untrusted_checkout(checkout_jwt: str, raw_checkout: dict[str, Any] | None) -> AimoCheckout:
    try:
        return read_checkout(checkout_jwt)
    except TrustError:
        if raw_checkout is not None:
            try:
                return AimoCheckout.model_validate(raw_checkout)
            except ValidationError:
                pass
    raise HTTPException(status_code=502, detail="gateway returned an unreadable quote token")


def _verdict_audit_summary(verdict: Verdict) -> tuple[str, str, str | None]:
    what = f"Verdict {verdict.decision} for {verdict.total_minor / 100:.2f} {verdict.currency}."
    triggered = [r for r in verdict.rules if r.outcome != "pass"]
    if triggered:
        why = "; ".join(r.message for r in triggered)
        return what, why, triggered[0].rule_id
    spend = next((r for r in verdict.rules if r.rule_id == "spend-limit"), None)
    why = spend.message if spend else "All guardrail rules passed."
    return what, why, (spend.rule_id if spend else None)


def _invoke_notify(
    notify_fn: NotifyFn,
    approval: ApprovalRequest,
    approval_url: str | None,
) -> None:
    """Trigger chef notification without ever letting a notification error affect the verdict."""
    try:
        sig = inspect.signature(notify_fn)
        accepts_url = "approval_url" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except (TypeError, ValueError):
        accepts_url = False

    try:
        if accepts_url:
            notify_fn(approval, approval_url=approval_url)
        else:
            notify_fn(approval)
    except Exception as err:  # noqa: BLE001
        logger.warning(
            "Notification callback failed for approval %s (%s)",
            approval.approval_id,
            type(err).__name__,
        )


def create_app(
    *,
    http_client: httpx.Client | None = None,
    policy_path: Path | None = None,
    judge_fn: JudgeFn | None = None,
    signer: HarnessSigner | None = None,
    store: ApprovalStore | None = None,
    notify_fn: NotifyFn | None = None,
) -> FastAPI:
    active_judge = judge_fn if judge_fn is not None else judge_substitution
    active_store = store if store is not None else ApprovalStore()
    active_signer = signer if signer is not None else HarnessSigner()
    active_notify = notify_fn if notify_fn is not None else notify_approval

    @contextmanager
    def _gateway_client():
        if http_client is not None:
            yield http_client
        else:
            with httpx.Client(base_url=merchant_url(), timeout=15.0) as client:
                yield client

    def _fetch_jwks(client: httpx.Client) -> dict[str, Any]:
        try:
            resp = client.get("/.well-known/jwks.json")
        except httpx.HTTPError as err:
            raise HTTPException(status_code=502, detail=f"merchant gateway unreachable while fetching JWKS: {err}") from err
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"could not fetch gateway JWKS (HTTP {resp.status_code})")
        try:
            return resp.json()
        except ValueError as err:
            raise HTTPException(status_code=502, detail="gateway JWKS response is not valid JSON") from err

    def _fetch_quote(client: httpx.Client, checkout_id: str) -> tuple[str, dict[str, Any] | None]:
        try:
            resp = client.get(f"/checkouts/{checkout_id}")
        except httpx.HTTPError as err:
            raise HTTPException(
                status_code=502,
                detail=f"merchant gateway unreachable while fetching quote {checkout_id}: {err}",
            ) from err
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"unknown checkout {checkout_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"gateway returned HTTP {resp.status_code} for {checkout_id}")
        try:
            body = resp.json()
        except ValueError as err:
            raise HTTPException(status_code=502, detail="gateway quote response is not valid JSON") from err
        token = body.get("checkout_jwt")
        if not isinstance(token, str) or not token:
            raise HTTPException(status_code=502, detail="gateway response missing checkout_jwt")
        return token, body.get("checkout")

    def _submit_mandate_and_verify_receipt(
        client: httpx.Client,
        checkout_id: str,
        authorization: Authorization,
        jwks: dict[str, Any],
    ) -> tuple[Order | None, list[str]]:
        """Send signed AP2 mandates to the merchant gateway and verify the signed receipt before trusting it.

        Core principle ("submission is not acceptance"): an order is only reported as `ordered`
        if the gateway returns HTTP 200 AND its `receipt_jwt` verifies against the gateway's JWKS
        with matching `order_id`, `mandate_reference`, and `status == "Success"`.
        """
        try:
            resp = client.post(
                f"/checkouts/{checkout_id}/complete",
                json=authorization.model_dump(mode="json"),
            )
        except httpx.HTTPError as err:
            raise HTTPException(
                status_code=502,
                detail=f"merchant gateway unreachable while completing {checkout_id}: {err}",
            ) from err

        if resp.status_code == 403:
            try:
                body = resp.json()
                problems = body.get("problems") or ["gateway refused order"]
            except ValueError:
                problems = ["gateway refused order"]
            return None, [str(p) for p in problems]
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"gateway complete returned HTTP {resp.status_code}",
            )

        try:
            order = Order.model_validate(resp.json())
        except (ValidationError, ValueError) as err:
            raise HTTPException(status_code=502, detail=f"gateway returned an invalid Order payload: {err}") from err

        if not order.receipt_jwt:
            raise HTTPException(status_code=502, detail="gateway order missing signed receipt_jwt")
        try:
            receipt_claims = verify_receipt(order.receipt_jwt, jwks)
        except TrustError as err:
            raise HTTPException(status_code=502, detail=f"invalid gateway receipt signature: {err}") from err

        if (
            receipt_claims.get("order_id") != order.order_id
            or receipt_claims.get("reference") != order.mandate_reference
            or receipt_claims.get("status") != "Success"
        ):
            raise HTTPException(status_code=502, detail="gateway receipt does not match order or mandate reference")
        return order, []

    api = FastAPI(title="Buyer Guardrails Harness", version="0.1")
    api.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.post("/authorize")
    def authorize(request: AuthorizeRequest) -> AuthorizationStatus:
        """Main entrypoint called by the agent (`authorize_checkout` MCP tool).

        The agent passes only `checkout_id` and `request_text`. The harness fetches the signed
        quote directly from the merchant gateway, verifies the signature, evaluates all rules,
        and then either signs (`auto`), queues a human approval (`human`), or refuses (`deny`).
        """
        now = clock.now().astimezone(HELSINKI)
        expired_items = active_store.expire_due(now)
        _record_expired_audits(expired_items, now)

        # Idempotent retry: asking to authorize the same quote twice returns its current status.
        existing = active_store.get_authorization(request.checkout_id)
        if existing is not None:
            return existing

        policy = load_policy(policy_path)
        log = _audit()

        with _gateway_client() as client:
            jwks = _fetch_jwks(client)
            checkout_jwt, raw_checkout = _fetch_quote(client, request.checkout_id)
            digest = checkout_hash(checkout_jwt)

            log.append(
                "buyer",
                "agent",
                "authorization_requested",
                f"The agent asked to order quote {request.checkout_id}.",
                f"Request: {request.request_text}",
                checkout_id=request.checkout_id,
                checkout_hash=digest,
                now=now,
            )

            checkout, sig_rule = _verify_quote_token(checkout_jwt, raw_checkout, jwks, now)
            if sig_rule.outcome == "pass":
                exp_str = f"{checkout.expires_at:%Y-%m-%d %H:%M}" if checkout.expires_at else "unknown"
                log.append(
                    "buyer",
                    "harness",
                    "quote_verified",
                    "Quote signature and expiry checked.",
                    f"Signed by {checkout.merchant.id}, valid until {exp_str}.",
                    checkout_id=checkout.id,
                    checkout_hash=digest,
                    rule="quote-signature",
                    now=now,
                )
            else:
                log.append(
                    "buyer",
                    "harness",
                    "quote_rejected",
                    "Quote signature check failed.",
                    sig_rule.message,
                    checkout_id=request.checkout_id,
                    checkout_hash=digest,
                    rule="quote-signature",
                    now=now,
                )

            verdict = evaluate(
                policy,
                checkout,
                now,
                sig_rule,
                judge=active_judge,
                checkout_hash=digest,
            )
            # Align checkout_id with requested id if an untrusted quote had a different id
            if verdict.checkout_id != request.checkout_id:
                verdict = verdict.model_copy(update={"checkout_id": request.checkout_id})

            v_what, v_why, v_rule = _verdict_audit_summary(verdict)
            log.append(
                "buyer",
                "harness",
                "verdict",
                v_what,
                v_why,
                checkout_id=verdict.checkout_id,
                checkout_hash=digest,
                rule=v_rule,
                now=now,
            )

            if verdict.decision == "deny":
                denied_status = AuthorizationStatus(
                    status="denied",
                    checkout_id=verdict.checkout_id,
                    decision="deny",
                    signed_by=None,
                    order_id=None,
                    reasons=[f"{r.rule_id}: {r.message}" for r in verdict.rules if r.outcome != "pass"],
                    approval_id=None,
                    approval_url=None,
                    deadline=None,
                )
                active_store.save_outcome(verdict, denied_status, checkout_jwt=checkout_jwt)
                return denied_status

            if verdict.decision == "human":
                approval, pending_status = active_store.create_approval(
                    verdict,
                    request.request_text,
                    checkout_jwt=checkout_jwt,
                    approval_url_base=harness_url(),
                    now=now,
                )
                log.append(
                    "buyer",
                    "harness",
                    "approval_requested",
                    f"Approval {approval.approval_id} opened for {verdict.total_minor / 100:.2f} {verdict.currency}.",
                    "; ".join(r.message for r in approval.reasons),
                    checkout_id=verdict.checkout_id,
                    checkout_hash=digest,
                    rule=approval.reasons[0].rule_id if approval.reasons else None,
                    now=now,
                )
                _invoke_notify(active_notify, approval, pending_status.approval_url)
                return pending_status

            # Verdict == "auto": reuse saved mandate on network retry so the gateway replays the same order,
            # or sign a fresh agent mandate inside the manager's open mandates and persist it before sending.
            cached_mandate = active_store.get_signed_mandate(verdict.checkout_id)
            if cached_mandate is not None and cached_mandate.signed_by == "agent":
                authorization = cached_mandate
            else:
                authorization = active_signer.sign_auto(checkout_jwt, policy=policy)
                active_store.save_signed_mandate(verdict.checkout_id, authorization, checkout_jwt=checkout_jwt)
                log.append(
                    "buyer",
                    "harness",
                    "mandate_signed",
                    "Mandate closed with the agent's key.",
                    "Verdict auto: the agent may sign inside the manager's open mandate.",
                    checkout_id=verdict.checkout_id,
                    checkout_hash=digest,
                    now=now,
                )

            order, problems = _submit_mandate_and_verify_receipt(
                client,
                verdict.checkout_id,
                authorization,
                jwks,
            )
            if order is None:
                refused_status = AuthorizationStatus(
                    status="denied",
                    checkout_id=verdict.checkout_id,
                    decision="deny",
                    signed_by=None,
                    order_id=None,
                    reasons=problems,
                    approval_id=None,
                    approval_url=None,
                    deadline=None,
                )
                log.append(
                    "buyer",
                    "harness",
                    "order_refused",
                    f"Gateway refused order for {verdict.checkout_id}.",
                    "; ".join(problems),
                    checkout_id=verdict.checkout_id,
                    checkout_hash=digest,
                    now=now,
                )
                active_store.save_outcome(verdict, refused_status, checkout_jwt=checkout_jwt)
                return refused_status

            merchant_label = checkout.merchant.name or checkout.merchant.id
            log.append(
                "buyer",
                "harness",
                "order_confirmed",
                f"Order {order.order_id} accepted by {merchant_label}.",
                f"Receipt signed by {checkout.merchant.id}, reference matches our mandate.",
                checkout_id=verdict.checkout_id,
                checkout_hash=digest,
                now=now,
            )
            ordered_status = AuthorizationStatus(
                status="ordered",
                checkout_id=verdict.checkout_id,
                decision="auto",
                signed_by="agent",
                order_id=order.order_id,
                reasons=[],
                approval_id=None,
                approval_url=None,
                deadline=None,
            )
            active_store.save_outcome(verdict, ordered_status, checkout_jwt=checkout_jwt)
            return ordered_status

    @api.post("/approvals/{approval_id}/decision")
    def decide_approval(approval_id: str, body: ApprovalDecision) -> AuthorizationStatus:
        now = clock.now().astimezone(HELSINKI)
        try:
            approval, expired_status, newly_expired = active_store.check_ready_for_decision(approval_id, now=now)
        except ApprovalNotFoundError as err:
            raise HTTPException(status_code=404, detail=f"unknown approval {approval_id}") from err
        except ApprovalAlreadyDecidedError as err:
            raise HTTPException(status_code=409, detail=str(err)) from err

        log = _audit()
        if expired_status is not None:
            if newly_expired:
                _record_expired_audits([approval], now)
            return expired_status

        if body.decision == "reject":
            _, rejected_status = active_store.record_rejected(approval_id, body.decided_by, now=now)
            log.append(
                "buyer",
                "human",
                "approval_rejected",
                f"Approval {approval_id} rejected by {body.decided_by}.",
                "The approver rejected the request.",
                checkout_id=approval.checkout_id,
                checkout_hash=approval.checkout_hash,
                now=now,
            )
            return rejected_status

        # Approve: verify quote hash still matches, sign (or replay) human mandate, complete order, verify receipt.
        stored_jwt = active_store.get_checkout_jwt(approval.checkout_id)
        with _gateway_client() as client:
            jwks = _fetch_jwks(client)
            if stored_jwt is None:
                stored_jwt, _ = _fetch_quote(client, approval.checkout_id)

            if checkout_hash(stored_jwt) != approval.checkout_hash:
                raise HTTPException(
                    status_code=409,
                    detail="quote token changed since approval was requested; hash mismatch",
                )

            quote_obj = read_checkout(stored_jwt)
            merchant_id = quote_obj.merchant.id
            merchant_label = quote_obj.merchant.name or merchant_id

            cached_mandate = active_store.get_signed_mandate(approval.checkout_id)
            if cached_mandate is not None and cached_mandate.signed_by == "human":
                authorization = cached_mandate
            else:
                authorization = active_signer.sign_human(stored_jwt)
                active_store.save_signed_mandate(approval.checkout_id, authorization, checkout_jwt=stored_jwt)
                log.append(
                    "buyer",
                    "human",
                    "mandate_signed",
                    f"Mandate signed by human ({body.decided_by}).",
                    f"Approved {approval_id} for exact quote hash {approval.checkout_hash}.",
                    checkout_id=approval.checkout_id,
                    checkout_hash=approval.checkout_hash,
                    now=now,
                )

            order, problems = _submit_mandate_and_verify_receipt(
                client,
                approval.checkout_id,
                authorization,
                jwks,
            )
            if order is None:
                # If the quote expired right as the decision arrived, transition the approval to `expired`.
                if any("expired" in p.lower() for p in problems):
                    exp_req, exp_status = active_store.record_expired(
                        approval_id,
                        reason="; ".join(problems),
                        now=now,
                    )
                    _record_expired_audits([exp_req], now)
                    return exp_status

                log.append(
                    "buyer",
                    "harness",
                    "order_refused",
                    f"Gateway refused human-signed order for {approval.checkout_id}.",
                    "; ".join(problems),
                    checkout_id=approval.checkout_id,
                    checkout_hash=approval.checkout_hash,
                    now=now,
                )
                raise HTTPException(status_code=403, detail={"problems": problems})

            _, approved_status = active_store.record_approved(
                approval_id,
                body.decided_by,
                order.order_id,
                now=now,
            )
            log.append(
                "buyer",
                "harness",
                "order_confirmed",
                f"Order {order.order_id} accepted by {merchant_label}.",
                f"Receipt signed by {merchant_id}, reference matches human mandate.",
                checkout_id=approval.checkout_id,
                checkout_hash=approval.checkout_hash,
                now=now,
            )
            return approved_status

    @api.get("/authorizations")
    def list_authorizations() -> list[AuthorizationStatus]:
        now = clock.now().astimezone(HELSINKI)
        _record_expired_audits(active_store.expire_due(now), now)
        return active_store.list_authorizations()

    @api.get("/authorizations/{checkout_id}")
    def get_authorization(checkout_id: str) -> AuthorizationStatus:
        now = clock.now().astimezone(HELSINKI)
        _record_expired_audits(active_store.expire_due(now), now)
        status = active_store.get_authorization(checkout_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"no authorization for {checkout_id}")
        return status

    @api.get("/verdicts/{checkout_id}")
    def get_verdict(checkout_id: str) -> Verdict:
        verdict = active_store.get_verdict(checkout_id)
        if verdict is None:
            raise HTTPException(status_code=404, detail=f"no verdict for {checkout_id}")
        return verdict

    @api.get("/approvals")
    def list_approvals(status: Annotated[ApprovalStatusFilter | None, Query()] = None) -> list[ApprovalRequest]:
        now = clock.now().astimezone(HELSINKI)
        _record_expired_audits(active_store.expire_due(now), now)
        return active_store.list_approvals(status=status)

    @api.get("/approvals/{approval_id}")
    def get_approval(approval_id: str) -> ApprovalRequest:
        now = clock.now().astimezone(HELSINKI)
        _record_expired_audits(active_store.expire_due(now), now)
        approval = active_store.get_approval(approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail=f"no approval {approval_id}")
        return approval

    @api.get("/policy")
    def get_policy() -> BuyerPolicy:
        return load_policy(policy_path)

    @api.get("/mandates/open")
    def get_open_mandate_proofs() -> dict[str, str]:
        return active_signer.open_mandate_proofs(load_policy(policy_path))

    @api.get("/audit")
    def get_audit() -> list[AuditEvent]:
        return _audit().read()

    if CONTRACT_EXAMPLES.exists():
        api.mount("/contract/examples", StaticFiles(directory=CONTRACT_EXAMPLES), name="contract_examples")
    if SURFACE_STATIC.exists():
        api.mount("/", StaticFiles(directory=SURFACE_STATIC, html=True), name="surface")

    return api


app = create_app()
