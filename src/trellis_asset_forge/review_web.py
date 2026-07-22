"""Loopback-only human review workspace for generated candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from trellis_asset_forge.forge import AssetForge


def create_review_app(workspace: Path) -> FastAPI:
    """Create a local review app bound to one initialized workspace."""
    forge = AssetForge.open(workspace)
    templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
    app = FastAPI(
        title="Trellis Asset Forge Review",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def context(request: Request, *, error: str | None = None) -> dict[str, object]:
        assets = forge.list_assets()
        generations = forge.list_generations()
        return {
            "request": request,
            "assets": assets,
            "generations": generations,
            "error": error,
        }

    def redirect() -> RedirectResponse:
        return RedirectResponse(url="/", status_code=303)

    @app.get("/")
    def dashboard(request: Request) -> object:
        return templates.TemplateResponse(request, "review.html", context(request))

    @app.get("/generations/{generation_id}/model.glb")
    def model(generation_id: str) -> FileResponse:
        try:
            generation = forge.catalog.get_generation(generation_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        artifact = generation.artifact_path
        if artifact is None or not artifact.is_file():
            raise HTTPException(status_code=404, detail="Candidate has no local artifact")
        return FileResponse(artifact, media_type="model/gltf-binary", filename="model.glb")

    @app.post("/generations/{generation_id}/inspect")
    def inspect(generation_id: str) -> RedirectResponse:
        try:
            forge.inspect_generation(generation_id)
        except (KeyError, OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return redirect()

    @app.post("/generations/{generation_id}/approve")
    def approve(
        generation_id: str,
        notes: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        try:
            forge.approve_generation(generation_id, notes=notes)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return redirect()

    @app.post("/generations/{generation_id}/reject")
    def reject(
        generation_id: str,
        notes: Annotated[str, Form()],
    ) -> RedirectResponse:
        try:
            forge.reject_generation(generation_id, notes=notes)
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return redirect()

    return app
