"""Supported fal image-to-3D models and endpoint selection."""

from typing import Literal

TRELLIS_MODEL: Literal["fal-ai/trellis-2"] = "fal-ai/trellis-2"
MESHY_MODEL: Literal["fal-ai/meshy/v6-preview/image-to-3d"] = (
    "fal-ai/meshy/v6-preview/image-to-3d"
)
HUNYUAN_V3_MODEL: Literal["fal-ai/hunyuan3d-v3/image-to-3d"] = (
    "fal-ai/hunyuan3d-v3/image-to-3d"
)
HUNYUAN_V31_PRO_MODEL: Literal["fal-ai/hunyuan-3d/v3.1/pro/image-to-3d"] = (
    "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d"
)
HUNYUAN_MODELS = frozenset({HUNYUAN_V3_MODEL, HUNYUAN_V31_PRO_MODEL})

FalModel = Literal[
    "fal-ai/trellis-2",
    "fal-ai/meshy/v6-preview/image-to-3d",
    "fal-ai/hunyuan3d-v3/image-to-3d",
    "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
]

DEFAULT_MODEL: FalModel = TRELLIS_MODEL
SUPPORTED_ENDPOINTS = frozenset(
    {
        DEFAULT_MODEL,
        "fal-ai/trellis-2/multi",
        MESHY_MODEL,
        HUNYUAN_V3_MODEL,
        HUNYUAN_V31_PRO_MODEL,
    }
)


def endpoint_for(model: FalModel, *, reference_count: int) -> str:
    """Resolve the fal queue endpoint for a supported model and reference count."""
    if model == TRELLIS_MODEL and reference_count > 1:
        return "fal-ai/trellis-2/multi"
    return model


def hunyuan_view_field(model: str, view: str) -> str | None:
    """Map a human-facing reference view label to a Hunyuan API field."""
    normalized = view.strip().lower().replace("_", "-").replace(" ", "-")
    common = {
        "back": "back_image_url",
        "rear": "back_image_url",
        "back-three-quarter": "back_image_url",
        "rear-three-quarter": "back_image_url",
        "left": "left_image_url",
        "left-side": "left_image_url",
        "right": "right_image_url",
        "right-side": "right_image_url",
    }
    field = common.get(normalized)
    if field is not None or model != HUNYUAN_V31_PRO_MODEL:
        return field
    return {
        "top": "top_image_url",
        "bottom": "bottom_image_url",
        "left-front": "left_front_image_url",
        "front-left": "left_front_image_url",
        "left-front-three-quarter": "left_front_image_url",
        "front-left-three-quarter": "left_front_image_url",
        "right-front": "right_front_image_url",
        "front-right": "right_front_image_url",
        "right-front-three-quarter": "right_front_image_url",
        "front-right-three-quarter": "right_front_image_url",
    }.get(normalized)
