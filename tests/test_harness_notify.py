"""Tests for step L6 (`harness/notify.py` + `harness/app.py` integration) using httpx.MockTransport."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
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
    AuthorizationStatus,
    CheckoutResponse,
    RuleResult,
)
from harness.app import create_app
from harness.notify import DEFAULT_TIMEOUT_SECONDS, NotifyResult, notify_approval
from trust.checkout import read_checkout, sign_checkout
from trust.keys import private_key, public_jwks

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "contract" / "examples"
FIXTURES = ROOT / "contract" / "fixtures"
FROZEN_NOW = "2026-11-14T13:20:00+02:00"
SECRET_TOKEN = "987654321:AAH_super_secret_chef_bot_token_42"
ENCODED_SECRET_TOKEN = "987654321%3AAAH_super_secret_chef_bot_token_42"
CHAT_ID = "-100192837465"


def _sample_approval(
    *,
    total_minor: int = 17232,
    deadline: datetime | None = datetime(2026, 11, 15, 15, 0, tzinfo=UTC),
    reasons: list[RuleResult] | None = None,
) -> ApprovalRequest:
    if reasons is None:
        reasons = [
            RuleResult(
                rule_id="substitution-within-preferences",
                outcome="human",
                message="The judge is unsure about this substitute (0.48, threshold 0.85): a human must sign.",
                evidence={"original": "474880", "substitute": "475072"},
            )
        ]
    return ApprovalRequest(
        approval_id="apr_7c1e0b52",
        checkout_id="chk_sub_demo",
        checkout_hash="2vSHcWbHMqq_qrVjbTJK6qv2sTzYBJK590250T5WPLU",
        status="pending",
        total_minor=total_minor,
        currency="EUR",
        reasons=reasons,
        judge=[],
        request_text="Order squeaky cheese for the Nordic menu.",
        requested_at=datetime(2026, 11, 14, 11, 20, tzinfo=UTC),
        deadline=deadline,
        decided_by=None,
        decided_at=None,
        order_id=None,
    )


def _build_quote_gateway() -> FastAPI:
    """Minimal in-memory gateway serving valid auto, human, and tampered quotes."""
    merchant_key = private_key("merchant")
    jwks = public_jwks()

    act1 = AimoCheckout.model_validate_json((EXAMPLES / "checkout.act1.json").read_text(encoding="utf-8"))
    act2 = AimoCheckout.model_validate_json((EXAMPLES / "checkout.act2.json").read_text(encoding="utf-8"))
    tampered_jwt = (FIXTURES / "checkout.tampered.jwt").read_text(encoding="utf-8").strip()

    quotes = {
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

    gw = FastAPI()

    @gw.get("/.well-known/jwks.json")
    def get_jwks():
        return jwks

    @gw.get("/checkouts/{checkout_id}")
    def get_checkout(checkout_id: str):
        if checkout_id not in quotes:
            raise HTTPException(status_code=404, detail="unknown checkout")
        return quotes[checkout_id]

    return gw


@pytest.mark.parametrize(
    ("token_val", "chat_val"),
    [
        (None, None),
        ("", ""),
        ("   ", CHAT_ID),
        (SECRET_TOKEN, ""),
        (None, CHAT_ID),
        (SECRET_TOKEN, None),
    ],
)
def test_unset_or_empty_telegram_vars_make_zero_http_calls(monkeypatch, token_val, chat_val):
    if token_val is None:
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token_val)

    if chat_val is None:
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_CHAT_ID", chat_val)

    requests_made: list[httpx.Request] = []

    def fail_if_called(request: httpx.Request) -> httpx.Response:
        requests_made.append(request)
        raise AssertionError("No HTTP call may happen when Telegram vars are unset or empty")

    mock_client = httpx.Client(transport=httpx.MockTransport(fail_if_called))
    result = notify_approval(_sample_approval(), http_client=mock_client)

    assert result == NotifyResult(status="skipped", reason="telegram_not_configured")
    assert not result
    assert requests_made == []


def test_configured_vars_send_concise_telegram_alert_with_helsinki_deadline_and_page_link(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT_ID)
    monkeypatch.setenv("HARNESS_URL", "http://localhost:8002/")

    captured: list[httpx.Request] = []

    def ok_handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 101}})

    # Deadline 15:00 UTC in November is 17:00 Europe/Helsinki (+02:00)
    approval = _sample_approval(
        total_minor=17232,
        deadline=datetime(2026, 11, 15, 15, 0, tzinfo=UTC),
    )
    mock_client = httpx.Client(transport=httpx.MockTransport(ok_handler))
    result = notify_approval(approval, http_client=mock_client)

    assert result.sent is True
    assert bool(result) is True
    assert len(captured) == 1

    req = captured[0]
    assert req.method == "POST"
    assert str(req.url) == f"https://api.telegram.org/bot{SECRET_TOKEN}/sendMessage"

    # Verify strict 2.0-second timeout was passed to httpx
    timeouts = req.extensions.get("timeout", {})
    assert timeouts.get("read") == DEFAULT_TIMEOUT_SECONDS
    assert timeouts.get("connect") == DEFAULT_TIMEOUT_SECONDS

    payload = json.loads(req.content.decode("utf-8"))
    assert payload["chat_id"] == CHAT_ID
    assert payload["disable_web_page_preview"] is True

    text = payload["text"]
    assert "The judge is unsure about this substitute (0.48, threshold 0.85): a human must sign." in text
    assert "172.32 EUR" in text
    assert "2026-11-15 17:00" in text  # Converted from 15:00 UTC to Europe/Helsinki
    assert "http://localhost:8002/#/approvals/apr_7c1e0b52" in text
    # Approval stays on the web page, never inline callback buttons in Telegram
    assert "reply_markup" not in payload


def test_env_file_fallback_and_none_deadline_and_multi_rule_one_sentence(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("HARNESS_URL", raising=False)

    env_file = tmp_path / ".env"
    env_file.write_text(
        f"TELEGRAM_BOT_TOKEN={SECRET_TOKEN}\n"
        f"TELEGRAM_CHAT_ID={CHAT_ID}\n"
        "HARNESS_URL=https://portal.demo.example\n",
        encoding="utf-8",
    )

    captured: list[dict] = []

    def ok_handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 102}})

    approval = _sample_approval(
        deadline=None,
        reasons=[
            RuleResult(
                rule_id="spend-limit",
                outcome="human",
                message="2020.00 EUR is above the 1500.00 EUR limit: a human must sign.",
            ),
            RuleResult(
                rule_id="delivery-on-time",
                outcome="human",
                message="Delivery on 2026-11-17 is later than requested 2026-11-16: a human must sign.",
            ),
        ],
    )
    mock_client = httpx.Client(transport=httpx.MockTransport(ok_handler))
    result = notify_approval(approval, http_client=mock_client, env_path=env_file)

    assert result.sent is True
    assert len(captured) == 1
    lines = captured[0]["text"].splitlines()
    reason_line = next(line for line in lines if line.startswith("Reason: "))
    assert "plus 1 more triggered rule" in reason_line
    assert "Deadline (Helsinki): none" in captured[0]["text"]
    assert "https://portal.demo.example/#/approvals/apr_7c1e0b52" in captured[0]["text"]


@pytest.mark.parametrize(
    "failure_mode",
    ["timeout", "connect_error", "http_500", "telegram_not_ok", "invalid_json"],
)
def test_failures_are_swallowed_and_bot_token_is_never_logged(monkeypatch, caplog, failure_mode):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT_ID)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        if failure_mode == "timeout":
            raise httpx.ReadTimeout(f"Read timed out for url {request.url}", request=request)
        if failure_mode == "connect_error":
            raise httpx.ConnectError(
                f"DNS lookup failed for https://api.telegram.org/bot{ENCODED_SECRET_TOKEN}/sendMessage",
                request=request,
            )
        if failure_mode == "http_500":
            return httpx.Response(500, text=f"Upstream error on /bot{SECRET_TOKEN}/sendMessage")
        if failure_mode == "telegram_not_ok":
            return httpx.Response(200, json={"ok": False, "description": f"Unauthorized token {SECRET_TOKEN}"})
        return httpx.Response(200, content=b"<<<not-json>>>")

    mock_client = httpx.Client(transport=httpx.MockTransport(failing_handler))
    with caplog.at_level(logging.WARNING, logger="harness.notify"):
        result = notify_approval(_sample_approval(), http_client=mock_client)

    assert result.status == "failed"
    assert not result
    assert len(caplog.records) == 1
    assert SECRET_TOKEN not in caplog.text
    assert ENCODED_SECRET_TOKEN not in caplog.text
    if failure_mode == "invalid_json":
        assert "JSONDecodeError" in caplog.text
    else:
        assert "<redacted>" in caplog.text


def test_harness_authorize_notifies_once_on_new_pending_approval_not_on_repeat(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN_NOW)
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT_ID)

    sent_payloads: list[dict] = []

    def telegram_handler(request: httpx.Request) -> httpx.Response:
        sent_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"ok": True, "result": {"message_id": len(sent_payloads)}})

    tg_client = httpx.Client(transport=httpx.MockTransport(telegram_handler))
    gw = _build_quote_gateway()

    with TestClient(gw) as gw_client:
        app = create_app(
            http_client=gw_client,
            judge_fn=lambda *_a, **_kw: [],
            notify_fn=lambda approval, approval_url=None: notify_approval(
                approval,
                approval_url=approval_url,
                http_client=tg_client,
            ),
        )
        with TestClient(app) as client:
            # 1) Denied quote -> zero Telegram messages
            r_deny = client.post(
                "/authorize",
                json={"checkout_id": "chk_tampered_demo", "request_text": "Order tampered quote."},
            )
            assert r_deny.status_code == 200
            assert r_deny.json()["status"] == "denied"
            assert sent_payloads == []

            # 2) New pending human approval (EUR 2,020 > EUR 1,500 cap) -> sends ONE Telegram message
            r_first = client.post(
                "/authorize",
                json={"checkout_id": "chk_act2_demo", "request_text": "Make it 2,000 litres."},
            )
            assert r_first.status_code == 200
            first_status = AuthorizationStatus.model_validate(r_first.json())
            assert first_status.status == "pending_approval"
            assert first_status.approval_id is not None
            assert first_status.approval_url == f"http://localhost:8002/#/approvals/{first_status.approval_id}"
            assert len(sent_payloads) == 1
            assert "2020.00 EUR" in sent_payloads[0]["text"]
            assert first_status.approval_url in sent_payloads[0]["text"]

            # 3) Idempotent repeat POST /authorize on already-pending checkout -> does NOT spam a second message
            r_repeat = client.post(
                "/authorize",
                json={"checkout_id": "chk_act2_demo", "request_text": "Make it 2,000 litres."},
            )
            assert r_repeat.status_code == 200
            repeat_status = AuthorizationStatus.model_validate(r_repeat.json())
            assert repeat_status == first_status
            assert len(sent_payloads) == 1


def test_telegram_outage_never_blocks_pending_verdict_or_breaks_audit_chain(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AIMO_FROZEN_NOW", FROZEN_NOW)
    monkeypatch.setenv("VALIO_MODE", "replay")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", SECRET_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT_ID)

    def broken_telegram(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout(f"Timed out connecting to {request.url}", request=request)

    tg_client = httpx.Client(transport=httpx.MockTransport(broken_telegram))
    gw = _build_quote_gateway()

    with TestClient(gw) as gw_client:
        app = create_app(
            http_client=gw_client,
            judge_fn=lambda *_a, **_kw: [],
            notify_fn=lambda approval, approval_url=None: notify_approval(
                approval,
                approval_url=approval_url,
                http_client=tg_client,
            ),
        )
        with TestClient(app) as client, caplog.at_level(logging.WARNING, logger="harness.notify"):
            resp = client.post(
                "/authorize",
                json={"checkout_id": "chk_act2_demo", "request_text": "Make it 2,000 litres."},
            )
            assert resp.status_code == 200
            pending = AuthorizationStatus.model_validate(resp.json())
            assert pending.status == "pending_approval"
            assert pending.decision == "human"
            assert pending.approval_id is not None

            # Token never leaked in logs
            assert SECRET_TOKEN not in caplog.text
            assert ENCODED_SECRET_TOKEN not in caplog.text

            # Buyer audit log recorded all 4 expected steps and its SHA-256 chain is intact
            events = [AuditEvent.model_validate(e) for e in client.get("/audit").json()]
            assert [e.action for e in events] == [
                "authorization_requested",
                "quote_verified",
                "verdict",
                "approval_requested",
            ]
            assert AuditLog(default_log_path("buyer")).verify() is None
