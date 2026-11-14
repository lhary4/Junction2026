"""Record the demo state examples again from real runs: contract/examples/demo-state.*.json.

Run: VALIO_MODE=live uv run python scripts/record_demo_states.py        add --policy <file> for another buyer policy

It runs the demo driver through the real gateway and the real harness, in this process and on an empty temporary state
folder, and writes what GET /state answers at five moments: nothing run yet, the normal order, the substitution waiting
for the chef, the same once the chef approved, and the attack. Nothing is typed by hand: to change an example, change
the code or the scenario and record again. Live mode needs the keys of .env and the data files (scripts/fetch_data.py).
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from contract.models import DemoState
from harness.app import create_app as create_harness
from merchant.app import app as gateway_app
from scenarios.run import Driver
from scripts.dev import env_file

EXAMPLES = ROOT / "contract" / "examples"


def write(name: str, state: DemoState) -> None:
    path = EXAMPLES / f"demo-state.{name}.json"
    path.write_text(json.dumps(state.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}: {state.scenario.status}")


def expect(state: DemoState, status: str) -> DemoState:
    if state.scenario.status != status:
        said = state.verdict.decision if state.verdict else "no verdict"
        raise SystemExit(
            f"{state.scenario.id} ended {state.scenario.status} ({said}), expected {status}: nothing written"
        )
    return state


def main(argv: list[str]) -> int:
    policy = Path(argv[argv.index("--policy") + 1]) if "--policy" in argv else None
    for name, value in env_file().items():
        os.environ.setdefault(name, value)  # the keys of .env, unless the terminal already set them

    with tempfile.TemporaryDirectory() as state_folder:
        os.environ["AIMO_STATE_DIR"] = state_folder
        gateway = TestClient(gateway_app)
        harness = TestClient(create_harness(http_client=gateway, policy_path=policy))
        with gateway, harness:
            driver = Driver(gateway=gateway, harness=harness)
            write("idle", expect(driver.reset(), "idle"))
            write("normal-order", expect(driver.run("normal-order"), "done"))
            driver.reset()
            pending = expect(driver.run("substitution"), "waiting_for_human")
            write("substitution.pending", pending)
            # The chef's decision, the way the page sends it: to the harness, never through the driver.
            decision = {"decision": "approve", "decided_by": "chef"}
            answer = harness.post(f"/approvals/{pending.approval.approval_id}/decision", json=decision)
            if answer.status_code != 200:
                raise SystemExit(f"the harness refused the chef's approval: {answer.text}")
            write("substitution.approved", expect(driver.state(), "done"))
            driver.reset()
            write("attack", expect(driver.run("attack"), "refused"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
