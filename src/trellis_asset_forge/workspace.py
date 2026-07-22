"""Workspace discovery and local storage configuration."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(ValueError):
    """Raised when a workspace cannot be opened safely."""


@dataclass(frozen=True, slots=True)
class Workspace:
    """Resolved paths owned by an Asset Forge workspace."""

    root: Path
    config_path: Path
    private_dir: Path
    catalog_path: Path
    artifacts_dir: Path
    export_root: Path

    @classmethod
    def initialize(cls, root: Path, *, export_root: str = "game-assets") -> Workspace:
        """Create or reopen a workspace rooted at ``root``."""
        resolved_root = root.expanduser().resolve()
        config_path = resolved_root / "asset-forge.toml"
        if config_path.exists():
            return cls.open(resolved_root)

        private_dir = resolved_root / ".asset-forge"
        artifacts_dir = private_dir / "artifacts"
        catalog_path = private_dir / "catalog.sqlite3"
        resolved_root.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        catalog_path.touch(exist_ok=True)

        config = (
            "version = 1\n\n"
            "[paths]\n"
            f"catalog = {json.dumps('.asset-forge/catalog.sqlite3')}\n"
            f"artifacts = {json.dumps('.asset-forge/artifacts')}\n"
            f"export = {json.dumps(export_root)}\n"
        )
        config_path.write_text(config)
        return cls.open(resolved_root)

    @classmethod
    def open(cls, root: Path) -> Workspace:
        """Open and validate an existing workspace."""
        resolved_root = root.expanduser().resolve()
        config_path = resolved_root / "asset-forge.toml"
        if not config_path.is_file():
            raise WorkspaceError(f"No asset-forge.toml found in {resolved_root}")

        with config_path.open("rb") as handle:
            config = tomllib.load(handle)
        if config.get("version") != 1:
            raise WorkspaceError("Unsupported workspace configuration version")
        paths = config.get("paths")
        if not isinstance(paths, dict):
            raise WorkspaceError("Workspace configuration is missing [paths]")

        private_dir = resolved_root / ".asset-forge"
        catalog_path = cls._resolve_config_path(resolved_root, paths, "catalog")
        artifacts_dir = cls._resolve_config_path(resolved_root, paths, "artifacts")
        export_path = cls._resolve_config_path(resolved_root, paths, "export")
        private_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.touch(exist_ok=True)
        return cls(
            root=resolved_root,
            config_path=config_path,
            private_dir=private_dir,
            catalog_path=catalog_path,
            artifacts_dir=artifacts_dir,
            export_root=export_path,
        )

    @staticmethod
    def _resolve_config_path(root: Path, paths: dict[object, object], key: str) -> Path:
        raw_value = paths.get(key)
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise WorkspaceError(f"Workspace path {key!r} must be a non-empty string")
        configured = Path(raw_value).expanduser()
        return (configured if configured.is_absolute() else root / configured).resolve()

