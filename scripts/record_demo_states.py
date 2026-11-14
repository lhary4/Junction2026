"""Record the demo state examples again from real runs: contract/examples/demo-state.*.json.

Run: VALIO_MODE=live uv run python scripts/record_demo_states.py        add --policy <file> for another buyer policy
     add --greener-only to record only the greener swap below, and leave the other examples as they are

It runs the demo driver through the real gateway and the real harness, in this process and on an empty temporary state
folder, and writes what GET /state answers at six moments: nothing run yet, the normal order, the substitution waiting
for the chef, the same once the chef approved, the attack, and the normal order with the butter swapped for the greener
margarine. It also writes the carbon footprint of the normal order before and after that swap (footprint.*.json). Nothing is typed by hand: to change an example, change
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

from contract.models import DemoState, Need
from harness.app import create_app as create_harness
from merchant.app import app as gateway_app
from merchant.footprint import ECO_PAIRS
from scenarios.run import SCENARIOS, Driver
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


def greener_needs() -> list[Need]:
    """The normal order with each line Valio offers a greener product for swapped, the way the chef does on the page."""
    swap = {pair.original: pair.alternative for pair in ECO_PAIRS}
    return [Need(product_id=swap.get(p, p), amount=a, unit=u) for p, a, u in SCENARIOS[0].needs]


def write_footprint(name: str, answer: dict) -> None:
    path = EXAMPLES / f"footprint.{name}.json"
    path.write_text(json.dumps(answer, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}: {answer['total_kg_co2e']} kg CO2e")


def record_greener(driver: Driver) -> None:
    """The footprint of the normal order before and after the greener swap, and the swapped order run to its end."""
    plain = [Need(product_id=p, amount=a, unit=u) for p, a, u in SCENARIOS[0].needs]
    write_footprint("normal-order", driver.footprint(plain))
    write_footprint("normal-order.greener", driver.footprint(greener_needs()))
    driver.reset()
    write("normal-order.greener", expect(driver.run("normal-order", greener_needs()), "done"))


def main(argv: list[str]) -> int:
    policy = Path(argv[argv.index("--policy") + 1]) if "--policy" in argv else None
    greener_only = "--greener-only" in argv
    for name, value in env_file().items():
        os.environ.setdefault(name, value)  # the keys of .env, unless the terminal already set them

    with tempfile.TemporaryDirectory() as state_folder:
        os.environ["AIMO_STATE_DIR"] = state_folder
        gateway = TestClient(gateway_app)
        quiet = lambda *_args, **_kwargs: None  # a recording must never message the chef's phone
        harness = TestClient(create_harness(http_client=gateway, policy_path=policy, notify_fn=quiet))
        with gateway, harness:
            driver = Driver(gateway=gateway, harness=harness)
            if greener_only:
                record_greener(driver)
                return 0
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
            record_greener(driver)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
