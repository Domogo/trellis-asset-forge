"""Command-line interface for Trellis Asset Forge."""

from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from trellis_asset_forge import __version__
from trellis_asset_forge.fal import FalError, FalGenerator
from trellis_asset_forge.forge import AssetForge
from trellis_asset_forge.generation import CostLimitError

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


@app.command("generate")
def generate_command(
    asset_id: Annotated[str, typer.Argument(help="Catalog asset identifier.")],
    workspace: Annotated[
        Path,
        typer.Option(help="Initialized Asset Forge workspace."),
    ] = Path("."),
    max_cost: Annotated[
        float,
        typer.Option(help="Hard USD ceiling for this submission batch.", min=0),
    ] = 1.0,
    media_ttl: Annotated[
        int,
        typer.Option(help="Seconds before fal-hosted input/output media expires."),
    ] = 3600,
) -> None:
    """Submit all configured variants for one asset to fal."""
    try:
        forge = AssetForge.open(workspace)
        generator = FalGenerator.from_environment(media_ttl_seconds=media_ttl)
        generations = forge.submit_asset(
            asset_id,
            generator=generator,
            max_cost_usd=Decimal(str(max_cost)),
        )
    except (CostLimitError, FalError, KeyError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    for generation in generations:
        typer.echo(
            f"Submitted {generation.generation_id} seed={generation.seed} "
            f"request={generation.request_id}"
        )
    typer.echo("Run `trellis-forge sync` until the local status is downloaded.")


@app.command("sync")
def sync_command(
    workspace: Annotated[
        Path,
        typer.Option(help="Initialized Asset Forge workspace."),
    ] = Path("."),
    media_ttl: Annotated[
        int,
        typer.Option(help="fal media lifetime used for authenticated queue requests."),
    ] = 3600,
) -> None:
    """Poll active fal jobs and immediately download completed GLBs."""
    try:
        forge = AssetForge.open(workspace)
        generator = FalGenerator.from_environment(media_ttl_seconds=media_ttl)
        generations = forge.sync(generator=generator)
    except (FalError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    if not generations:
        typer.echo("No active generations.")
        return
    for generation in generations:
        typer.echo(f"{generation.generation_id}  {generation.status}")


@app.command("generations")
def list_generations_command(
    workspace: Annotated[
        Path,
        typer.Option(help="Initialized Asset Forge workspace."),
    ] = Path("."),
    asset: Annotated[
        str | None,
        typer.Option(help="Optional catalog asset identifier."),
    ] = None,
) -> None:
    """List local candidate state without contacting fal."""
    forge = AssetForge.open(workspace)
    generations = forge.list_generations(asset)
    if not generations:
        typer.echo("No generations recorded.")
        return
    for generation in generations:
        artifact = str(generation.artifact_path) if generation.artifact_path else "-"
        typer.echo(
            f"{generation.generation_id}  {generation.asset_id}  "
            f"seed={generation.seed}  {generation.status}  {artifact}"
        )


if __name__ == "__main__":
    app()
