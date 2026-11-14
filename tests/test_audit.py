"""Tests for the hash-chained audit log in common/audit.py (step L2)."""

import json
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from common.audit import AuditLog, default_log_path, digest

HELSINKI = ZoneInfo("Europe/Helsinki")
FIXED_NOW = datetime(2026, 11, 14, 13, 15, 3, tzinfo=HELSINKI)


def _append_three(log: AuditLog):
    e1 = log.append(
        "buyer",
        "agent",
        "authorization_requested",
        "The agent asked to order quote chk_act1_demo.",
        "Request: I need 1,000 litres of lactose-free milk by Monday.",
        checkout_id="chk_act1_demo",
        checkout_hash="HPbwv03b_5_cOl_TQwWrY_WxEUd6wG790GBTxBTQgaI",
        now=FIXED_NOW,
    )
    e2 = log.append(
        "buyer",
        "harness",
        "quote_verified",
        "Quote signature and expiry checked.",
        "Signed by valio-aimo, valid until 2026-11-15 17:00.",
        checkout_id="chk_act1_demo",
        checkout_hash="HPbwv03b_5_cOl_TQwWrY_WxEUd6wG790GBTxBTQgaI",
        rule="quote-signature",
        now=FIXED_NOW,
    )
    e3 = log.append(
        "buyer",
        "harness",
        "verdict",
        "Verdict auto for 1010.00 EUR.",
        "1010.00 EUR is within the 1500.00 EUR limit, no other rule triggered.",
        checkout_id="chk_act1_demo",
        checkout_hash="HPbwv03b_5_cOl_TQwWrY_WxEUd6wG790GBTxBTQgaI",
        rule="spend-limit",
        now=FIXED_NOW,
    )
    return e1, e2, e3


def test_empty_or_missing_log_reads_empty_and_verifies(tmp_path):
    log = AuditLog(tmp_path / "buyer" / "audit.jsonl")
    assert log.read() == []
    assert log.verify() is None


def test_three_appends_chain_and_verify(tmp_path):
    log = AuditLog(tmp_path / "buyer" / "audit.jsonl")
    e1, e2, e3 = _append_three(log)

    events = log.read()
    assert [e.seq for e in events] == [1, 2, 3]
    assert events[0].prev_hash is None
    assert events[1].prev_hash == e1.hash
    assert events[2].prev_hash == e2.hash
    assert all(len(e.hash) == 64 and e.hash == digest(e) for e in (e1, e2, e3))
    assert log.verify() is None


@pytest.mark.parametrize("tampered_index", [0, 1, 2])
def test_edited_line_is_caught_at_exact_index(tmp_path, tampered_index):
    path = tmp_path / "buyer" / "audit.jsonl"
    log = AuditLog(path)
    _append_three(log)

    lines = path.read_text(encoding="utf-8").splitlines()
    edited = json.loads(lines[tampered_index])
    edited["what"] = "Tampered description"
    lines[tampered_index] = json.dumps(edited)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert log.verify() == tampered_index


def test_rehashed_middle_line_breaks_next_event_prev_hash(tmp_path):
    path = tmp_path / "buyer" / "audit.jsonl"
    log = AuditLog(path)
    _append_three(log)

    events = log.read()
    events[0].what = "Rewritten history with recomputed hash"
    events[0].hash = digest(events[0])
    path.write_text("\n".join(e.model_dump_json() for e in events) + "\n", encoding="utf-8")

    # Line 0 passes its own hash check, so line 1 is caught because its prev_hash no longer matches.
    assert log.verify() == 1


def test_corrupted_json_or_deleted_line_is_caught(tmp_path):
    path = tmp_path / "merchant" / "audit.jsonl"
    log = AuditLog(path)
    _append_three(log)

    lines = path.read_text(encoding="utf-8").splitlines()
    # Delete first line -> remaining first event has seq=2 and non-null prev_hash -> index 0 fails
    path.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    assert log.verify() == 0

    # Corrupt second line JSON -> index 1 fails
    lines_corrupt = [lines[0], "{not valid json", lines[2]]
    path.write_text("\n".join(lines_corrupt) + "\n", encoding="utf-8")
    assert log.verify() == 1


def test_append_uses_frozen_clock_when_now_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMO_FROZEN_NOW", "2026-11-14T13:15:00+02:00")
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))

    path = default_log_path("buyer")
    assert path == tmp_path / "buyer" / "audit.jsonl"

    log = AuditLog(path)
    event = log.append("buyer", "harness", "verdict", "Verdict auto.", "All rules passed.")
    assert event.at.isoformat() == "2026-11-14T13:15:00+02:00"
    assert log.verify() is None


def test_concurrent_separate_audit_log_instances_keep_chain_intact(tmp_path):
    """Creating a fresh AuditLog(path) per request across 8 threads must still serialize writes cleanly."""
    path = tmp_path / "buyer" / "audit.jsonl"

    def worker(thread_id: int) -> None:
        for idx in range(25):
            AuditLog(path).append(
                "buyer",
                "harness",
                "verdict",
                f"Thread {thread_id} event {idx}.",
                "Concurrent write test.",
                now=FIXED_NOW,
            )

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = AuditLog(path).read()
    assert len(events) == 200
    assert [e.seq for e in events] == list(range(1, 201))
    assert AuditLog(path).verify() is None
