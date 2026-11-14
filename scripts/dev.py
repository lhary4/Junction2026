"""Start the two services for local work: the Valio gateway on 8001 and the harness on 8002.

Run: uv run python scripts/dev.py            add --reload to restart a service when its code changes
Stop both with Ctrl+C. Works the same on macOS, Linux and Windows.

The variables in .env are handed to both services. A variable already set in your terminal wins over .env.
A service whose code is not in the repo yet is skipped, so this works before the harness is merged.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES = (("gateway", "merchant.app:app", 8001), ("harness", "harness.app:app", 8002))
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


def main() -> int:
    reload = ["--reload"] if "--reload" in sys.argv[1:] else []
    env = {**env_file(), **os.environ}
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
