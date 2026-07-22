from typer.testing import CliRunner

from trellis_asset_forge import __version__
from trellis_asset_forge.cli import app


def test_version_option_reports_package_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"trellis-asset-forge {__version__}"

