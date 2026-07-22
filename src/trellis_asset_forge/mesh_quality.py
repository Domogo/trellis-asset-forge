"""Deterministic, engine-neutral inspection of generated GLB meshes."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Literal

import numpy as np
import trimesh
from pydantic import BaseModel, ConfigDict

from trellis_asset_forge.profiles import GameProfile


class QualityIssue(BaseModel):
    """One actionable mesh-quality finding."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["error", "warning"]
    message: str


class MeshQualityReport(BaseModel):
    """Measured topology evidence evaluated against a game profile."""

    model_config = ConfigDict(frozen=True)

    path: Path
    file_size_bytes: int
    triangles: int
    vertices: int
    components: int
    degenerate_faces: int
    boundary_edges: int
    non_manifold_edges: int
    materials: int
    textures: int
    watertight: bool
    bounds: tuple[float, float, float]
    issues: tuple[QualityIssue, ...]
    passed: bool


def inspect_glb(path: Path, profile: GameProfile) -> MeshQualityReport:
    """Load one GLB, measure its topology, and enforce the selected profile."""
    resolved = path.resolve()
    if resolved.suffix.lower() != ".glb":
        raise ValueError(f"Expected a .glb artifact: {resolved}")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)

    scene = trimesh.load(resolved, force="scene", process=False)
    if not isinstance(scene, trimesh.Scene) or not scene.geometry:
        raise ValueError(f"GLB contains no mesh geometry: {resolved}")
    mesh = scene.to_geometry()
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise ValueError(f"GLB contains no triangle mesh: {resolved}")

    faces = np.asarray(mesh.faces, dtype=np.int64)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    triangles = int(faces.shape[0])
    vertex_count = int(vertices.shape[0])
    degenerate_faces = _count_degenerate_faces(faces, vertices)
    topology_faces, topology_vertex_count = _weld_attribute_seams(faces, vertices)
    boundary_edges, non_manifold_edges = _edge_defects(topology_faces)
    components = _component_count(topology_faces, topology_vertex_count)
    materials, textures = _material_counts(resolved, scene)
    extents = np.asarray(mesh.extents, dtype=np.float64)
    bounds = tuple(float(value) for value in extents)

    issues: list[QualityIssue] = []
    if triangles > profile.triangle_budget:
        issues.append(
            QualityIssue(
                code="triangle-budget",
                severity="error",
                message=(
                    f"{triangles:,} triangles exceed the {profile.name} budget of "
                    f"{profile.triangle_budget:,}."
                ),
            )
        )
    if components > profile.max_components:
        issues.append(
            QualityIssue(
                code="component-budget",
                severity="error",
                message=(
                    f"{components} connected components exceed the profile limit of "
                    f"{profile.max_components}."
                ),
            )
        )
    if degenerate_faces:
        issues.append(
            QualityIssue(
                code="degenerate-faces",
                severity="error",
                message=f"Mesh contains {degenerate_faces} zero-area or collapsed faces.",
            )
        )
    if non_manifold_edges:
        issues.append(
            QualityIssue(
                code="non-manifold-edges",
                severity="error",
                message=f"Mesh contains {non_manifold_edges} non-manifold edges.",
            )
        )
    if boundary_edges:
        issues.append(
            QualityIssue(
                code="open-boundaries",
                severity="warning",
                message=f"Mesh contains {boundary_edges} open boundary edges.",
            )
        )
    if materials > profile.max_materials:
        issues.append(
            QualityIssue(
                code="material-budget",
                severity="error",
                message=(
                    f"{materials} materials exceed the profile limit of "
                    f"{profile.max_materials}."
                ),
            )
        )
    if textures == 0:
        issues.append(
            QualityIssue(
                code="missing-textures",
                severity="warning",
                message="No embedded PBR texture maps were detected.",
            )
        )
    if extents.shape != (3,) or not np.all(np.isfinite(extents)) or np.any(extents <= 0):
        issues.append(
            QualityIssue(
                code="invalid-bounds",
                severity="error",
                message="Mesh bounds must be finite and non-zero on all three axes.",
            )
        )

    return MeshQualityReport(
        path=resolved,
        file_size_bytes=resolved.stat().st_size,
        triangles=triangles,
        vertices=vertex_count,
        components=components,
        degenerate_faces=degenerate_faces,
        boundary_edges=boundary_edges,
        non_manifold_edges=non_manifold_edges,
        materials=materials,
        textures=textures,
        watertight=boundary_edges == 0 and non_manifold_edges == 0,
        bounds=bounds,  # type: ignore[arg-type]
        issues=tuple(issues),
        passed=not any(issue.severity == "error" for issue in issues),
    )


def _count_degenerate_faces(faces: np.ndarray, vertices: np.ndarray) -> int:
    repeated = (
        (faces[:, 0] == faces[:, 1])
        | (faces[:, 1] == faces[:, 2])
        | (faces[:, 2] == faces[:, 0])
    )
    first = vertices[faces[:, 1]] - vertices[faces[:, 0]]
    second = vertices[faces[:, 2]] - vertices[faces[:, 0]]
    doubled_areas = np.linalg.norm(np.cross(first, second), axis=1)
    return int(np.count_nonzero(repeated | (doubled_areas <= 1e-12)))


def _edge_defects(faces: np.ndarray) -> tuple[int, int]:
    edges = np.concatenate(
        (faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]), axis=0
    )
    edges.sort(axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int(np.count_nonzero(counts == 1)), int(np.count_nonzero(counts > 2))


def _weld_attribute_seams(
    faces: np.ndarray, vertices: np.ndarray
) -> tuple[np.ndarray, int]:
    """Remap coincident positions before evaluating geometric connectivity.

    glTF must duplicate a vertex when UVs, normals, tangents, colors, or material
    boundaries differ. Those render vertices are not disconnected geometry and
    must not inflate component or open-boundary evidence.
    """
    if vertices.size == 0 or not np.all(np.isfinite(vertices)):
        return faces, int(vertices.shape[0])
    extents = np.ptp(vertices, axis=0)
    scale = float(np.max(extents))
    if scale <= 0.0:
        return faces, int(vertices.shape[0])
    tolerance = max(scale * 1e-7, 1e-12)
    quantized = np.rint((vertices - np.min(vertices, axis=0)) / tolerance).astype(
        np.int64
    )
    _, inverse = np.unique(quantized, axis=0, return_inverse=True)
    remapped = inverse[faces]
    return np.asarray(remapped, dtype=np.int64), int(np.max(inverse)) + 1


def _component_count(faces: np.ndarray, vertex_count: int) -> int:
    """Count face-connected components without an optional scipy dependency."""
    parent = np.arange(vertex_count, dtype=np.int64)

    def find(item: int) -> int:
        while int(parent[item]) != item:
            parent[item] = parent[int(parent[item])]
            item = int(parent[item])
        return item

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    used: set[int] = set()
    for first, second, third in faces:
        a, b, c = int(first), int(second), int(third)
        used.update((a, b, c))
        union(a, b)
        union(b, c)
    return len({find(item) for item in used})


def _material_counts(path: Path, scene: trimesh.Scene) -> tuple[int, int]:
    declared = _glb_declared_material_counts(path)
    if declared is not None:
        return declared

    materials: set[int] = set()
    textures: set[int] = set()
    texture_fields = (
        "baseColorTexture",
        "emissiveTexture",
        "metallicRoughnessTexture",
        "normalTexture",
        "occlusionTexture",
        "image",
    )
    for geometry in scene.geometry.values():
        material = getattr(geometry.visual, "material", None)
        if material is None:
            continue
        materials.add(id(material))
        for field in texture_fields:
            texture = getattr(material, field, None)
            if texture is not None:
                textures.add(id(texture))
    return len(materials), len(textures)


def _glb_declared_material_counts(path: Path) -> tuple[int, int] | None:
    """Read standard glTF catalog counts from the JSON chunk of a GLB."""
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) != 12:
            return None
        magic, version, _ = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2:
            return None
        while chunk_header := handle.read(8):
            if len(chunk_header) != 8:
                return None
            chunk_length, chunk_type = struct.unpack("<II", chunk_header)
            payload = handle.read(chunk_length)
            if len(payload) != chunk_length:
                return None
            if chunk_type != 0x4E4F534A:
                continue
            try:
                document = json.loads(payload.rstrip(b" \t\r\n\x00"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None
            if not isinstance(document, dict):
                return None
            materials = document.get("materials", [])
            textures = document.get("textures", [])
            if not isinstance(materials, list) or not isinstance(textures, list):
                return None
            return len(materials), len(textures)
    return None
