"""Command-line interface for Trellis Asset Forge."""

from pathlib import Path
from typing import Annotated

import typer

from trellis_asset_forge import __version__
from trellis_asset_forge.forge import AssetForge

app = typer.Typer(
    name="trellis-forge",
    help="Catalog, generate, review, and promote game-ready 3D assets.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"trellis-asset-forge {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the installed version and exit.",
        ),
    ] = None,
) -> None:
    """Run Trellis Asset Forge."""


@app.command("init")
def initialize_workspace(
    directory: Annotated[
        Path,
        typer.Argument(help="Directory that will own the catalog and exports."),
    ] = Path("."),
    export_root: Annotated[
        str,
        typer.Option(help="Export directory, relative to the workspace unless absolute."),
    ] = "game-assets",
) -> None:
    """Initialize a local Asset Forge workspace."""
    forge = AssetForge.initialize(directory, export_root=export_root)
    typer.echo(f"Workspace ready: {forge.workspace.root}")
    typer.echo(f"Catalog: {forge.workspace.catalog_path}")
    typer.echo(f"Export root: {forge.workspace.export_root}")


@app.command("import")
def import_manifest_command(
    manifest: Annotated[Path, typer.Argument(help="Version 1 YAML asset manifest.")],
    workspace: Annotated[
        Path,
        typer.Option(help="Initialized Asset Forge workspace."),
    ] = Path("."),
) -> None:
    """Validate and catalog an asset manifest without generating anything."""
    forge = AssetForge.open(workspace)
    result = forge.import_manifest(manifest)
    typer.echo(
        f"Imported {result.assets_imported} assets and planned "
        f"{result.generations_planned} generations (${result.estimated_cost_usd:.2f} estimated)."
    )


@app.command("assets")
def list_assets_command(
    workspace: Annotated[
        Path,
        typer.Option(help="Initialized Asset Forge workspace."),
    ] = Path("."),
) -> None:
    """List cataloged assets and their active game profile."""
    forge = AssetForge.open(workspace)
    assets = forge.list_assets()
    if not assets:
        typer.echo("No assets cataloged.")
        return
    for asset in assets:
        typer.echo(
            f"{asset.asset_id}  {asset.name}  {asset.profile}  "
            f"{asset.triangle_budget:,} tris  {len(asset.references)} refs"
        )


if __name__ == "__main__":
    app()
