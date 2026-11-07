"""Colour-based cube perception.

The detector deliberately uses classical computer vision rather than a learned
model, because the lab teaches the geometry: RGB -> HSV thresholding ->
connected components -> pixel centroid -> back-projection onto the table plane.

The same function is imported by the local episode runner and by the ROS 2
``perception_node`` wrapper, so the code a learner writes runs unchanged on both
transports.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .config import CameraIntrinsics, SceneConfig
from .render.pinhole import CameraPose, backproject_to_plane, project_point
from .sim.schema import RgbFrame

__all__ = ["Detection", "detect_cubes", "rgb_to_hsv"]

MIN_SATURATION = 0.35
MIN_VALUE = 0.12
HUE_TOLERANCE_DEG = 20.0
MIN_COMPONENT_AREA = 20


@dataclass(frozen=True)
class Detection:
    color: str
    u: float
    v: float
    area: int
    bbox: tuple[int, int, int, int]
    position: tuple[float, float, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "color": self.color,
            "pixel_centroid": [float(self.u), float(self.v)],
            "area": int(self.area),
            "bbox": [int(v) for v in self.bbox],
            "position": [float(v) for v in self.position],
        }


def _as_rgb_array(frame: RgbFrame | np.ndarray) -> np.ndarray:
    if isinstance(frame, RgbFrame):
        if frame.encoding != "rgb8":
            raise ValueError(f"unsupported encoding {frame.encoding!r}; expected rgb8")
        array = np.frombuffer(frame.data, dtype=np.uint8).reshape(frame.height, frame.width, 3)
        return array
    array = np.asarray(frame)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError(f"frame must be HxWx3 RGB, got shape {array.shape}")
    if array.dtype != np.uint8:
        raise ValueError(f"frame must be uint8, got {array.dtype}")
    return array


def rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised RGB->HSV for a float array in ``[0, 1]``; hue in degrees."""
    values = np.asarray(rgb, dtype=np.float32)
    if values.max(initial=0.0) > 1.0:
        values = values / 255.0
    red, green, blue = values[..., 0], values[..., 1], values[..., 2]
    maximum = values.max(axis=-1)
    minimum = values.min(axis=-1)
    delta = maximum - minimum
    safe_delta = np.where(delta == 0, 1.0, delta)
    safe_max = np.where(maximum == 0, 1.0, maximum)

    hue = np.zeros_like(maximum)
    red_mask = (maximum == red) & (delta > 0)
    green_mask = (maximum == green) & (delta > 0) & ~red_mask
    blue_mask = (delta > 0) & ~red_mask & ~green_mask
    hue[red_mask] = (60.0 * ((green - blue) / safe_delta))[red_mask] % 360.0
    hue[green_mask] = (60.0 * (2.0 + (blue - red) / safe_delta))[green_mask]
    hue[blue_mask] = (60.0 * (4.0 + (red - green) / safe_delta))[blue_mask]
    saturation = np.where(maximum == 0, 0.0, delta / safe_max)
    return hue, saturation, maximum


def _hue_of_rgb(rgb: Sequence[int]) -> float:
    array = np.asarray(rgb, dtype=np.float32).reshape(1, 1, 3) / 255.0
    return float(rgb_to_hsv(array)[0][0, 0])


def _resolve_target(target_color: str | Sequence[int], scene: SceneConfig) -> tuple[str, float]:
    if isinstance(target_color, str):
        return target_color, _hue_of_rgb(scene.color_rgb(target_color))
    if len(target_color) != 3:
        raise ValueError("target_color must be a palette name or an RGB triple")
    return "custom", _hue_of_rgb(target_color)


def _components(mask: np.ndarray) -> list[tuple[int, float, float, int, int, int, int]]:
    """8-connected components in deterministic raster order."""
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    found: list[tuple[int, float, float, int, int, int, int]] = []
    rows, cols = np.nonzero(mask)
    for start_row, start_col in zip(rows.tolist(), cols.tolist(), strict=True):
        if visited[start_row, start_col]:
            continue
        stack = [(start_row, start_col)]
        visited[start_row, start_col] = True
        area = 0
        sum_row = 0.0
        sum_col = 0.0
        min_row = max_row = start_row
        min_col = max_col = start_col
        while stack:
            row, col = stack.pop()
            area += 1
            sum_row += row
            sum_col += col
            if row < min_row:
                min_row = row
            elif row > max_row:
                max_row = row
            if col < min_col:
                min_col = col
            elif col > max_col:
                max_col = col
            for delta_row in (-1, 0, 1):
                for delta_col in (-1, 0, 1):
                    if delta_row == 0 and delta_col == 0:
                        continue
                    neighbour_row = row + delta_row
                    neighbour_col = col + delta_col
                    if (
                        0 <= neighbour_row < height
                        and 0 <= neighbour_col < width
                        and mask[neighbour_row, neighbour_col]
                        and not visited[neighbour_row, neighbour_col]
                    ):
                        visited[neighbour_row, neighbour_col] = True
                        stack.append((neighbour_row, neighbour_col))
        if area >= MIN_COMPONENT_AREA:
            found.append(
                (
                    area,
                    sum_row / area,
                    sum_col / area,
                    min_col,
                    min_row,
                    max_col,
                    max_row,
                )
            )
    return found


def detect_cubes(
    frame: RgbFrame | np.ndarray,
    target_color: str | Sequence[int],
    *,
    scene: SceneConfig | None = None,
    intrinsics: CameraIntrinsics | None = None,
    pose: CameraPose | None = None,
    plane_z: float | None = None,
    hue_tolerance: float = HUE_TOLERANCE_DEG,
) -> list[Detection]:
    """Detect cubes of ``target_color`` and return deterministic 3D grasp poses.

    ``frame`` may be an :class:`~isaac_starter_lab.sim.schema.RgbFrame` or an
    ``HxWx3`` uint8 NumPy array.  ``pose`` defaults to the teaching camera in
    ``SceneConfig``; the DR evaluator passes the jittered per-seed pose.
    Returns detections sorted by descending area, then pixel position.
    """
    scene = scene or SceneConfig()
    intrinsics = intrinsics or CameraIntrinsics()
    pose = pose or CameraPose.from_look_at(
        scene.camera_position, scene.camera_look_at, scene.camera_up
    )
    plane = scene.cube_center_z if plane_z is None else float(plane_z)
    color_name, target_hue = _resolve_target(target_color, scene)

    rgb = _as_rgb_array(frame)
    hue, saturation, value = rgb_to_hsv(rgb)
    distance = np.abs(hue - target_hue)
    distance = np.minimum(distance, 360.0 - distance)
    mask = (distance <= hue_tolerance) & (saturation >= MIN_SATURATION) & (value >= MIN_VALUE)

    detections: list[Detection] = []
    for area, row, col, min_col, min_row, max_col, max_row in _components(mask):
        point = backproject_to_plane(col, row, plane, pose, intrinsics)
        detections.append(
            Detection(
                color=color_name,
                u=float(col),
                v=float(row),
                area=int(area),
                bbox=(int(min_col), int(min_row), int(max_col), int(max_row)),
                position=(float(point[0]), float(point[1]), float(point[2])),
            )
        )
    detections.sort(key=lambda d: (-d.area, d.v, d.u))
    return detections


def project_detection(detection: Detection, pose: CameraPose, intrinsics: CameraIntrinsics):
    return project_point(detection.position, pose, intrinsics)


def pixel_distance(a: Detection, b: Detection) -> float:
    return math.hypot(a.u - b.u, a.v - b.v)
