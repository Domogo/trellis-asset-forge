from pathlib import Path

import trimesh

from trellis_asset_forge.mesh_quality import inspect_glb
from trellis_asset_forge.profiles import get_profile


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

