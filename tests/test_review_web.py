from pathlib import Path

import trimesh
from fastapi.testclient import TestClient

from trellis_asset_forge.domain import GenerationRequest
from trellis_asset_forge.forge import AssetForge
from trellis_asset_forge.review_web import create_review_app


def _workspace_with_candidate(tmp_path: Path) -> None:
    reference = tmp_path / "crate.png"
    reference.write_bytes(b"reference")
    manifest = tmp_path / "assets.yaml"
    manifest.write_text(
        """
version: 1
project: demo
assets:
  - id: props.crate
    name: Scrap Crate
    category: props
    profile: mobile-prop
    references:
      - path: crate.png
    export: props/crate.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path)
    forge.import_manifest(manifest)
    request = GenerationRequest(
        generation_id="candidate-1",
        asset_id="props.crate",
        variant=0,
        seed=42,
        endpoint="fal-ai/trellis-2",
        references=(reference,),
        resolution=1024,
        texture_size=1024,
        decimation_target=20_000,
        remesh=True,
    )
    forge.catalog.create_generation(request, estimated_cost_usd="0.30")
    artifact = forge.workspace.artifacts_dir / "props.crate" / "candidate-1" / "source.glb"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(trimesh.creation.box().export(file_type="glb"))
    forge.catalog.mark_downloaded(
        "candidate-1", artifact_path=artifact, remote_url="https://media.example/model.glb"
    )


def test_private_review_workspace_previews_inspects_and_approves_candidate(
    tmp_path: Path,
) -> None:
    _workspace_with_candidate(tmp_path)
    client = TestClient(create_review_app(tmp_path))

    dashboard = client.get("/")
    preview = client.get("/generations/candidate-1/model.glb")
    inspected = client.post("/generations/candidate-1/inspect", follow_redirects=True)
    approved = client.post(
        "/generations/candidate-1/approve",
        data={"notes": "shape and topology approved"},
        follow_redirects=True,
    )

    assert dashboard.status_code == 200
    assert "Scrap Crate" in dashboard.text
    assert "candidate-1" in dashboard.text
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "model/gltf-binary"
    assert inspected.status_code == 200
    assert "12" in inspected.text
    assert approved.status_code == 200
    assert "Approved" in approved.text
    assert "shape and topology approved" in approved.text
