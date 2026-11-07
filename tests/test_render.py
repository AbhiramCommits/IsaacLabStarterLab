"""Pinhole camera geometry and software-renderer tests."""

from __future__ import annotations

import numpy as np
import pytest

from isaac_starter_lab.config import CameraIntrinsics, SceneConfig
from isaac_starter_lab.render.pinhole import (
    CameraPose,
    backproject_to_plane,
    project_point,
    render_scene,
    unproject_pixel,
)
from isaac_starter_lab.scene.build_scene import sample_cube_layout


def default_pose() -> CameraPose:
    cfg = SceneConfig()
    return CameraPose.from_look_at(cfg.camera_position, cfg.camera_look_at, cfg.camera_up)


def test_intrinsics_are_the_usd_camera_values():
    intr = CameraIntrinsics()
    assert intr.fx == pytest.approx(24.0 * 640 / 36.0)
    assert intr.fy == intr.fx
    assert intr.cx == 319.5
    assert intr.cy == 239.5
    assert intr.vertical_aperture_mm == pytest.approx(27.0)
    assert intr.fovx_deg == pytest.approx(73.739795, rel=1e-6)


def test_projection_center_maps_to_principal_point():
    intr = CameraIntrinsics()
    pose = CameraPose.from_look_at((0, 0, 1), (0, 0, 0), (0, 1, 0))
    u, v, depth = project_point((0, 0, 0), pose, intr)
    assert (u, v) == pytest.approx((intr.cx, intr.cy))
    assert depth == pytest.approx(1.0)


def test_project_backproject_round_trip():
    intr = CameraIntrinsics()
    pose = default_pose()
    plane = SceneConfig().cube_center_z
    for u, v in ((320.0, 240.0), (100.0, 400.0), (600.0, 400.0), (319.5, 239.5)):
        point = backproject_to_plane(u, v, plane, pose, intr)
        assert point[2] == pytest.approx(plane)
        recovered = project_point(point, pose, intr)
        assert recovered[0] == pytest.approx(u, abs=1e-6)
        assert recovered[1] == pytest.approx(v, abs=1e-6)
        assert recovered[2] > 0


def test_round_trip_3d_error_under_one_micrometre():
    intr = CameraIntrinsics()
    pose = default_pose()
    cfg = SceneConfig()
    for placement in sample_cube_layout(cfg, 7):
        u, v, _ = project_point(placement.position, pose, intr)
        recovered = backproject_to_plane(u, v, cfg.cube_center_z, pose, intr)
        assert np.linalg.norm(recovered - np.asarray(placement.position)) < 1e-6


def test_ray_behind_plane_is_rejected():
    intr = CameraIntrinsics()
    pose = default_pose()
    with pytest.raises(ValueError):
        backproject_to_plane(320, 240, 2.0, pose, intr)


def test_unproject_returns_unit_vector():
    direction = unproject_pixel(320, 240, default_pose(), CameraIntrinsics())
    assert np.linalg.norm(direction) == pytest.approx(1.0)


def test_rendered_frame_shape_and_dtype():
    cfg = SceneConfig()
    cubes = [(p.position, p.rgb) for p in sample_cube_layout(cfg, 7)]
    image = render_scene(cubes, cfg, CameraIntrinsics())
    assert image.shape == (480, 640, 3)
    assert image.dtype == np.uint8
    # The scene is not a blank frame: table, bin and five coloured cubes exist.
    assert len(np.unique(image.reshape(-1, 3), axis=0)) > 10


def test_isolated_cube_centroid_within_one_pixel():
    cfg = SceneConfig(n_cubes=1)
    placement = sample_cube_layout(cfg, 7)[0]
    image, ids = render_scene(
        [(placement.position, placement.rgb)], cfg, CameraIntrinsics(), return_ids=True
    )
    mask = ids == 2
    rows, cols = np.nonzero(mask)
    assert len(cols) > 200
    u, v, _ = project_point(placement.position, default_pose(), CameraIntrinsics())
    assert abs(cols.mean() - u) < 1.0
    assert abs(rows.mean() - v) < 1.0
    # The cube's own pixels carry its palette colour, not the table grey.
    red, green, blue = image[mask].mean(axis=0)
    assert red > green and red > blue


def test_bin_and_table_have_distinct_ids():
    cfg = SceneConfig()
    cubes = [(p.position, p.rgb) for p in sample_cube_layout(cfg, 7)]
    _, ids = render_scene(cubes, cfg, CameraIntrinsics(), return_ids=True)
    assert set(np.unique(ids)) == {-1, 0, 1, 2, 3, 4, 5, 6}


def test_camera_pose_dict_round_trip():
    pose = default_pose()
    recovered = CameraPose.from_dict(pose.to_dict())
    assert np.allclose(recovered.position, pose.position)
    assert np.allclose(recovered.rotation, pose.rotation)


def test_invalid_camera_geometry():
    with pytest.raises(ValueError):
        CameraPose.from_look_at((0, 0, 0), (0, 0, 0))
    with pytest.raises(ValueError):
        CameraPose.from_look_at((0, 0, 1), (0, 0, 0), (0, 0, 1))
