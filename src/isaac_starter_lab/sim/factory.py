"""Backend selection for the lab.

``kinematic`` is the deterministic CPU path used for every measured result in
this repository.  ``isaac`` lazily constructs the Isaac Sim adapter; importing
it on a machine without Isaac Sim raises a helpful
:class:`~isaac_starter_lab.sim.isaac_backend.IsaacUnavailableError` only when the
backend is actually requested.
"""

from __future__ import annotations

import os
from typing import Any

from ..config import LAB_SEED, ArmConfig, SceneConfig

__all__ = ["make_backend", "make_backend_name"]


def make_backend_name(name: str | None = None) -> str:
    resolved = (name or os.environ.get("LAB_BACKEND") or "kinematic").lower()
    if resolved not in ("kinematic", "isaac"):
        raise ValueError(
            f"unknown backend {resolved!r}; choose 'kinematic' (CPU) or 'isaac' (GPU)"
        )
    return resolved


def make_backend(
    name: str | None = None,
    *,
    scene: SceneConfig | None = None,
    arm: ArmConfig | None = None,
    seed: int = LAB_SEED,
    **kwargs: Any,
):
    resolved = make_backend_name(name)
    if resolved == "kinematic":
        from .kinematic import KinematicSim

        kwargs.pop("usda_path", None)
        kwargs.pop("headless", None)
        kwargs.pop("enable_ros2", None)
        return KinematicSim(scene=scene, arm=arm, seed=seed, **kwargs)
    from .isaac_backend import IsaacSimBackend

    return IsaacSimBackend(scene=scene, arm=arm, seed=seed, **kwargs)
