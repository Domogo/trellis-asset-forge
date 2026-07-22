from decimal import Decimal
from pathlib import Path

import pytest
import trimesh
from typer.testing import CliRunner

from trellis_asset_forge.cli import app
from trellis_asset_forge.domain import GenerationRequest, RemoteJob, RemoteUpdate
from trellis_asset_forge.forge import AssetForge


class MeshGenerator:
    def submit(self, request: GenerationRequest) -> RemoteJob:
        return RemoteJob(
            request_id="mesh-job",
            status_url="https://queue.example/mesh-job/status",
            response_url="https://queue.example/mesh-job",
        )

    def poll(self, job: RemoteJob) -> RemoteUpdate:
        return RemoteUpdate(status="completed", result_url="https://media.example/mesh.glb")

    def download(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(trimesh.creation.box().export(file_type="glb"))
        return destination


def _downloaded_generation(tmp_path: Path) -> tuple[AssetForge, str]:
    reference = tmp_path / "crate.png"
    reference.write_bytes(b"reference")
    manifest = tmp_path / "assets.yaml"
    manifest.write_text(
        """
version: 1
project: demo
assets:
  - id: props.crate
    name: Crate
    category: props
    profile: mobile-prop
    references:
      - path: crate.png
    generation:
      resolution: 512
      seed: 12
    export: props/crate.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path)
    forge.import_manifest(manifest)
    generator = MeshGenerator()
    generation = forge.submit_asset(
        "props.crate", generator=generator, max_cost_usd=Decimal("0.25")
    )[0]
    forge.sync(generator=generator)
    return forge, generation.generation_id


def test_candidate_requires_passing_inspection_before_human_approval(tmp_path: Path) -> None:
    forge, generation_id = _downloaded_generation(tmp_path)

    with pytest.raises(ValueError, match="Inspect the candidate"):
        forge.approve_generation(generation_id, notes="looks good")

    inspected = forge.inspect_generation(generation_id)
    approved = forge.approve_generation(generation_id, notes="silhouette and UVs approved")

    assert inspected.status == "inspected"
    assert inspected.quality_report is not None
    assert inspected.quality_report.triangles == 12
    assert approved.status == "approved"
    assert approved.review_notes == "silhouette and UVs approved"


def test_rejection_records_human_feedback_for_the_next_variant(tmp_path: Path) -> None:
    forge, generation_id = _downloaded_generation(tmp_path)
    forge.inspect_generation(generation_id)

    rejected = forge.reject_generation(generation_id, notes="underside is too noisy")

    assert rejected.status == "rejected"
    assert rejected.review_notes == "underside is too noisy"


def test_cli_inspects_and_records_review_decisions(tmp_path: Path) -> None:
    _, generation_id = _downloaded_generation(tmp_path)
    runner = CliRunner()

    inspected = runner.invoke(
        app, ["inspect", generation_id, "--workspace", str(tmp_path)]
    )
    approved = runner.invoke(
        app,
        [
            "approve",
            generation_id,
            "--workspace",
            str(tmp_path),
            "--notes",
            "approved in cli",
        ],
    )

    assert inspected.exit_code == 0
    assert "PASS" in inspected.stdout
    assert "12 tris" in inspected.stdout
    assert approved.exit_code == 0
    assert f"Approved {generation_id}" in approved.stdout
