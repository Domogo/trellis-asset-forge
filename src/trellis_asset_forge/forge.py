"""High-leverage interface for project workflows."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from trellis_asset_forge.catalog import Catalog
from trellis_asset_forge.domain import AssetRecord, ImportResult
from trellis_asset_forge.manifest import load_manifest
from trellis_asset_forge.pricing import estimate_generation_cost
from trellis_asset_forge.workspace import Workspace


class AssetForge:
    """Project-neutral interface for catalog and generation workflows."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.catalog = Catalog(workspace.catalog_path)

    @classmethod
    def initialize(cls, root: Path, *, export_root: str = "game-assets") -> AssetForge:
        return cls(Workspace.initialize(root, export_root=export_root))

    @classmethod
    def open(cls, root: Path) -> AssetForge:
        return cls(Workspace.open(root))

    def import_manifest(self, path: Path) -> ImportResult:
        """Validate, hash, cost, and catalog every asset in a manifest."""
        resolved = load_manifest(path)
        generations_planned = 0
        estimated_cost = Decimal("0")
        for asset in resolved.assets:
            self.catalog.upsert_asset(asset)
            generations_planned += asset.spec.generation.variants
            estimated_cost += estimate_generation_cost(asset.spec.generation)
        return ImportResult(
            project=resolved.manifest.project,
            assets_imported=len(resolved.assets),
            generations_planned=generations_planned,
            estimated_cost_usd=estimated_cost.quantize(Decimal("0.01")),
        )

    def list_assets(self) -> list[AssetRecord]:
        """List cataloged assets in stable order."""
        return self.catalog.list_assets()

