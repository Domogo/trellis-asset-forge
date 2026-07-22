from decimal import Decimal
from pathlib import Path

import pytest

from trellis_asset_forge.domain import GenerationRequest, RemoteJob, RemoteUpdate
from trellis_asset_forge.forge import AssetForge
from trellis_asset_forge.generation import CostLimitError


class RecordingGenerator:
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def submit(self, request: GenerationRequest) -> RemoteJob:
        self.requests.append(request)
        request_id = f"fal-{request.variant}"
        return RemoteJob(
            request_id=request_id,
            status_url=f"https://queue.example/{request_id}/status",
            response_url=f"https://queue.example/{request_id}",
        )

    def poll(self, job: RemoteJob) -> RemoteUpdate:
        return RemoteUpdate(
            status="completed",
            result_url=f"https://media.example/{job.request_id}.glb",
        )

    def download(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"generated-glb")
        return destination


def test_submit_records_each_reproducible_variant_before_returning(tmp_path: Path) -> None:
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
      variants: 2
      resolution: 512
      seed: 10
    export: props/crate.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path)
    forge.import_manifest(manifest)
    generator = RecordingGenerator()

    submitted = forge.submit_asset(
        "props.crate",
        generator=generator,
        max_cost_usd=Decimal("0.50"),
    )

    assert [request.seed for request in generator.requests] == [10, 11]
    assert {request.endpoint for request in generator.requests} == {"fal-ai/trellis-2"}
    assert {request.decimation_target for request in generator.requests} == {10_000}
    assert len(submitted) == 2
    assert {generation.status for generation in submitted} == {"submitted"}
    assert {generation.request_id for generation in submitted} == {"fal-0", "fal-1"}
    assert forge.list_generations("props.crate") == submitted


def test_manifest_can_select_meshy_v6_preview(tmp_path: Path) -> None:
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
    references:
      - path: crate.png
    generation:
      model: fal-ai/meshy/v6-preview/image-to-3d
      variants: 1
    export: props/crate.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path)
    imported = forge.import_manifest(manifest)
    generator = RecordingGenerator()

    forge.submit_asset(
        "props.crate",
        generator=generator,
        max_cost_usd=Decimal("0.80"),
    )

    assert imported.estimated_cost_usd == Decimal("0.80")
    assert generator.requests[0].endpoint == "fal-ai/meshy/v6-preview/image-to-3d"


@pytest.mark.parametrize(
    "model",
    [
        "fal-ai/hunyuan3d-v3/image-to-3d",
        "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
    ],
)
def test_manifest_can_select_hunyuan_models_with_named_views(
    tmp_path: Path,
    model: str,
) -> None:
    (tmp_path / "front.png").write_bytes(b"front")
    (tmp_path / "back.png").write_bytes(b"back")
    manifest = tmp_path / "assets.yaml"
    manifest.write_text(
        f"""
version: 1
project: demo
assets:
  - id: props.crate
    name: Crate
    category: props
    references:
      - {{path: front.png, view: front}}
      - {{path: back.png, view: rear}}
    generation:
      model: {model}
    export: props/crate.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path)
    imported = forge.import_manifest(manifest)
    generator = RecordingGenerator()

    with pytest.raises(CostLimitError, match=r"estimated at \$0.53"):
        forge.submit_asset(
            "props.crate",
            generator=generator,
            max_cost_usd=Decimal("0.524"),
        )
    forge.submit_asset(
        "props.crate",
        generator=generator,
        max_cost_usd=Decimal("0.525"),
    )

    assert imported.estimated_cost_usd == Decimal("0.53")
    assert generator.requests[0].endpoint == model
    assert generator.requests[0].reference_views == ("front", "rear")


def test_cost_limit_stops_the_batch_before_remote_or_catalog_activity(tmp_path: Path) -> None:
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
    profile: desktop-prop
    references:
      - path: crate.png
    generation:
      variants: 3
      resolution: 1024
    export: props/crate.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path)
    forge.import_manifest(manifest)
    generator = RecordingGenerator()

    with pytest.raises(CostLimitError, match=r"estimated at \$0.90"):
        forge.submit_asset(
            "props.crate",
            generator=generator,
            max_cost_usd=Decimal("0.89"),
        )

    assert generator.requests == []
    assert forge.list_generations("props.crate") == []


def test_sync_downloads_completed_jobs_into_private_artifact_storage(tmp_path: Path) -> None:
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
    references:
      - path: crate.png
    generation:
      variants: 1
      resolution: 512
      seed: 12
    export: props/crate.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path)
    forge.import_manifest(manifest)
    generator = RecordingGenerator()
    generation = forge.submit_asset(
        "props.crate", generator=generator, max_cost_usd=Decimal("0.25")
    )[0]

    synced = forge.sync(generator=generator)

    assert len(synced) == 1
    assert synced[0].generation_id == generation.generation_id
    assert synced[0].status == "downloaded"
    assert synced[0].artifact_path is not None
    assert synced[0].artifact_path.read_bytes() == b"generated-glb"
    assert tmp_path / ".asset-forge" / "artifacts" in synced[0].artifact_path.parents


def test_submit_all_cost_gates_the_whole_catalog_before_remote_work(tmp_path: Path) -> None:
    first = tmp_path / "crate.png"
    second = tmp_path / "barrel.png"
    first.write_bytes(b"crate")
    second.write_bytes(b"barrel")
    manifest = tmp_path / "assets.yaml"
    manifest.write_text(
        """
version: 1
project: demo
assets:
  - id: props.crate
    name: Crate
    category: props
    references: [{path: crate.png}]
    generation: {resolution: 512, seed: 10}
    export: props/crate.glb
  - id: props.barrel
    name: Barrel
    category: props
    references: [{path: barrel.png}]
    generation: {resolution: 512, seed: 20}
    export: props/barrel.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path)
    forge.import_manifest(manifest)
    generator = RecordingGenerator()

    with pytest.raises(CostLimitError, match=r"Catalog batch is estimated at \$0.50"):
        forge.submit_all(generator=generator, max_cost_usd=Decimal("0.49"))

    assert generator.requests == []
    assert forge.list_generations() == []

    submitted = forge.submit_all(generator=generator, max_cost_usd=Decimal("0.50"))
    assert len(submitted) == 2
    assert {request.asset_id for request in generator.requests} == {
        "props.crate",
        "props.barrel",
    }

    repeated = forge.submit_all(generator=generator, max_cost_usd=Decimal("0"))
    assert repeated == []
    assert len(generator.requests) == 2
