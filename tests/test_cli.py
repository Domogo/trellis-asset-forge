from pathlib import Path

from typer.testing import CliRunner

from trellis_asset_forge import __version__
from trellis_asset_forge.cli import app


def test_version_option_reports_package_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"trellis-asset-forge {__version__}"


def test_init_command_creates_a_reopenable_workspace(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["init", str(tmp_path), "--export-root", "exports"],
    )

    assert result.exit_code == 0
    assert "Workspace ready" in result.stdout
    assert (tmp_path / "asset-forge.toml").is_file()
    assert (tmp_path / ".asset-forge" / "catalog.sqlite3").is_file()


def test_import_and_assets_commands_report_the_plan(tmp_path: Path) -> None:
    reference = tmp_path / "crate.png"
    reference.write_bytes(b"reference")
    manifest = tmp_path / "assets.yaml"
    manifest.write_text(
        """
version: 1
project: demo
assets:
  - id: props.crate
    name: Crate
    category: props
    profile: mobile-prop
    references:
      - path: crate.png
    generation:
      variants: 2
      resolution: 512
    export: props/crate.glb
""".strip()
        + "\n"
    )
    runner = CliRunner()
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0

    imported = runner.invoke(
        app,
        ["import", str(manifest), "--workspace", str(tmp_path)],
    )
    assets = runner.invoke(app, ["assets", "--workspace", str(tmp_path)])

    assert imported.exit_code == 0
    assert "2 generations" in imported.stdout
    assert "$0.50 estimated" in imported.stdout
    assert assets.exit_code == 0
    assert "props.crate" in assets.stdout
    assert "20,000 tris" in assets.stdout
