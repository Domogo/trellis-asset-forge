from pathlib import Path

import pytest
from typer.testing import CliRunner

from trellis_asset_forge import __version__
from trellis_asset_forge.cli import app
from trellis_asset_forge.domain import GenerationRequest, RemoteJob, RemoteUpdate
from trellis_asset_forge.forge import AssetForge


class CliGenerator:
    def submit(self, request: GenerationRequest) -> RemoteJob:
        return RemoteJob(
            request_id=f"remote-{request.variant}",
            status_url=f"https://queue.example/{request.variant}/status",
            response_url=f"https://queue.example/{request.variant}",
        )

    def poll(self, job: RemoteJob) -> RemoteUpdate:
        return RemoteUpdate(
            status="completed", result_url=f"https://media.example/{job.request_id}.glb"
        )

    def download(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"generated")
        return destination


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


def test_generate_command_fails_cleanly_without_server_side_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)
    AssetForge.initialize(tmp_path)

    result = CliRunner().invoke(
        app,
        ["generate", "props.crate", "--workspace", str(tmp_path), "--max-cost", "1.00"],
    )

    assert result.exit_code == 1
    assert "FAL_KEY is not set" in result.stderr


def test_cli_generates_syncs_and_lists_catalog_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    references:
      - path: crate.png
    generation:
      variants: 1
      resolution: 512
      seed: 5
    export: props/crate.glb
""".strip()
        + "\n"
    )
    forge = AssetForge.initialize(tmp_path)
    forge.import_manifest(manifest)
    generator = CliGenerator()
    monkeypatch.setattr(
        "trellis_asset_forge.cli.FalGenerator.from_environment",
        lambda **_: generator,
    )
    runner = CliRunner()

    generated = runner.invoke(
        app,
        ["generate", "props.crate", "--workspace", str(tmp_path), "--max-cost", "0.25"],
    )
    active = runner.invoke(app, ["generations", "--workspace", str(tmp_path)])
    synced = runner.invoke(app, ["sync", "--workspace", str(tmp_path)])
    downloaded = runner.invoke(app, ["generations", "--workspace", str(tmp_path)])
    generated_all = runner.invoke(
        app,
        ["generate-all", "--workspace", str(tmp_path), "--max-cost", "0.25"],
    )

    assert generated.exit_code == 0
    assert "Submitted" in generated.stdout
    assert "submitted" in active.stdout
    assert synced.exit_code == 0
    assert "downloaded" in synced.stdout
    assert "downloaded" in downloaded.stdout
    assert generated_all.exit_code == 0
    assert "Submitted 1 candidates" in generated_all.stdout


def test_review_command_is_always_bound_to_loopback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    AssetForge.initialize(tmp_path)
    observed: dict[str, object] = {}

    def fake_run(app: object, **options: object) -> None:
        observed.update(options)

    monkeypatch.setattr("trellis_asset_forge.cli.uvicorn.run", fake_run)

    result = CliRunner().invoke(
        app, ["review", "--workspace", str(tmp_path), "--port", "9876"]
    )

    assert result.exit_code == 0
    assert "http://127.0.0.1:9876" in result.stdout
    assert observed["host"] == "127.0.0.1"
    assert observed["port"] == 9876
