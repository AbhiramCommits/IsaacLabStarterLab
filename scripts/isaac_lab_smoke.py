#!/usr/bin/env python3
"""Smoke-test the Isaac Lab task: build the env, reset, and step it.

Must run where Isaac Lab is importable (``isaaclab.sh -p`` or ``uv run``):

    ./isaaclab.sh -p <repo>/scripts/isaac_lab_smoke.py --num_envs 2 --steps 5

Prints observation/action dimensions, the reward and termination term names,
and the per-step reward, so configuration errors surface before a training run.
"""

from __future__ import annotations

import argparse

from isaaclab.app import AppLauncher

parser = argparse.ArgumentParser()
parser.add_argument("--num_envs", type=int, default=2)
parser.add_argument("--steps", type=int, default=5)
AppLauncher.add_app_launcher_args(parser)
args_cli = parser.parse_args()
app_launcher = AppLauncher(args_cli)
simulation_app = app_launcher.app

import gymnasium as gym  # noqa: E402
import torch  # noqa: E402
from isaaclab.envs import ManagerBasedRLEnv  # noqa: E402

from isaac_starter_lab.isaac_lab.pick_place_task import (  # noqa: E402
    PickPlaceTaskCfg,
    register,
)


def main() -> int:
    task_id = register()
    spec = gym.spec(task_id)
    print(f"registered task: {task_id} entry_point={spec.entry_point}")

    cfg = PickPlaceTaskCfg()
    cfg.scene.num_envs = args_cli.num_envs
    cfg.sim.device = args_cli.device
    cfg.seed = 7
    env = ManagerBasedRLEnv(cfg)

    print(f"num_envs={env.num_envs} num_actions={env.action_space.shape[-1]}")
    print(f"observation groups: {list(env.observation_manager.active_terms)}")
    for group in env.observation_manager.active_terms:
        print(
            f"  {group}: dim={env.observation_manager.group_obs_dim[group]} "
            f"terms={env.observation_manager.active_terms[group]}"
        )
    print(f"rewards: {env.reward_manager.active_terms}")
    print(f"terminations: {env.termination_manager.active_terms}")

    obs, _ = env.reset()
    print(f"reset obs shape: {tuple(obs['policy'].shape)}")
    gripper_ids, gripper_names = env.scene["robot"].find_bodies("gripper")
    print(f"gripper body: {gripper_names} ids={gripper_ids}")
    print("env_origin[0]=", [round(v, 4) for v in env.scene.env_origins[0].tolist()])
    robot = env.scene["robot"]
    print("joint_names:", robot.joint_names)
    print("joint_pos[0]:", [round(v, 3) for v in robot.data.joint_pos.torch[0].tolist()])
    print("default_joint_pos[0]:", [round(v, 3) for v in robot.data.default_joint_pos.torch[0].tolist()])
    print("limits:", [tuple(round(x, 2) for x in lim) for lim in robot.data.joint_limits.torch[0].tolist()])
    print("root_pos_w[0]:", [round(v, 3) for v in robot.data.root_pos_w.torch[0].tolist()])
    for name, pos in zip(robot.body_names, robot.data.body_pos_w.torch[0].tolist(), strict=True):
        print(f"  body {name}: {[round(v, 3) for v in pos]}")
    print(
        "object_pos[0]=",
        [round(v, 4) for v in env.scene["object"].data.root_pos_w.torch[0].tolist()],
        "ee_pos[0]=",
        [
            round(v, 4)
            for v in env.scene["robot"].data.body_pos_w.torch[0, gripper_ids[0]].tolist()
        ],
    )
    actions = torch.zeros(env.action_space.shape, device=env.device)
    for step in range(args_cli.steps):
        obs, reward, terminated, truncated, _ = env.step(actions)
        print(
            f"step {step}: reward_mean={reward.mean().item():.6f} "
            f"terminated={int(terminated.sum())} truncated={int(truncated.sum())}"
        )
    print("SMOKE_OK")
    env.close()
    return 0


if __name__ == "__main__":
    code = main()
    simulation_app.close()
    raise SystemExit(code)
