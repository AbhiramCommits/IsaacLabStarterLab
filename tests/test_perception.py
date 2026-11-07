"""Perception tests on rendered frames with known ground truth."""

from __future__ import annotations

import math

import numpy as np
import pytest

from isaac_starter_lab.config import CameraIntrinsics, SceneConfig
from isaac_starter_lab.perception import detect_cubes, rgb_to_hsv
from isaac_starter_lab.render.pinhole import CameraPose, project_point, render_scene
from isaac_starter_lab.scene.build_scene import sample_cube_layout
from isaac_starter_lab.sim.schema import RgbFrame


def _frame(cfg: SceneConfig) -> tuple[np.ndarray, tuple, CameraPose, CameraIntrinsics]:
    placements = sample_cube_layout(cfg, 7)
    image = render_scene([(p.position, p.rgb) for p in placements], cfg, CameraIntrinsics())
    pose = CameraPose.from_look_at(cfg.camera_position, cfg.camera_look_at, cfg.camera_up)
    return image, placements, pose, CameraIntrinsics()


def test_rgb_to_hsv_known_values():
    rgb = np.asarray([[[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0]]], dtype=np.float32)
    hue, saturation, value = rgb_to_hsv(rgb / 255.0)
    assert hue[0, 0] == pytest.approx(0.0)
    assert hue[0, 1] == pytest.approx(120.0)
    assert hue[0, 2] == pytest.approx(240.0)
    assert hue[0, 3] == pytest.approx(60.0)
    assert saturation.max() == pytest.approx(1.0)
    assert value.min() == pytest.approx(1.0)


def test_detects_every_palette_colour_once():
    cfg = SceneConfig()
    image, placements, pose, intrinsics = _frame(cfg)
    for placement in placements:
        detections = detect_cubes(image, placement.color_name, pose=pose, intrinsics=intrinsics)
        assert len(detections) == 1, placement.color_name
        detection = detections[0]
        assert detection.area >= 20
        assert detection.position[2] == pytest.approx(cfg.cube_center_z)


def test_isolated_cube_pixel_error_below_one_pixel():
    cfg = SceneConfig(n_cubes=1)
    image, placements, pose, intrinsics = _frame(cfg)
    placement = placements[0]
    detection = detect_cubes(image, placement.color_name, pose=pose, intrinsics=intrinsics)[0]
    u, v, _ = project_point(placement.position, pose, intrinsics)
    assert math.hypot(detection.u - u, detection.v - v) < 1.0
    assert np.linalg.norm(np.asarray(detection.position) - np.asarray(placement.position)) < 0.005


def test_detection_is_deterministic_and_sorted():
    cfg = SceneConfig()
    image, placements, pose, intrinsics = _frame(cfg)
    first = detect_cubes(image, "green", pose=pose, intrinsics=intrinsics)
    second = detect_cubes(image, "green", pose=pose, intrinsics=intrinsics)
    assert [d.to_dict() for d in first] == [d.to_dict() for d in second]
    assert first == sorted(first, key=lambda d: (-d.area, d.v, d.u))


def test_rgb_frame_and_array_inputs_agree():
    cfg = SceneConfig()
    image, placements, pose, intrinsics = _frame(cfg)
    frame = RgbFrame(stamp=0.0, width=640, height=480, encoding="rgb8", data=image.tobytes())
    from_array = detect_cubes(image, placements[0].color_name, pose=pose, intrinsics=intrinsics)
    from_message = detect_cubes(frame, placements[0].color_name, pose=pose, intrinsics=intrinsics)
    assert [d.to_dict() for d in from_array] == [d.to_dict() for d in from_message]


def test_rgb_triple_target():
    cfg = SceneConfig(n_cubes=1)
    image, placements, pose, intrinsics = _frame(cfg)
    placement = placements[0]
    detections = detect_cubes(
        image, placement.rgb, pose=pose, intrinsics=intrinsics
    )
    assert len(detections) == 1


def test_low_saturation_table_is_not_detected():
    cfg = SceneConfig()
    image, _, pose, intrinsics = _frame(cfg)
    detections = detect_cubes(
        image, cfg.table_color, pose=pose, intrinsics=intrinsics, hue_tolerance=5.0
    )
    assert detections == []


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        detect_cubes(np.zeros((10, 10), dtype=np.uint8), "red")
    with pytest.raises(ValueError):
        detect_cubes(np.zeros((10, 10, 3), dtype=np.float32), "red")
    with pytest.raises(KeyError):
        detect_cubes(np.zeros((10, 10, 3), dtype=np.uint8), "not_a_colour")


def test_backprojection_uses_custom_plane():
    cfg = SceneConfig(n_cubes=1)
    image, placements, pose, intrinsics = _frame(cfg)
    placement = placements[0]
    detection = detect_cubes(
        image, placement.color_name, pose=pose, intrinsics=intrinsics, plane_z=0.9
    )[0]
    assert detection.position[2] == pytest.approx(0.9)
