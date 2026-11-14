"""Real Isaac Lab task for the tabletop pick-and-place lab.

This module is imported only on a GPU host with Isaac Lab installed.  It builds
a :class:`ManagerBasedRLEnvCfg` around the lab's own arm and tabletop:

* robot: ``usd/lab_arm.usda`` — the same flat articulation the PhysX episodes
  use, authored by :mod:`isaac_starter_lab.sim.arm_usd`.
* scene: ``usd/lab_task_seed7.usda`` — table, bin, lights and camera without the
  canonical visual robot.
* object: one 50 mm cube spawned as a rigid body on the table.

The MDP is a dense reach/lift/place reward with a binary gripper action.  On a
CPU host the import raises ``ImportError`` from Isaac Lab; nothing here is
imported by the CPU test suite.

Register and train with ``scripts/train_isaac_lab_ppo.py``.
"""

from __future__ import annotations

from pathlib import Path

import isaaclab.envs.mdp as mdp
import isaaclab.sim as sim_utils
import torch
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets import ArticulationCfg, AssetBaseCfg, RigidObjectCfg
from isaaclab.envs import ManagerBasedRLEnvCfg
from isaaclab.managers import (
    EventTermCfg as EventTerm,
)
from isaaclab.managers import (
    ObservationGroupCfg as ObsGroup,
)
from isaaclab.managers import (
    ObservationTermCfg as ObsTerm,
)
from isaaclab.managers import (
    RewardTermCfg as RewTerm,
)
from isaaclab.managers import (
    SceneEntityCfg,
)
from isaaclab.managers import (
    TerminationTermCfg as DoneTerm,
)
from isaaclab.scene import InteractiveSceneCfg
from isaaclab.sim import RigidBodyPropertiesCfg, UsdFileCfg
from isaaclab.utils.configclass import configclass
from isaaclab_physx.physics import PhysxCfg
from isaaclab_rl.rsl_rl import RslRlMLPModelCfg, RslRlOnPolicyRunnerCfg, RslRlPpoAlgorithmCfg

from ..config import ArmConfig, SceneConfig

LAB_ROOT = Path(__file__).resolve().parents[3]

TASK_ID = "IsaacLabStarterLab-PickPlace-v0"

_ARM = ArmConfig()
_SCENE = SceneConfig()
ARM_USD = str(LAB_ROOT / "usd" / "lab_arm.usda")
SCENE_USD = str(LAB_ROOT / "usd" / "lab_task_seed7.usda")

ARM_JOINTS = [
    "joint_base_yaw",
    "joint_shoulder",
    "joint_elbow",
    "joint_wrist_pitch",
    "joint_wrist_roll",
]
JAW_JOINT = "jaw_joint"

#: Bin centre that the placing reward and the success termination target.
BIN_X = 0.25
BIN_Y = 0.14
BIN_Z = _SCENE.table_top + 0.04
#: Start pose: the assembled arm (all joints zero) with the jaw open, which is
#: exactly where the PhysX backend starts before its controller takes over.
START_Q = {name: 0.0 for name in ARM_JOINTS}
START_Q[JAW_JOINT] = 0.07

#: Object spawn on the table, in front of the arm.
OBJECT_X = 0.14
OBJECT_Y = 0.0
OBJECT_Z = _SCENE.cube_center_z


# ----------------------------------------------------------------------
# MDP terms (plain functions, resolved by the managers at build time)
# ----------------------------------------------------------------------
def ee_object_distance(
    env,
    std: float,
    object_cfg: SceneEntityCfg = SceneEntityCfg("object"),  # noqa: B008
    robot_cfg: SceneEntityCfg = SceneEntityCfg("robot", body_names="gripper"),  # noqa: B008
) -> torch.Tensor:
    """Tanh-kernel reward on the gripper-to-cube distance."""
    obj = env.scene[object_cfg.name]
    robot = env.scene[robot_cfg.name]
    cube = obj.data.root_pos_w.torch
    ee = robot.data.body_pos_w.torch[:, robot_cfg.body_ids]
    if ee.dim() == 3:
        # ``body_ids`` resolves to a slice when a single body name is given.
        ee = ee[:, 0]
    distance = torch.linalg.norm(cube - ee, dim=1)
    return 1.0 - torch.tanh(distance / std)


def object_lifted(
    env, minimal_height: float, object_cfg: SceneEntityCfg = SceneEntityCfg("object")  # noqa: B008
) -> torch.Tensor:
    """1.0 while the cube is above ``minimal_height`` (world z)."""
    obj = env.scene[object_cfg.name]
    return torch.where(obj.data.root_pos_w.torch[:, 2] > minimal_height, 1.0, 0.0)


def object_to_bin(
    env,
    std: float,
    bin_xyz: tuple[float, float, float],
    minimal_height: float,
    object_cfg: SceneEntityCfg = SceneEntityCfg("object"),  # noqa: B008
) -> torch.Tensor:
    """Tanh-kernel reward on the lifted cube's distance to the bin centre."""
    obj = env.scene[object_cfg.name]
    pos = obj.data.root_pos_w.torch
    target = torch.tensor(bin_xyz, dtype=pos.dtype, device=pos.device)
    distance = torch.linalg.norm(pos - target, dim=1)
    lifted = pos[:, 2] > minimal_height
    return lifted.float() * (1.0 - torch.tanh(distance / std))


def cube_in_bin(
    env,
    bin_xyz: tuple[float, float, float],
    threshold: float,
    object_cfg: SceneEntityCfg = SceneEntityCfg("object"),  # noqa: B008
) -> torch.Tensor:
    """Termination: the cube is inside the bin radius and above the table top."""
    obj = env.scene[object_cfg.name]
    pos = obj.data.root_pos_w.torch
    target = torch.tensor(bin_xyz, dtype=pos.dtype, device=pos.device)
    horizontal = torch.linalg.norm((pos - target)[:, :2], dim=1)
    return (horizontal < threshold) & (pos[:, 2] > _SCENE.table_top)


# ----------------------------------------------------------------------
# Scene
# ----------------------------------------------------------------------
@configclass
class PickPlaceSceneCfg(InteractiveSceneCfg):
    """Table, bin, lights and camera; the arm and the cube are added below."""

    tabletop = AssetBaseCfg(
        prim_path="{ENV_REGEX_NS}/Tabletop",
        spawn=UsdFileCfg(usd_path=SCENE_USD),
        init_state=AssetBaseCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0)),
    )

    robot: ArticulationCfg = ArticulationCfg(
        prim_path="{ENV_REGEX_NS}/RobotIsaac",
        spawn=UsdFileCfg(usd_path=ARM_USD),
        init_state=ArticulationCfg.InitialStateCfg(
            # The arm's links are authored in world coordinates under a
            # root that sits at the origin, so placing the root at the arm's
            # base position reproduces the assembled pose in every env.
            pos=_ARM.base_position,
            joint_pos=dict(START_Q),
            joint_vel={name: 0.0 for name in ARM_JOINTS + [JAW_JOINT]},
        ),
        actuators={
            # RL gains: the backend's 1e5 drive is for slew-limited position
            # tracking, not for random policy actions, where it diverges.
            "arm": ImplicitActuatorCfg(
                joint_names_expr=ARM_JOINTS,
                stiffness=200.0,
                damping=10.0,
                effort_limit_sim=50.0,
            ),
            "gripper": ImplicitActuatorCfg(
                joint_names_expr=[JAW_JOINT],
                stiffness=200.0,
                damping=10.0,
                effort_limit_sim=20.0,
            ),
        },
    )

    object: RigidObjectCfg = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/Object",
        spawn=sim_utils.CuboidCfg(
            size=(_SCENE.cube_size, _SCENE.cube_size, _SCENE.cube_size),
            rigid_props=RigidBodyPropertiesCfg(),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.05),
            collision_props=sim_utils.CollisionPropertiesCfg(),
            visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=(0.12, 0.71, 0.24)),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=(OBJECT_X, OBJECT_Y, OBJECT_Z)),
    )


@configclass
class ActionsCfg:
    arm_action = mdp.JointPositionActionCfg(
        asset_name="robot",
        joint_names=ARM_JOINTS,
        scale=1.5,
        use_default_offset=True,
    )
    gripper_action = mdp.BinaryJointPositionActionCfg(
        asset_name="robot",
        joint_names=[JAW_JOINT],
        open_command_expr={JAW_JOINT: 0.07},
        close_command_expr={JAW_JOINT: 0.0},
    )


@configclass
class ObservationsCfg:
    @configclass
    class PolicyCfg(ObsGroup):
        joint_pos = ObsTerm(func=mdp.joint_pos_rel)
        joint_vel = ObsTerm(func=mdp.joint_vel_rel)
        object_position = ObsTerm(
            func=mdp.root_pos_w,
            params={"asset_cfg": SceneEntityCfg("object")},
        )
        actions = ObsTerm(func=mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    policy: PolicyCfg = PolicyCfg()


@configclass
class RewardsCfg:
    reaching = RewTerm(
        func=ee_object_distance,
        weight=1.0,
        params={"std": 0.50},
    )
    lifting = RewTerm(
        func=object_lifted,
        weight=5.0,
        params={"minimal_height": _SCENE.table_top + 0.04},
    )
    placing = RewTerm(
        func=object_to_bin,
        weight=10.0,
        params={
            "std": 0.10,
            "bin_xyz": (BIN_X, BIN_Y, BIN_Z),
            "minimal_height": _SCENE.table_top + 0.04,
        },
    )
    action_rate = RewTerm(func=mdp.action_rate_l2, weight=-1.0e-4)
    joint_vel = RewTerm(
        func=mdp.joint_vel_l2,
        weight=-1.0e-4,
        params={"asset_cfg": SceneEntityCfg("robot")},
    )


@configclass
class TerminationsCfg:
    time_out = DoneTerm(func=mdp.time_out, time_out=True)
    success = DoneTerm(
        func=cube_in_bin,
        params={"bin_xyz": (BIN_X, BIN_Y, BIN_Z), "threshold": 0.08},
    )
    dropped = DoneTerm(
        func=mdp.root_height_below_minimum,
        params={"minimum_height": 0.60, "asset_cfg": SceneEntityCfg("object")},
    )


@configclass
class EventCfg:
    reset_all = EventTerm(func=mdp.reset_scene_to_default, mode="reset")
    reset_object = EventTerm(
        func=mdp.reset_root_state_uniform,
        mode="reset",
        params={
            "pose_range": {"x": (-0.05, 0.05), "y": (-0.05, 0.05), "z": (0.0, 0.0)},
            "velocity_range": {},
            "asset_cfg": SceneEntityCfg("object"),
        },
    )


@configclass
class PickPlaceTaskCfg(ManagerBasedRLEnvCfg):
    """Top-level ManagerBasedRLEnv configuration for the lab."""

    scene: PickPlaceSceneCfg = PickPlaceSceneCfg(num_envs=32, env_spacing=2.0, replicate_physics=True)
    observations: ObservationsCfg = ObservationsCfg()
    actions: ActionsCfg = ActionsCfg()
    rewards: RewardsCfg = RewardsCfg()
    terminations: TerminationsCfg = TerminationsCfg()
    events: EventCfg = EventCfg()

    def __post_init__(self):
        self.decimation = 4
        self.episode_length_s = 8.0
        self.sim.dt = 1.0 / 120.0
        self.sim.render_interval = self.decimation
        self.sim.physics = PhysxCfg()
        self.viewer.eye = (2.0, -1.5, 1.5)
        self.viewer.lookat = (0.0, 0.0, 0.8)


@configclass
class LabPpoAgentCfg(RslRlOnPolicyRunnerCfg):
    """PPO/rsl_rl runner configuration for the lab task."""

    seed = 7
    clip_actions = 1.0
    num_steps_per_env = 48
    max_iterations = 300
    save_interval = 100
    experiment_name = "lab_pick_place"
    run_name = ""
    actor = RslRlMLPModelCfg(
        hidden_dims=[256, 128, 64],
        activation="elu",
        obs_normalization=True,
        distribution_cfg=RslRlMLPModelCfg.GaussianDistributionCfg(init_std=1.0),
    )
    critic = RslRlMLPModelCfg(
        hidden_dims=[256, 128, 64],
        activation="elu",
        obs_normalization=True,
    )
    algorithm = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.005,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=1.0e-3,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )


def register() -> str:
    """Register the task with gymnasium and return its id."""
    import gymnasium as gym

    if TASK_ID not in gym.registry:
        gym.register(
            id=TASK_ID,
            entry_point="isaaclab.envs:ManagerBasedRLEnv",
            kwargs={
                "env_cfg_entry_point": PickPlaceTaskCfg,
                "rsl_rl_cfg_entry_point": LabPpoAgentCfg,
            },
            disable_env_checker=True,
        )
    return TASK_ID


def external_callback():
    """Isaac Lab ``train.py --external_callback`` hook.

    Registers the task before Isaac Lab resolves the gym spec, then returns the
    arguments that Hydra should still see.
    """
    import sys

    register()
    return sys.argv[1:]
