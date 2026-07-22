from decimal import Decimal
from pathlib import Path

import pytest

from trellis_asset_forge.forge import AssetForge
from trellis_asset_forge.manifest import ManifestError


def test_manifest_import_catalogs_reproducible_asset_plan(tmp_path: Path) -> None:
    reference = tmp_path / "references" / "crate.png"
    reference.parent.mkdir()
    reference.write_bytes(b"stable-reference")
    manifest = tmp_path / "assets.yaml"
    manifest.write_text(
        """
version: 1
project: example-game
assets:
  - id: props.scrap-crate
    name: Scrap Crate
    category: props
    brief: Chunky static crate with a clean silhouette.
    topology_notes: Preserve broad bevels and avoid thin floating shards.
    profile: desktop-prop
    game:
      scale_meters: 1.2
      pivot: base-center
      collision: convex
    references:
      - path: references/crate.png
        view: hero
    generation:
      resolution: 1024
      variants: 3
      seed: 4200
    export: props/scrap-crate.glb
""".strip()
        + "\n"
    )

    forge = AssetForge.initialize(tmp_path, export_root="exports")
    result = forge.import_manifest(manifest)
    asset = forge.list_assets()[0]

    assert result.project == "example-game"
    assert result.assets_imported == 1
    assert result.generations_planned == 3
    assert result.estimated_cost_usd == Decimal("0.90")
    assert asset.asset_id == "props.scrap-crate"
    assert asset.profile == "desktop-prop"
    assert asset.triangle_budget == 50_000
    assert asset.game.scale_meters == 1.2
    assert asset.game.pivot == "base-center"
    assert asset.game.collision == "convex"
    assert "floating shards" in asset.topology_notes
    assert asset.references[0].path == reference.resolve()
    assert asset.references[0].sha256 == (
        "21d23169913420f8c18a00ffc74033b65f839abade71f712769fc1253bc55320"
    )


def test_manifest_rejects_multiple_references_for_meshy_image_to_3d(
    tmp_path: Path,
) -> None:
    (tmp_path / "front.png").write_bytes(b"front")
    (tmp_path / "back.png").write_bytes(b"back")
    manifest = tmp_path / "assets.yaml"
    manifest.write_text(
        """
version: 1
project: demo
assets:
  - id: props.crate
    name: Crate
    category: props
    references:
      - {path: front.png, view: front}
      - {path: back.png, view: back}
    generation:
      model: fal-ai/meshy/v6-preview/image-to-3d
    export: props/crate.glb
""".strip()
        + "\n"
    )

    with pytest.raises(ManifestError, match="Meshy v6 image-to-3D requires exactly one"):
        AssetForge.initialize(tmp_path).import_manifest(manifest)


@pytest.mark.parametrize(
    ("model", "views", "error"),
    [
        (
            "fal-ai/hunyuan3d-v3/image-to-3d",
            ("front", "top"),
            "unsupported Hunyuan reference view",
        ),
        (
            "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
            ("front", "back", "rear"),
            "duplicate Hunyuan reference view",
        ),
    ],
)
def test_manifest_rejects_invalid_hunyuan_reference_views(
    tmp_path: Path,
    model: str,
    views: tuple[str, ...],
    error: str,
) -> None:
    references = []
    for index, view in enumerate(views):
        path = tmp_path / f"view-{index}.png"
        path.write_bytes(view.encode())
        references.append(f"      - {{path: {path.name}, view: {view}}}")
    manifest = tmp_path / "assets.yaml"
    manifest.write_text(
        "\n".join(
            [
                "version: 1",
                "project: demo",
                "assets:",
                "  - id: props.crate",
                "    name: Crate",
                "    category: props",
                "    references:",
                *references,
                "    generation:",
                f"      model: {model}",
                "    export: props/crate.glb",
            ]
        )
        + "\n"
    )

    with pytest.raises(ManifestError, match=error):
        AssetForge.initialize(tmp_path).import_manifest(manifest)
