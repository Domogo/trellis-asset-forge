import json
from pathlib import Path

import pytest
import trimesh
from typer.testing import CliRunner

from trellis_asset_forge.cli import app
from trellis_asset_forge.domain import GenerationRequest
from trellis_asset_forge.forge import AssetForge
from trellis_asset_forge.processing import GltfpackProcessor, ProcessingError


def _approved_generation(tmp_path: Path) -> tuple[AssetForge, str]:
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
    game:
      scale_meters: 1.5
      pivot: base-center
      collision: convex
    references:
      - path: crate.png
    generation:
      resolution: 512
      seed: 42
    export: props/crate.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path, export_root="exports")
    forge.import_manifest(manifest)
    request = GenerationRequest(
        generation_id="candidate-1",
        asset_id="props.crate",
        variant=0,
        seed=42,
        endpoint="fal-ai/trellis-2",
        references=(reference,),
        resolution=512,
        texture_size=1024,
        decimation_target=20_000,
        remesh=True,
    )
    forge.catalog.create_generation(request, estimated_cost_usd="0.25")
    source = forge.workspace.artifacts_dir / "props.crate" / "candidate-1" / "source.glb"
    source.parent.mkdir(parents=True)
    source.write_bytes(trimesh.creation.box().export(file_type="glb"))
    forge.catalog.mark_downloaded(
        "candidate-1", artifact_path=source, remote_url="https://media.example/source.glb"
    )
    forge.inspect_generation("candidate-1")
    forge.approve_generation("candidate-1", notes="approved")
    return forge, "candidate-1"


def _fake_gltfpack(tmp_path: Path) -> Path:
    executable = tmp_path / "gltfpack"
    executable.write_text(
        """#!/usr/bin/env python3
import shutil
import sys
source = sys.argv[sys.argv.index('-i') + 1]
destination = sys.argv[sys.argv.index('-o') + 1]
shutil.copyfile(source, destination)
"""
    )
    executable.chmod(0o755)
    return executable


def test_processing_builds_validated_profile_lods_from_approved_candidate(
    tmp_path: Path,
) -> None:
    forge, generation_id = _approved_generation(tmp_path)
    processor = GltfpackProcessor(executable=_fake_gltfpack(tmp_path))

    processed = forge.process_generation(generation_id, processor=processor)

    assert processed.status == "processed"
    assert [artifact.lod for artifact in processed.processed_artifacts] == [0, 1, 2]
    assert [artifact.ratio for artifact in processed.processed_artifacts] == [1.0, 0.5, 0.2]
    assert all(artifact.path.is_file() for artifact in processed.processed_artifacts)
    assert all(artifact.quality_report.passed for artifact in processed.processed_artifacts)


def test_promotion_exports_lods_and_catalog_provenance_for_game_import(tmp_path: Path) -> None:
    forge, generation_id = _approved_generation(tmp_path)
    processor = GltfpackProcessor(executable=_fake_gltfpack(tmp_path))
    forge.process_generation(generation_id, processor=processor)

    promoted = forge.promote_generation(generation_id)

    export_root = tmp_path / "exports" / "props"
    assert promoted.status == "promoted"
    assert (export_root / "crate.glb").is_file()
    assert (export_root / "crate.lod1.glb").is_file()
    assert (export_root / "crate.lod2.glb").is_file()
    assert promoted.promotion_manifest_path == export_root / "crate.asset-forge.json"
    provenance = json.loads(promoted.promotion_manifest_path.read_text())
    assert provenance["asset"]["id"] == "props.crate"
    assert provenance["asset"]["game"] == {
        "collision": "convex",
        "pivot": "base-center",
        "scale_meters": 1.5,
    }
    assert provenance["source"]["generation_id"] == generation_id
    assert [output["lod"] for output in provenance["outputs"]] == [0, 1, 2]


def test_cli_processes_and_promotes_an_approved_candidate(tmp_path: Path) -> None:
    _, generation_id = _approved_generation(tmp_path)
    runner = CliRunner()

    processed = runner.invoke(
        app,
        [
            "process",
            generation_id,
            "--workspace",
            str(tmp_path),
            "--gltfpack",
            str(_fake_gltfpack(tmp_path)),
        ],
    )
    promoted = runner.invoke(
        app, ["promote", generation_id, "--workspace", str(tmp_path)]
    )

    assert processed.exit_code == 0
    assert "LOD0" in processed.stdout
    assert "LOD2" in processed.stdout
    assert promoted.exit_code == 0
    assert "Provenance:" in promoted.stdout
    assert (tmp_path / "exports" / "props" / "crate.glb").is_file()


def test_processing_reports_missing_and_failed_gltfpack_tools(tmp_path: Path) -> None:
    with pytest.raises(ProcessingError, match="was not found"):
        GltfpackProcessor(executable=tmp_path / "missing-gltfpack")

    forge, generation_id = _approved_generation(tmp_path)
    failing = tmp_path / "gltfpack-failing"
    failing.write_text("#!/bin/sh\necho 'bad mesh' >&2\nexit 3\n")
    failing.chmod(0o755)

    with pytest.raises(ProcessingError, match="exit 3: bad mesh"):
        forge.process_generation(
            generation_id,
            processor=GltfpackProcessor(executable=failing),
        )
