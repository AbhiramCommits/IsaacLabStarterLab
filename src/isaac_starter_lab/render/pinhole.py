"""Software pinhole renderer for the CPU lab track.

This module is a deliberate stand-in for Isaac Sim's RTX renderer.  It uses the
**same** :class:`~isaac_starter_lab.config.CameraIntrinsics` derived from
``/World/Camera`` (24 mm focal length, 36 mm horizontal aperture, 640x480) and
the **same** RGB/label schema the GPU track emits, but it is pure NumPy: every
pixel casts a ray against axis-aligned boxes and the table plane, then applies
flat dome lighting.  There is no shadow map, no anti-aliasing and no material
model beyond diffuse colour.

If you change the camera in the USD stage, change ``CameraIntrinsics`` here too;
the round-trip test in ``tests/test_render.py`` enforces that the projection and
back-projection helpers agree with the USD attributes.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from ..config import CameraIntrinsics, SceneConfig

__all__ = [
    "CameraPose",
    "backproject_to_plane",
    "project_point",
    "render_scene",
    "unproject_pixel",
]

SKY_COLOR = (198, 204, 214)
LIGHT_DIRECTION = np.asarray([0.3, 0.4, 0.85], dtype=np.float32)
LIGHT_DIRECTION /= np.linalg.norm(LIGHT_DIRECTION)


@dataclass(frozen=True)
class CameraPose:
    """World-to-camera extrinsics in computer-vision convention.

    ``rotation`` rows are the camera's right, down and forward axes expressed in
    world coordinates, so ``camera_xyz = rotation @ (world_xyz - position)``.
    """

    position: np.ndarray
    rotation: np.ndarray
    look_at: np.ndarray
    up: np.ndarray

    @classmethod
    def from_look_at(
        cls,
        position: Sequence[float],
        look_at: Sequence[float],
        up: Sequence[float] = (0.0, 0.0, 1.0),
    ) -> CameraPose:
        eye = np.asarray(position, dtype=float)
        target = np.asarray(look_at, dtype=float)
        up_vec = np.asarray(up, dtype=float)
        forward = target - eye
        norm = np.linalg.norm(forward)
        if norm < 1e-12:
            raise ValueError("camera position and look_at must differ")
        forward = forward / norm
        right = np.cross(forward, up_vec)
        right_norm = np.linalg.norm(right)
        if right_norm < 1e-12:
            raise ValueError("camera up vector is parallel to the view direction")
        right = right / right_norm
        down = np.cross(forward, right)
        rotation = np.vstack([right, down, forward])
        return cls(position=eye, rotation=rotation, look_at=target, up=up_vec)

    def to_dict(self) -> dict[str, object]:
        return {
            "position": [float(v) for v in self.position],
            "look_at": [float(v) for v in self.look_at],
            "up": [float(v) for v in self.up],
            "rotation": [[float(v) for v in row] for row in self.rotation],
        }

    @classmethod
    def from_dict(cls, data: dict) -> CameraPose:
        return cls(
            position=np.asarray(data["position"], dtype=float),
            rotation=np.asarray(data["rotation"], dtype=float),
            look_at=np.asarray(data["look_at"], dtype=float),
            up=np.asarray(data.get("up", (0.0, 0.0, 1.0)), dtype=float),
        )


def project_point(
    point: Sequence[float],
    pose: CameraPose,
    intrinsics: CameraIntrinsics,
) -> tuple[float, float, float]:
    """Project a world point to ``(u, v, depth)``; NaNs when behind the camera."""
    p = np.asarray(point, dtype=float)
    camera = pose.rotation @ (p - pose.position)
    if camera[2] <= 1e-9:
        return (math.nan, math.nan, float(camera[2]))
    u = intrinsics.fx * camera[0] / camera[2] + intrinsics.cx
    v = intrinsics.fy * camera[1] / camera[2] + intrinsics.cy
    return (float(u), float(v), float(camera[2]))


def unproject_pixel(
    u: float,
    v: float,
    pose: CameraPose,
    intrinsics: CameraIntrinsics,
) -> np.ndarray:
    """Return the unit world-space ray direction through pixel ``(u, v)``."""
    camera_dir = np.asarray(
        [(u - intrinsics.cx) / intrinsics.fx, (v - intrinsics.cy) / intrinsics.fy, 1.0]
    )
    world_dir = pose.rotation.T @ camera_dir
    return world_dir / np.linalg.norm(world_dir)


def backproject_to_plane(
    u: float,
    v: float,
    plane_z: float,
    pose: CameraPose,
    intrinsics: CameraIntrinsics,
) -> np.ndarray:
    """Intersect the pixel ray with the horizontal plane ``z = plane_z``."""
    direction = unproject_pixel(u, v, pose, intrinsics)
    if abs(direction[2]) < 1e-9:
        raise ValueError("pixel ray is parallel to the target plane")
    distance = (plane_z - pose.position[2]) / direction[2]
    if distance <= 0:
        raise ValueError("target plane is behind the camera")
    return pose.position + distance * direction


def _box_intersection(
    origin: np.ndarray,
    directions: np.ndarray,
    low: np.ndarray,
    high: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Slab intersection for every ray; returns t_entry, hit mask and entry axis."""
    with np.errstate(divide="ignore", invalid="ignore"):
        t0 = (low - origin) / directions
        t1 = (high - origin) / directions
    t_near = np.minimum(t0, t1)
    t_far = np.maximum(t0, t1)
    t_entry = np.max(t_near, axis=-1)
    t_exit = np.min(t_far, axis=-1)
    hit = (t_exit >= np.maximum(t_entry, 0.0)) & (t_entry > 1e-5)
    axis = np.argmax(
        np.where(np.isfinite(t_near), t_near, -np.inf), axis=-1
    )
    return t_entry, hit, axis


def _shade(
    base_color: np.ndarray,
    normal: np.ndarray,
    light_intensity: float,
) -> np.ndarray:
    diffuse = np.clip(np.sum(normal * LIGHT_DIRECTION, axis=-1), 0.0, 1.0)
    brightness = (0.38 + 0.62 * diffuse) * float(light_intensity)
    return np.clip(base_color * brightness[..., None], 0.0, 1.0)


def _table_boxes(scene: SceneConfig) -> list[tuple[np.ndarray, np.ndarray, tuple[int, int, int], int]]:
    """Return the four bin walls as ``(low, high, rgb, id)`` boxes."""
    (lo_x, lo_y, lo_z), (hi_x, hi_y, hi_z) = scene.bin_aabb
    t = scene.bin_wall_thickness
    walls = [
        ((lo_x, hi_y - t, lo_z), (hi_x, hi_y, hi_z)),
        ((lo_x, lo_y, lo_z), (hi_x, lo_y + t, hi_z)),
        ((hi_x - t, lo_y, lo_z), (hi_x, hi_y, hi_z)),
        ((lo_x, lo_y, lo_z), (lo_x + t, hi_y, hi_z)),
    ]
    return [
        (np.asarray(low, dtype=np.float32), np.asarray(high, dtype=np.float32), scene.bin_color, 1)
        for low, high in walls
    ]


def _screen_bbox(
    low: np.ndarray,
    high: np.ndarray,
    pose: CameraPose,
    intrinsics: CameraIntrinsics,
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    corners = np.asarray(
        [
            [x, y, z]
            for x in (low[0], high[0])
            for y in (low[1], high[1])
            for z in (low[2], high[2])
        ],
        dtype=float,
    )
    camera = (corners - pose.position) @ pose.rotation.T
    if np.all(camera[:, 2] <= 1e-6):
        return None
    if np.any(camera[:, 2] <= 1e-6):
        return (0, 0, width, height)
    u = intrinsics.fx * camera[:, 0] / camera[:, 2] + intrinsics.cx
    v = intrinsics.fy * camera[:, 1] / camera[:, 2] + intrinsics.cy
    x0 = max(0, int(math.floor(u.min())) - 1)
    x1 = min(width, int(math.ceil(u.max())) + 2)
    y0 = max(0, int(math.floor(v.min())) - 1)
    y1 = min(height, int(math.ceil(v.max())) + 2)
    if x0 >= x1 or y0 >= y1:
        return None
    return (x0, y0, x1, y1)


def render_scene(
    cubes: Sequence[tuple[Sequence[float], Sequence[int]]],
    scene: SceneConfig,
    intrinsics: CameraIntrinsics,
    camera_position: Sequence[float] | None = None,
    look_at: Sequence[float] | None = None,
    table_color: Sequence[int] | None = None,
    light_intensity: float | None = None,
    return_ids: bool = False,
):
    """Ray-cast the scene to a ``(height, width, 3)`` uint8 RGB array.

    ``cubes`` is a sequence of ``(centre_xyz, rgb)`` pairs.  When ``return_ids``
    is true the result is ``(image, id_buffer)`` where the id buffer contains
    ``-1`` for background, ``0`` for the table, ``1`` for bin walls and
    ``2 + index`` for each cube.  Ground-truth visibility uses this buffer.

    Boxes are only tested inside their projected screen-space bounding box, which
    keeps a 640x480 frame in the low tens of milliseconds on a CPU.
    """
    pose = CameraPose.from_look_at(
        camera_position or scene.camera_position,
        look_at or scene.camera_look_at,
        scene.camera_up,
    )
    width, height = intrinsics.width, intrinsics.height
    xs = np.arange(width, dtype=np.float32)
    ys = np.arange(height, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(xs, ys)
    camera_dirs = np.stack(
        [
            (grid_x - intrinsics.cx) / intrinsics.fx,
            (grid_y - intrinsics.cy) / intrinsics.fy,
            np.ones_like(grid_x),
        ],
        axis=-1,
    )
    directions = camera_dirs @ pose.rotation.astype(np.float32)
    directions /= np.linalg.norm(directions, axis=-1, keepdims=True)

    table = np.asarray(
        table_color if table_color is not None else scene.table_color, dtype=np.float32
    ) / 255.0
    intensity = scene.light_intensity if light_intensity is None else light_intensity
    origin = pose.position.astype(np.float32)

    colour = np.empty((height, width, 3), dtype=np.float32)
    colour[:] = np.asarray(SKY_COLOR, dtype=np.float32) / 255.0
    ids = np.full((height, width), -1, dtype=np.int16)
    best_t = np.full((height, width), np.inf, dtype=np.float32)

    # Table top plane, clipped to the table AABB.
    with np.errstate(divide="ignore", invalid="ignore"):
        t_plane = (scene.table_top - pose.position[2]) / directions[..., 2]
    hit_x = pose.position[0] + t_plane * directions[..., 0]
    hit_y = pose.position[1] + t_plane * directions[..., 1]
    (tlo_x, tlo_y, _), (thi_x, thi_y, _) = scene.table_aabb
    plane_hit = (
        (directions[..., 2] < 0)
        & (t_plane > 1e-5)
        & (hit_x >= tlo_x)
        & (hit_x <= thi_x)
        & (hit_y >= tlo_y)
        & (hit_y <= thi_y)
    )
    update = plane_hit & (t_plane < best_t)
    table_up = np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
    table_pixel = _shade(table, table_up, intensity)
    colour[update] = table_pixel
    best_t = np.where(update, t_plane, best_t)
    ids[update] = 0

    boxes: list[tuple[np.ndarray, np.ndarray, Sequence[int], int]] = _table_boxes(scene)
    half = scene.cube_size / 2.0
    for index, (centre, rgb) in enumerate(cubes):
        centre_array = np.asarray(centre, dtype=np.float32)
        boxes.append((centre_array - half, centre_array + half, rgb, 2 + index))

    for low, high, rgb, object_id in boxes:
        bbox = _screen_bbox(low, high, pose, intrinsics, width, height)
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        sub_directions = directions[y0:y1, x0:x1]
        t_entry, hit, axis = _box_intersection(origin, sub_directions, low, high)
        update = hit & (t_entry < best_t[y0:y1, x0:x1])
        if not np.any(update):
            continue
        rows, cols = np.nonzero(update)
        axes = axis[rows, cols]
        normal = np.zeros((rows.size, 3), dtype=np.float32)
        normal[np.arange(rows.size), axes] = -np.sign(sub_directions[rows, cols, axes])
        base_color = np.asarray(rgb, dtype=np.float32) / 255.0
        shaded = _shade(base_color, normal, intensity)
        colour[y0 + rows, x0 + cols] = shaded
        best_t[y0 + rows, x0 + cols] = t_entry[rows, cols]
        ids[y0 + rows, x0 + cols] = object_id

    image = np.clip(colour * 255.0 + 0.5, 0, 255).astype(np.uint8)
    if return_ids:
        return image, ids
    return image
