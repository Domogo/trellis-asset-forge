"""Generation workflow types and guards."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from trellis_asset_forge.domain import GenerationRequest, RemoteJob, RemoteUpdate


class Generator(Protocol):
    """Seam implemented by a remote generation adapter."""

    def submit(self, request: GenerationRequest) -> RemoteJob:
        """Submit one durable request without waiting for completion."""
        ...

    def poll(self, job: RemoteJob) -> RemoteUpdate:
        """Return the current queue state and a result URL when complete."""
        ...

    def download(self, url: str, destination: Path) -> Path:
        """Download a completed artifact to an explicit local destination."""
        ...


class CostLimitError(ValueError):
    """Raised before network activity when a batch exceeds its ceiling."""
