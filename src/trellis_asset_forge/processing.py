"""Game-ready mesh optimization behind a replaceable processor interface."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from trellis_asset_forge.domain import ProcessedArtifact
from trellis_asset_forge.mesh_quality import inspect_glb
from trellis_asset_forge.profiles import GameProfile


class ProcessingError(RuntimeError):
    """Raised when an approved mesh cannot be optimized safely."""


class MeshProcessor(Protocol):
    """Boundary for an interchangeable local mesh optimization tool."""

    def process(
        self,
        source: Path,
        destination_dir: Path,
        profile: GameProfile,
    ) -> tuple[ProcessedArtifact, ...]: ...


class GltfpackProcessor:
    """Build optimized GLB LODs with meshoptimizer's gltfpack executable."""

    def __init__(self, executable: Path | str = "gltfpack") -> None:
        raw = str(executable)
        resolved = shutil.which(raw)
        if resolved is None and Path(raw).is_file():
            resolved = str(Path(raw).resolve())
        if resolved is None:
            raise ProcessingError(
                "gltfpack was not found; install meshoptimizer or pass --gltfpack PATH"
            )
        self.executable = Path(resolved)

    def process(
        self,
        source: Path,
        destination_dir: Path,
        profile: GameProfile,
    ) -> tuple[ProcessedArtifact, ...]:
        """Optimize LOD0 and simplify the remaining declared profile LODs."""
        resolved_source = source.resolve()
        if not resolved_source.is_file():
            raise ProcessingError(f"Source artifact does not exist: {resolved_source}")
        destination_dir.mkdir(parents=True, exist_ok=True)
        artifacts: list[ProcessedArtifact] = []
        for lod, ratio in enumerate(profile.lod_ratios):
            destination = destination_dir / f"lod{lod}.glb"
            temporary = destination_dir / f".lod{lod}.part.glb"
            command = [
                str(self.executable),
                "-i",
                str(resolved_source),
                "-o",
                str(temporary),
                "-si",
                str(ratio),
                "-kn",
                "-km",
                "-ke",
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ProcessingError(f"gltfpack failed for LOD{lod}: {error}") from error
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()
                raise ProcessingError(
                    f"gltfpack failed for LOD{lod} with exit {completed.returncode}: {detail}"
                )
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise ProcessingError(f"gltfpack produced no GLB for LOD{lod}")
            os.replace(temporary, destination)
            report = inspect_glb(destination, profile)
            if not report.passed:
                codes = ", ".join(
                    issue.code for issue in report.issues if issue.severity == "error"
                )
                raise ProcessingError(f"LOD{lod} failed quality gates: {codes}")
            artifacts.append(
                ProcessedArtifact(
                    lod=lod,
                    ratio=ratio,
                    path=destination.resolve(),
                    sha256=_sha256(destination),
                    quality_report=report,
                )
            )
        return tuple(artifacts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
