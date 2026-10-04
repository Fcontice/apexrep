import json
from pathlib import Path

import pytest
from pydantic import JsonValue

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures" / "als"


def load_fixture(name: str) -> JsonValue:
    body: JsonValue = json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))
    return body


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
