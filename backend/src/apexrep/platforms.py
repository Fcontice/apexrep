from enum import StrEnum

from apexrep.als.models import Platform


class PlatformSlug(StrEnum):
    """Platform as it appears in URLs."""

    PC = "pc"
    PS = "ps"
    XBOX = "xbox"


_SLUG_TO_PLATFORM: dict[PlatformSlug, Platform] = {
    PlatformSlug.PC: Platform.PC,
    PlatformSlug.PS: Platform.PS4,
    PlatformSlug.XBOX: Platform.X1,
}
_PLATFORM_TO_SLUG: dict[Platform, PlatformSlug] = {
    platform: slug for slug, platform in _SLUG_TO_PLATFORM.items()
}


def to_platform(slug: PlatformSlug) -> Platform:
    return _SLUG_TO_PLATFORM[slug]


def to_slug(platform: Platform) -> PlatformSlug:
    return _PLATFORM_TO_SLUG[platform]
