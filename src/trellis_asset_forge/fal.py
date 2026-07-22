"""Privacy-aware fal queue adapter for TRELLIS.2."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from trellis_asset_forge.domain import GenerationRequest, RemoteJob, RemoteUpdate

QUEUE_ORIGIN = "https://queue.fal.run"
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/avif", "image/gif"}


class FalError(RuntimeError):
    """Raised when fal rejects or returns an invalid generation response."""


class FalGenerator:
    """Submit TRELLIS.2 jobs without persisting fal request payloads."""

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
    def from_environment(cls, *, media_ttl_seconds: int = 3600) -> FalGenerator:
        """Create an adapter from the server-side ``FAL_KEY`` environment variable."""
        api_key = os.environ.get("FAL_KEY", "")
        if not api_key:
            raise FalError("FAL_KEY is not set")
        return cls(api_key=api_key, media_ttl_seconds=media_ttl_seconds)

    def submit(self, request: GenerationRequest) -> RemoteJob:
        """Encode local references and submit one asynchronous queue request."""
        payload = self._payload(request)
        endpoint = request.endpoint.strip("/")
        if not endpoint.startswith("fal-ai/trellis-2") or ".." in endpoint:
            raise FalError(f"Unsupported fal endpoint: {request.endpoint}")
        with self._client() as client:
            try:
                response = client.post(f"{QUEUE_ORIGIN}/{endpoint}", json=payload)
                response.raise_for_status()
                data: Any = response.json()
            except (httpx.HTTPError, ValueError) as error:
                raise FalError(f"fal submission failed: {error}") from error
        if not isinstance(data, dict):
            raise FalError("fal submission returned a non-object response")
        return RemoteJob(
            request_id=self._required_string(data, "request_id"),
            status_url=self._required_string(data, "status_url"),
            response_url=self._required_string(data, "response_url"),
        )

    def poll(self, job: RemoteJob) -> RemoteUpdate:
        """Poll fal and resolve the output GLB URL when the queue completes."""
        status_data = self._queue_json(job.status_url, operation="status poll")
        raw_status = status_data.get("status")
        if not isinstance(raw_status, str):
            raise FalError("fal status response is missing status")
        status = raw_status.upper()
        if status in {"IN_QUEUE", "QUEUED"}:
            return RemoteUpdate(status="queued")
        if status in {"IN_PROGRESS", "RUNNING"}:
            return RemoteUpdate(status="running")
        if status in {"FAILED", "CANCELLED"}:
            error = status_data.get("error")
            return RemoteUpdate(
                status="failed",
                error=str(error) if error else f"fal job ended with {status}",
            )
        if status != "COMPLETED":
            raise FalError(f"Unknown fal queue status: {raw_status}")

        result_data = self._queue_json(job.response_url, operation="result fetch")
        model_glb = result_data.get("model_glb")
        if not isinstance(model_glb, dict):
            raise FalError("fal result is missing model_glb")
        return RemoteUpdate(
            status="completed",
            result_url=self._required_string(model_glb, "url"),
        )

    def download(self, url: str, destination: Path) -> Path:
        """Download fal media without forwarding the fal API key to its CDN."""
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not (host == "fal.media" or host.endswith(".fal.media")):
            raise FalError(f"Refusing non-fal media URL: {url}")
        resolved_destination = destination.expanduser().resolve()
        if resolved_destination.suffix.lower() != ".glb":
            raise FalError("Generated artifacts must use a .glb destination")
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
                raise FalError("fal returned an empty GLB")
            partial.replace(resolved_destination)
        except (httpx.HTTPError, OSError) as error:
            partial.unlink(missing_ok=True)
            raise FalError(f"fal artifact download failed: {error}") from error
        return resolved_destination

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

    def _payload(self, request: GenerationRequest) -> dict[str, object]:
        encoded_references = [self._data_uri(path) for path in request.references]
        payload: dict[str, object] = {
            "seed": request.seed,
            "resolution": request.resolution,
            "texture_size": request.texture_size,
            "decimation_target": request.decimation_target,
            "remesh": request.remesh,
        }
        if request.endpoint.endswith("/multi"):
            if len(encoded_references) < 2:
                raise FalError("The TRELLIS.2 multi endpoint requires at least two references")
            payload["image_urls"] = encoded_references
        else:
            if len(encoded_references) != 1:
                raise FalError("The TRELLIS.2 single-image endpoint requires exactly one reference")
            payload["image_url"] = encoded_references[0]
        return payload

    @staticmethod
    def _data_uri(path: Path) -> str:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise FalError(f"Reference image not found: {resolved}")
        mime_type, _ = mimetypes.guess_type(resolved.name)
        if mime_type not in SUPPORTED_IMAGE_TYPES:
            raise FalError(f"Unsupported reference image type for {resolved.name}: {mime_type}")
        encoded = base64.b64encode(resolved.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _required_string(data: dict[object, object], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise FalError(f"fal submission response is missing {key}")
        return value
