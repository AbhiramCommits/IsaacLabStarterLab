#!/usr/bin/env python3
"""Scripted grasp check: descend, close the jaw, lift, and read the cube height.

Runs on one environment and does not learn anything.  It proves that the jaw
travel and the collision geometry can actually hold the cube, independently of
the PPO policy.

    ./isaaclab.sh -p scripts/isaac_lab_grasp_check.py --headless
"""

from __future__ import annotations

import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import torch  # noqa: E402
from isaaclab.envs import ManagerBasedRLEnv  # noqa: E402

from isaac_starter_lab.isaac_lab.pick_place_task import PickPlaceTaskCfg  # noqa: E402

#: Joint-position actions (relative to the start pose, scale 0.5) solved with
#: isaac_starter_lab.sim.kinematics.inverse_kinematics for the tool tip 2 cm
#: above the cube and then 10 cm above it.
DESCEND = (-0.197, 0.487, -0.270, -0.218, 0.0)
LIFT = (-0.197, -0.308, 0.082, 0.226, 0.0)


def _action(arm: tuple[float, ...], close: float) -> torch.Tensor:
    return torch.tensor([[*arm, close]], dtype=torch.float32)


def main() -> int:
    cfg = PickPlaceTaskCfg()
    cfg.scene.num_envs = 1
    cfg.sim.device = args_cli.device
    cfg.seed = 7
    env = ManagerBasedRLEnv(cfg)
    env.reset()

    cube = env.scene["object"]
    robot = env.scene["robot"]
    jaw_ids, _ = robot.find_joints("jaw_joint")
    print(f"cube start z = {cube.data.root_pos_w.torch[0, 2].item():.4f}")

    def run(action: torch.Tensor, steps: int, label: str) -> None:
        for _ in range(steps):
            env.step(action.to(env.device))
        ee = robot.data.body_pos_w.torch[0, robot.find_bodies("gripper")[0][0]]
        term = env.action_manager.get_term("gripper_action")
        print(
            f"{label}: cube z={cube.data.root_pos_w.torch[0, 2].item():.4f} "
            f"jaw q={robot.data.joint_pos.torch[0, jaw_ids[0]].item():.4f} "
            f"jaw target={term.processed_actions[0, 0].item():.4f} "
            f"ee={[round(v, 3) for v in ee.tolist()]}"
        )

    run(_action(DESCEND, 0.0), 40, "after descend")
    run(_action(DESCEND, 1.0), 40, "after close")
    run(_action(LIFT, 1.0), 45, "after lift")

    final_z = cube.data.root_pos_w.torch[0, 2].item()
    lifted = final_z > 0.80
    print(f"GRASP_CHECK {'LIFTED' if lifted else 'NOT_LIFTED'} z={final_z:.4f}")
    env.close()
    return 0 if lifted else 1


if __name__ == "__main__":
    code = main()
    simulation_app.close()
    raise SystemExit(code)
