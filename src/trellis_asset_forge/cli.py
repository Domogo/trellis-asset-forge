"""Command-line interface for Trellis Asset Forge."""

from typing import Annotated

import typer

from trellis_asset_forge import __version__

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


if __name__ == "__main__":
    app()

