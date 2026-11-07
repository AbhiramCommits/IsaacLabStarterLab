"""Frozen configuration objects shared by every backend.

All geometry is expressed in metres in a Z-up world.  The table top is the
plane ``z = 0.75``; cube centres rest at ``table_top + cube_size / 2``.

The values below are the single source of truth used by the USD scene builder,
the CPU kinematic simulator, the software renderer and the Isaac Sim adapter,
so a frame rendered by the CPU path and a frame rendered by Isaac Sim share the
same camera intrinsics and the same artifact layout.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

LAB_SEED = 7

#: (name, (r, g, b)) ordered so hue separation is at least 50 degrees.
DEFAULT_PALETTE: tuple[tuple[str, tuple[int, int, int]], ...] = (
    ("red", (220, 30, 30)),
    ("green", (30, 180, 60)),
    ("blue", (40, 80, 220)),
    ("yellow", (230, 200, 20)),
    ("magenta", (200, 40, 200)),
)


def _as_xyz(value: Sequence[float], label: str) -> tuple[float, float, float]:
    if len(value) != 3:
        raise ValueError(f"{label} must have exactly 3 components, got {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))


@dataclass(frozen=True)
class CameraIntrinsics:
    """Pinhole camera intrinsics derived from a real USD ``UsdGeom.Camera``.

    ``fx``/``fy`` are in pixels and are derived from the focal length and the
    horizontal aperture exactly the way USD's ``UsdGeom.Camera`` defines them
    for a horizontally fitted sensor with square pixels.
    """

    width: int = 640
    height: int = 480
    focal_length_mm: float = 24.0
    horizontal_aperture_mm: float = 36.0

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("camera width and height must be positive")
        if self.focal_length_mm <= 0 or self.horizontal_aperture_mm <= 0:
            raise ValueError("focal length and aperture must be positive")

    @property
    def vertical_aperture_mm(self) -> float:
        """Vertical aperture matching the image aspect ratio (square pixels)."""
        return self.horizontal_aperture_mm * self.height / self.width

    @property
    def fx(self) -> float:
        return self.focal_length_mm * self.width / self.horizontal_aperture_mm

    @property
    def fy(self) -> float:
        # Square pixels: same focal length in pixel units on both axes.
        return self.fx

    @property
    def cx(self) -> float:
        return (self.width - 1) / 2.0

    @property
    def cy(self) -> float:
        return (self.height - 1) / 2.0

    @property
    def fovx_deg(self) -> float:
        import math

        return math.degrees(2.0 * math.atan(self.horizontal_aperture_mm / (2.0 * self.focal_length_mm)))

    def to_dict(self) -> dict[str, float | int]:
        return {
            "width": self.width,
            "height": self.height,
            "focal_length_mm": self.focal_length_mm,
            "horizontal_aperture_mm": self.horizontal_aperture_mm,
            "vertical_aperture_mm": self.vertical_aperture_mm,
            "fx": self.fx,
            "fy": self.fy,
            "cx": self.cx,
            "cy": self.cy,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> CameraIntrinsics:
        return cls(
            width=int(data["width"]),
            height=int(data["height"]),
            focal_length_mm=float(data["focal_length_mm"]),
            horizontal_aperture_mm=float(data["horizontal_aperture_mm"]),
        )


@dataclass(frozen=True)
class SceneConfig:
    """Tabletop scene description.

    ``table_aabb`` and ``bin_aabb`` are ``(min_xyz, max_xyz)`` pairs.  Cubes are
    sampled inside ``placement_aabb`` (a rectangle on the table top), which is
    deliberately smaller than the table so every cube is fully supported.
    """

    table_aabb: tuple[tuple[float, float, float], tuple[float, float, float]] = (
        (-0.55, -0.45, 0.71),
        (0.55, 0.45, 0.75),
    )
    bin_aabb: tuple[tuple[float, float, float], tuple[float, float, float]] = (
        (0.13, 0.02, 0.75),
        (0.37, 0.26, 0.83),
    )
    placement_aabb: tuple[tuple[float, float, float], tuple[float, float, float]] = (
        (-0.22, -0.12, 0.75),
        (0.22, 0.10, 0.75),
    )
    n_cubes: int = 5
    cube_size: float = 0.05
    palette: tuple[tuple[str, tuple[int, int, int]], ...] = DEFAULT_PALETTE
    table_color: tuple[int, int, int] = (120, 120, 125)
    bin_color: tuple[int, int, int] = (70, 74, 80)
    camera_position: tuple[float, float, float] = (0.0, -0.68, 1.02)
    camera_look_at: tuple[float, float, float] = (0.02, 0.02, 0.77)
    camera_up: tuple[float, float, float] = (0.0, 0.0, 1.0)
    light_intensity: float = 1.0
    cube_margin: float = 0.006
    bin_wall_thickness: float = 0.012

    def __post_init__(self) -> None:
        if self.n_cubes < 1:
            raise ValueError("n_cubes must be >= 1")
        if not 0.0 < self.cube_size < 0.2:
            raise ValueError("cube_size must be in (0, 0.2) metres")
        if self.light_intensity < 0:
            raise ValueError("light_intensity must be >= 0")
        if len(self.palette) < self.n_cubes:
            raise ValueError("palette must contain at least n_cubes distinct colours")
        for label, aabb in (("table_aabb", self.table_aabb), ("bin_aabb", self.bin_aabb)):
            lo, hi = aabb
            if any(high <= low for low, high in zip(lo, hi, strict=True)):
                raise ValueError(f"{label} must have min < max on every axis")
        lo, hi = self.placement_aabb
        tlo, thi = self.table_aabb
        if any(low < tlo_ or high > thi_ for low, high, tlo_, thi_ in zip(lo, hi, tlo, thi, strict=True)):
            raise ValueError("placement_aabb must lie inside table_aabb")

    @property
    def table_top(self) -> float:
        return self.table_aabb[1][2]

    @property
    def cube_center_z(self) -> float:
        return self.table_top + self.cube_size / 2.0

    @property
    def bin_inner_aabb(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        lo, hi = self.bin_aabb
        t = self.bin_wall_thickness
        return (
            (lo[0] + t, lo[1] + t, lo[2]),
            (hi[0] - t, hi[1] - t, hi[2]),
        )

    def color_rgb(self, name: str) -> tuple[int, int, int]:
        for color_name, rgb in self.palette:
            if color_name == name:
                return rgb
        raise KeyError(f"unknown palette colour {name!r}")


@dataclass(frozen=True)
class ArmConfig:
    """5-DOF tabletop arm: base yaw, shoulder, elbow, wrist pitch, wrist roll."""

    base_position: tuple[float, float, float] = (0.0, -0.32, 0.75)
    base_height: float = 0.35
    link1_length: float = 0.30
    link2_length: float = 0.30
    wrist_length: float = 0.06
    tool_length: float = 0.06
    joint_limits: tuple[tuple[float, float], ...] = (
        (-2.90, 2.90),
        (-1.70, 1.70),
        (-2.60, 0.05),
        (-2.90, 2.90),
        (-3.05, 3.05),
    )
    home_pose: tuple[float, ...] = (0.0, 0.60, -1.20, -0.97, 0.0)
    max_joint_velocity: float = 1.8
    gripper_open: float = 0.06
    gripper_closed: float = 0.012
    joint_names: tuple[str, ...] = (
        "joint_base_yaw",
        "joint_shoulder",
        "joint_elbow",
        "joint_wrist_pitch",
        "joint_wrist_roll",
    )
    joint_axes: tuple[str, ...] = ("Z", "Y", "Y", "Y", "X")

    def __post_init__(self) -> None:
        if len(self.joint_limits) != 5:
            raise ValueError("joint_limits must contain 5 (min, max) pairs")
        if len(self.home_pose) != 5:
            raise ValueError("home_pose must contain 5 joint values")
        if len(self.joint_names) != 5 or len(self.joint_axes) != 5:
            raise ValueError("joint_names and joint_axes must contain 5 entries")
        for lo, hi in self.joint_limits:
            if hi <= lo:
                raise ValueError("every joint limit must satisfy min < max")
        for value, (lo, hi) in zip(self.home_pose, self.joint_limits, strict=True):
            if not lo <= value <= hi:
                raise ValueError(f"home_pose {value} outside joint limits {(lo, hi)}")
        if self.base_height <= 0 or min(self.link1_length, self.link2_length) <= 0:
            raise ValueError("arm dimensions must be positive")

    @property
    def shoulder_z(self) -> float:
        return self.base_position[2] + self.base_height

    @property
    def tool_offset(self) -> float:
        """Distance from the wrist centre to the gripper tip along the tool axis."""
        return self.wrist_length + self.tool_length

    @property
    def max_reach(self) -> float:
        return self.link1_length + self.link2_length + self.tool_offset


@dataclass(frozen=True)
class LabConfig:
    """Bundle used by the backends and the episode runner."""

    scene: SceneConfig = field(default_factory=SceneConfig)
    camera: CameraIntrinsics = field(default_factory=CameraIntrinsics)
    arm: ArmConfig = field(default_factory=ArmConfig)
    seed: int = LAB_SEED

    def __post_init__(self) -> None:
        if self.seed < 0:
            raise ValueError("seed must be non-negative")


def palette_names(palette: Iterable[tuple[str, tuple[int, int, int]]]) -> tuple[str, ...]:
    return tuple(name for name, _ in palette)
