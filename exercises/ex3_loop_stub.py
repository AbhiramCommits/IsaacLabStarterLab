"""Exercise 3 starter stub: close the perception -> controller loop.

The runner must:

1. create a backend (``make_backend``) and a bridge (``make_bridge``);
2. publish ``/lab/joint_states``, ``/lab/cube_poses`` and periodic
   ``/lab/rgb`` messages from the simulator;
3. deliver them with ``bridge.spin_once()`` so ``PickPlaceController`` sees them;
4. deliver the controller's ``/lab/cmd_joint`` and ``/lab/gripper_cmd`` back to
   the simulator;
5. write ``trajectory.jsonl``, ``summary.json``, ``frame_000.png`` and
   ``frame_final.png`` under ``artifacts/episodes/seed_7/``.

The tested implementation is in ``src/isaac_starter_lab/episode.py``.
"""

from __future__ import annotations


def run_pick_place_loop(*args, **kwargs):
    raise NotImplementedError(
        "wire the backend and bridge through the lab topics, then run the "
        "60 Hz loop until the controller reaches DONE"
    )
