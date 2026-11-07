"""Software rendering and camera geometry."""

from .pinhole import (
    CameraPose,
    backproject_to_plane,
    project_point,
    render_scene,
    unproject_pixel,
)

__all__ = [
    "CameraPose",
    "backproject_to_plane",
    "project_point",
    "render_scene",
    "unproject_pixel",
]
