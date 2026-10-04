"""Record real ALS responses as test fixtures: `uv run apexrep-record-fixture --name <EA name>`."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from pydantic import JsonValue

from apexrep.als.errors import error_message
from apexrep.als.models import Platform
from apexrep.als.parser import parse_bridge
from apexrep.config import REPO_ROOT, Settings, get_settings

DEFAULT_OUT_DIR: Path = REPO_ROOT / "backend" / "tests" / "fixtures" / "als"
MISSING_PLAYER_NAME: str = "apexrep-no-such-player-fixture"
PAUSE_BETWEEN_CALLS_S: float = 1.0


def _json_body(response: httpx.Response) -> JsonValue:
    try:
        body: JsonValue = response.json()
    except ValueError:
        return None
    return body


def _save(out_dir: Path, filename: str, response: httpx.Response) -> None:
    body = _json_body(response)
    text = response.text if body is None else json.dumps(body, indent=2, ensure_ascii=False) + "\n"
    (out_dir / filename).write_text(text, encoding="utf-8")
    print(f"{filename}: HTTP {response.status_code}, {len(response.content)} bytes")


def _require_success(response: httpx.Response, what: str) -> None:
    """Stop before an error response overwrites a success fixture."""
    message = error_message(_json_body(response))
    if response.status_code != httpx.codes.OK or message is not None:
        raise SystemExit(
            f"{what} failed: HTTP {response.status_code}, {message or response.text[:200]}\n"
            "On PC use the EA account name, not the Steam name. "
            "The success fixtures were not changed."
        )


async def record(settings: Settings, platform: Platform, name: str, out_dir: Path) -> None:
    api_key = settings.als_api_key.get_secret_value()
    if not api_key:
        raise SystemExit("ALS_API_KEY is not set (put it in .env at the repo root)")
    out_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(
        base_url=settings.als_base_url,
        timeout=settings.als_timeout_s,
        headers={"Authorization": api_key},
    ) as http:
        merge_params = {"platform": platform.value, "merge": "1", "removeMerged": "1"}

        by_name = await http.get("/bridge", params={"player": name, **merge_params})
        _require_success(by_name, f"/bridge for {name!r} on {platform.value}")
        _save(out_dir, "bridge_ok.json", by_name)
        snapshot = parse_bridge(_json_body(by_name), platform)

        # The worker polls by UID, so confirm that path answers for the same player.
        await asyncio.sleep(PAUSE_BETWEEN_CALLS_S)
        by_uid = await http.get("/bridge", params={"uid": snapshot.uid, **merge_params})
        _require_success(by_uid, f"/bridge for uid {snapshot.uid}")
        print(f"/bridge by uid: HTTP {by_uid.status_code}, {len(by_uid.content)} bytes")

        await asyncio.sleep(PAUSE_BETWEEN_CALLS_S)
        missing = await http.get("/bridge", params={"player": MISSING_PLAYER_NAME, **merge_params})
        _save(out_dir, "bridge_not_found.json", missing)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record ALS responses as test fixtures.")
    parser.add_argument("--name", required=True, help="player name (EA name on PC)")
    parser.add_argument("--platform", choices=[p.value for p in Platform], default="PC")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    asyncio.run(record(get_settings(), Platform(args.platform), args.name, args.out))


if __name__ == "__main__":
    main()
