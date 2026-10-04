import asyncio

from apexrep.als.errors import AlsError
from apexrep.als.models import Platform, PlayerSnapshot
from apexrep.als.parser import parse_bridge
from tests.conftest import load_fixture

FIXTURE_UID: str = "1011572188996"


class FakeAls:
    """Stands in for AlsClient: serves the recorded snapshot and counts calls."""

    def __init__(self) -> None:
        self.snapshot: PlayerSnapshot = parse_bridge(load_fixture("bridge_ok.json"), Platform.PC)
        self.error: AlsError | None = None
        self.errors_by_uid: dict[str, AlsError] = {}
        self.delay_s: float = 0.0
        self.backlog: float = 0.0
        self.by_uid_calls: int = 0
        self.by_name_calls: int = 0

    async def bridge_by_uid(self, uid: str, platform: Platform) -> PlayerSnapshot:
        self.by_uid_calls += 1
        if uid in self.errors_by_uid:
            raise self.errors_by_uid[uid]
        snapshot = await self._respond()
        return snapshot.model_copy(update={"uid": uid, "platform": platform})

    async def bridge_by_name(self, name: str, platform: Platform) -> PlayerSnapshot:
        self.by_name_calls += 1
        return await self._respond()

    def backlog_s(self) -> float:
        return self.backlog

    async def _respond(self) -> PlayerSnapshot:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return self.snapshot


class FakeClock:
    def __init__(self) -> None:
        self.now: float = 1000.0

    def __call__(self) -> float:
        return self.now
