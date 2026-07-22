from decimal import Decimal
from pathlib import Path

from trellis_asset_forge.forge import AssetForge


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
    profile: desktop-prop
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
    assert asset.references[0].path == reference.resolve()
    assert asset.references[0].sha256 == (
        "21d23169913420f8c18a00ffc74033b65f839abade71f712769fc1253bc55320"
    )
