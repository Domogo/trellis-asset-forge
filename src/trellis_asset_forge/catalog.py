"""SQLite-backed asset catalog."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from pydantic import TypeAdapter

from trellis_asset_forge.domain import (
    AssetRecord,
    GameSpec,
    GenerationRecord,
    GenerationRequest,
    GenerationSpec,
    GenerationStatus,
    ProcessedArtifact,
    ReferenceRecord,
    RemoteJob,
)
from trellis_asset_forge.manifest import ResolvedAsset
from trellis_asset_forge.profiles import get_profile

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    brief TEXT NOT NULL,
    topology_notes TEXT NOT NULL,
    profile TEXT NOT NULL,
    export_path TEXT NOT NULL,
    generation_json TEXT NOT NULL,
    game_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asset_references (
    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    path TEXT NOT NULL,
    view TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    PRIMARY KEY (asset_id, position)
);
CREATE TABLE IF NOT EXISTS generations (
    generation_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    variant INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    endpoint TEXT NOT NULL,
    status TEXT NOT NULL,
    request_id TEXT,
    status_url TEXT,
    response_url TEXT,
    estimated_cost_usd TEXT NOT NULL,
    request_json TEXT NOT NULL,
    artifact_path TEXT,
    remote_url TEXT,
    error TEXT,
    quality_json TEXT,
    review_notes TEXT,
    processed_json TEXT,
    promotion_manifest_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS generations_asset_id ON generations(asset_id, created_at);
"""


class Catalog:
    """Own catalog persistence behind asset-level operations."""

    def __init__(self, path: Path) -> None:
        self.path = path
        with self._connection() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    def upsert_asset(self, asset: ResolvedAsset) -> None:
        """Insert or replace one asset and its ordered reference evidence."""
        now = datetime.now(UTC).isoformat()
        spec = asset.spec
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO assets (
                    asset_id, name, category, brief, topology_notes, profile,
                    export_path, generation_json, game_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    brief = excluded.brief,
                    topology_notes = excluded.topology_notes,
                    profile = excluded.profile,
                    export_path = excluded.export_path,
                    generation_json = excluded.generation_json,
                    game_json = excluded.game_json,
                    updated_at = excluded.updated_at
                """,
                (
                    spec.id,
                    spec.name,
                    spec.category,
                    spec.brief,
                    spec.topology_notes,
                    spec.profile,
                    spec.export,
                    spec.generation.model_dump_json(),
                    spec.game.model_dump_json(),
                    now,
                    now,
                ),
            )
            connection.execute("DELETE FROM asset_references WHERE asset_id = ?", (spec.id,))
            connection.executemany(
                """
                INSERT INTO asset_references (asset_id, position, path, view, sha256)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (spec.id, position, str(reference.path), reference.view, reference.sha256)
                    for position, reference in enumerate(asset.references)
                ],
            )

    def list_assets(self) -> list[AssetRecord]:
        """Return all cataloged assets ordered by stable identifier."""
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM assets ORDER BY asset_id").fetchall()
            result: list[AssetRecord] = []
            for row in rows:
                reference_rows = connection.execute(
                    """
                    SELECT path, view, sha256 FROM asset_references
                    WHERE asset_id = ? ORDER BY position
                    """,
                    (row["asset_id"],),
                ).fetchall()
                profile = get_profile(str(row["profile"]))
                generation = GenerationSpec.model_validate_json(str(row["generation_json"]))
                game = GameSpec.model_validate_json(str(row["game_json"]))
                result.append(
                    AssetRecord(
                        asset_id=str(row["asset_id"]),
                        name=str(row["name"]),
                        category=str(row["category"]),
                        brief=str(row["brief"]),
                        topology_notes=str(row["topology_notes"]),
                        profile=profile.name,
                        triangle_budget=profile.triangle_budget,
                        texture_size=generation.texture_size or profile.texture_size,
                        export_path=str(row["export_path"]),
                        generation=generation,
                        game=game,
                        references=tuple(
                            ReferenceRecord(
                                path=Path(str(reference_row["path"])),
                                view=str(reference_row["view"]),
                                sha256=str(reference_row["sha256"]),
                            )
                            for reference_row in reference_rows
                        ),
                    )
                )
            return result

    def get_asset(self, asset_id: str) -> AssetRecord:
        """Return one asset or raise a stable lookup error."""
        for asset in self.list_assets():
            if asset.asset_id == asset_id:
                return asset
        raise KeyError(f"Unknown asset: {asset_id}")

    def create_generation(
        self,
        request: GenerationRequest,
        *,
        estimated_cost_usd: str,
    ) -> GenerationRecord:
        """Persist a planned candidate before its remote submission."""
        now = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO generations (
                    generation_id, asset_id, variant, seed, endpoint, status,
                    estimated_cost_usd, request_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'planned', ?, ?, ?, ?)
                """,
                (
                    request.generation_id,
                    request.asset_id,
                    request.variant,
                    request.seed,
                    request.endpoint,
                    estimated_cost_usd,
                    request.model_dump_json(),
                    now,
                    now,
                ),
            )
        return self.get_generation(request.generation_id)

    def mark_submitted(self, generation_id: str, remote_job: RemoteJob) -> GenerationRecord:
        """Attach remote queue coordinates to a planned generation."""
        self._update_generation(
            generation_id,
            status="submitted",
            request_id=remote_job.request_id,
            status_url=remote_job.status_url,
            response_url=remote_job.response_url,
        )
        return self.get_generation(generation_id)

    def mark_failed(self, generation_id: str, error: str) -> GenerationRecord:
        """Record a failure without losing the submitted request evidence."""
        self._update_generation(generation_id, status="failed", error=error)
        return self.get_generation(generation_id)

    def mark_running(self, generation_id: str) -> GenerationRecord:
        """Record that fal has started processing a candidate."""
        self._update_generation(generation_id, status="running")
        return self.get_generation(generation_id)

    def mark_downloaded(
        self,
        generation_id: str,
        *,
        artifact_path: Path,
        remote_url: str,
    ) -> GenerationRecord:
        """Attach the locally owned artifact immediately after download."""
        self._update_generation(
            generation_id,
            status="downloaded",
            artifact_path=str(artifact_path.resolve()),
            remote_url=remote_url,
        )
        return self.get_generation(generation_id)

    def mark_inspected(
        self, generation_id: str, quality_report_json: str
    ) -> GenerationRecord:
        """Persist measured quality evidence for a downloaded candidate."""
        self._update_generation(
            generation_id,
            status="inspected",
            quality_json=quality_report_json,
        )
        return self.get_generation(generation_id)

    def mark_reviewed(
        self,
        generation_id: str,
        *,
        status: GenerationStatus,
        notes: str,
    ) -> GenerationRecord:
        """Persist an explicit human approval or rejection decision."""
        if status not in {"approved", "rejected"}:
            raise ValueError("Review status must be approved or rejected")
        self._update_generation(
            generation_id,
            status=status,
            review_notes=notes,
        )
        return self.get_generation(generation_id)

    def mark_processed(
        self, generation_id: str, processed_artifacts_json: str
    ) -> GenerationRecord:
        """Persist the validated LOD set built from an approved candidate."""
        self._update_generation(
            generation_id,
            status="processed",
            processed_json=processed_artifacts_json,
        )
        return self.get_generation(generation_id)

    def mark_promoted(
        self, generation_id: str, promotion_manifest_path: Path
    ) -> GenerationRecord:
        """Record that an approved LOD set is now available to a game project."""
        self._update_generation(
            generation_id,
            status="promoted",
            promotion_manifest_path=str(promotion_manifest_path.resolve()),
        )
        return self.get_generation(generation_id)

    def list_generations(self, asset_id: str | None = None) -> list[GenerationRecord]:
        """Return generations in deterministic creation order."""
        query = "SELECT * FROM generations"
        parameters: tuple[str, ...] = ()
        if asset_id is not None:
            query += " WHERE asset_id = ?"
            parameters = (asset_id,)
        query += " ORDER BY created_at, variant, generation_id"
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._generation_from_row(row) for row in rows]

    def get_generation(self, generation_id: str) -> GenerationRecord:
        """Return one generation by local stable identifier."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM generations WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown generation: {generation_id}")
        return self._generation_from_row(row)

    def _update_generation(
        self,
        generation_id: str,
        *,
        status: GenerationStatus,
        request_id: str | None = None,
        status_url: str | None = None,
        response_url: str | None = None,
        error: str | None = None,
        artifact_path: str | None = None,
        remote_url: str | None = None,
        quality_json: str | None = None,
        review_notes: str | None = None,
        processed_json: str | None = None,
        promotion_manifest_path: str | None = None,
    ) -> None:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE generations SET
                    status = ?,
                    request_id = COALESCE(?, request_id),
                    status_url = COALESCE(?, status_url),
                    response_url = COALESCE(?, response_url),
                    error = COALESCE(?, error),
                    artifact_path = COALESCE(?, artifact_path),
                    remote_url = COALESCE(?, remote_url),
                    quality_json = COALESCE(?, quality_json),
                    review_notes = COALESCE(?, review_notes),
                    processed_json = COALESCE(?, processed_json),
                    promotion_manifest_path = COALESCE(?, promotion_manifest_path),
                    updated_at = ?
                WHERE generation_id = ?
                """,
                (
                    status,
                    request_id,
                    status_url,
                    response_url,
                    error,
                    artifact_path,
                    remote_url,
                    quality_json,
                    review_notes,
                    processed_json,
                    promotion_manifest_path,
                    datetime.now(UTC).isoformat(),
                    generation_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown generation: {generation_id}")

    @staticmethod
    def _generation_from_row(row: sqlite3.Row) -> GenerationRecord:
        from trellis_asset_forge.mesh_quality import MeshQualityReport

        artifact = row["artifact_path"]
        quality_json = row["quality_json"]
        processed_json = row["processed_json"]
        return GenerationRecord(
            generation_id=str(row["generation_id"]),
            asset_id=str(row["asset_id"]),
            variant=int(row["variant"]),
            seed=int(row["seed"]),
            endpoint=str(row["endpoint"]),
            status=cast(GenerationStatus, str(row["status"])),
            request_id=str(row["request_id"]) if row["request_id"] is not None else None,
            status_url=str(row["status_url"]) if row["status_url"] is not None else None,
            response_url=(
                str(row["response_url"]) if row["response_url"] is not None else None
            ),
            estimated_cost_usd=Decimal(str(row["estimated_cost_usd"])),
            artifact_path=Path(str(artifact)) if artifact is not None else None,
            remote_url=str(row["remote_url"]) if row["remote_url"] is not None else None,
            error=str(row["error"]) if row["error"] is not None else None,
            quality_report=(
                MeshQualityReport.model_validate_json(str(quality_json))
                if quality_json is not None
                else None
            ),
            review_notes=(
                str(row["review_notes"]) if row["review_notes"] is not None else None
            ),
            processed_artifacts=(
                TypeAdapter(tuple[ProcessedArtifact, ...]).validate_json(
                    str(processed_json)
                )
                if processed_json is not None
                else ()
            ),
            promotion_manifest_path=(
                Path(str(row["promotion_manifest_path"]))
                if row["promotion_manifest_path"] is not None
                else None
            ),
        )

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        """Apply additive catalog migrations for pre-release workspaces."""
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(generations)").fetchall()
        }
        if "quality_json" not in columns:
            connection.execute("ALTER TABLE generations ADD COLUMN quality_json TEXT")
        if "review_notes" not in columns:
            connection.execute("ALTER TABLE generations ADD COLUMN review_notes TEXT")
        if "processed_json" not in columns:
            connection.execute("ALTER TABLE generations ADD COLUMN processed_json TEXT")
        if "promotion_manifest_path" not in columns:
            connection.execute(
                "ALTER TABLE generations ADD COLUMN promotion_manifest_path TEXT"
            )
        asset_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(assets)").fetchall()
        }
        if "game_json" not in asset_columns:
            connection.execute(
                "ALTER TABLE assets ADD COLUMN game_json TEXT NOT NULL "
                "DEFAULT '{\"scale_meters\":1.0,\"pivot\":\"base-center\","
                "\"collision\":\"convex\"}'"
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()
