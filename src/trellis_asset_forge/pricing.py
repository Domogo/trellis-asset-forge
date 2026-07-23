"""Explicit fal price estimates used by local cost gates."""

from decimal import ROUND_CEILING, Decimal

from trellis_asset_forge.audio import (
    STABLE_AUDIO_MUSIC_MODEL,
    AudioRequest,
    CassetteMusicRequest,
    ElevenLabsMusicRequest,
    ElevenLabsSfxRequest,
)
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


def estimate_audio_cost(request: AudioRequest) -> Decimal:
    """Estimate one audio request using the provider's advertised billing unit."""
    duration = Decimal(str(request.duration_seconds))
    if isinstance(request, ElevenLabsMusicRequest):
        billed_minutes = (duration / Decimal("60")).to_integral_value(
            rounding=ROUND_CEILING
        )
        return billed_minutes * Decimal("0.80")
    if isinstance(request, ElevenLabsSfxRequest):
        return duration * Decimal("0.002")
    if isinstance(request, CassetteMusicRequest):
        return duration / Decimal("60") * Decimal("0.02")
    if request.model == STABLE_AUDIO_MUSIC_MODEL:
        return Decimal("0.0376")
    return Decimal("0.0206")
