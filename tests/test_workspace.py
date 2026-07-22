from pathlib import Path

from trellis_asset_forge.workspace import Workspace


def test_workspace_initialization_is_local_and_idempotent(tmp_path: Path) -> None:
    first = Workspace.initialize(tmp_path, export_root="game-assets")
    second = Workspace.initialize(tmp_path, export_root="ignored-on-reopen")

    assert first == second
    assert first.root == tmp_path.resolve()
    assert first.export_root == (tmp_path / "game-assets").resolve()
    assert first.catalog_path.is_file()
    assert first.artifacts_dir.is_dir()
    assert first.config_path.read_text().startswith("version = 1\n")

