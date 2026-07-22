from decimal import Decimal

from trellis_asset_forge.domain import GenerationSpec
from trellis_asset_forge.pricing import estimate_generation_cost


def test_model_pricing_supports_hunyuan_single_view_and_explicit_overrides() -> None:
    hunyuan = GenerationSpec(model="fal-ai/hunyuan3d-v3/image-to-3d")
    overridden = GenerationSpec(
        model="fal-ai/meshy/v6-preview/image-to-3d",
        variants=2,
        unit_cost_usd=Decimal("0.42"),
    )

    assert estimate_generation_cost(hunyuan) == Decimal("0.375")
    assert estimate_generation_cost(overridden) == Decimal("0.840")
