"""High-leverage interface for project workflows."""

from __future__ import annotations

import secrets
import uuid
from decimal import Decimal
from pathlib import Path

from trellis_asset_forge.catalog import Catalog
from trellis_asset_forge.domain import (
    AssetRecord,
    GenerationRecord,
    GenerationRequest,
    ImportResult,
    RemoteJob,
)
from trellis_asset_forge.generation import CostLimitError, Generator
from trellis_asset_forge.manifest import load_manifest
from trellis_asset_forge.pricing import estimate_generation_cost
from trellis_asset_forge.profiles import get_profile
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

    def submit_asset(
        self,
        asset_id: str,
        *,
        generator: Generator,
        max_cost_usd: Decimal,
    ) -> list[GenerationRecord]:
        """Submit every configured variant after enforcing a batch cost ceiling."""
        asset = self.catalog.get_asset(asset_id)
        estimated_cost = estimate_generation_cost(asset.generation)
        if estimated_cost > max_cost_usd:
            raise CostLimitError(
                f"{asset_id} is estimated at ${estimated_cost:.2f}, "
                f"above the ${max_cost_usd:.2f} limit"
            )
        profile = get_profile(asset.profile)
        unit_cost = (estimated_cost / asset.generation.variants).quantize(Decimal("0.01"))
        base_seed = asset.generation.seed
        if base_seed is None:
            base_seed = secrets.randbelow(2_147_483_647 - asset.generation.variants)
        endpoint = (
            "fal-ai/trellis-2/multi" if len(asset.references) > 1 else "fal-ai/trellis-2"
        )
        submitted: list[GenerationRecord] = []
        for variant in range(asset.generation.variants):
            request = GenerationRequest(
                generation_id=str(uuid.uuid4()),
                asset_id=asset.asset_id,
                variant=variant,
                seed=base_seed + variant,
                endpoint=endpoint,
                references=tuple(reference.path for reference in asset.references),
                resolution=asset.generation.resolution,
                texture_size=asset.generation.texture_size or profile.texture_size,
                decimation_target=(
                    asset.generation.decimation_target or profile.triangle_budget
                ),
                remesh=asset.generation.remesh,
            )
            self.catalog.create_generation(request, estimated_cost_usd=str(unit_cost))
            try:
                remote_job = generator.submit(request)
            except Exception as error:
                self.catalog.mark_failed(request.generation_id, str(error))
                raise
            submitted.append(self.catalog.mark_submitted(request.generation_id, remote_job))
        return submitted

    def list_generations(self, asset_id: str | None = None) -> list[GenerationRecord]:
        """List durable generation state, optionally scoped to one asset."""
        return self.catalog.list_generations(asset_id)

    def sync(self, *, generator: Generator) -> list[GenerationRecord]:
        """Poll active jobs and immediately own completed GLB artifacts locally."""
        synced: list[GenerationRecord] = []
        for generation in self.catalog.list_generations():
            if generation.status not in {"submitted", "running"}:
                continue
            if (
                not generation.request_id
                or not generation.status_url
                or not generation.response_url
            ):
                synced.append(
                    self.catalog.mark_failed(
                        generation.generation_id,
                        "Submitted generation is missing remote queue coordinates",
                    )
                )
                continue
            remote_job = RemoteJob(
                request_id=generation.request_id,
                status_url=generation.status_url,
                response_url=generation.response_url,
            )
            try:
                update = generator.poll(remote_job)
                if update.status == "queued":
                    synced.append(generation)
                elif update.status == "running":
                    synced.append(self.catalog.mark_running(generation.generation_id))
                elif update.status == "failed":
                    synced.append(
                        self.catalog.mark_failed(
                            generation.generation_id,
                            update.error or "Remote generation failed",
                        )
                    )
                else:
                    if update.result_url is None:
                        raise ValueError("Completed generation is missing its result URL")
                    destination = (
                        self.workspace.artifacts_dir
                        / generation.asset_id
                        / generation.generation_id
                        / "source.glb"
                    )
                    artifact_path = generator.download(update.result_url, destination)
                    synced.append(
                        self.catalog.mark_downloaded(
                            generation.generation_id,
                            artifact_path=artifact_path,
                            remote_url=update.result_url,
                        )
                    )
            except Exception as error:
                synced.append(self.catalog.mark_failed(generation.generation_id, str(error)))
        return synced
