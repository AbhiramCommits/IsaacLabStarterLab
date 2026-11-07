# Verification status

This file records what was actually executed while building the repository and
what is GPU-gated. It is updated at the end of every step. "Executed" means a
command ran on the build machine in this session and its output is committed
under `results/`.

## Build machine

| Item | Value |
| --- | --- |
| Host OS | macOS 27.2 (arm64), not Linux |
| Python used for the build | CPython 3.11.14 (`.venv`) |
| Supported Python | 3.10, 3.11, 3.12 (`pyproject.toml`) |
| GPU | none (Apple Silicon, no CUDA) |
| Isaac Sim / Isaac Lab | not installed |
| ROS 2 / `rclpy` | not installed |
| Docker | Docker 29.8.2, Linux containers via `linux/amd64` emulation |
| OpenUSD | `usd-core==25.11` (real `pxr` Python API) |

The build host is macOS rather than Linux. The CPU headless path is pure Python
plus the real `pxr`, NumPy and Pillow wheels, and its determinism is tested on
this machine. Linux-specific behaviour is exercised by the Docker image and by
GitHub Actions (`ubuntu-latest`); the Docker cold run is recorded in
`learner-testing/cold_runs/run_3.md`.

## Executed in this build

| Component | Path | Status |
| --- | --- | --- |
| OpenUSD scene builder + hashing | `src/isaac_starter_lab/scene/` | executed, hash pinned in `usd/EXPECTED_HASHES.json` |
| CPU kinematic simulator | `src/isaac_starter_lab/sim/kinematic.py` | executed |
| Software pinhole renderer | `src/isaac_starter_lab/render/pinhole.py` | executed |
| Local in-process bus | `src/isaac_starter_lab/bridge/localbus.py` | executed |
| Perception + controller | `src/isaac_starter_lab/perception.py`, `controller.py` | executed |
| DR dataset generation | `src/isaac_starter_lab/datasets/dr.py` | executed |
| Perception / episode evaluation | `src/isaac_starter_lab/evaluation.py` | executed |
| Self-check grader | `src/isaac_starter_lab/grading.py` | executed |
| Knowledge-check grading | `src/isaac_starter_lab/quiz.py` | executed |
| pytest suite | `tests/` | executed locally |
| Docker lab image | `docker/Dockerfile.lab` | executed (amd64 emulation) in Step 7 cold run |
| CI workflow | `.github/workflows/ci.yml` | configuration only; not executed on GitHub from this machine |

## GPU-gated and unexecuted

| Component | Path | Why it did not run |
| --- | --- | --- |
| Isaac Sim backend | `src/isaac_starter_lab/sim/isaac_backend.py` | requires NVIDIA GPU + `nvcr.io/nvidia/isaac-sim:4.5.0`; only the import guard and message mapping are tested |
| Isaac Lab task config | `src/isaac_starter_lab/isaac_lab/pick_place_env_cfg.py` | requires Isaac Lab on a GPU host; dataclass validation is tested on CPU |
| `rclpy` transport | `src/isaac_starter_lab/bridge/ros2_bridge.py` | requires a ROS 2 installation; only the missing-`rclpy` error path is tested |
| ROS 2 ament package build | `ros2_ws/src/starter_lab/` | requires ROS 2 Humble/Jazzy; source only |
| GPU Isaac Sim image | `docker/Dockerfile.isaac` | GPU-host-only; never built in CI |

No performance, success-rate or accuracy number in this repository comes from
the GPU path. Every measured number is produced by the CPU headless path and
stored under `results/`.

## Scene determinism evidence (Step 2)

Executed on the build machine:

```
lab-scene --seed 7 --out artifacts/scene_seed7.usda
hash: ea579b2f4ed56d1b68134217e1645aac5602d6b883f4bb8c25bffa72f3587f04
prims: 46
```

`tests/test_scene.py` (33 tests) confirms identical hashes for identical
seeds, different hashes for different seeds, cube non-overlap and containment,
prim types and the camera-intrinsics round-trip. The committed canonical stage
`usd/tabletop_seed7.usda` hashes to the pinned value above.
