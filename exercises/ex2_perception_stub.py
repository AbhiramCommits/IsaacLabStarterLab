"""Exercise 2 starter stub: colour-based cube detection.

Goal: return one :class:`~isaac_starter_lab.perception.Detection` per cube of
``target_color``, with the pixel centroid and the back-projected 3D grasp pose.

Hints
-----
1. Convert RGB to HSV (hue in degrees).
2. Threshold on hue distance + saturation + value.
3. Label 8-connected components and discard areas below ~20 pixels.
4. The centroid is ``(mean column, mean row)`` of the component.
5. Back-project to ``z = SceneConfig.cube_center_z`` with
   ``render.pinhole.backproject_to_plane``.

Copy this file over the matching function in
``src/isaac_starter_lab/perception.py`` and run ``labcheck ex2``.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from isaac_starter_lab.perception import Detection


def detect_cubes(
    frame: np.ndarray,
    target_color: str | Sequence[int],
    **kwargs,
) -> list[Detection]:
    raise NotImplementedError(
        "detect_cubes is not implemented yet: threshold HSV, label components, "
        "then back-project each centroid onto the table plane"
    )
