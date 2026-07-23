"""Privacy-aware fal adapters for text-to-music and text-to-SFX endpoints."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from trellis_asset_forge.domain import RemoteJob, RemoteUpdate
from trellis_asset_forge.fal import QUEUE_ORIGIN, FalError

STABLE_AUDIO_MUSIC_MODEL: Literal[
    "fal-ai/stable-audio-3/medium/text-to-audio"
] = "fal-ai/stable-audio-3/medium/text-to-audio"
STABLE_AUDIO_SFX_MODEL: Literal[
    "fal-ai/stable-audio-3/small/sfx/text-to-audio"
] = "fal-ai/stable-audio-3/small/sfx/text-to-audio"
ELEVENLABS_MUSIC_MODEL: Literal[
    "fal-ai/elevenlabs/music"
] = "fal-ai/elevenlabs/music"
ELEVENLABS_SFX_MODEL: Literal[
    "fal-ai/elevenlabs/sound-effects/v2"
] = "fal-ai/elevenlabs/sound-effects/v2"
CASSETTE_MUSIC_MODEL: Literal[
    "cassetteai/music-generator"
] = "cassetteai/music-generator"

StableAudioModel = Literal[
    "fal-ai/stable-audio-3/medium/text-to-audio",
    "fal-ai/stable-audio-3/small/sfx/text-to-audio",
]
StableAudioFormat = Literal["mp3", "wav", "flac", "ogg", "opus", "m4a", "aac"]
AUDIO_SUFFIXES = frozenset(
    {".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".pcm", ".ulaw", ".alaw"}
)
ElevenLabsOutputFormat = Literal[
    "mp3_22050_32",
    "mp3_44100_32",
    "mp3_44100_64",
    "mp3_44100_96",
    "mp3_44100_128",
    "mp3_44100_192",
    "pcm_8000",
    "pcm_16000",
    "pcm_22050",
    "pcm_24000",
    "pcm_44100",
    "pcm_48000",
    "ulaw_8000",
    "alaw_8000",
    "opus_48000_32",
    "opus_48000_64",
    "opus_48000_96",
    "opus_48000_128",
    "opus_48000_192",
]


class StableAudioRequest(BaseModel):
    """Controls shared by Stable Audio 3 music and SFX generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: StableAudioModel = STABLE_AUDIO_MUSIC_MODEL
    prompt: str = Field(min_length=1, max_length=10_000)
    negative_prompt: str = Field(default="", max_length=10_000)
    duration_seconds: float = Field(default=30, gt=0)
    num_inference_steps: int = Field(default=8, ge=1, le=100)
    guidance_scale: float = Field(default=1, ge=0, le=20)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    enable_prompt_expansion: bool = False
    enable_safety_checker: bool = True
    output_format: StableAudioFormat = "wav"
    bitrate: str = Field(default="192k", pattern=r"^[1-9][0-9]*k$")

    @model_validator(mode="after")
    def validate_music_duration(self) -> StableAudioRequest:
        if self.model == STABLE_AUDIO_MUSIC_MODEL and self.duration_seconds > 380:
            raise ValueError("Stable Audio 3 Medium supports at most 380 seconds")
        return self


class ElevenLabsMusicRequest(BaseModel):
    """Prompt-driven ElevenLabs music controls supported by fal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Literal["fal-ai/elevenlabs/music"] = ELEVENLABS_MUSIC_MODEL
    prompt: str = Field(min_length=1, max_length=10_000)
    duration_seconds: int = Field(default=30, ge=3, le=600)
    force_instrumental: bool = True
    output_format: ElevenLabsOutputFormat = "mp3_44100_128"


class ElevenLabsSfxRequest(BaseModel):
    """ElevenLabs sound-effect controls supported by fal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Literal["fal-ai/elevenlabs/sound-effects/v2"] = ELEVENLABS_SFX_MODEL
    prompt: str = Field(min_length=1, max_length=10_000)
    duration_seconds: float = Field(default=5, ge=0.5, le=22)
    prompt_influence: float = Field(default=0.3, ge=0, le=1)
    output_format: ElevenLabsOutputFormat = "mp3_44100_128"
    loop: bool = False


class CassetteMusicRequest(BaseModel):
    """CassetteAI's intentionally small prompt-and-duration interface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Literal["cassetteai/music-generator"] = CASSETTE_MUSIC_MODEL
    prompt: str = Field(min_length=1, max_length=10_000)
    duration_seconds: int = Field(ge=1)


AudioRequest = (
    StableAudioRequest
    | ElevenLabsMusicRequest
    | ElevenLabsSfxRequest
    | CassetteMusicRequest
)


def audio_file_suffix(request: AudioRequest) -> str:
    """Return the required destination suffix for a model's selected output."""
    if isinstance(request, CassetteMusicRequest):
        return ".wav"
    if isinstance(request, (ElevenLabsMusicRequest, ElevenLabsSfxRequest)):
        return f".{request.output_format.split('_', maxsplit=1)[0]}"
    return f".{request.output_format}"


class FalAudioGenerator:
    """Submit supported text-to-audio jobs without retaining fal request payloads."""

    def __init__(
        self,
        *,
        api_key: str,
        media_ttl_seconds: int = 3600,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key.strip():
            raise FalError("FAL_KEY is empty")
        if media_ttl_seconds < 60:
            raise FalError("fal media lifetime must be at least 60 seconds")
        self._api_key = api_key
        self._media_ttl_seconds = media_ttl_seconds
        self._transport = transport
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls, *, media_ttl_seconds: int = 3600) -> FalAudioGenerator:
        """Create an adapter from the server-side ``FAL_KEY`` environment variable."""
        api_key = os.environ.get("FAL_KEY", "")
        if not api_key:
            raise FalError("FAL_KEY is not set")
        return cls(api_key=api_key, media_ttl_seconds=media_ttl_seconds)

    def submit(self, request: AudioRequest) -> RemoteJob:
        """Submit one validated text-to-audio request to the fal queue."""
        payload = self._payload(request)
        with self._client() as client:
            try:
                response = client.post(f"{QUEUE_ORIGIN}/{request.model}", json=payload)
                response.raise_for_status()
                data: Any = response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise FalError(f"fal audio submission failed: {error}") from error
        if not isinstance(data, dict):
            raise FalError("fal audio submission returned a non-object response")
        return RemoteJob(
            request_id=self._required_string(data, "request_id"),
            status_url=self._required_string(data, "status_url"),
            response_url=self._required_string(data, "response_url"),
        )

    def poll(self, job: RemoteJob) -> RemoteUpdate:
        """Poll fal and normalize supported audio output shapes."""
        status_data = self._queue_json(job.status_url, operation="audio status poll")
        raw_status = status_data.get("status")
        if not isinstance(raw_status, str):
            raise FalError("fal audio status response is missing status")
        status = raw_status.upper()
        if status in {"IN_QUEUE", "QUEUED"}:
            return RemoteUpdate(status="queued")
        if status in {"IN_PROGRESS", "RUNNING"}:
            return RemoteUpdate(status="running")
        if status in {"FAILED", "CANCELLED"}:
            error = status_data.get("error")
            return RemoteUpdate(
                status="failed",
                error=str(error) if error else f"fal audio job ended with {status}",
            )
        if status != "COMPLETED":
            raise FalError(f"Unknown fal audio queue status: {raw_status}")

        result_data = self._queue_json(job.response_url, operation="audio result fetch")
        return RemoteUpdate(
            status="completed",
            result_url=self._result_url(result_data),
        )

    def download(self, url: str, destination: Path) -> Path:
        """Download fal audio without forwarding the fal API key to media storage."""
        parsed = urlparse(url)
        host = parsed.hostname or ""
        is_fal_media = host == "fal.media" or host.endswith(".fal.media")
        if parsed.scheme != "https" or not (is_fal_media or host == "storage.googleapis.com"):
            raise FalError(f"Refusing non-fal media URL: {url}")
        resolved_destination = destination.expanduser().resolve()
        if resolved_destination.suffix.lower() not in AUDIO_SUFFIXES:
            raise FalError("Generated audio destination has an unsupported extension")
        if resolved_destination.is_file() and resolved_destination.stat().st_size > 0:
            return resolved_destination
        resolved_destination.parent.mkdir(parents=True, exist_ok=True)
        partial = resolved_destination.with_suffix(resolved_destination.suffix + ".part")
        try:
            with (
                httpx.Client(
                    timeout=self._timeout_seconds,
                    transport=self._transport,
                ) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                with partial.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
            if partial.stat().st_size == 0:
                raise FalError("fal returned empty audio")
            partial.replace(resolved_destination)
        except (FalError, httpx.HTTPError, OSError) as error:
            partial.unlink(missing_ok=True)
            raise FalError(f"fal audio download failed: {error}") from error
        return resolved_destination

    def generate(
        self,
        request: AudioRequest,
        destination: Path,
        *,
        poll_interval_seconds: float = 2.0,
        timeout_seconds: float = 900.0,
    ) -> Path:
        """Submit, wait for, and download one audio generation."""
        if poll_interval_seconds < 0:
            raise FalError("poll interval cannot be negative")
        if timeout_seconds <= 0:
            raise FalError("audio generation timeout must be positive")
        expected_suffix = audio_file_suffix(request)
        if destination.suffix.lower() != expected_suffix:
            output_format = getattr(request, "output_format", "wav")
            raise FalError(
                f"{request.model} with {output_format} requires a "
                f"{expected_suffix} destination"
            )
        resolved_destination = destination.expanduser().resolve()
        if resolved_destination.exists():
            raise FalError(f"Audio destination already exists: {resolved_destination}")

        job = self.submit(request)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            update = self.poll(job)
            if update.status == "completed":
                if update.result_url is None:
                    raise FalError("completed fal audio job is missing its result URL")
                return self.download(update.result_url, destination)
            if update.status == "failed":
                raise FalError(update.error or "fal audio generation failed")
            if poll_interval_seconds:
                time.sleep(poll_interval_seconds)
        raise FalError(f"fal audio generation timed out after {timeout_seconds:g} seconds")

    @staticmethod
    def _payload(request: AudioRequest) -> dict[str, object]:
        if isinstance(request, CassetteMusicRequest):
            return {
                "prompt": request.prompt,
                "duration": request.duration_seconds,
            }
        if isinstance(request, ElevenLabsSfxRequest):
            return {
                "text": request.prompt,
                "duration_seconds": request.duration_seconds,
                "prompt_influence": request.prompt_influence,
                "output_format": request.output_format,
                "loop": request.loop,
            }
        if isinstance(request, ElevenLabsMusicRequest):
            return {
                "prompt": request.prompt,
                "music_length_ms": request.duration_seconds * 1000,
                "force_instrumental": request.force_instrumental,
                "output_format": request.output_format,
            }
        payload: dict[str, object] = {
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "duration": request.duration_seconds,
            "num_inference_steps": request.num_inference_steps,
            "guidance_scale": request.guidance_scale,
            "enable_prompt_expansion": request.enable_prompt_expansion,
            "enable_safety_checker": request.enable_safety_checker,
            "output_format": request.output_format,
            "bitrate": request.bitrate,
        }
        if request.seed is not None:
            payload["seed"] = request.seed
        return payload

    def _client(self) -> httpx.Client:
        return httpx.Client(
            headers={
                "Authorization": f"Key {self._api_key}",
                "X-Fal-Store-IO": "0",
                "X-Fal-Object-Lifecycle-Preference": json.dumps(
                    {"expiration_duration_seconds": self._media_ttl_seconds},
                    separators=(",", ":"),
                ),
            },
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    def _queue_json(self, url: str, *, operation: str) -> dict[object, object]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "queue.fal.run":
            raise FalError(f"Refusing invalid fal queue URL: {url}")
        with self._client() as client:
            try:
                response = client.get(url)
                response.raise_for_status()
                data: Any = response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise FalError(f"fal {operation} failed: {error}") from error
        if not isinstance(data, dict):
            raise FalError(f"fal {operation} returned a non-object response")
        return data

    @classmethod
    def _result_url(cls, data: dict[object, object]) -> str:
        for key in ("audio", "audio_file"):
            audio = data.get(key)
            if isinstance(audio, str) and audio:
                return audio
            if isinstance(audio, dict):
                return cls._required_string(audio, "url")
        raise FalError("fal audio result is missing audio or audio_file")

    @staticmethod
    def _required_string(data: dict[object, object], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise FalError(f"fal audio submission response is missing {key}")
        return value
