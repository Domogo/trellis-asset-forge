"""Manifest loading and reference resolution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from trellis_asset_forge.domain import AssetManifest, AssetSpec, ReferenceRecord


class ManifestError(ValueError):
    """Raised when a manifest or one of its references is invalid."""


@dataclass(frozen=True, slots=True)
class ResolvedAsset:
    """Validated asset specification paired with local reference evidence."""

    spec: AssetSpec
    references: tuple[ReferenceRecord, ...]


@dataclass(frozen=True, slots=True)
class ResolvedManifest:
    """Validated manifest with all paths resolved relative to its file."""

    manifest: AssetManifest
    assets: tuple[ResolvedAsset, ...]


def load_manifest(path: Path) -> ResolvedManifest:
    """Load YAML, validate its schema, and hash every reference."""
    manifest_path = path.expanduser().resolve()
    if not manifest_path.is_file():
        raise ManifestError(f"Manifest not found: {manifest_path}")
    try:
        raw: Any = yaml.safe_load(manifest_path.read_text())
        manifest = AssetManifest.model_validate(raw)
    except (yaml.YAMLError, ValueError) as error:
        raise ManifestError(f"Invalid manifest {manifest_path}: {error}") from error

    resolved_assets: list[ResolvedAsset] = []
    for asset in manifest.assets:
        references: list[ReferenceRecord] = []
        for reference in asset.references:
            configured = Path(reference.path).expanduser()
            reference_path = (
                configured if configured.is_absolute() else manifest_path.parent / configured
            ).resolve()
            if not reference_path.is_file():
                raise ManifestError(f"Reference not found for {asset.id}: {reference_path}")
            references.append(
                ReferenceRecord(
                    path=reference_path,
                    view=reference.view,
                    sha256=_sha256(reference_path),
                )
            )
        resolved_assets.append(ResolvedAsset(spec=asset, references=tuple(references)))
    return ResolvedManifest(manifest=manifest, assets=tuple(resolved_assets))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

