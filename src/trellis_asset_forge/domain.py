"""Validated domain models shared by manifests and workflows."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from trellis_asset_forge.mesh_quality import MeshQualityReport
from trellis_asset_forge.models import (
    DEFAULT_MODEL,
    HUNYUAN_MODELS,
    MESHY_MODEL,
    FalModel,
    hunyuan_view_field,
)
from trellis_asset_forge.profiles import PROFILES

ASSET_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class ReferenceSpec(BaseModel):
    """A named image view used to condition generation."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    view: str = Field(default="reference", min_length=1, max_length=40)


class GenerationSpec(BaseModel):
    """Image-to-3D model selection and generation controls."""

    model_config = ConfigDict(extra="forbid")

    model: FalModel = DEFAULT_MODEL
    resolution: Literal[512, 1024, 1536] = 1024
    variants: int = Field(default=1, ge=1, le=20)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    texture_size: Literal[1024, 2048, 4096] | None = None
    decimation_target: int | None = Field(default=None, ge=5_000, le=500_000)
    remesh: bool = True
    unit_cost_usd: Decimal | None = Field(default=None, gt=0)


class GameSpec(BaseModel):
    """Engine-neutral import policy promoted with a finished asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scale_meters: float = Field(default=1.0, gt=0, le=10_000)
    pivot: Literal["source", "center", "base-center"] = "base-center"
    collision: Literal["none", "convex", "trimesh"] = "convex"


class AssetSpec(BaseModel):
    """One planned asset and its game-readiness policy."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    brief: str = Field(default="", max_length=2_000)
    topology_notes: str = Field(default="", max_length=2_000)
    profile: str = "desktop-prop"
    references: list[ReferenceSpec] = Field(min_length=1, max_length=12)
    generation: GenerationSpec = Field(default_factory=GenerationSpec)
    game: GameSpec = Field(default_factory=GameSpec)
    export: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def validate_asset_id(cls, value: str) -> str:
        if not ASSET_ID_PATTERN.fullmatch(value):
            raise ValueError("must contain lowercase letters/numbers separated by '.', '_' or '-'")
        return value

    @field_validator("profile")
    @classmethod
    def validate_profile(cls, value: str) -> str:
        if value not in PROFILES:
            raise ValueError(f"must be one of: {', '.join(sorted(PROFILES))}")
        return value

    @field_validator("export")
    @classmethod
    def validate_export_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("must be a relative path beneath the workspace export root")
        if path.suffix.lower() != ".glb":
            raise ValueError("must end in .glb")
        return path.as_posix()

    @model_validator(mode="after")
    def validate_model_references(self) -> AssetSpec:
        model = self.generation.model
        if model == MESHY_MODEL and len(self.references) != 1:
            raise ValueError("Meshy v6 image-to-3D requires exactly one reference")
        if model not in HUNYUAN_MODELS:
            return self

        fields: set[str] = set()
        for reference in self.references[1:]:
            field = hunyuan_view_field(model, reference.view)
            if field is None:
                raise ValueError(
                    f"unsupported Hunyuan reference view {reference.view!r} for {model}"
                )
            if field in fields:
                raise ValueError(f"duplicate Hunyuan reference view {reference.view!r}")
            fields.add(field)
        return self


class AssetManifest(BaseModel):
    """Versioned collection of project-independent asset plans."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    project: str = Field(min_length=1, max_length=120)
    assets: list[AssetSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_asset_ids(self) -> AssetManifest:
        ids = [asset.id for asset in self.assets]
        duplicates = sorted({asset_id for asset_id in ids if ids.count(asset_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate asset ids: {', '.join(duplicates)}")
        return self


class ReferenceRecord(BaseModel):
    """Resolved and content-addressed reference image."""

    model_config = ConfigDict(frozen=True)

    path: Path
    view: str
    sha256: str


class AssetRecord(BaseModel):
    """Catalog representation returned to callers."""

    model_config = ConfigDict(frozen=True)

    asset_id: str
    name: str
    category: str
    brief: str
    topology_notes: str
    profile: str
    triangle_budget: int
    texture_size: int
    export_path: str
    generation: GenerationSpec
    game: GameSpec
    references: tuple[ReferenceRecord, ...]


class ImportResult(BaseModel):
    """Observable result of importing a manifest."""

    model_config = ConfigDict(frozen=True)

    project: str
    assets_imported: int
    generations_planned: int
    estimated_cost_usd: Decimal


class GenerationRequest(BaseModel):
    """Complete, reproducible request passed to a remote generator adapter."""

    model_config = ConfigDict(frozen=True)

    generation_id: str
    asset_id: str
    variant: int = Field(ge=0)
    seed: int = Field(ge=0, le=2_147_483_647)
    endpoint: str
    references: tuple[Path, ...]
    reference_views: tuple[str, ...] = ()
    resolution: Literal[512, 1024, 1536]
    texture_size: Literal[1024, 2048, 4096]
    decimation_target: int = Field(ge=5_000, le=500_000)
    remesh: bool

    @model_validator(mode="after")
    def validate_reference_views(self) -> GenerationRequest:
        if self.reference_views and len(self.reference_views) != len(self.references):
            raise ValueError("reference_views must match references")
        return self


class RemoteJob(BaseModel):
    """Durable queue coordinates returned by a generator adapter."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    status_url: str
    response_url: str


class RemoteUpdate(BaseModel):
    """Provider-neutral observation of a queued remote job."""

    model_config = ConfigDict(frozen=True)

    status: Literal["queued", "running", "completed", "failed"]
    result_url: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> RemoteUpdate:
        if self.status == "completed" and not self.result_url:
            raise ValueError("completed remote jobs require a result URL")
        return self


GenerationStatus = Literal[
    "planned",
    "submitted",
    "running",
    "downloaded",
    "failed",
    "inspected",
    "approved",
    "rejected",
    "processed",
    "promoted",
]


class ProcessedArtifact(BaseModel):
    """One immutable, measured LOD produced from an approved candidate."""

    model_config = ConfigDict(frozen=True)

    lod: int = Field(ge=0)
    ratio: float = Field(gt=0, le=1)
    path: Path
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    quality_report: MeshQualityReport


class GenerationRecord(BaseModel):
    """Locally durable state for one generated candidate."""

    model_config = ConfigDict(frozen=True)

    generation_id: str
    asset_id: str
    variant: int
    seed: int
    endpoint: str
    status: GenerationStatus
    request_id: str | None = None
    status_url: str | None = None
    response_url: str | None = None
    estimated_cost_usd: Decimal
    artifact_path: Path | None = None
    remote_url: str | None = None
    error: str | None = None
    quality_report: MeshQualityReport | None = None
    review_notes: str | None = None
    processed_artifacts: tuple[ProcessedArtifact, ...] = ()
    promotion_manifest_path: Path | None = None
