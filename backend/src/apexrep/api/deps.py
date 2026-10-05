import hmac
import math
import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from apexrep.api.ip_limit import IpLimiters, IpRateLimiter
from apexrep.config import Settings, get_settings
from apexrep.meta import MetaService
from apexrep.players.service import PlayerService

# Headers the Next.js server sets on every call.
INTERNAL_TOKEN_HEADER: str = "X-Internal-Token"
CLIENT_IP_HEADER: str = "X-Client-IP"
CLIENT_USER_AGENT_HEADER: str = "X-Client-User-Agent"

_CRAWLER_PATTERN: re.Pattern[str] = re.compile(
    r"bot\b|bot/|crawl|spider|slurp|facebookexternalhit|embedly|preview|headlesschrome"
    r"|lighthouse|python-requests|curl/|wget/",
    re.IGNORECASE,
)


def is_crawler(user_agent: str | None) -> bool:
    # A missing user agent is treated as a crawler: real browsers always send one.
    return not user_agent or _CRAWLER_PATTERN.search(user_agent) is not None


class ClientInfo(BaseModel):
    ip: str | None
    is_crawler: bool


def require_internal_token(
    settings: Annotated[Settings, Depends(get_settings)],
    token: Annotated[str | None, Header(alias=INTERNAL_TOKEN_HEADER)] = None,
) -> None:
    expected = settings.internal_token.get_secret_value()
    # An unset token rejects everything rather than opening the API.
    if not expected or token is None or not hmac.compare_digest(token, expected):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


def get_client_info(
    ip: Annotated[str | None, Header(alias=CLIENT_IP_HEADER)] = None,
    user_agent: Annotated[str | None, Header(alias=CLIENT_USER_AGENT_HEADER)] = None,
) -> ClientInfo:
    return ClientInfo(ip=ip, is_crawler=is_crawler(user_agent))


def get_ip_limiters(request: Request) -> IpLimiters:
    limiters: IpLimiters = request.app.state.ip_limiters
    return limiters


def enforce_limit(limiter: IpRateLimiter, client: ClientInfo) -> None:
    # Requests with no forwarded IP share one bucket, so they cannot dodge the limit.
    retry_after_s = limiter.check(client.ip or "unknown")
    if retry_after_s is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate_limited",
            headers={"Retry-After": str(math.ceil(retry_after_s))},
        )


def limit_resolve(
    limiters: Annotated[IpLimiters, Depends(get_ip_limiters)],
    client: Annotated[ClientInfo, Depends(get_client_info)],
) -> None:
    enforce_limit(limiters.resolve, client)


def limit_track(
    limiters: Annotated[IpLimiters, Depends(get_ip_limiters)],
    client: Annotated[ClientInfo, Depends(get_client_info)],
) -> None:
    enforce_limit(limiters.track, client)


def get_player_service(request: Request) -> PlayerService:
    service: PlayerService = request.app.state.players
    return service


def get_meta_service(request: Request) -> MetaService:
    service: MetaService = request.app.state.meta
    return service
