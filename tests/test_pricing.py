from decimal import Decimal

from trellis_asset_forge.audio import (
    STABLE_AUDIO_SFX_MODEL,
    CassetteMusicRequest,
    ElevenLabsMusicRequest,
    ElevenLabsSfxRequest,
    StableAudioRequest,
)
from trellis_asset_forge.domain import GenerationSpec
from trellis_asset_forge.pricing import estimate_audio_cost, estimate_generation_cost


def test_model_pricing_supports_hunyuan_single_view_and_explicit_overrides() -> None:
    hunyuan = GenerationSpec(model="fal-ai/hunyuan3d-v3/image-to-3d")
    overridden = GenerationSpec(
        model="fal-ai/meshy/v6-preview/image-to-3d",
        variants=2,
        unit_cost_usd=Decimal("0.42"),
    )

    assert estimate_generation_cost(hunyuan) == Decimal("0.375")
    assert estimate_generation_cost(overridden) == Decimal("0.840")


def test_audio_pricing_matches_each_supported_provider_billing_unit() -> None:
    stable_music = StableAudioRequest(prompt="music", duration_seconds=180)
    stable_sfx = StableAudioRequest(
        model=STABLE_AUDIO_SFX_MODEL,
        prompt="impact",
        duration_seconds=3,
    )
    eleven_music = ElevenLabsMusicRequest(prompt="music", duration_seconds=61)
    eleven_sfx = ElevenLabsSfxRequest(prompt="impact", duration_seconds=3.5)
    cassette = CassetteMusicRequest(prompt="music", duration_seconds=45)

    assert estimate_audio_cost(stable_music) == Decimal("0.0376")
    assert estimate_audio_cost(stable_sfx) == Decimal("0.0206")
    assert estimate_audio_cost(eleven_music) == Decimal("1.60")
    assert estimate_audio_cost(eleven_sfx) == Decimal("0.0070")
    assert estimate_audio_cost(cassette) == Decimal("0.015")
