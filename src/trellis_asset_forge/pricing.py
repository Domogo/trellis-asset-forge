"""Explicit fal price estimates used by local cost gates."""

from decimal import Decimal

from trellis_asset_forge.domain import GenerationSpec
from trellis_asset_forge.models import HUNYUAN_MODELS, MESHY_MODEL

DEFAULT_UNIT_PRICES_USD: dict[int, Decimal] = {
    512: Decimal("0.25"),
    1024: Decimal("0.30"),
    1536: Decimal("0.35"),
}


def estimate_generation_cost(spec: GenerationSpec, *, reference_count: int = 1) -> Decimal:
    """Estimate variant cost; an explicit manifest override wins."""
    if spec.unit_cost_usd is not None:
        unit_cost = spec.unit_cost_usd
    elif spec.model == MESHY_MODEL:
        unit_cost = Decimal("0.80")
    elif spec.model in HUNYUAN_MODELS:
        unit_cost = Decimal("0.375")
        if reference_count > 1:
            unit_cost += Decimal("0.15")
    else:
        unit_cost = DEFAULT_UNIT_PRICES_USD[spec.resolution]
    return (unit_cost * spec.variants).quantize(Decimal("0.001"))
