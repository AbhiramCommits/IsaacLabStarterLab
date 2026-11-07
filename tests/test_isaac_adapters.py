"""GPU-gated adapters are importable and fail with actionable errors."""

from __future__ import annotations

import importlib.util
from dataclasses import FrozenInstanceError

import pytest

from isaac_starter_lab.isaac_lab.pick_place_env_cfg import (
    ObservationTermCfg,
    PickPlaceEnvCfg,
    SceneCfg,
)
from isaac_starter_lab.sim.factory import make_backend, make_backend_name
from isaac_starter_lab.sim.isaac_backend import (
    CONTAINER_IMAGE,
    IsaacSimBackend,
    IsaacUnavailableError,
)
from isaac_starter_lab.sim.kinematic import KinematicSim


def test_kinematic_backend_is_default(monkeypatch):
    monkeypatch.delenv("LAB_BACKEND", raising=False)
    assert make_backend_name(None) == "kinematic"
    assert isinstance(make_backend(None), KinematicSim)


def test_backend_env_selection(monkeypatch):
    monkeypatch.setenv("LAB_BACKEND", "isaac")
    assert make_backend_name(None) == "isaac"
    backend = make_backend(None)
    assert isinstance(backend, IsaacSimBackend)
    assert not backend._app  # construction is lazy


def test_unknown_backend_is_rejected(monkeypatch):
    monkeypatch.delenv("LAB_BACKEND", raising=False)
    with pytest.raises(ValueError, match="unknown backend"):
        make_backend("gazebo")


def test_isaac_start_raises_actionable_error():
    backend = IsaacSimBackend(usda_path="usd/tabletop_seed7.usda")
    with pytest.raises(IsaacUnavailableError) as excinfo:
        backend.start()
    message = str(excinfo.value)
    assert CONTAINER_IMAGE in message
    assert "--gpus all" in message
    assert "LAB_BACKEND=isaac" in message
    assert "NVIDIA GPU" in message


def test_isaac_module_does_not_import_omniverse_eagerly():
    assert importlib.util.find_spec("isaacsim") is None
    assert importlib.util.find_spec("omni") is None


def test_isaac_lab_cfg_defaults_and_validation():
    cfg = PickPlaceEnvCfg()
    assert cfg.decimation == 4
    assert cfg.sim_dt == pytest.approx(1 / 60)
    assert cfg.control_dt == pytest.approx(4 / 60)
    assert cfg.episode_length_s == 20.0
    assert cfg.episode_length_steps == 300
    assert cfg.scene.num_envs == 1
    assert cfg.scene.env_spacing == 2.0
    assert "joint_pos" in cfg.observations.policy
    assert isinstance(cfg.observations.policy["joint_pos"], ObservationTermCfg)
    assert len(cfg.actions.joint_velocities.joint_names) == 5
    assert cfg.rewards.placing.weight == 5.0
    assert cfg.terminations.cube_in_bin.func == "cube_in_bin"
    assert cfg.events.terms.randomize_camera_yaw is True

    with pytest.raises(ValueError):
        PickPlaceEnvCfg(decimation=0)
    with pytest.raises(ValueError):
        PickPlaceEnvCfg(sim_dt=0.5)
    with pytest.raises(ValueError):
        PickPlaceEnvCfg(episode_length_s=0)
    with pytest.raises(ValueError):
        SceneCfg(num_envs=0)
    with pytest.raises(ValueError):
        SceneCfg(env_spacing=0)


def test_isaac_lab_cfg_is_frozen():
    cfg = PickPlaceEnvCfg()
    with pytest.raises(FrozenInstanceError):
        cfg.decimation = 8  # type: ignore[misc]


def test_register_task_reports_missing_gymnasium():
    if importlib.util.find_spec("gymnasium") is not None:
        pytest.skip("gymnasium is installed; the GPU registration path is available")
    from isaac_starter_lab.isaac_lab.pick_place_env_cfg import register_task

    with pytest.raises(RuntimeError, match="gymnasium is required"):
        register_task()
