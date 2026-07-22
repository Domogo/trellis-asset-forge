"""Built-in game asset quality profiles."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class GameProfile:
    """Measurable mesh and texture budgets for a static game asset."""

    name: str
    triangle_budget: int
    texture_size: Literal[1024, 2048, 4096]
    max_materials: int
    max_components: int
    lod_ratios: tuple[float, ...]


PROFILES: dict[str, GameProfile] = {
    "mobile-prop": GameProfile(
        name="mobile-prop",
        triangle_budget=20_000,
        texture_size=1024,
        max_materials=2,
        max_components=8,
        lod_ratios=(1.0, 0.5, 0.2),
    ),
    "desktop-prop": GameProfile(
        name="desktop-prop",
        triangle_budget=50_000,
        texture_size=2048,
        max_materials=4,
        max_components=16,
        lod_ratios=(1.0, 0.5, 0.2),
    ),
    "hero-static": GameProfile(
        name="hero-static",
        triangle_budget=100_000,
        texture_size=4096,
        max_materials=6,
        max_components=24,
        lod_ratios=(1.0, 0.6, 0.3),
    ),
}


def get_profile(name: str) -> GameProfile:
    """Return a profile or raise with the supported names."""
    try:
        return PROFILES[name]
    except KeyError as error:
        supported = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown game profile {name!r}; choose one of: {supported}") from error
