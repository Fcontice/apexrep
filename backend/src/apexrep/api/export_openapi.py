"""Write the OpenAPI schema the frontend generates its types from.

`uv run apexrep-export-openapi` then `npm run gen:api` in frontend/.
"""

import argparse
import json
from pathlib import Path

from apexrep.api.app import app
from apexrep.config import REPO_ROOT

DEFAULT_OUT: Path = REPO_ROOT / "frontend" / "openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the API's OpenAPI schema.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out: Path = args.out
    out.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
