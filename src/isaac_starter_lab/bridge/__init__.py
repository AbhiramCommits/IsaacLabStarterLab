"""Bridge selection: ``localbus`` (CPU) or ``ros2`` (transport track)."""

from __future__ import annotations

import os

from .base import Bridge
from .localbus import LocalBus
from .ros2_bridge import Ros2Bridge, Ros2UnavailableError

__all__ = ["Bridge", "LocalBus", "Ros2Bridge", "Ros2UnavailableError", "make_bridge"]


def make_bridge(name: str | None = None) -> Bridge:
    resolved = (name or os.environ.get("LAB_BRIDGE") or "localbus").lower()
    if resolved == "localbus":
        return LocalBus()
    if resolved == "ros2":
        return Ros2Bridge()
    raise ValueError(
        f"unknown bridge {resolved!r}; choose 'localbus' (no ROS install) or 'ros2'"
    )
