"""Explicit fal price estimates used by local cost gates."""

from decimal import Decimal

from trellis_asset_forge.domain import GenerationSpec

DEFAULT_UNIT_PRICES_USD: dict[int, Decimal] = {
    512: Decimal("0.25"),
    1024: Decimal("0.30"),
    1536: Decimal("0.35"),
}


def estimate_generation_cost(spec: GenerationSpec) -> Decimal:
    """Estimate variant cost; an explicit manifest override wins."""
    unit_cost = spec.unit_cost_usd or DEFAULT_UNIT_PRICES_USD[spec.resolution]
    return (unit_cost * spec.variants).quantize(Decimal("0.01"))

