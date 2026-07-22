import json
from pathlib import Path

import httpx

from trellis_asset_forge.domain import GenerationRequest, RemoteJob
from trellis_asset_forge.fal import FalGenerator


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
