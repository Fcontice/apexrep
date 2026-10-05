import base64
import binascii

from pydantic import ValidationError

from apexrep.players.repo import MatchCursor


class InvalidCursor(ValueError):
    pass


def encode_cursor(cursor: MatchCursor) -> str:
    return base64.urlsafe_b64encode(cursor.model_dump_json().encode()).decode()


def decode_cursor(value: str) -> MatchCursor:
    try:
        return MatchCursor.model_validate_json(base64.urlsafe_b64decode(value.encode()))
    except (binascii.Error, ValidationError, ValueError) as exc:
        raise InvalidCursor("invalid cursor") from exc
