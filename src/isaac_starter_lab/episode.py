"""One deterministic pick-and-place episode, with committed artifacts.

The episode runner wires a backend, a bridge, perception and the controller
through the public topics only.  Nothing bypasses the message schema, which is
why the same controller runs against ``localbus``/``KinematicSim`` and against
``ros2``/``IsaacSimBackend``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .bridge import make_bridge
from .config import LAB_SEED, ArmConfig, CameraIntrinsics, SceneConfig
from .controller import PickPlaceController
from .perception import detect_cubes
from .sim.factory import make_backend
from .sim.schema import (
    CMD_JOINT_TOPIC,
    CUBE_POSES_TOPIC,
    GRIPPER_CMD_TOPIC,
    JOINT_STATES_TOPIC,
    RGB_TOPIC,
    STATUS_TOPIC,
    CubePoseArray,
    LabStatus,
    RgbFrame,
)

__all__ = ["run_episode", "run_episode_command"]

RGB_PERIOD_TICKS = 30


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rgb_message(
    sim,
    scene: SceneConfig,
    intrinsics: CameraIntrinsics,
    backend: str,
    stamp: float,
) -> RgbFrame:
    if backend == "isaac":
        return sim.rgb_frame()
    image = sim.render_rgb(
        intrinsics=intrinsics,
        camera_position=scene.camera_position,
        look_at=scene.camera_look_at,
        table_color=scene.table_color,
        light_intensity=scene.light_intensity,
    )
    return RgbFrame(
        stamp=stamp,
        width=intrinsics.width,
        height=intrinsics.height,
        encoding="rgb8",
        data=image.tobytes(),
    )


def _save_rgb(message: RgbFrame, path: Path) -> str:
    image = np.frombuffer(message.data, dtype=np.uint8).reshape(
        message.height, message.width, 3
    )
    Image.fromarray(image).save(path)
    return _sha256_bytes(path.read_bytes())


def _most_visible_palette_color(
    sim, scene: SceneConfig, intrinsics: CameraIntrinsics, backend: str, pose=None
) -> str:
    """Pick the least-occluded palette colour from the initial camera frame.

    A real picker should not attempt an occluded cube it cannot localise.  This
    uses the learner-facing detector on the first frame and therefore exercises
    the same code path as the rest of the episode.
    """
    frame = _rgb_message(sim, scene, intrinsics, backend, 0.0)
    best_area = -1
    best_color = scene.palette[0][0]
    for name, _rgb in scene.palette:
        detections = detect_cubes(
            frame, name, scene=scene, intrinsics=intrinsics, pose=pose
        )
        if detections and detections[0].area > best_area:
            best_area = detections[0].area
            best_color = name
    return best_color


def run_episode(
    seed: int = LAB_SEED,
    *,
    backend: str = "kinematic",
    bridge_name: str = "localbus",
    out_dir: str | Path | None = None,
    target_color: str | None = None,
    target_override: tuple[float, float, float] | None = None,
    max_ticks: int = 4000,
    write_frames: bool = True,
    verbose: bool = True,
) -> dict:
    scene = SceneConfig()
    arm = ArmConfig()
    intrinsics = CameraIntrinsics()
    out = Path(out_dir) if out_dir else Path(f"artifacts/episodes/seed_{seed}")
    out.mkdir(parents=True, exist_ok=True)

    sim = make_backend(
        backend,
        scene=scene,
        arm=arm,
        seed=seed,
        usda_path=Path("usd/tabletop_seed7.usda"),
        enable_ros2=(bridge_name == "ros2"),
    )
    if backend == "isaac":
        sim.start()
    # The USB camera transform and the CPU look-at agree; use the scene pose.
    camera_pose = None
    if target_color is None and target_override is None:
        target_color = _most_visible_palette_color(
            sim, scene, intrinsics, backend, pose=camera_pose
        )

    bridge = make_bridge(bridge_name)
    if backend == "isaac":
        bridge.subscribe(CMD_JOINT_TOPIC, lambda m: sim.apply_joint_velocities(m.velocities))
        bridge.subscribe(GRIPPER_CMD_TOPIC, lambda m: sim.apply_gripper(m.closure))
    else:
        bridge.subscribe(CMD_JOINT_TOPIC, lambda m: sim.command_joint_velocities(m.velocities))
        bridge.subscribe(GRIPPER_CMD_TOPIC, lambda m: sim.command_gripper(m.closure))

    last_command: dict[str, dict] = {}
    bridge.subscribe(CMD_JOINT_TOPIC, lambda m: last_command.__setitem__("joint", m.to_dict()))
    bridge.subscribe(
        GRIPPER_CMD_TOPIC, lambda m: last_command.__setitem__("gripper", m.to_dict())
    )

    controller = PickPlaceController(
        scene,
        arm,
        intrinsics,
        bridge,
        target_color=target_color,
        target_override=target_override,
        camera_pose=camera_pose,
        center_offset=(backend == "isaac"),
        max_ticks=max_ticks,
    )

    frame_000_sha = None
    frame_final_sha = None
    if write_frames:
        first = _rgb_message(sim, scene, intrinsics, backend, 0.0)
        frame_000_sha = _save_rgb(first, out / "frame_000.png")

    trajectory_path = out / "trajectory.jsonl"
    trajectory_hash = hashlib.sha256()
    last_rgb_meta: dict | None = None
    status: LabStatus | None = None

    try:
        with trajectory_path.open("w", encoding="utf-8") as trajectory:
            for tick in range(max_ticks):
                joint_state = sim.joint_state()
                cube_poses: CubePoseArray = sim.cube_pose_array()
                bridge.publish(JOINT_STATES_TOPIC, joint_state)
                bridge.publish(CUBE_POSES_TOPIC, cube_poses)

                rgb_message = None
                if tick % RGB_PERIOD_TICKS == 0:
                    rgb_message = _rgb_message(
                        sim, scene, intrinsics, backend, float(tick) / 60.0
                    )
                    bridge.publish(RGB_TOPIC, rgb_message)
                    last_rgb_meta = rgb_message.to_dict(include_data=False)
                    last_rgb_meta["data_sha256"] = _sha256_bytes(rgb_message.data)

                bridge.spin_once()
                controller.step()
                bridge.spin_once()
                sim.step()

                status = LabStatus(
                    stamp=float(tick + 1) / 60.0,
                    tick=tick,
                    state=controller.state,
                    success=controller.success,
                    message=controller.failure_reason or "",
                )
                bridge.publish(STATUS_TOPIC, status)

                messages = {
                    JOINT_STATES_TOPIC: joint_state.to_dict(),
                    CUBE_POSES_TOPIC: cube_poses.to_dict(),
                    STATUS_TOPIC: status.to_dict(),
                }
                if "joint" in last_command:
                    messages[CMD_JOINT_TOPIC] = last_command["joint"]
                if "gripper" in last_command:
                    messages[GRIPPER_CMD_TOPIC] = last_command["gripper"]
                if rgb_message is not None and last_rgb_meta is not None:
                    messages[RGB_TOPIC] = last_rgb_meta
                record = {
                    "tick": tick,
                    "time_s": float(tick + 1) / 60.0,
                    "messages": messages,
                }
                line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
                trajectory.write(line)
                trajectory_hash.update(line.encode("utf-8"))
                if controller.done:
                    break
    finally:
        if write_frames:
            final_frame = _rgb_message(
                sim, scene, intrinsics, backend, float(controller.tick) / 60.0
            )
            frame_final_sha = _save_rgb(final_frame, out / "frame_final.png")

    if not controller.done:
        controller.abort("MAX_TICKS")
    status = LabStatus(
        stamp=float(controller.tick) / 60.0,
        tick=controller.tick,
        state=controller.state,
        success=controller.success,
        message=controller.failure_reason or "",
    )

    cube_states = sim.cube_pose_array()
    final_positions = {
        name: [float(v) for v in position]
        for name, position in zip(cube_states.names, cube_states.positions, strict=True)
    }
    summary = {
        "schema": "isaac_starter_lab.episode_summary.v1",
        "seed": seed,
        "backend": backend,
        "bridge": bridge_name,
        "target_color": controller.target_color,
        "target_cube": controller.target_cube_name,
        "success": bool(controller.success),
        "state": controller.state,
        "failure_reason": controller.failure_reason,
        "cycle_time_s": float(sim.time_s),
        "ticks": int(controller.tick),
        "final_cube_positions": final_positions,
        "trajectory_sha256": trajectory_hash.hexdigest(),
        "trajectory_messages": controller.tick,
        "frame_000_sha256": frame_000_sha,
        "frame_final_sha256": frame_final_sha,
    }
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    bridge.close()
    if backend == "isaac":
        sim.close()

    if verbose:
        outcome = "SUCCESS" if summary["success"] else f"FAILED ({summary['failure_reason']})"
        print(f"episode seed={seed} backend={backend} bridge={bridge_name}")
        print(f"  target: {controller.target_color} ({controller.target_cube_name})")
        print(f"  {outcome} in {summary['cycle_time_s']:.3f} s / {summary['ticks']} ticks")
        print(f"  summary: {out / 'summary.json'}")
    return summary


def run_episode_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    out = Path(args.out) if args.out else Path(f"artifacts/episodes/seed_{args.seed}")
    if not out.is_absolute():
        out = root / out
    run_episode(
        seed=args.seed,
        backend=args.backend,
        bridge_name=args.bridge,
        out_dir=out,
        target_color=args.target_color,
        max_ticks=args.max_ticks,
    )
    return 0
