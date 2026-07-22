import json
from pathlib import Path

import httpx
import pytest

from trellis_asset_forge.domain import GenerationRequest, RemoteJob
from trellis_asset_forge.fal import FalError, FalGenerator


def test_fal_submission_uses_multi_view_payload_and_privacy_headers(tmp_path: Path) -> None:
    front = tmp_path / "front.png"
    rear = tmp_path / "rear.png"
    front.write_bytes(b"front")
    rear.write_bytes(b"rear")

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url == "https://queue.fal.run/fal-ai/trellis-2/multi"
        assert request.headers["Authorization"] == "Key secret-key"
        assert request.headers["X-Fal-Store-IO"] == "0"
        assert json.loads(request.headers["X-Fal-Object-Lifecycle-Preference"]) == {
            "expiration_duration_seconds": 900
        }
        assert payload["image_urls"] == [
            "data:image/png;base64,ZnJvbnQ=",
            "data:image/png;base64,cmVhcg==",
        ]
        assert payload["seed"] == 12
        assert payload["resolution"] == 1024
        assert payload["texture_size"] == 2048
        assert payload["decimation_target"] == 50_000
        assert payload["remesh"] is True
        assert "prompt" not in payload
        return httpx.Response(
            200,
            json={
                "request_id": "remote-123",
                "status_url": "https://queue.fal.run/status/remote-123",
                "response_url": "https://queue.fal.run/result/remote-123",
            },
        )

    generator = FalGenerator(
        api_key="secret-key",
        media_ttl_seconds=900,
        transport=httpx.MockTransport(handle),
    )
    request = GenerationRequest(
        generation_id="local-123",
        asset_id="props.robot",
        variant=0,
        seed=12,
        endpoint="fal-ai/trellis-2/multi",
        references=(front, rear),
        resolution=1024,
        texture_size=2048,
        decimation_target=50_000,
        remesh=True,
    )

    job = generator.submit(request)

    assert job.request_id == "remote-123"
    assert job.status_url.endswith("/status/remote-123")


def test_fal_submission_translates_meshy_generation_controls(tmp_path: Path) -> None:
    image = tmp_path / "crate.png"
    image.write_bytes(b"reference")

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == (
            "https://queue.fal.run/fal-ai/meshy/v6-preview/image-to-3d"
        )
        assert json.loads(request.content) == {
            "image_url": "data:image/png;base64,cmVmZXJlbmNl",
            "target_polycount": 25_000,
            "should_remesh": True,
        }
        return httpx.Response(
            200,
            json={
                "request_id": "meshy-123",
                "status_url": "https://queue.fal.run/status/meshy-123",
                "response_url": "https://queue.fal.run/result/meshy-123",
            },
        )

    generator = FalGenerator(api_key="secret", transport=httpx.MockTransport(handle))
    request = GenerationRequest(
        generation_id="local-123",
        asset_id="props.crate",
        variant=0,
        seed=12,
        endpoint="fal-ai/meshy/v6-preview/image-to-3d",
        references=(image,),
        resolution=1024,
        texture_size=2048,
        decimation_target=25_000,
        remesh=True,
    )

    job = generator.submit(request)

    assert job.request_id == "meshy-123"


def test_fal_submission_maps_hunyuan_v3_reference_views(tmp_path: Path) -> None:
    references = tuple(tmp_path / name for name in ("front.png", "back.png", "left.png"))
    for reference in references:
        reference.write_bytes(reference.stem.encode())

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://queue.fal.run/fal-ai/hunyuan3d-v3/image-to-3d"
        assert json.loads(request.content) == {
            "input_image_url": "data:image/png;base64,ZnJvbnQ=",
            "back_image_url": "data:image/png;base64,YmFjaw==",
            "left_image_url": "data:image/png;base64,bGVmdA==",
        }
        return httpx.Response(
            200,
            json={
                "request_id": "hunyuan-123",
                "status_url": "https://queue.fal.run/status/hunyuan-123",
                "response_url": "https://queue.fal.run/result/hunyuan-123",
            },
        )

    generator = FalGenerator(api_key="secret", transport=httpx.MockTransport(handle))
    request = GenerationRequest(
        generation_id="local-123",
        asset_id="props.crate",
        variant=0,
        seed=12,
        endpoint="fal-ai/hunyuan3d-v3/image-to-3d",
        references=references,
        reference_views=("front", "rear", "left"),
        resolution=1024,
        texture_size=2048,
        decimation_target=25_000,
        remesh=True,
    )

    job = generator.submit(request)

    assert job.request_id == "hunyuan-123"


def test_fal_submission_supports_hunyuan_v31_extended_views(tmp_path: Path) -> None:
    references = tuple(tmp_path / name for name in ("front.png", "top.png", "angle.png"))
    for reference in references:
        reference.write_bytes(reference.stem.encode())
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "request_id": "hunyuan-v31",
                "status_url": "https://queue.fal.run/status/hunyuan-v31",
                "response_url": "https://queue.fal.run/result/hunyuan-v31",
            },
        )

    generator = FalGenerator(api_key="secret", transport=httpx.MockTransport(handle))
    generator.submit(
        GenerationRequest(
            generation_id="local-123",
            asset_id="props.crate",
            variant=0,
            seed=12,
            endpoint="fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
            references=references,
            reference_views=("front", "top", "front-left"),
            resolution=1024,
            texture_size=2048,
            decimation_target=25_000,
            remesh=True,
        )
    )

    assert captured == {
        "input_image_url": "data:image/png;base64,ZnJvbnQ=",
        "top_image_url": "data:image/png;base64,dG9w",
        "left_front_image_url": "data:image/png;base64,YW5nbGU=",
    }


def test_fal_poll_resolves_and_downloads_completed_glb_without_leaking_key(
    tmp_path: Path,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status"):
            assert request.headers["Authorization"] == "Key secret-key"
            return httpx.Response(200, json={"status": "COMPLETED"})
        if request.url.host == "queue.fal.run":
            assert request.headers["Authorization"] == "Key secret-key"
            return httpx.Response(
                200,
                json={"model_glb": {"url": "https://v3.fal.media/files/result.glb"}},
            )
        assert request.url == "https://v3.fal.media/files/result.glb"
        assert "Authorization" not in request.headers
        assert "X-Fal-Store-IO" not in request.headers
        return httpx.Response(200, content=b"glTF-binary")

    generator = FalGenerator(api_key="secret-key", transport=httpx.MockTransport(handle))
    job = RemoteJob(
        request_id="remote-123",
        status_url="https://queue.fal.run/fal-ai/trellis-2/requests/remote-123/status",
        response_url="https://queue.fal.run/fal-ai/trellis-2/requests/remote-123",
    )

    update = generator.poll(job)
    destination = generator.download(update.result_url or "", tmp_path / "asset.glb")

    assert update.status == "completed"
    assert destination.read_bytes() == b"glTF-binary"
    assert not (tmp_path / "asset.glb.part").exists()


@pytest.mark.parametrize(
    ("remote_status", "expected"),
    [("IN_QUEUE", "queued"), ("IN_PROGRESS", "running"), ("FAILED", "failed")],
)
def test_fal_poll_maps_active_and_failed_queue_states(
    remote_status: str,
    expected: str,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"status": remote_status, "error": "provider failed"},
        )
    )
    generator = FalGenerator(api_key="secret", transport=transport)
    job = RemoteJob(
        request_id="job",
        status_url="https://queue.fal.run/job/status",
        response_url="https://queue.fal.run/job",
    )

    update = generator.poll(job)

    assert update.status == expected
    if expected == "failed":
        assert update.error == "provider failed"


def test_fal_rejects_unsafe_urls_endpoints_and_reference_shapes(tmp_path: Path) -> None:
    image = tmp_path / "front.png"
    other = tmp_path / "rear.png"
    image.write_bytes(b"front")
    other.write_bytes(b"rear")
    generator = FalGenerator(api_key="secret", transport=httpx.MockTransport(lambda _: None))
    base = dict(
        generation_id="local",
        asset_id="props.crate",
        variant=0,
        seed=1,
        resolution=512,
        texture_size=1024,
        decimation_target=20_000,
        remesh=True,
    )

    with pytest.raises(FalError, match="Unsupported fal endpoint"):
        generator.submit(
            GenerationRequest(
                **base,
                endpoint="fal-ai/trellis-2/../other",
                references=(image,),
            )
        )
    with pytest.raises(FalError, match="multi endpoint requires"):
        generator.submit(
            GenerationRequest(
                **base,
                endpoint="fal-ai/trellis-2/multi",
                references=(image,),
            )
        )
    with pytest.raises(FalError, match="single-image endpoint requires"):
        generator.submit(
            GenerationRequest(
                **base,
                endpoint="fal-ai/trellis-2",
                references=(image, other),
            )
        )
    with pytest.raises(FalError, match="Meshy v6 image-to-3D requires exactly one"):
        generator.submit(
            GenerationRequest(
                **base,
                endpoint="fal-ai/meshy/v6-preview/image-to-3d",
                references=(image, other),
            )
        )
    with pytest.raises(FalError, match="Hunyuan image-to-3D requires at least one"):
        generator.submit(
            GenerationRequest(
                **base,
                endpoint="fal-ai/hunyuan3d-v3/image-to-3d",
                references=(),
            )
        )
    with pytest.raises(FalError, match="requires named reference views"):
        generator.submit(
            GenerationRequest(
                **base,
                endpoint="fal-ai/hunyuan3d-v3/image-to-3d",
                references=(image, other),
            )
        )
    with pytest.raises(FalError, match="Unsupported Hunyuan reference view"):
        generator.submit(
            GenerationRequest(
                **base,
                endpoint="fal-ai/hunyuan3d-v3/image-to-3d",
                references=(image, other),
                reference_views=("front", "top"),
            )
        )
    with pytest.raises(FalError, match="Duplicate Hunyuan reference view"):
        generator.submit(
            GenerationRequest(
                **base,
                endpoint="fal-ai/hunyuan3d-v3/image-to-3d",
                references=(image, other, other),
                reference_views=("front", "back", "rear"),
            )
        )
    with pytest.raises(ValueError, match="reference_views must match references"):
        GenerationRequest(
            **base,
            endpoint="fal-ai/hunyuan3d-v3/image-to-3d",
            references=(image, other),
            reference_views=("front",),
        )
    with pytest.raises(FalError, match="Refusing non-fal media URL"):
        generator.download("https://example.com/model.glb", tmp_path / "model.glb")
    with pytest.raises(FalError, match=r"must use a \.glb destination"):
        generator.download("https://v3.fal.media/model.glb", tmp_path / "model.obj")


def test_fal_reports_invalid_status_and_result_responses() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"status": "MYSTERY"}),
            httpx.Response(200, json={"status": "COMPLETED"}),
            httpx.Response(200, json={"wrong": "shape"}),
        ]
    )
    generator = FalGenerator(
        api_key="secret",
        transport=httpx.MockTransport(lambda _: next(responses)),
    )
    job = RemoteJob(
        request_id="job",
        status_url="https://queue.fal.run/job/status",
        response_url="https://queue.fal.run/job",
    )

    with pytest.raises(FalError, match="Unknown fal queue status"):
        generator.poll(job)
    with pytest.raises(FalError, match="missing model_glb"):
        generator.poll(job)


def test_fal_rejects_invalid_queue_and_submission_responses(tmp_path: Path) -> None:
    invalid_job = RemoteJob(
        request_id="job",
        status_url="https://example.com/job/status",
        response_url="https://queue.fal.run/job",
    )
    generator = FalGenerator(
        api_key="secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )

    with pytest.raises(FalError, match="Refusing invalid fal queue URL"):
        generator.poll(invalid_job)

    non_object_job = invalid_job.model_copy(
        update={"status_url": "https://queue.fal.run/job/status"}
    )
    with pytest.raises(FalError, match="status poll returned a non-object response"):
        generator.poll(non_object_job)

    image = tmp_path / "image.png"
    image.write_bytes(b"reference")
    request = GenerationRequest(
        generation_id="local",
        asset_id="props.crate",
        variant=0,
        seed=1,
        endpoint="fal-ai/trellis-2",
        references=(image,),
        resolution=512,
        texture_size=1024,
        decimation_target=20_000,
        remesh=True,
    )
    empty_response = FalGenerator(
        api_key="secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    )
    with pytest.raises(FalError, match="missing request_id"):
        empty_response.submit(request)

    missing_reference = request.model_copy(update={"references": (tmp_path / "missing.png",)})
    with pytest.raises(FalError, match="Reference image not found"):
        empty_response.submit(missing_reference)


def test_fal_validates_configuration_and_reference_file_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(FalError, match="not set"):
        FalGenerator.from_environment()
    with pytest.raises(FalError, match="empty"):
        FalGenerator(api_key=" ")
    with pytest.raises(FalError, match="at least 60"):
        FalGenerator(api_key="secret", media_ttl_seconds=59)

    unsupported = tmp_path / "front.txt"
    unsupported.write_text("not an image")
    generator = FalGenerator(api_key="secret")
    request = GenerationRequest(
        generation_id="local",
        asset_id="props.crate",
        variant=0,
        seed=1,
        endpoint="fal-ai/trellis-2",
        references=(unsupported,),
        resolution=512,
        texture_size=1024,
        decimation_target=20_000,
        remesh=True,
    )
    with pytest.raises(FalError, match="Unsupported reference image type"):
        generator.submit(request)
