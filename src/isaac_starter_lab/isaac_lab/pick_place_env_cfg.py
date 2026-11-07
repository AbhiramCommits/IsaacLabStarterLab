"""Isaac Lab task configuration mirroring the ``ManagerBasedRLEnvCfg`` API.

The dataclasses here are importable and unit-testable **without** Isaac Lab
installed.  On a GPU host, register the task and launch training:

.. code-block:: bash

   ./isaaclab.sh -p scripts/reinforcement_learning/rsl_rl/train.py \
       --task IsaacLabStarterLab-PickPlace-v0 --headless

The task id is registered by :func:`register_task`, which is called from the
same GPU launch wrapper:

.. code-block:: python

   from isaaclab.envs import ManagerBasedRLEnv
   import gymnasium as gym
   from isaac_starter_lab.isaac_lab.pick_place_env_cfg import PickPlaceEnvCfg

   gym.register(
       id="IsaacLabStarterLab-PickPlace-v0",
       entry_point="isaaclab.envs:ManagerBasedRLEnv",
       kwargs={"env_cfg_entry_point": PickPlaceEnvCfg},
   )

Nothing in this module imports Isaac Lab at module import time, so `pytest` and
`labcheck env` work on the CPU track.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "ActionTermCfg",
    "ActionsCfg",
    "AssetCfg",
    "EventCfg",
    "EventsCfg",
    "ObservationTermCfg",
    "ObservationsCfg",
    "PickPlaceEnvCfg",
    "RewardTermCfg",
    "RewardsCfg",
    "SceneCfg",
    "TerminationTermCfg",
    "TerminationsCfg",
    "register_task",
]


@dataclass(frozen=True)
class AssetCfg:
    prim_path: str
    usd_path: str | None = None
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    orientation: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class SceneCfg:
    num_envs: int = 1
    env_spacing: float = 2.0
    robot: AssetCfg = field(
        default_factory=lambda: AssetCfg(prim_path="{ENV_REGEX_NS}/Robot", usd_path=None)
    )
    table: AssetCfg = field(
        default_factory=lambda: AssetCfg(
            prim_path="{ENV_REGEX_NS}/Table", usd_path="{LAB_USD}/tabletop_seed7.usda"
        )
    )
    bin: AssetCfg = field(
        default_factory=lambda: AssetCfg(prim_path="{ENV_REGEX_NS}/Bin")
    )
    cube: AssetCfg = field(
        default_factory=lambda: AssetCfg(prim_path="{ENV_REGEX_NS}/Cubes/Cube_.*")
    )
    camera: AssetCfg = field(
        default_factory=lambda: AssetCfg(prim_path="{ENV_REGEX_NS}/Camera")
    )

    def __post_init__(self) -> None:
        if self.num_envs < 1:
            raise ValueError("num_envs must be >= 1")
        if self.env_spacing <= 0:
            raise ValueError("env_spacing must be positive")


@dataclass(frozen=True)
class ObservationTermCfg:
    func: str
    scale: float | None = None
    noise_std: float = 0.0
    clip: tuple[float, float] | None = None


@dataclass(frozen=True)
class ObservationsCfg:
    policy: dict[str, ObservationTermCfg] = field(
        default_factory=lambda: {
            "joint_pos": ObservationTermCfg("joint_pos_rel", scale=1.0),
            "joint_vel": ObservationTermCfg("joint_vel_rel", scale=0.1),
            "cube_positions": ObservationTermCfg("cube_positions_in_world_frame"),
            "gripper_state": ObservationTermCfg("gripper_state"),
            "camera_rgb": ObservationTermCfg("camera_rgb", scale=1.0 / 255.0),
        }
    )


@dataclass(frozen=True)
class ActionTermCfg:
    joint_names: tuple[str, ...] = (
        "joint_base_yaw",
        "joint_shoulder",
        "joint_elbow",
        "joint_wrist_pitch",
        "joint_wrist_roll",
    )
    scale: float = 1.0
    clip: tuple[float, float] = (-1.0, 1.0)


@dataclass(frozen=True)
class ActionsCfg:
    joint_velocities: ActionTermCfg = field(default_factory=ActionTermCfg)
    gripper: ActionTermCfg = field(
        default_factory=lambda: ActionTermCfg(joint_names=("gripper",), scale=1.0)
    )


@dataclass(frozen=True)
class RewardTermCfg:
    weight: float
    params: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RewardsCfg:
    reaching: RewardTermCfg = field(
        default_factory=lambda: RewardTermCfg(1.0, {"std": 0.05})
    )
    lifting: RewardTermCfg = field(default_factory=lambda: RewardTermCfg(2.0))
    placing: RewardTermCfg = field(default_factory=lambda: RewardTermCfg(5.0))
    action_rate: RewardTermCfg = field(default_factory=lambda: RewardTermCfg(-0.01))


@dataclass(frozen=True)
class TerminationTermCfg:
    func: str
    params: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TerminationsCfg:
    time_out: TerminationTermCfg = field(default_factory=lambda: TerminationTermCfg("time_out"))
    cube_in_bin: TerminationTermCfg = field(
        default_factory=lambda: TerminationTermCfg("cube_in_bin")
    )
    cube_dropped: TerminationTermCfg = field(
        default_factory=lambda: TerminationTermCfg("cube_dropped", {"min_height": 0.60})
    )


@dataclass(frozen=True)
class EventCfg:
    reset_scene: bool = True
    randomize_light: bool = True
    randomize_camera_yaw: bool = True
    randomize_cube_colors: bool = True


@dataclass(frozen=True)
class EventsCfg:
    mode: str = "reset"
    terms: EventCfg = field(default_factory=EventCfg)


@dataclass(frozen=True)
class PickPlaceEnvCfg:
    """Top-level config; field names match Isaac Lab's ManagerBasedRLEnvCfg."""

    scene: SceneCfg = field(default_factory=SceneCfg)
    observations: ObservationsCfg = field(default_factory=ObservationsCfg)
    actions: ActionsCfg = field(default_factory=ActionsCfg)
    rewards: RewardsCfg = field(default_factory=RewardsCfg)
    terminations: TerminationsCfg = field(default_factory=TerminationsCfg)
    events: EventsCfg = field(default_factory=EventsCfg)
    decimation: int = 4
    episode_length_s: float = 20.0
    sim_dt: float = 1.0 / 60.0

    def __post_init__(self) -> None:
        if self.decimation < 1:
            raise ValueError("decimation must be >= 1")
        if not 0.0 < self.sim_dt <= 0.1:
            raise ValueError("sim_dt must be in (0, 0.1] seconds")
        if self.episode_length_s <= 0:
            raise ValueError("episode_length_s must be positive")

    @property
    def control_dt(self) -> float:
        return self.sim_dt * self.decimation

    @property
    def episode_length_steps(self) -> int:
        return int(round(self.episode_length_s / self.control_dt))


def register_task() -> str:
    """Register the gym task on a GPU host; returns the task id."""
    try:
        import gymnasium as gym
    except ImportError as exc:  # pragma: no cover - GPU host only
        raise RuntimeError(
            "gymnasium is required to register the Isaac Lab task. "
            "Run inside the Isaac Lab container (see docs/LAB_GUIDE.md Exercise 5)."
        ) from exc
    task_id = "IsaacLabStarterLab-PickPlace-v0"
    gym.register(
        id=task_id,
        entry_point="isaaclab.envs:ManagerBasedRLEnv",
        kwargs={"env_cfg_entry_point": PickPlaceEnvCfg},
    )
    return task_id
