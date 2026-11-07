"""The lab's single message contract.

Every backend and both bridges speak these six messages.  Keeping one schema
means the exact same learner-written perception and control code runs on the
CPU ``kinematic``/``localbus`` track and on the GPU ``isaac``/``ros2`` track.

Wire format notes
-----------------
* ``RgbFrame.data`` is raw ``rgb8`` bytes in memory and base64 text on the wire.
* All other messages are plain JSON-compatible dictionaries with tuples converted
  to lists, so ``json.dumps`` is enough for the local bus, ROS 2 ``String``
  payloads and the committed trajectory files.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

# Topic names are part of the public contract; do not rename them.
JOINT_STATES_TOPIC = "/lab/joint_states"
RGB_TOPIC = "/lab/rgb"
CUBE_POSES_TOPIC = "/lab/cube_poses"
CMD_JOINT_TOPIC = "/lab/cmd_joint"
GRIPPER_CMD_TOPIC = "/lab/gripper_cmd"
STATUS_TOPIC = "/lab/status"


def _tuple_floats(values: Any) -> tuple[float, ...]:
    return tuple(float(v) for v in values)


def _tuple_xyz(values: Any) -> tuple[tuple[float, float, float], ...]:
    return tuple((float(v[0]), float(v[1]), float(v[2])) for v in values)


@dataclass(frozen=True)
class JointState:
    TOPIC: ClassVar[str] = JOINT_STATES_TOPIC

    stamp: float
    names: tuple[str, ...]
    positions: tuple[float, ...]
    velocities: tuple[float, ...]
    gripper: float

    def __post_init__(self) -> None:
        if len(self.names) != len(self.positions) or len(self.names) != len(self.velocities):
            raise ValueError("JointState names, positions and velocities must have equal length")

    def to_dict(self) -> dict[str, Any]:
        return {
            "stamp": float(self.stamp),
            "names": list(self.names),
            "positions": [float(v) for v in self.positions],
            "velocities": [float(v) for v in self.velocities],
            "gripper": float(self.gripper),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JointState:
        return cls(
            stamp=float(data["stamp"]),
            names=tuple(str(v) for v in data["names"]),
            positions=_tuple_floats(data["positions"]),
            velocities=_tuple_floats(data["velocities"]),
            gripper=float(data["gripper"]),
        )


@dataclass(frozen=True)
class RgbFrame:
    TOPIC: ClassVar[str] = RGB_TOPIC

    stamp: float
    width: int
    height: int
    encoding: str
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        expected = self.width * self.height * 3
        if self.encoding != "rgb8":
            raise ValueError("only rgb8 frames are supported")
        if len(self.data) != expected:
            raise ValueError(f"frame data has {len(self.data)} bytes, expected {expected}")

    def to_dict(self, include_data: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stamp": float(self.stamp),
            "width": int(self.width),
            "height": int(self.height),
            "encoding": self.encoding,
        }
        if include_data:
            payload["data_b64"] = base64.b64encode(self.data).decode("ascii")
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RgbFrame:
        return cls(
            stamp=float(data["stamp"]),
            width=int(data["width"]),
            height=int(data["height"]),
            encoding=str(data["encoding"]),
            data=base64.b64decode(data["data_b64"]),
        )


@dataclass(frozen=True)
class CubePoseArray:
    TOPIC: ClassVar[str] = CUBE_POSES_TOPIC

    stamp: float
    names: tuple[str, ...]
    positions: tuple[tuple[float, float, float], ...]
    colors: tuple[str, ...]
    grasped: str | None = None

    def __post_init__(self) -> None:
        if not (len(self.names) == len(self.positions) == len(self.colors)):
            raise ValueError("CubePoseArray names, positions and colors must have equal length")

    def to_dict(self) -> dict[str, Any]:
        return {
            "stamp": float(self.stamp),
            "names": list(self.names),
            "positions": [list(p) for p in self.positions],
            "colors": list(self.colors),
            "grasped": self.grasped,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CubePoseArray:
        return cls(
            stamp=float(data["stamp"]),
            names=tuple(str(v) for v in data["names"]),
            positions=_tuple_xyz(data["positions"]),
            colors=tuple(str(v) for v in data["colors"]),
            grasped=None if data.get("grasped") is None else str(data["grasped"]),
        )


@dataclass(frozen=True)
class JointCommand:
    TOPIC: ClassVar[str] = CMD_JOINT_TOPIC

    stamp: float
    velocities: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"stamp": float(self.stamp), "velocities": [float(v) for v in self.velocities]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JointCommand:
        return cls(stamp=float(data["stamp"]), velocities=_tuple_floats(data["velocities"]))


@dataclass(frozen=True)
class GripperCommand:
    TOPIC: ClassVar[str] = GRIPPER_CMD_TOPIC

    stamp: float
    #: 0.0 = fully open, 1.0 = fully closed.
    closure: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.closure <= 1.0:
            raise ValueError("gripper closure must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {"stamp": float(self.stamp), "closure": float(self.closure)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GripperCommand:
        return cls(stamp=float(data["stamp"]), closure=float(data["closure"]))


@dataclass(frozen=True)
class LabStatus:
    TOPIC: ClassVar[str] = STATUS_TOPIC

    stamp: float
    tick: int
    state: str
    success: bool
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stamp": float(self.stamp),
            "tick": int(self.tick),
            "state": self.state,
            "success": bool(self.success),
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> LabStatus:
        return cls(
            stamp=float(data["stamp"]),
            tick=int(data["tick"]),
            state=str(data["state"]),
            success=bool(data["success"]),
            message=str(data.get("message", "")),
        )


MESSAGE_TYPES: dict[str, type] = {
    JOINT_STATES_TOPIC: JointState,
    RGB_TOPIC: RgbFrame,
    CUBE_POSES_TOPIC: CubePoseArray,
    CMD_JOINT_TOPIC: JointCommand,
    GRIPPER_CMD_TOPIC: GripperCommand,
    STATUS_TOPIC: LabStatus,
}

TOPICS = tuple(MESSAGE_TYPES)

__all__ = [
    "CMD_JOINT_TOPIC",
    "CUBE_POSES_TOPIC",
    "GRIPPER_CMD_TOPIC",
    "JOINT_STATES_TOPIC",
    "MESSAGE_TYPES",
    "RGB_TOPIC",
    "STATUS_TOPIC",
    "TOPICS",
    "CubePoseArray",
    "GripperCommand",
    "JointCommand",
    "JointState",
    "LabStatus",
    "RgbFrame",
]
