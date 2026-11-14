"""Optional Telegram alert when an order waits for human approval (step L6).

Why this module is shaped the way it is:
- A chef in kitchen service is not watching a browser tab, so the harness sends one short
  alert to Telegram with the reason, the total, the Helsinki deadline, and a link to the page.
- Approving and signing NEVER happen inside Telegram chat (a chat button cannot verify a
  browser passkey or bind the click to the exact ES256-signed quote shown on screen).
- Notifications are strictly best-effort: missing settings make zero network calls, a strict
  2-second timeout bounds latency, and every network/HTTP/JSON error is logged (with the bot
  token redacted) and swallowed so an alert problem can never change, fail, or delay a verdict.
"""

from __future__ import annotations

import logging
import os
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx

from contract.models import ApprovalRequest

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
ROOT = _REPO_ROOT
HELSINKI = ZoneInfo("Europe/Helsinki")
TELEGRAM_API_BASE = "https://api.telegram.org"
DEFAULT_HARNESS_URL = "http://localhost:8002"
DEFAULT_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class NotifyResult:
    """Outcome of a best-effort chef notification attempt.

    Evaluates truthy (`bool(result) is True`) only when Telegram accepted the message,
    while still distinguishing `skipped` (no env vars set) from `failed` (error swallowed).
    """

    status: Literal["sent", "skipped", "failed"]
    reason: str | None = None

    @property
    def sent(self) -> bool:
        return self.status == "sent"

    def __bool__(self) -> bool:
        return self.status == "sent"


NotifyFn = Callable[..., Any]


def _from_env_file(name: str, env_path: Path | None = None) -> str | None:
    """Read one variable from `.env` without exporting it to the process environment."""
    # During pytest runs, ignore real Telegram credentials in the repo's `.env` unless a test
    # explicitly points `env_path` or `ROOT` at a test `.env` file, so unrelated service tests
    # never send real messages to the chef's phone.
    if (
        env_path is None
        and ROOT == _REPO_ROOT
        and "PYTEST_CURRENT_TEST" in os.environ
        and name.startswith("TELEGRAM_")
    ):
        return None

    path = env_path if env_path is not None else (ROOT / ".env")
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == name and not key.lstrip().startswith("#"):
            cleaned = value.strip().strip("'\"")
            return cleaned or None
    return None


def _resolve_setting(
    name: str,
    explicit: str | None = None,
    *,
    env_path: Path | None = None,
) -> str | None:
    """Resolve a setting from an explicit argument, then `os.environ`, then `.env`."""
    if explicit is not None:
        return explicit.strip() or None
    if name in os.environ:
        return os.environ[name].strip() or None
    return _from_env_file(name, env_path=env_path)


def default_approval_url(approval_id: str, *, env_path: Path | None = None) -> str:
    """Build the direct link to the web approval page (never an in-chat approval action)."""
    base = (
        _resolve_setting("HARNESS_URL", env_path=env_path) or DEFAULT_HARNESS_URL
    ).rstrip("/")
    return f"{base}/#/approvals/{approval_id}"


def _one_sentence_reason(approval: ApprovalRequest) -> str:
    """Summarize why human approval is needed in a single clean sentence."""
    if not approval.reasons:
        return "A guardrail rule routed this order to human review."

    first = " ".join(approval.reasons[0].message.split())
    if len(approval.reasons) == 1:
        return first if first.endswith((".", "!", "?")) else f"{first}."

    extra = len(approval.reasons) - 1
    noun = "rule" if extra == 1 else "rules"
    return f"{first.rstrip('.!?')} (plus {extra} more triggered {noun})."


def format_approval_message(
    approval: ApprovalRequest,
    *,
    approval_url: str | None = None,
    env_path: Path | None = None,
) -> str:
    """Format a concise plain-text Telegram alert for the chef.

    We intentionally send plain text (no Telegram Markdown parse mode) so underscores or
    parentheses in product/checkout IDs and URLs can never cause a 400 formatting error.
    """
    reason = _one_sentence_reason(approval)
    total_str = f"{approval.total_minor / 100:.2f} {approval.currency}"
    deadline_str = (
        approval.deadline.astimezone(HELSINKI).strftime("%Y-%m-%d %H:%M")
        if approval.deadline is not None
        else "none"
    )
    link = approval_url or default_approval_url(approval.approval_id, env_path=env_path)
    return (
        f"Approval needed ({approval.checkout_id})\n"
        f"Reason: {reason}\n"
        f"Total: {total_str}\n"
        f"Deadline (Helsinki): {deadline_str}\n"
        f"Approve or reject on the page: {link}"
    )


def _redact_token(text: str, token: str) -> str:
    """Remove the bot token (raw or URL-encoded) from any error text before logging."""
    if not token:
        return text
    redacted = text.replace(token, "<redacted>")
    encoded = urllib.parse.quote(token, safe="")
    if encoded != token:
        redacted = redacted.replace(encoded, "<redacted>")
    return re.sub(r"bot[^/\s]+/", "bot<redacted>/", redacted)


def notify_approval(
    approval: ApprovalRequest,
    *,
    approval_url: str | None = None,
    bot_token: str | None = None,
    chat_id: str | None = None,
    http_client: httpx.Client | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    env_path: Path | None = None,
) -> NotifyResult:
    """Send one Telegram message when a pending human approval is created.

    - If `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID` is unset/empty, returns `skipped`
      immediately without opening any network connection.
    - Enforces a strict 2.0-second timeout by default.
    - Swallows and logs any network, HTTP, or JSON failure (with the bot token redacted)
      so notification issues never block, fail, or delay a harness verdict.
    """
    resolved_token = _resolve_setting("TELEGRAM_BOT_TOKEN", bot_token, env_path=env_path)
    resolved_chat_id = _resolve_setting("TELEGRAM_CHAT_ID", chat_id, env_path=env_path)
    if not resolved_token or not resolved_chat_id:
        return NotifyResult(status="skipped", reason="telegram_not_configured")

    url = f"{TELEGRAM_API_BASE}/bot{resolved_token}/sendMessage"
    payload = {
        "chat_id": resolved_chat_id,
        "text": format_approval_message(approval, approval_url=approval_url, env_path=env_path),
        "disable_web_page_preview": True,
    }

    try:
        if http_client is not None:
            response = http_client.post(url, json=payload, timeout=timeout_seconds)
        else:
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.post(url, json=payload, timeout=timeout_seconds)

        if response.status_code != 200:
            snippet = _redact_token(response.text[:200], resolved_token)
            logger.warning(
                "Telegram alert for approval %s returned HTTP %s: %s",
                approval.approval_id,
                response.status_code,
                snippet,
            )
            return NotifyResult(status="failed", reason=f"http_{response.status_code}")

        body = response.json()
        if not isinstance(body, dict) or body.get("ok") is not True:
            desc = _redact_token(str(body.get("description") if isinstance(body, dict) else body), resolved_token)
            logger.warning(
                "Telegram alert for approval %s was not acknowledged: %s",
                approval.approval_id,
                desc,
            )
            return NotifyResult(status="failed", reason="telegram_not_ok")

        return NotifyResult(status="sent")
    except Exception as err:  # noqa: BLE001 — never let notification failure affect a verdict
        safe_err = _redact_token(str(err), resolved_token)
        logger.warning(
            "Telegram alert for approval %s failed (%s): %s",
            approval.approval_id,
            type(err).__name__,
            safe_err,
        )
        return NotifyResult(status="failed", reason=type(err).__name__)
