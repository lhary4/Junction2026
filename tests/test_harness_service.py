"""Tests for the buyer guardrails harness service (step L4): fake gateway + real merchant gateway integration."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from common.audit import AuditLog, default_log_path
from contract.models import (
    AimoCheckout,
    ApprovalRequest,
    AuditEvent,
    Authorization,
    AuthorizationStatus,
    CheckoutResponse,
    Order,
    Receipt,
    Verdict,
)
from harness.app import create_app
from merchant.app import app as real_merchant_app
from trust.checkout import checkout_hash, read_checkout, sign_checkout
from trust.keys import private_key, public_jwk, public_jwks
from trust.mandates import verify_mandates
from trust.receipts import sign_receipt, verify_receipt

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "contract" / "examples"
FIXTURES = ROOT / "contract" / "fixtures"

FROZEN_NOW = "2026-11-14T13:20:00+02:00"
AFTER_CUTOFF = "2026-11-15T17:05:00+02:00"


def _build_fake_gateway() -> tuple[FastAPI, dict[str, dict], list[tuple[str, Authorization]]]:
    """Minimal in-memory Valio gateway verifying real AP2 mandates and issuing real ES256 receipts."""
    merchant_key = private_key("merchant")
    manager_pub = public_jwk("manager")
    jwks = public_jwks()

    act1 = AimoCheckout.model_validate_json((EXAMPLES / "checkout.act1.json").read_text(encoding="utf-8"))
    act2 = AimoCheckout.model_validate_json((EXAMPLES / "checkout.act2.json").read_text(encoding="utf-8"))
    tampered_jwt = (FIXTURES / "checkout.tampered.jwt").read_text(encoding="utf-8").strip()

    quotes: dict[str, dict] = {
        act1.id: CheckoutResponse(
            checkout_id=act1.id,
            checkout_jwt=sign_checkout(act1, merchant_key),
            checkout=act1,
        ).model_dump(mode="json"),
        act2.id: CheckoutResponse(
            checkout_id=act2.id,
            checkout_jwt=sign_checkout(act2, merchant_key),
            checkout=act2,
        ).model_dump(mode="json"),
        "chk_tampered_demo": {
            "checkout_id": "chk_tampered_demo",
            "checkout_jwt": tampered_jwt,
            "checkout": read_checkout(tampered_jwt).model_dump(mode="json"),
        },
    }
    completed_calls: list[tuple[str, Authorization]] = []

    gw = FastAPI()

    @gw.get("/.well-known/jwks.json")
    def get_jwks():
        return jwks

    @gw.get("/checkouts/{checkout_id}")
    def get_checkout(checkout_id: str):
        if checkout_id not in quotes:
            raise HTTPException(status_code=404, detail="unknown checkout")
        return quotes[checkout_id]

    @gw.post("/checkouts/{checkout_id}/complete")
    def complete_checkout(checkout_id: str, authorization: Authorization):
        completed_calls.append((checkout_id, authorization))
        quote_entry = quotes[checkout_id]
        token = quote_entry["checkout_jwt"]
        check = verify_mandates(authorization, token, manager_pub)
        if not check.ok or check.signed_by is None or check.reference is None:
            raise HTTPException(status_code=403, detail={"problems": check.problems})

        parsed = read_checkout(token)
        order_id = f"ord_{uuid.uuid4().hex[:8]}"
        receipt_jwt = sign_receipt(order_id, check.reference, merchant_key)
        order = Order(
            order_id=order_id,
            status="accepted",
            checkout_id=checkout_id,
            checkout_hash=checkout_hash(token),
            mandate_reference=check.reference,
            signed_by=check.signed_by,
            total_minor=parsed.total_minor(),
            currency=parsed.currency,
            delivery_date=parsed.aimo.delivery_date,
            created_at=parsed.aimo.issued_at,
            accepted_at=parsed.aimo.issued_at,
            receipt_jwt=receipt_jwt,
            receipt=Receipt.model_validate(verify_receipt(receipt_jwt, jwks)),
        )
        return order.model_dump(mode="json")

    return gw, quotes, completed_calls


@pytest.fixture
def harness_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN_NOW)
    monkeypatch.setenv("VALIO_MODE", "replay")
    gw, quotes, completed_calls = _build_fake_gateway()
    with TestClient(gw) as gw_client:
        app = create_app(http_client=gw_client, judge_fn=lambda *_a, **_kw: [])
        with TestClient(app) as client:
            yield client, quotes, completed_calls, tmp_path


def test_auto_verdict_signs_as_agent_verifies_receipt_and_orders(harness_env):
    client, _, completed_calls, _ = harness_env

    resp = client.post(
        "/authorize",
        json={"checkout_id": "chk_act1_demo", "request_text": "I need 1,000 litres of lactose-free milk by Monday."},
    )
    assert resp.status_code == 200
    status = AuthorizationStatus.model_validate(resp.json())
    assert status.status == "ordered"
    assert status.decision == "auto"
    assert status.signed_by == "agent"
    assert status.order_id is not None and status.order_id.startswith("ord_")
    assert len(completed_calls) == 1
    assert completed_calls[0][1].signed_by == "agent"

    # GET /authorizations/{id} and GET /verdicts/{id} match
    fetched = AuthorizationStatus.model_validate(client.get("/authorizations/chk_act1_demo").json())
    assert fetched == status
    verdict = Verdict.model_validate(client.get("/verdicts/chk_act1_demo").json())
    assert verdict.decision == "auto"

    # Buyer audit log has all 5 steps and verifies hash chain
    audit_events = [AuditEvent.model_validate(e) for e in client.get("/audit").json()]
    assert [e.action for e in audit_events] == [
        "authorization_requested",
        "quote_verified",
        "verdict",
        "mandate_signed",
        "order_confirmed",
    ]
    assert AuditLog(default_log_path("buyer")).verify() is None


def test_human_then_approve_orders_with_human_signature_once(harness_env):
    client, _, completed_calls, tmp_path = harness_env

    resp = client.post(
        "/authorize",
        json={"checkout_id": "chk_act2_demo", "request_text": "Make it 2,000 litres."},
    )
    assert resp.status_code == 200
    pending = AuthorizationStatus.model_validate(resp.json())
    assert pending.status == "pending_approval"
    assert pending.decision == "human"
    assert pending.signed_by is None
    assert pending.order_id is None
    assert pending.approval_id is not None
    assert pending.approval_url == f"http://localhost:8002/#/approvals/{pending.approval_id}"
    assert len(completed_calls) == 0

    # Pending list contains the approval and matches persisted JSON file
    pending_list = [ApprovalRequest.model_validate(a) for a in client.get("/approvals?status=pending").json()]
    assert [a.approval_id for a in pending_list] == [pending.approval_id]
    assert (tmp_path / "buyer" / "approvals.json").exists()

    # Human approves
    decide_resp = client.post(
        f"/approvals/{pending.approval_id}/decision",
        json={"decision": "approve", "decided_by": "procurement.manager@demo-hotel.example"},
    )
    assert decide_resp.status_code == 200
    ordered = AuthorizationStatus.model_validate(decide_resp.json())
    assert ordered.status == "ordered"
    assert ordered.decision == "human"
    assert ordered.signed_by == "human"
    assert ordered.order_id is not None
    assert len(completed_calls) == 1
    assert completed_calls[0][1].signed_by == "human"

    # Approval is no longer pending, and deciding a second time is HTTP 409
    assert client.get("/approvals?status=pending").json() == []
    second = client.post(
        f"/approvals/{pending.approval_id}/decision",
        json={"decision": "reject", "decided_by": "procurement.manager@demo-hotel.example"},
    )
    assert second.status_code == 409
    assert AuditLog(default_log_path("buyer")).verify() is None


def test_human_then_reject_creates_no_order(harness_env):
    client, _, completed_calls, _ = harness_env

    pending = AuthorizationStatus.model_validate(
        client.post(
            "/authorize",
            json={"checkout_id": "chk_act2_demo", "request_text": "Make it 2,000 litres."},
        ).json()
    )
    assert pending.approval_id is not None

    decide_resp = client.post(
        f"/approvals/{pending.approval_id}/decision",
        json={"decision": "reject", "decided_by": "procurement.manager@demo-hotel.example"},
    )
    assert decide_resp.status_code == 200
    rejected = AuthorizationStatus.model_validate(decide_resp.json())
    assert rejected.status == "rejected"
    assert rejected.signed_by is None
    assert rejected.order_id is None
    assert completed_calls == []

    # Second decision attempt is refused
    again = client.post(
        f"/approvals/{pending.approval_id}/decision",
        json={"decision": "approve", "decided_by": "procurement.manager@demo-hotel.example"},
    )
    assert again.status_code == 409


def test_tampered_quote_is_denied_and_never_signed(harness_env):
    client, _, completed_calls, _ = harness_env

    resp = client.post(
        "/authorize",
        json={"checkout_id": "chk_tampered_demo", "request_text": "Order the discounted quote."},
    )
    assert resp.status_code == 200
    denied = AuthorizationStatus.model_validate(resp.json())
    assert denied.status == "denied"
    assert denied.decision == "deny"
    assert denied.signed_by is None
    assert denied.order_id is None
    assert any("quote-signature" in r for r in denied.reasons)
    assert completed_calls == []
    assert AuditLog(default_log_path("buyer")).verify() is None


def test_deciding_after_cutoff_deadline_returns_expired(harness_env, monkeypatch):
    client, _, completed_calls, _ = harness_env

    pending = AuthorizationStatus.model_validate(
        client.post(
            "/authorize",
            json={"checkout_id": "chk_act2_demo", "request_text": "Make it 2,000 litres."},
        ).json()
    )
    assert pending.approval_id is not None

    monkeypatch.setenv("AIMO_FROZEN_NOW", AFTER_CUTOFF)
    resp = client.post(
        f"/approvals/{pending.approval_id}/decision",
        json={"decision": "approve", "decided_by": "procurement.manager@demo-hotel.example"},
    )
    assert resp.status_code == 200
    expired = AuthorizationStatus.model_validate(resp.json())
    assert expired.status == "expired"
    assert expired.order_id is None
    assert completed_calls == []


def test_policy_surface_static_and_cors(harness_env):
    client, _, _, _ = harness_env

    pol = client.get("/policy", headers={"Origin": "http://localhost:8003"})
    assert pol.status_code == 200
    assert pol.headers["access-control-allow-origin"] == "http://localhost:8003"
    assert pol.json()["policy_id"] == "pol_demo_restaurant_1"
    assert pol.json()["customer"] == "demo-restaurant-helsinki"
    assert pol.json()["approver"] == "chef@demo-restaurant.example"

    page = client.get("/")
    assert page.status_code == 200
    assert "Trusted Trade Agents" in page.text


# ---------- Real cross-service integration with Adrien's merchant.app ----------


def test_real_gateway_and_harness_end_to_end_act1_and_act2(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN_NOW)

    with TestClient(real_merchant_app) as merchant_client:
        harness_app = create_app(http_client=merchant_client, judge_fn=lambda *_a, **_kw: [])
        with TestClient(harness_app) as harness_client:
            # Act 1: 1,000 L of 464306 -> EUR 1,010 -> auto -> ordered with agent signature
            q1 = merchant_client.post(
                "/checkouts",
                json={
                    "customer": "demo-hotel-chain",
                    "delivery_date": "2026-11-16",
                    "needs": [{"product_id": "464306", "amount": 1000, "unit": "L"}],
                },
            )
            assert q1.status_code == 200
            chk1_id = q1.json()["checkout_id"]

            a1 = harness_client.post(
                "/authorize",
                json={"checkout_id": chk1_id, "request_text": "I need 1,000 litres of lactose-free milk by Monday."},
            )
            assert a1.status_code == 200
            s1 = AuthorizationStatus.model_validate(a1.json())
            assert s1.status == "ordered"
            assert s1.signed_by == "agent"
            assert s1.order_id is not None

            order1 = Order.model_validate(merchant_client.get(f"/orders/{s1.order_id}").json())
            assert order1.signed_by == "agent"
            assert order1.total_minor == 101000

            # Act 2: 2,000 L of 464306 -> EUR 2,020 -> pending_approval -> human approves -> ordered with human signature
            q2 = merchant_client.post(
                "/checkouts",
                json={
                    "customer": "demo-hotel-chain",
                    "delivery_date": "2026-11-16",
                    "needs": [{"product_id": "464306", "amount": 2000, "unit": "L"}],
                },
            )
            assert q2.status_code == 200
            chk2_id = q2.json()["checkout_id"]

            a2 = harness_client.post(
                "/authorize",
                json={"checkout_id": chk2_id, "request_text": "Make it 2,000 litres."},
            )
            p2 = AuthorizationStatus.model_validate(a2.json())
            assert p2.status == "pending_approval"
            assert p2.approval_id is not None

            d2 = harness_client.post(
                f"/approvals/{p2.approval_id}/decision",
                json={"decision": "approve", "decided_by": "procurement.manager@demo-hotel.example"},
            )
            s2 = AuthorizationStatus.model_validate(d2.json())
            assert s2.status == "ordered"
            assert s2.signed_by == "human"
            assert s2.order_id is not None

            order2 = Order.model_validate(merchant_client.get(f"/orders/{s2.order_id}").json())
            assert order2.signed_by == "human"
            assert order2.total_minor == 202000

            # Both buyer and merchant audit logs verify cleanly!
            assert AuditLog(default_log_path("buyer")).verify() is None
            assert AuditLog(default_log_path("merchant")).verify() is None
            assert len(json.loads(merchant_client.get("/audit").text)) >= 6


def test_real_gateway_act3_coffee_milk_calls_judge_and_deadline_matches_quote_expiry(tmp_path, monkeypatch):
    """Covers Adrien's findings #1 and #2 against the real merchant.app in replay mode."""
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN_NOW)

    judge_calls: list[tuple[dict, dict]] = []

    def recording_judge(original: dict, candidate: dict, _prefs: str, **_kw) -> list[dict]:
        judge_calls.append((original, candidate))
        # Valio UHT milk 464201 is accepted (0.95); Arla Cafe milk 463380 is sent to human (0.09)
        prob = 0.95 if candidate["id"] == "464201" else 0.09
        return [
            {
                "question_key": "within_preferences",
                "type": "noul",
                "instructions": "within preferences?",
                "subject": {"original": original["id"], "candidate": candidate["id"]},
                "probability": prob,
                "confidence": 0.95,
                "auto_threshold": 0.85,
                "floor": 0.15,
                "routed": "auto" if prob >= 0.85 else "human",
                "model": "gemini-decision-1",
            },
            {
                "question_key": "same_use",
                "type": "noul",
                "instructions": "same use?",
                "subject": {"original": original["id"], "candidate": candidate["id"]},
                "probability": prob,
                "confidence": 0.95,
                "auto_threshold": 0.85,
                "floor": 0.15,
                "routed": "auto" if prob >= 0.85 else "human",
                "model": "gemini-decision-1",
            },
        ]

    with TestClient(real_merchant_app) as merchant_client:
        harness_app = create_app(http_client=merchant_client, judge_fn=recording_judge)
        with TestClient(harness_app) as harness_client:
            # 1) Default Valio Act 3 pick (469363 -> 464306, catalog-listed) stays `auto` with 0 judge calls
            q_default = merchant_client.post(
                "/checkouts",
                json={
                    "customer": "demo-hotel-chain",
                    "delivery_date": "2026-11-16",
                    "needs": [{"product_id": "469363", "amount": 500, "unit": "L"}],
                },
            ).json()
            s_default = AuthorizationStatus.model_validate(
                harness_client.post(
                    "/authorize",
                    json={"checkout_id": q_default["checkout_id"], "request_text": "500 L of Arla milk."},
                ).json()
            )
            assert s_default.status == "ordered"
            assert len(judge_calls) == 0

            # 2) Agent picks Arla Cafe milk (463380) -> MUST call judge (with enriched claims) -> pending_approval!
            q_cafe = merchant_client.post(
                "/checkouts",
                json={
                    "customer": "demo-hotel-chain",
                    "delivery_date": "2026-11-16",
                    "needs": [{"product_id": "469363", "amount": 500, "unit": "L", "substitute_with": "463380"}],
                },
            ).json()
            s_cafe = AuthorizationStatus.model_validate(
                harness_client.post(
                    "/authorize",
                    json={"checkout_id": q_cafe["checkout_id"], "request_text": "500 L of Arla milk."},
                ).json()
            )
            assert s_cafe.status == "pending_approval"
            assert len(judge_calls) == 1
            orig_sent, cand_sent = judge_calls[0]
            assert "FREE_FROM_LACTOSE" in orig_sent.get("nutritional_claims", [])
            assert "FREE_FROM_LACTOSE" in cand_sent.get("nutritional_claims", [])
            assert "GOODS_FROM_FINLAND_BLUE_SWAN" in orig_sent.get("labels", [])
            assert (orig_sent.get("brand") or "").strip() == "Arla"
            assert (cand_sent.get("brand") or "").strip() == "Arla"
            assert orig_sent.get("size_per_sales_unit", {}).get("unit") == "L"
            assert cand_sent.get("size_per_sales_unit", {}).get("unit") == "L"

            # 3) Approval deadline equals quote's `expires_at` (not 17:00), so at 15:00 next day it expires cleanly!
            assert s_cafe.deadline == datetime.fromisoformat(q_cafe["checkout"]["expires_at"])
            monkeypatch.setenv("AIMO_FROZEN_NOW", "2026-11-15T15:00:00+02:00")
            dec = harness_client.post(
                f"/approvals/{s_cafe.approval_id}/decision",
                json={"decision": "approve", "decided_by": "procurement.manager@demo-hotel.example"},
            )
            assert dec.status_code == 200
            assert dec.json()["status"] == "expired"

            # 4) Agent picks Valio UHT milk (464201) -> calls judge -> judge approves (0.95) -> `ordered`!
            monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN_NOW)
            q_valio_uht = merchant_client.post(
                "/checkouts",
                json={
                    "customer": "demo-hotel-chain",
                    "delivery_date": "2026-11-16",
                    "needs": [{"product_id": "469363", "amount": 500, "unit": "L", "substitute_with": "464201"}],
                },
            ).json()
            s_valio_uht = AuthorizationStatus.model_validate(
                harness_client.post(
                    "/authorize",
                    json={"checkout_id": q_valio_uht["checkout_id"], "request_text": "500 L of Arla milk."},
                ).json()
            )
            assert s_valio_uht.status == "ordered"
            assert s_valio_uht.signed_by == "agent"


def test_network_error_malformed_outer_checkout_and_lost_complete_retry(tmp_path, monkeypatch):
    """Covers Adrien's finding #3: HTTP 502 on gateway down, clean deny on malformed outer checkout,
    and replaying the identical signed mandate when a `/complete` response was lost."""
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN_NOW)

    # 1) Unreachable gateway -> clean HTTP 502, never a bare 500
    def unreachable_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    down_app = create_app(http_client=httpx.Client(transport=httpx.MockTransport(unreachable_handler), base_url="http://gw"))
    with TestClient(down_app) as down_client:
        r_down = down_client.post("/authorize", json={"checkout_id": "chk_1", "request_text": "Order milk."})
        assert r_down.status_code == 502
        assert "unreachable" in r_down.json()["detail"]

    # 2) Outer `checkout` missing required fields next to valid JWT -> clean `denied` (`quote-signature`), never 500
    act1 = AimoCheckout.model_validate(json.loads((EXAMPLES / "checkout.act1.json").read_text(encoding="utf-8")))
    act1_jwt = sign_checkout(act1, private_key("merchant"))

    def broken_outer_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/.well-known/jwks.json":
            return httpx.Response(200, json=public_jwks())
        if request.url.path == f"/checkouts/{act1.id}":
            return httpx.Response(200, json={"checkout_id": act1.id, "checkout_jwt": act1_jwt, "checkout": {"id": act1.id}})
        return httpx.Response(404)

    broken_app = create_app(
        http_client=httpx.Client(transport=httpx.MockTransport(broken_outer_handler), base_url="http://gw")
    )
    with TestClient(broken_app) as broken_client:
        r_broken = broken_client.post("/authorize", json={"checkout_id": act1.id, "request_text": "Order milk."})
        assert r_broken.status_code == 200
        assert r_broken.json()["status"] == "denied"
        assert any("quote-signature" in reason for reason in r_broken.json()["reasons"])

    # 3) Answer lost after gateway accepted `/complete`: retry resends identical mandate and gets `ordered`!
    with TestClient(real_merchant_app) as real_gw:
        q = real_gw.post(
            "/checkouts",
            json={
                "customer": "demo-hotel-chain",
                "delivery_date": "2026-11-16",
                "needs": [{"product_id": "464306", "amount": 1000, "unit": "L"}],
            },
        ).json()
        chk_id = q["checkout_id"]

        complete_attempts = 0

        def flaky_complete_handler(request: httpx.Request) -> httpx.Response:
            nonlocal complete_attempts
            resp = real_gw.request(
                request.method,
                str(request.url.raw_path, "ascii"),
                content=request.content,
                headers=dict(request.headers),
            )
            if request.method == "POST" and request.url.path.endswith("/complete"):
                complete_attempts += 1
                if complete_attempts == 1:
                    # Gateway ALREADY accepted & saved the order, then the network drops before harness sees it!
                    assert resp.status_code == 200
                    raise httpx.ReadTimeout("response lost in transit", request=request)
            return httpx.Response(resp.status_code, content=resp.content, headers=dict(resp.headers))

        flaky_client = httpx.Client(transport=httpx.MockTransport(flaky_complete_handler), base_url="http://gw")
        retry_app = create_app(http_client=flaky_client)
        with TestClient(retry_app) as retry_client:
            first_try = retry_client.post("/authorize", json={"checkout_id": chk_id, "request_text": "1000 L milk."})
            assert first_try.status_code == 502  # first call lost response

            second_try = retry_client.post("/authorize", json={"checkout_id": chk_id, "request_text": "1000 L milk."})
            assert second_try.status_code == 200
            recovered = AuthorizationStatus.model_validate(second_try.json())
            assert recovered.status == "ordered"
            assert recovered.signed_by == "agent"
            assert recovered.order_id is not None
            assert complete_attempts == 2
            assert AuditLog(default_log_path("buyer")).verify() is None
