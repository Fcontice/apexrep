from pydantic import JsonValue


class AlsError(Exception):
    """Base class for every Apex Legends Status API failure."""


class PlayerNotFound(AlsError):
    pass


class RateLimited(AlsError):
    pass


class InvalidApiKey(AlsError):
    pass


class UnknownPlatform(AlsError):
    pass


class UpstreamError(AlsError):
    """Transient or unexplained failure; the only error the client retries."""


_RATE_LIMIT_HINTS: tuple[str, ...] = ("rate limit", "too many", "slow down")
_NOT_FOUND_HINTS: tuple[str, ...] = ("not found", "doesn't exist", "does not exist")
_API_KEY_HINTS: tuple[str, ...] = ("api key", "unauthorized")


def error_message(body: JsonValue) -> str | None:
    """Return the message of an ALS error body such as {"Error": "..."}."""
    if not isinstance(body, dict):
        return None
    for key, value in body.items():
        if key.lower() == "error":
            return str(value)
    return None


def error_for_status(status_code: int, detail: str) -> AlsError:
    message = f"ALS responded {status_code}: {detail}"
    match status_code:
        case 403:
            return InvalidApiKey(message)
        case 404:
            return PlayerNotFound(message)
        case 410:
            return UnknownPlatform(message)
        case 429:
            return RateLimited(message)
        case _:
            return UpstreamError(message)


def error_for_body(message: str) -> AlsError:
    """Classify an error body that arrived with a 200 status."""
    lowered = message.lower()
    if any(hint in lowered for hint in _RATE_LIMIT_HINTS):
        return RateLimited(message)
    if any(hint in lowered for hint in _NOT_FOUND_HINTS):
        return PlayerNotFound(message)
    if any(hint in lowered for hint in _API_KEY_HINTS):
        return InvalidApiKey(message)
    return UpstreamError(message)
