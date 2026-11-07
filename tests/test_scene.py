"""Scene construction, determinism and camera round-trip tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pxr import Usd, UsdGeom, UsdPhysics

from isaac_starter_lab.config import CameraIntrinsics, SceneConfig
from isaac_starter_lab.scene.build_scene import (
    SceneSamplingError,
    build_stage,
    sample_cube_layout,
)
from isaac_starter_lab.scene.hashing import stage_hash, stage_hash_from_file

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PRIMS = {
    "/World": UsdGeom.Xform,
    "/World/Table": UsdGeom.Cube,
    "/World/Bin": UsdGeom.Xform,
    "/World/Bin/Wall_north": UsdGeom.Cube,
    "/World/Bin/Wall_south": UsdGeom.Cube,
    "/World/Bin/Wall_east": UsdGeom.Cube,
    "/World/Bin/Wall_west": UsdGeom.Cube,
    "/World/Cubes": UsdGeom.Xform,
    "/World/Cubes/Cube_00": UsdGeom.Cube,
    "/World/Cubes/Cube_04": UsdGeom.Cube,
    "/World/Robot": UsdGeom.Xform,
    "/World/Robot/base": UsdGeom.Xform,
    "/World/Robot/base/link0": UsdGeom.Xform,
    "/World/Robot/base/link0/link1": UsdGeom.Xform,
    "/World/Robot/base/link0/link1/link2": UsdGeom.Xform,
    "/World/Robot/base/link0/link1/link2/wrist": UsdGeom.Xform,
    "/World/Robot/base/link0/link1/link2/wrist/gripper": UsdGeom.Xform,
    "/World/Camera": UsdGeom.Camera,
    "/World/Lights/DomeLight": UsdGeom.Xformable,
    "/World/Robot/Joints/joint_base_yaw": UsdPhysics.RevoluteJoint,
    "/World/Robot/Joints/joint_wrist_roll": UsdPhysics.RevoluteJoint,
}


@pytest.fixture(scope="module")
def stage7():
    return build_stage(SceneConfig(), 7)


def test_same_seed_same_hash():
    assert stage_hash(build_stage(SceneConfig(), 7)) == stage_hash(build_stage(SceneConfig(), 7))


def test_different_seeds_different_hashes():
    hashes = {stage_hash(build_stage(SceneConfig(), seed)) for seed in (0, 1, 7, 8)}
    assert len(hashes) == 4


def test_stage_metadata(stage7):
    assert UsdGeom.GetStageUpAxis(stage7) == UsdGeom.Tokens.z
    assert UsdGeom.GetStageMetersPerUnit(stage7) == 1.0
    assert stage7.GetDefaultPrim().GetPath() == "/World"


@pytest.mark.parametrize("path,schema", sorted(EXPECTED_PRIMS.items()))
def test_expected_prim_path_and_type(stage7, path, schema):
    prim = stage7.GetPrimAtPath(path)
    assert prim.IsValid(), f"missing prim {path}"
    assert prim.IsA(schema), f"{path} is {prim.GetTypeName()}, expected {schema}"


def test_physics_apis_and_bin_aabb(stage7):
    table = stage7.GetPrimAtPath("/World/Table")
    assert table.HasAPI(UsdPhysics.CollisionAPI)
    for index in range(5):
        prim = stage7.GetPrimAtPath(f"/World/Cubes/Cube_{index:02d}")
        assert prim.HasAPI(UsdPhysics.RigidBodyAPI)
        assert prim.HasAPI(UsdPhysics.MassAPI)
        assert prim.HasAPI(UsdPhysics.CollisionAPI)
        assert prim.GetAttribute("primvars:displayColor").Get()
    aabb = stage7.GetPrimAtPath("/World/Bin").GetAttribute("lab:aabb").Get()
    assert len(aabb) == 6
    assert aabb[3] > aabb[0] and aabb[4] > aabb[1] and aabb[5] > aabb[2]


def test_cubes_are_inside_table_and_do_not_overlap(stage7):
    cfg = SceneConfig()
    positions = []
    for index in range(cfg.n_cubes):
        prim = stage7.GetPrimAtPath(f"/World/Cubes/Cube_{index:02d}")
        translate = prim.GetAttribute("xformOp:translate").Get()
        positions.append((translate[0], translate[1], translate[2]))
        half = cfg.cube_size / 2
        (lo_x, lo_y, lo_z), (hi_x, hi_y, hi_z) = cfg.table_aabb
        assert lo_x <= translate[0] - half
        assert translate[0] + half <= hi_x
        assert lo_y <= translate[1] - half
        assert translate[1] + half <= hi_y
        assert translate[2] - half >= lo_z - 1e-9
        assert translate[2] + half <= hi_z + cfg.cube_size

    for i, a in enumerate(positions):
        for b in positions[i + 1 :]:
            separation = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
            assert separation >= cfg.cube_size - 1e-9


def test_camera_intrinsics_round_trip(stage7):
    camera = UsdGeom.Camera(stage7.GetPrimAtPath("/World/Camera"))
    intrinsics = CameraIntrinsics(
        width=640,
        height=480,
        focal_length_mm=camera.GetFocalLengthAttr().Get(),
        horizontal_aperture_mm=camera.GetHorizontalApertureAttr().Get(),
    )
    expected = CameraIntrinsics()
    assert intrinsics.focal_length_mm == expected.focal_length_mm
    assert intrinsics.horizontal_aperture_mm == expected.horizontal_aperture_mm
    assert intrinsics.fx == pytest.approx(expected.fx)
    assert intrinsics.fy == pytest.approx(expected.fy)
    assert intrinsics.cx == pytest.approx(319.5)
    assert intrinsics.cy == pytest.approx(239.5)
    assert camera.GetVerticalApertureAttr().Get() == pytest.approx(27.0)


def test_committed_scene_matches_pinned_hash():
    expected = json.loads((ROOT / "usd" / "EXPECTED_HASHES.json").read_text())
    entry = expected["scenes"]["tabletop_seed7"]
    path = ROOT / "usd" / entry["file"]
    assert path.exists()
    assert stage_hash_from_file(path) == entry["hash"]
    assert stage_hash(build_stage(SceneConfig(), 7)) == entry["hash"]
    assert len(list(Usd.Stage.Open(str(path)).Traverse())) == entry["prim_count"]


def test_documentation_and_comments_do_not_change_hash():
    stage = build_stage(SceneConfig(), 7)
    base = stage_hash(stage)
    stage.GetPrimAtPath("/World").SetDocumentation("a timestamp-free comment")
    stage.GetRootLayer().comment = "layer level comment"
    assert stage_hash(stage) == base


def test_sampling_is_deterministic_and_colour_unique():
    cfg = SceneConfig()
    first = sample_cube_layout(cfg, 7)
    second = sample_cube_layout(cfg, 7)
    assert first == second
    assert len({p.color_name for p in first}) == cfg.n_cubes
    assert len({p.name for p in first}) == cfg.n_cubes


def test_rejection_sampling_exhaustion_is_loud():
    cfg = SceneConfig(
        n_cubes=5,
        placement_aabb=((-0.05, -0.05, 0.75), (0.05, 0.05, 0.75)),
    )
    with pytest.raises(SceneSamplingError, match="could not place 5 cubes"):
        sample_cube_layout(cfg, 7)


def test_invalid_configs_are_rejected():
    with pytest.raises(ValueError):
        CameraIntrinsics(width=0)
    with pytest.raises(ValueError):
        SceneConfig(n_cubes=0)
    with pytest.raises(ValueError):
        SceneConfig(cube_size=0.5)
    with pytest.raises(ValueError):
        SceneConfig(
            table_aabb=((-0.1, -0.1, 0.7), (0.1, 0.1, 0.7)),
        )


def test_scene_hash_independent_of_export_path(tmp_path):
    stage = build_stage(SceneConfig(), 7)
    out = tmp_path / "scene.usda"
    stage.GetRootLayer().Export(str(out))
    assert stage_hash_from_file(out) == stage_hash(stage)
