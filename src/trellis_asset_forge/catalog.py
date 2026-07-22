"""SQLite-backed asset catalog."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from trellis_asset_forge.domain import AssetRecord, GenerationSpec, ReferenceRecord
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
"""


class Catalog:
    """Own catalog persistence behind asset-level operations."""

    def __init__(self, path: Path) -> None:
        self.path = path
        with self._connection() as connection:
            connection.executescript(SCHEMA)

    def upsert_asset(self, asset: ResolvedAsset) -> None:
        """Insert or replace one asset and its ordered reference evidence."""
        now = datetime.now(UTC).isoformat()
        spec = asset.spec
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO assets (
                    asset_id, name, category, brief, topology_notes, profile,
                    export_path, generation_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    brief = excluded.brief,
                    topology_notes = excluded.topology_notes,
                    profile = excluded.profile,
                    export_path = excluded.export_path,
                    generation_json = excluded.generation_json,
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

