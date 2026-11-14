"""The gateway's memory: every quote it signed, as one JSON file under state/merchant/ (ignored by git).

The signed token is kept as issued: the order check (A5) must compare against exactly what Valio signed.
"""

import os
import re
from pathlib import Path

from contract.models import CheckoutResponse

ROOT = Path(__file__).resolve().parent.parent
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def state_dir() -> Path:
    return Path(os.environ.get("AIMO_STATE_DIR") or ROOT / "state") / "merchant"


def save_checkout(response: CheckoutResponse) -> None:
    folder = state_dir() / "checkouts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{response.checkout_id}.json").write_text(response.model_dump_json(exclude_none=True), encoding="utf-8")


def load_checkout(checkout_id: str) -> CheckoutResponse | None:
    if not SAFE_ID.match(checkout_id):
        return None
    path = state_dir() / "checkouts" / f"{checkout_id}.json"
    return CheckoutResponse.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None
