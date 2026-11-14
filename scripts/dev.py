"""Start the three services for local work: the Valio gateway on 8001, the harness on 8002 and the demo driver on 8003.

Run: uv run python scripts/dev.py            add --reload to restart a service when its code changes
                                             add --fresh to empty the local state first
Stop them all with Ctrl+C. Works the same on macOS, Linux and Windows.
The demo page is then on http://localhost:8002/portal.html, served by the harness.

The variables in .env are handed to every service. A variable already set in your terminal wins over .env.
A service whose code is not in the repo yet is skipped.

--fresh removes what earlier runs left: quotes, orders, the sandbox invoice accounts, approvals and both audit logs. Use it before a rehearsal or
the demo. In replay mode the clock is frozen, so an approval left pending never reaches its cut-off and would stay on
the approval page. It is a start option and not a separate script, because the harness keeps its approvals in memory:
emptying the files under a running harness would not empty the harness.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES = (
    ("gateway", "merchant.app:app", 8001),
    ("harness", "harness.app:app", 8002),
    ("driver", "scenarios.run:app", 8003),  # plays the buying agent for the demo page, keeps nothing on disk
)
STATE_FOLDERS = ("merchant", "buyer")  # what the gateway and the harness write, under the state folder
STOP_TIMEOUT_SECONDS = 10


def env_file() -> dict[str, str]:
    """The filled-in lines of .env. Empty values are left out so the defaults in the code apply."""
    path = ROOT / ".env"
    if not path.exists():
        return {}
    pairs = (line.partition("=") for line in path.read_text(encoding="utf-8").splitlines())
    return {
        key.strip(): value.strip()
        for key, sep, value in pairs
        if sep and value.strip() and not key.lstrip().startswith("#")
    }


def state_folder(env: dict[str, str]) -> Path:
    """Where both services write, read the way they read it: AIMO_STATE_DIR, or state/ at the root of the repo."""
    return ROOT / (env.get("AIMO_STATE_DIR") or "state")


def port_in_use(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def empty_state(env: dict[str, str]) -> None:
    """Remove the two folders the services write. Nothing else in the state folder, no key, no data file."""
    for name in STATE_FOLDERS:
        folder = state_folder(env) / name
        files = sum(path.is_file() for path in folder.rglob("*")) if folder.is_dir() else 0
        if folder.is_dir():
            shutil.rmtree(folder)
        print(f"fresh: {files} file(s) removed from {folder}", flush=True)


def main() -> int:
    reload = ["--reload"] if "--reload" in sys.argv[1:] else []
    env = {**env_file(), **os.environ}
    if "--fresh" in sys.argv[1:]:
        busy = [f"{name} (port {port})" for name, _, port in SERVICES if port_in_use(port)]
        if busy:
            print(f"fresh: nothing removed, still running: {', '.join(busy)}. Stop it first.", flush=True)
            return 1
        empty_state(env)
    running = []
    for name, target, port in SERVICES:
        code = ROOT / (target.split(":")[0].replace(".", "/") + ".py")
        if not code.exists():
            print(f"{name}: skipped, {code.relative_to(ROOT)} is not in the repo yet", flush=True)
            continue
        command = [sys.executable, "-m", "uvicorn", target, "--port", str(port), *reload]
        running.append((name, subprocess.Popen(command, cwd=ROOT, env=env)))
        print(f"{name}: http://localhost:{port} (API docs on /docs)", flush=True)
    try:
        while all(process.poll() is None for _, process in running):
            time.sleep(0.5)
    except KeyboardInterrupt:
        return _stop(running, 0)
    stopped = ", ".join(name for name, process in running if process.poll() is not None)
    print(f"{stopped} stopped on its own (see the error above), stopping the rest", flush=True)
    return _stop(running, 1)


def _stop(running, exit_code: int) -> int:
    for _, process in running:
        process.terminate()
    for _, process in running:
        try:
            process.wait(timeout=STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()  # a service that does not shut down must not keep its port
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
