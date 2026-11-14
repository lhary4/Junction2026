"""scripts/dev.py --fresh: it empties what the two services wrote, nothing else, and never under a running service."""

import socket
import sys

from harness.approvals import buyer_state_dir
from merchant import store
from scripts import dev


def leave_state(tmp_path, monkeypatch):
    """What a rehearsal leaves behind, in the folders the real services use, plus one file that is not theirs."""
    monkeypatch.setenv("AIMO_STATE_DIR", str(tmp_path))
    (store.state_dir() / "orders").mkdir(parents=True)
    (store.state_dir() / "orders" / "ord_1.json").write_text("{}", encoding="utf-8")
    (store.state_dir() / "audit.jsonl").write_text("{}\n", encoding="utf-8")
    buyer_state_dir().mkdir(parents=True)
    (buyer_state_dir() / "approvals.json").write_text("{}", encoding="utf-8")
    (tmp_path / "not-ours.txt").write_text("stays", encoding="utf-8")


def test_fresh_removes_what_both_services_wrote_and_nothing_else(tmp_path, monkeypatch, capsys):
    leave_state(tmp_path, monkeypatch)

    dev.empty_state({"AIMO_STATE_DIR": str(tmp_path)})

    assert not store.state_dir().exists() and not buyer_state_dir().exists()
    assert (tmp_path / "not-ours.txt").read_text(encoding="utf-8") == "stays"
    assert "2 file(s) removed" in capsys.readouterr().out
    dev.empty_state({"AIMO_STATE_DIR": str(tmp_path)})  # nothing left to remove is not an error


def test_the_state_folder_is_read_like_the_services_read_it():
    assert dev.state_folder({}) == dev.ROOT / "state"
    assert dev.state_folder({"AIMO_STATE_DIR": ""}) == dev.ROOT / "state"
    assert dev.state_folder({"AIMO_STATE_DIR": "elsewhere"}) == dev.ROOT / "elsewhere"  # services run from the root


def test_fresh_removes_nothing_while_a_service_still_runs(tmp_path, monkeypatch, capsys):
    leave_state(tmp_path, monkeypatch)
    with socket.socket() as running:
        running.bind(("127.0.0.1", 0))
        running.listen()
        monkeypatch.setattr(dev, "SERVICES", (("harness", "harness.app:app", running.getsockname()[1]),))
        monkeypatch.setattr(sys, "argv", ["dev.py", "--fresh"])

        assert dev.main() == 1

    assert (buyer_state_dir() / "approvals.json").exists()
    assert "still running: harness" in capsys.readouterr().out
