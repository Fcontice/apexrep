"""Look a player up through the real client: `uv run apexrep-lookup --name <EA name>`."""

import argparse
import asyncio

from apexrep.als.client import build_als_client
from apexrep.als.errors import AlsError
from apexrep.als.models import Platform
from apexrep.config import Settings, get_settings


async def lookup(settings: Settings, platform: Platform, name: str) -> None:
    client = build_als_client(settings, rate_per_s=settings.als_rate_backend_per_s)
    try:
        snapshot = await client.bridge_by_name(name, platform)
    except AlsError as exc:
        raise SystemExit(f"{type(exc).__name__}: {exc}") from exc
    finally:
        await client.aclose()
    print(snapshot.model_dump_json(indent=2, exclude={"raw"}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Look up a player and print the parsed snapshot.")
    parser.add_argument("--name", required=True, help="player name (EA name on PC)")
    parser.add_argument("--platform", choices=[p.value for p in Platform], default="PC")
    args = parser.parse_args()
    asyncio.run(lookup(get_settings(), Platform(args.platform), args.name))


if __name__ == "__main__":
    main()
