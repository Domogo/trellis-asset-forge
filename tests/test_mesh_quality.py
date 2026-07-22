from pathlib import Path

import numpy as np
import trimesh

from trellis_asset_forge.mesh_quality import inspect_glb
from trellis_asset_forge.profiles import GameProfile, get_profile


def test_inspection_measures_topology_against_game_profile(tmp_path: Path) -> None:
    source = tmp_path / "box.glb"
    source.write_bytes(trimesh.creation.box().export(file_type="glb"))

    report = inspect_glb(source, get_profile("mobile-prop"))

    assert report.passed is True
    assert report.triangles == 12
    assert report.vertices == 8
    assert report.components == 1
    assert report.degenerate_faces == 0
    assert report.boundary_edges == 0
    assert report.non_manifold_edges == 0
    assert report.watertight is True
    assert report.bounds == (1.0, 1.0, 1.0)
    assert {issue.code for issue in report.issues} == {"missing-textures"}


def test_inspection_fails_budget_component_and_open_surface_gates(tmp_path: Path) -> None:
    first = trimesh.creation.box()
    second = trimesh.creation.box(
        transform=trimesh.transformations.translation_matrix([2, 0, 0])
    )
    combined = trimesh.util.concatenate((first, second))
    source = tmp_path / "two-boxes.glb"
    source.write_bytes(combined.export(file_type="glb"))
    strict = GameProfile(
        name="test",
        triangle_budget=4,
        candidate_vertex_target=2,
        texture_size=1024,
        max_materials=2,
        max_components=1,
        lod_ratios=(1.0,),
    )

    report = inspect_glb(source, strict)

    assert report.passed is False
    assert {issue.code for issue in report.issues} >= {
        "triangle-budget",
        "component-budget",
    }

    plane = tmp_path / "plane.glb"
    plane.write_bytes(
        trimesh.Trimesh(
            vertices=np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]]),
            faces=np.array([[0, 1, 2]]),
            process=False,
        ).export(file_type="glb")
    )
    plane_report = inspect_glb(plane, get_profile("mobile-prop"))
    assert "open-boundaries" in {issue.code for issue in plane_report.issues}
    assert "invalid-bounds" in {issue.code for issue in plane_report.issues}


def test_inspection_detects_degenerate_and_non_manifold_topology(tmp_path: Path) -> None:
    source = tmp_path / "broken.glb"
    mesh = trimesh.Trimesh(
        vertices=np.array(
            [
                [0, 0, 0],
                [1, 0, 0],
                [0, 1, 0],
                [0, -1, 0],
                [0, 0, 1],
            ]
        ),
        faces=np.array(
            [
                [0, 1, 2],
                [1, 0, 3],
                [0, 1, 4],
                [0, 0, 2],
            ]
        ),
        process=False,
    )
    source.write_bytes(mesh.export(file_type="glb"))

    report = inspect_glb(source, get_profile("mobile-prop"))

    assert report.degenerate_faces == 1
    assert report.non_manifold_edges >= 1
    assert {issue.code for issue in report.issues} >= {
        "degenerate-faces",
        "non-manifold-edges",
    }
