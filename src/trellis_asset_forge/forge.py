"""High-leverage interface for project workflows."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import uuid
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from pydantic import TypeAdapter

from trellis_asset_forge.catalog import Catalog
from trellis_asset_forge.domain import (
    AssetRecord,
    GenerationRecord,
    GenerationRequest,
    ImportResult,
    ProcessedArtifact,
    RemoteJob,
)
from trellis_asset_forge.generation import CostLimitError, Generator
from trellis_asset_forge.manifest import load_manifest
from trellis_asset_forge.mesh_quality import inspect_glb
from trellis_asset_forge.models import endpoint_for
from trellis_asset_forge.pricing import estimate_generation_cost
from trellis_asset_forge.processing import MeshProcessor
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
            estimated_cost += estimate_generation_cost(
                asset.spec.generation,
                reference_count=len(asset.references),
            )
        return ImportResult(
            project=resolved.manifest.project,
            assets_imported=len(resolved.assets),
            generations_planned=generations_planned,
            estimated_cost_usd=estimated_cost.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
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
        estimated_cost = estimate_generation_cost(
            asset.generation,
            reference_count=len(asset.references),
        )
        if estimated_cost > max_cost_usd:
            display_cost = estimated_cost.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            raise CostLimitError(
                f"{asset_id} is estimated at ${display_cost:.2f}, "
                f"above the ${max_cost_usd:.2f} limit"
            )
        profile = get_profile(asset.profile)
        unit_cost = (estimated_cost / asset.generation.variants).quantize(
            Decimal("0.001"),
            rounding=ROUND_HALF_UP,
        )
        base_seed = asset.generation.seed
        if base_seed is None:
            base_seed = secrets.randbelow(2_147_483_647 - asset.generation.variants)
        endpoint = endpoint_for(
            asset.generation.model,
            reference_count=len(asset.references),
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
                reference_views=tuple(reference.view for reference in asset.references),
                resolution=asset.generation.resolution,
                texture_size=asset.generation.texture_size or profile.texture_size,
                decimation_target=(
                    asset.generation.decimation_target or profile.candidate_vertex_target
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

    def submit_all(
        self,
        *,
        generator: Generator,
        max_cost_usd: Decimal,
    ) -> list[GenerationRecord]:
        """Submit never-attempted assets after enforcing one aggregate cost ceiling."""
        assets = [
            asset
            for asset in self.catalog.list_assets()
            if not self.catalog.list_generations(asset.asset_id)
        ]
        estimated_cost = sum(
            (
                estimate_generation_cost(
                    asset.generation,
                    reference_count=len(asset.references),
                )
                for asset in assets
            ),
            start=Decimal("0"),
        )
        if estimated_cost > max_cost_usd:
            display_cost = estimated_cost.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            raise CostLimitError(
                f"Catalog batch is estimated at ${display_cost:.2f}, "
                f"above the ${max_cost_usd:.2f} limit"
            )
        submitted: list[GenerationRecord] = []
        for asset in assets:
            submitted.extend(
                self.submit_asset(
                    asset.asset_id,
                    generator=generator,
                    max_cost_usd=estimate_generation_cost(
                        asset.generation,
                        reference_count=len(asset.references),
                    ),
                )
            )
        return submitted

    def list_generations(self, asset_id: str | None = None) -> list[GenerationRecord]:
        """List durable generation state, optionally scoped to one asset."""
        return self.catalog.list_generations(asset_id)

    def inspect_generation(self, generation_id: str) -> GenerationRecord:
        """Measure a downloaded candidate against its declared game profile."""
        generation = self.catalog.get_generation(generation_id)
        if generation.status not in {"downloaded", "inspected", "rejected"}:
            raise ValueError("Only a downloaded candidate can be inspected")
        if generation.artifact_path is None:
            raise ValueError("Downloaded candidate is missing its local artifact")
        asset = self.catalog.get_asset(generation.asset_id)
        report = inspect_glb(generation.artifact_path, get_profile(asset.profile))
        return self.catalog.mark_inspected(generation_id, report.model_dump_json())

    def approve_generation(self, generation_id: str, *, notes: str = "") -> GenerationRecord:
        """Approve a candidate only after it passes recorded quality gates."""
        generation = self.catalog.get_generation(generation_id)
        if generation.status != "inspected" or generation.quality_report is None:
            raise ValueError("Inspect the candidate before approval")
        if not generation.quality_report.passed:
            raise ValueError("Candidate has failing topology or profile quality gates")
        return self.catalog.mark_reviewed(
            generation_id,
            status="approved",
            notes=notes.strip(),
        )

    def reject_generation(self, generation_id: str, *, notes: str) -> GenerationRecord:
        """Reject an inspected candidate while retaining actionable feedback."""
        generation = self.catalog.get_generation(generation_id)
        if generation.status not in {"inspected", "approved"}:
            raise ValueError("Inspect the candidate before rejection")
        cleaned = notes.strip()
        if not cleaned:
            raise ValueError("Rejection notes are required")
        return self.catalog.mark_reviewed(
            generation_id,
            status="rejected",
            notes=cleaned,
        )

    def process_generation(
        self,
        generation_id: str,
        *,
        processor: MeshProcessor,
    ) -> GenerationRecord:
        """Build and validate the declared LOD set from an approved candidate."""
        generation = self.catalog.get_generation(generation_id)
        if generation.status != "approved":
            raise ValueError("Only an approved candidate can be processed")
        if generation.artifact_path is None:
            raise ValueError("Approved candidate is missing its local artifact")
        asset = self.catalog.get_asset(generation.asset_id)
        destination_dir = generation.artifact_path.parent / "processed"
        artifacts = processor.process(
            generation.artifact_path,
            destination_dir,
            get_profile(asset.profile),
        )
        serialized = TypeAdapter(tuple[ProcessedArtifact, ...]).dump_json(artifacts).decode()
        return self.catalog.mark_processed(generation_id, serialized)

    def promote_generation(self, generation_id: str) -> GenerationRecord:
        """Atomically export validated LODs and portable provenance for game import."""
        generation = self.catalog.get_generation(generation_id)
        if generation.status != "processed" or not generation.processed_artifacts:
            raise ValueError("Only a processed candidate can be promoted")
        asset = self.catalog.get_asset(generation.asset_id)
        export_root = self.workspace.export_root.resolve()
        primary = (export_root / asset.export_path).resolve()
        if not primary.is_relative_to(export_root):
            raise ValueError("Asset export path escapes the configured export root")
        primary.parent.mkdir(parents=True, exist_ok=True)

        output_records: list[dict[str, object]] = []
        for artifact in generation.processed_artifacts:
            destination = (
                primary
                if artifact.lod == 0
                else primary.with_name(f"{primary.stem}.lod{artifact.lod}.glb")
            )
            self._atomic_copy(artifact.path, destination)
            output_records.append(
                {
                    "lod": artifact.lod,
                    "ratio": artifact.ratio,
                    "path": destination.name,
                    "sha256": artifact.sha256,
                    "triangles": artifact.quality_report.triangles,
                }
            )

        source_hash = ""
        if generation.artifact_path is not None:
            source_hash = self._hash_file(generation.artifact_path)
        provenance = {
            "version": 1,
            "asset": {
                "id": asset.asset_id,
                "name": asset.name,
                "category": asset.category,
                "profile": asset.profile,
                "brief": asset.brief,
                "topology_notes": asset.topology_notes,
                "game": asset.game.model_dump(mode="json"),
            },
            "source": {
                "generation_id": generation.generation_id,
                "seed": generation.seed,
                "endpoint": generation.endpoint,
                "sha256": source_hash,
                "review_notes": generation.review_notes or "",
                "references": [
                    {
                        "filename": reference.path.name,
                        "view": reference.view,
                        "sha256": reference.sha256,
                    }
                    for reference in asset.references
                ],
            },
            "outputs": output_records,
        }
        manifest_path = primary.with_name(f"{primary.stem}.asset-forge.json")
        temporary = manifest_path.with_name(f".{manifest_path.name}.part")
        temporary.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, manifest_path)
        return self.catalog.mark_promoted(generation_id, manifest_path)

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        if not source.is_file():
            raise FileNotFoundError(source)
        temporary = destination.with_name(f".{destination.name}.part")
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

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
