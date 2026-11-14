"""Download the three Valio Aimo data files into AIMO_DATA_DIR (default data/, ignored by git).

Run: uv run python scripts/fetch_data.py
Skips a file that is already there: the files do not change during the challenge.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from merchant import valio_api

FILES = {
    "products.json": "/products/download",
    "delivery-reliability.csv": "/delivery-reliability/download",
    "carbon-footprint.csv": "/carbon-footprint/download",
}


def main():
    target = valio_api.data_dir()
    target.mkdir(parents=True, exist_ok=True)
    for name, path in FILES.items():
        file = target / name
        if file.exists() and file.stat().st_size > 0:
            print(f"already there: {file}")
            continue
        file.write_bytes(valio_api.download(path))
        print(f"downloaded {file} ({file.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
