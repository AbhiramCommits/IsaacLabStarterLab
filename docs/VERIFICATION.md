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
hash: af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40
prims: 46
```

`tests/test_scene.py` (33 tests) confirms identical hashes for identical
seeds, different hashes for different seeds, cube non-overlap and containment,
prim types and the camera-intrinsics round-trip. The committed canonical stage
`usd/tabletop_seed7.usda` hashes to the pinned value above.

## Backend and renderer evidence (Step 3)

Executed on the build machine (CPU only):

| Check | Result |
| --- | --- |
| `pytest tests/test_kinematic.py tests/test_render.py tests/test_isaac_adapters.py` | 30 passed |
| Forward kinematics hand-computed poses | matches to 1e-9 |
| Analytic IK round-trip at four tabletop targets | error < 1e-9 m |
| Two 180-tick command sequences from seed 7 | identical joint states, cube positions and message dicts |
| `project_point` / `backproject_to_plane` round-trip | pixel error < 1e-6, 3D error < 1e-6 m |
| Software render | 640x480 uint8, ~16 ms/frame on this CPU |
| Isolated cube rendered centroid vs projected centre | < 1 px |
| `IsaacSimBackend.start()` without Isaac Sim | raises `IsaacUnavailableError` naming the container, `--gpus all`, and `LAB_BACKEND=isaac` |
| Isaac Lab dataclass config | validated on CPU; no Isaac Lab import at module load |

`IsaacSimBackend`, the ROS 2 bridge and the Isaac Lab environment remain
GPU/ROS-gated and were not executed. Their import guards and configuration
validation are covered by tests.

## ROS 2, perception, controller and DR evidence (Step 4)

All CPU-track numbers below were produced by the commands shown on the build
machine and stored under `results/`.

| Command | Observed |
| --- | --- |
| `make dr` (200 seeds) | 200 images + labels, dataset hash `9f14c0388aafd557c4325ebbc47319198c3fd1dac8786c9b9f106723b3b90c96`, 4.8 s |
| `lab-eval perception` | 200 seeds / 1000 cubes; pixel error mean 1.058 px, p95 3.577 px; 3D error mean 3.607 mm, p95 12.885 mm; recall 0.9611, precision 0.8693 |
| `lab-eval episodes` (100 seeds) | 100/100 success; mean 5.165 s, p95 5.467 s; no failure reasons |
| `pytest -q` | 87 passed |
| `ruff check .` | clean |

The `localbus` transport, `kinematic` backend, `detect_cubes` and the full
`PickPlaceController` state machine were executed. The ROS 2 `rclpy` transport
and the `starter_lab` ament_package were **not** executed: this machine has no
ROS 2 installation. Only the missing-`rclpy` guard and package-file structure are
tested. The Isaac backend remains GPU-gated.

## Guide tooling evidence (Step 5)

| Check | Result |
| --- | --- |
| `labcheck all` on generated artifacts | PASS, 45 checks |
| `lab-quiz` with a temporary answer file | 8/8, wrote `artifacts/quiz_result.json` |
| `scripts/check_mermaid.py` | 3 diagrams parsed, no dangling ids |
| `pytest -q` | 109 passed |
| `ruff check .` | clean |
| Walkthrough recording | `demo/walkthrough.log` captured with the `script` fallback (asciinema not installed); four PNGs in `demo/frames/` |
| Reference screenshots | `docs/img/*.png` generated by `scripts/make_reference_images.py` from real scene/episode/dataset output |

The guide's troubleshooting entries were produced by deliberately triggering
each error during this build; the exact messages are quoted from those runs.
The GPU exercise is documentation only and was not executed.

## Full pipeline, determinism and Docker evidence (Step 6)

| Check | Result |
| --- | --- |
| `make lab-headless` (native) | PASS, 51.823 s total: scene 0.095, DR 4.514, episode 0.353, perception eval 12.492, episode sweep 33.702, labcheck 0.667 |
| `make test` | 145 passed, 88.20% statement coverage (threshold 85%), 154.75 s including the full determinism test |
| `scripts/check_determinism.py` (full 200-seed / 100-episode run twice) | 610 artifacts compared, hashes identical, 124.65 s |
| `scripts/extract_guide_commands.py` | all 15 marked guide blocks passed, 75.51 s |
| `make lint` / `make check` | clean / PASS 45 checks |
| Docker lab image (`linux/amd64` under emulation) | build succeeded; full `make lab-headless` passed in 949.704 s (scene 0.888, DR 65.051, episode 5.670, perception eval 355.152, episode sweep 513.961, labcheck 8.981) |

The Docker run exposed a real portability bug: the same seed exported
translations with a last-bit difference on Linux, so the pinned scene hash did
not match. `scene/hashing.py` now canonicalises floating-point literals to nine
decimal places before hashing (`sha256-flattened-usda-canonical-floats-9`). The
rebuilt image produces the same scene hash as the host:
`af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40`.

The **dataset** hash remains environment-specific (`9f14c038...` native,
`f868fa8b...` in the Docker image) because PNG bytes and full-precision label
floats differ between platforms; every perception metric is identical. This
scope is stated in the guide and the README results are labelled as build-machine
measurements. `labcheck ex4` recomputes against the manifest in the current
environment rather than a hardcoded dataset hash.

The GitHub Actions workflow is syntactically valid and parsed locally, but the
jobs were not executed on GitHub from this machine. Its `gpu-isaac` job is a
documented, skipped placeholder for a self-hosted NVIDIA runner.
