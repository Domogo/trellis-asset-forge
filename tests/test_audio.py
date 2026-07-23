import json
from pathlib import Path

import httpx
import pytest

from trellis_asset_forge.audio import (
    CASSETTE_MUSIC_MODEL,
    ELEVENLABS_MUSIC_MODEL,
    ELEVENLABS_SFX_MODEL,
    STABLE_AUDIO_MUSIC_MODEL,
    STABLE_AUDIO_SFX_MODEL,
    CassetteMusicRequest,
    ElevenLabsMusicRequest,
    ElevenLabsSfxRequest,
    FalAudioGenerator,
    FalError,
    StableAudioRequest,
    audio_file_suffix,
)
from trellis_asset_forge.domain import RemoteJob


def test_stable_audio_music_submission_maps_reproducible_controls() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == (
            "https://queue.fal.run/fal-ai/stable-audio-3/medium/text-to-audio"
        )
        assert request.headers["Authorization"] == "Key secret-key"
        assert request.headers["X-Fal-Store-IO"] == "0"
        assert json.loads(request.content) == {
            "prompt": "Industrial percussion with bowed metal and no vocals",
            "negative_prompt": "speech, vocals",
            "duration": 90.0,
            "num_inference_steps": 8,
            "guidance_scale": 1.0,
            "seed": 4200,
            "enable_prompt_expansion": True,
            "enable_safety_checker": True,
            "output_format": "wav",
            "bitrate": "192k",
        }
        return httpx.Response(
            200,
            json={
                "request_id": "audio-123",
                "status_url": "https://queue.fal.run/status/audio-123",
                "response_url": "https://queue.fal.run/result/audio-123",
            },
        )

    generator = FalAudioGenerator(
        api_key="secret-key",
        media_ttl_seconds=900,
        transport=httpx.MockTransport(handle),
    )
    request = StableAudioRequest(
        model=STABLE_AUDIO_MUSIC_MODEL,
        prompt="Industrial percussion with bowed metal and no vocals",
        negative_prompt="speech, vocals",
        duration_seconds=90,
        seed=4200,
        enable_prompt_expansion=True,
        output_format="wav",
    )

    job = generator.submit(request)

    assert job.request_id == "audio-123"


def test_elevenlabs_music_submission_maps_duration_and_instrumental_controls() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://queue.fal.run/fal-ai/elevenlabs/music"
        assert json.loads(request.content) == {
            "prompt": "Tense scrapyard combat music with mechanical percussion",
            "music_length_ms": 125000,
            "force_instrumental": True,
            "output_format": "mp3_44100_192",
        }
        return httpx.Response(
            200,
            json={
                "request_id": "music-123",
                "status_url": "https://queue.fal.run/status/music-123",
                "response_url": "https://queue.fal.run/result/music-123",
            },
        )

    generator = FalAudioGenerator(
        api_key="secret-key",
        transport=httpx.MockTransport(handle),
    )

    job = generator.submit(
        ElevenLabsMusicRequest(
            model=ELEVENLABS_MUSIC_MODEL,
            prompt="Tense scrapyard combat music with mechanical percussion",
            duration_seconds=125,
            force_instrumental=True,
            output_format="mp3_44100_192",
        )
    )

    assert job.request_id == "music-123"


def test_elevenlabs_sfx_submission_maps_loop_and_prompt_influence() -> None:
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == (
            "https://queue.fal.run/fal-ai/elevenlabs/sound-effects/v2"
        )
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "request_id": "sfx-123",
                "status_url": "https://queue.fal.run/status/sfx-123",
                "response_url": "https://queue.fal.run/result/sfx-123",
            },
        )

    generator = FalAudioGenerator(
        api_key="secret-key",
        transport=httpx.MockTransport(handle),
    )
    generator.submit(
        ElevenLabsSfxRequest(
            model=ELEVENLABS_SFX_MODEL,
            prompt="Looping hydraulic pump with loose metal vibration",
            duration_seconds=8.5,
            prompt_influence=0.65,
            loop=True,
            output_format="opus_48000_128",
        )
    )

    assert captured == {
        "text": "Looping hydraulic pump with loose metal vibration",
        "duration_seconds": 8.5,
        "prompt_influence": 0.65,
        "output_format": "opus_48000_128",
        "loop": True,
    }


def test_stable_audio_sfx_uses_the_small_sfx_endpoint() -> None:
    observed_url = ""

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal observed_url
        observed_url = str(request.url)
        return httpx.Response(
            200,
            json={
                "request_id": "stable-sfx-123",
                "status_url": "https://queue.fal.run/status/stable-sfx-123",
                "response_url": "https://queue.fal.run/result/stable-sfx-123",
            },
        )

    generator = FalAudioGenerator(
        api_key="secret-key",
        transport=httpx.MockTransport(handle),
    )
    generator.submit(
        StableAudioRequest(
            model=STABLE_AUDIO_SFX_MODEL,
            prompt="Heavy steel hatch slamming in a reverberant cargo bay",
            duration_seconds=3,
            seed=77,
            output_format="flac",
        )
    )

    assert observed_url == (
        "https://queue.fal.run/fal-ai/stable-audio-3/small/sfx/text-to-audio"
    )


def test_cassette_music_submission_uses_its_minimal_prompt_duration_schema() -> None:
    captured: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://queue.fal.run/cassetteai/music-generator"
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "request_id": "cassette-123",
                "status_url": "https://queue.fal.run/status/cassette-123",
                "response_url": "https://queue.fal.run/result/cassette-123",
            },
        )

    generator = FalAudioGenerator(
        api_key="secret-key",
        transport=httpx.MockTransport(handle),
    )
    generator.submit(
        CassetteMusicRequest(
            model=CASSETTE_MUSIC_MODEL,
            prompt="Lo-fi salvage-yard menu music at 85 BPM",
            duration_seconds=45,
        )
    )

    assert captured == {
        "prompt": "Lo-fi salvage-yard menu music at 85 BPM",
        "duration": 45,
    }


def test_audio_poll_and_download_normalize_the_standard_audio_result(
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
                json={"audio": {"url": "https://v3.fal.media/files/result.wav"}},
            )
        assert request.url == "https://v3.fal.media/files/result.wav"
        assert "Authorization" not in request.headers
        return httpx.Response(200, content=b"RIFF-audio")

    generator = FalAudioGenerator(
        api_key="secret-key",
        transport=httpx.MockTransport(handle),
    )
    job = RemoteJob(
        request_id="audio-123",
        status_url="https://queue.fal.run/audio/requests/audio-123/status",
        response_url="https://queue.fal.run/audio/requests/audio-123",
    )

    update = generator.poll(job)
    destination = generator.download(update.result_url or "", tmp_path / "music.wav")

    assert update.status == "completed"
    assert destination.read_bytes() == b"RIFF-audio"


def test_audio_poll_normalizes_cassette_audio_file_results() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"status": "COMPLETED"}),
            httpx.Response(
                200,
                json={
                    "audio_file": {
                        "url": "https://storage.googleapis.com/falserverless/result.wav"
                    }
                },
            ),
        ]
    )
    generator = FalAudioGenerator(
        api_key="secret-key",
        transport=httpx.MockTransport(lambda _: next(responses)),
    )
    job = RemoteJob(
        request_id="cassette-123",
        status_url="https://queue.fal.run/cassette/requests/cassette-123/status",
        response_url="https://queue.fal.run/cassette/requests/cassette-123",
    )

    update = generator.poll(job)

    assert update.result_url == "https://storage.googleapis.com/falserverless/result.wav"


def test_generate_waits_for_completion_and_writes_the_requested_audio_file(
    tmp_path: Path,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "request_id": "audio-123",
                    "status_url": "https://queue.fal.run/audio/audio-123/status",
                    "response_url": "https://queue.fal.run/audio/audio-123",
                },
            )
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "COMPLETED"})
        if request.url.host == "queue.fal.run":
            return httpx.Response(
                200,
                json={"audio": {"url": "https://v3.fal.media/files/result.ogg"}},
            )
        return httpx.Response(200, content=b"OggS-audio")

    generator = FalAudioGenerator(
        api_key="secret-key",
        transport=httpx.MockTransport(handle),
    )
    destination = tmp_path / "combat-loop.ogg"

    result = generator.generate(
        StableAudioRequest(
            prompt="Industrial combat loop",
            duration_seconds=30,
            output_format="ogg",
        ),
        destination,
        timeout_seconds=1,
    )

    assert result == destination.resolve()
    assert result.read_bytes() == b"OggS-audio"


@pytest.mark.parametrize(
    ("remote_status", "expected"),
    [("IN_QUEUE", "queued"), ("IN_PROGRESS", "running"), ("FAILED", "failed")],
)
def test_audio_poll_maps_active_and_failed_queue_states(
    remote_status: str,
    expected: str,
) -> None:
    generator = FalAudioGenerator(
        api_key="secret-key",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"status": remote_status, "error": "provider failed"},
            )
        ),
    )
    job = RemoteJob(
        request_id="audio-123",
        status_url="https://queue.fal.run/audio/audio-123/status",
        response_url="https://queue.fal.run/audio/audio-123",
    )

    update = generator.poll(job)

    assert update.status == expected
    if expected == "failed":
        assert update.error == "provider failed"


def test_audio_adapter_rejects_unsafe_urls_formats_and_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(FalError, match="not set"):
        FalAudioGenerator.from_environment()
    with pytest.raises(FalError, match="empty"):
        FalAudioGenerator(api_key=" ")
    with pytest.raises(FalError, match="at least 60"):
        FalAudioGenerator(api_key="secret", media_ttl_seconds=59)

    generator = FalAudioGenerator(api_key="secret")
    with pytest.raises(FalError, match="Refusing non-fal media URL"):
        generator.download("https://example.com/audio.wav", tmp_path / "audio.wav")
    with pytest.raises(FalError, match="unsupported extension"):
        generator.download(
            "https://v3.fal.media/files/audio.wav",
            tmp_path / "audio.exe",
        )
    with pytest.raises(FalError, match=r"requires a \.wav destination"):
        generator.generate(
            StableAudioRequest(prompt="music"),
            tmp_path / "music.mp3",
        )
    with pytest.raises(ValueError, match="at most 380 seconds"):
        StableAudioRequest(prompt="music", duration_seconds=381)


def test_audio_adapter_reports_invalid_queue_and_result_responses() -> None:
    responses = iter(
        [
            httpx.Response(200, json={"status": "MYSTERY"}),
            httpx.Response(200, json={"status": "COMPLETED"}),
            httpx.Response(200, json={"wrong": "shape"}),
        ]
    )
    generator = FalAudioGenerator(
        api_key="secret",
        transport=httpx.MockTransport(lambda _: next(responses)),
    )
    job = RemoteJob(
        request_id="audio-123",
        status_url="https://queue.fal.run/audio/audio-123/status",
        response_url="https://queue.fal.run/audio/audio-123",
    )

    with pytest.raises(FalError, match="Unknown fal audio queue status"):
        generator.poll(job)
    with pytest.raises(FalError, match="missing audio or audio_file"):
        generator.poll(job)

    invalid_job = job.model_copy(
        update={"status_url": "https://example.com/audio/status"}
    )
    with pytest.raises(FalError, match="Refusing invalid fal queue URL"):
        generator.poll(invalid_job)


def test_audio_suffixes_and_environment_constructor_follow_provider_formats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert audio_file_suffix(CassetteMusicRequest(prompt="music", duration_seconds=30)) == ".wav"
    assert (
        audio_file_suffix(
            ElevenLabsMusicRequest(
                prompt="music",
                output_format="mp3_44100_128",
            )
        )
        == ".mp3"
    )
    monkeypatch.setenv("FAL_KEY", "environment-key")
    assert isinstance(FalAudioGenerator.from_environment(), FalAudioGenerator)


def test_audio_submission_and_poll_surface_malformed_provider_responses() -> None:
    request = StableAudioRequest(prompt="music")
    server_error = FalAudioGenerator(
        api_key="secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
    )
    with pytest.raises(FalError, match="audio submission failed"):
        server_error.submit(request)

    non_object = FalAudioGenerator(
        api_key="secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    )
    with pytest.raises(FalError, match="non-object response"):
        non_object.submit(request)

    missing_job_fields = FalAudioGenerator(
        api_key="secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    )
    with pytest.raises(FalError, match="missing request_id"):
        missing_job_fields.submit(request)

    missing_status = FalAudioGenerator(
        api_key="secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    )
    job = RemoteJob(
        request_id="audio-123",
        status_url="https://queue.fal.run/audio/audio-123/status",
        response_url="https://queue.fal.run/audio/audio-123",
    )
    with pytest.raises(FalError, match="missing status"):
        missing_status.poll(job)


def test_audio_download_is_idempotent_and_removes_empty_partial_files(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "existing.wav"
    existing.write_bytes(b"existing")
    generator = FalAudioGenerator(
        api_key="secret",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"")),
    )

    assert (
        generator.download("https://v3.fal.media/files/existing.wav", existing)
        == existing.resolve()
    )
    empty = tmp_path / "empty.wav"
    with pytest.raises(FalError, match="empty audio"):
        generator.download("https://v3.fal.media/files/empty.wav", empty)
    assert not (tmp_path / "empty.wav.part").exists()


def test_generate_rejects_invalid_wait_controls_before_submission(tmp_path: Path) -> None:
    generator = FalAudioGenerator(api_key="secret")
    request = StableAudioRequest(prompt="music")

    with pytest.raises(FalError, match="poll interval"):
        generator.generate(
            request,
            tmp_path / "music.wav",
            poll_interval_seconds=-1,
        )
    with pytest.raises(FalError, match="timeout must be positive"):
        generator.generate(
            request,
            tmp_path / "music.wav",
            timeout_seconds=0,
        )

    existing = tmp_path / "existing.wav"
    existing.write_bytes(b"do-not-replace")
    with pytest.raises(FalError, match="already exists"):
        generator.generate(request, existing)
    assert existing.read_bytes() == b"do-not-replace"
