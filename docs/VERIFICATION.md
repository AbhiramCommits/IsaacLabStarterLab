# Verification status

This file records what has been executed and what is gated on hardware. It is
updated at the end of every step. "Executed" means a command ran on the host
described below and its output is committed under `results/`.

## Host

| Item | Value |
| --- | --- |
| Host OS | macOS 27.2.1 (arm64), not Linux |
| Python used for the CPU track | CPython 3.11.14 (`.venv`) |
| Supported Python | 3.10, 3.11, 3.12 (`pyproject.toml`) |
| GPU | none (Apple Silicon, no CUDA) |
| Isaac Sim / Isaac Lab | not installed on the Mac |
| ROS 2 / `rclpy` | not installed on the Mac |
| Docker | Docker 29.8.2, Linux containers via `linux/amd64` emulation |
| OpenUSD | `usd-core==25.11` (real `pxr` Python API) |

The CPU headless path is pure Python plus the real `pxr`, NumPy and Pillow
wheels, and its determinism is tested on this machine. Linux-specific behaviour
is exercised by the Docker image and by GitHub Actions (`ubuntu-latest`).

## Executed

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
| pytest suite | `tests/` | executed locally and in CI |
| Docker lab image | `docker/Dockerfile.lab` | executed (amd64 emulation) |
| CI workflow | `.github/workflows/ci.yml` | green on GitHub Actions (run 42359023945, `main`) |

## GPU track status

The GPU track was exercised on Secure and Community RTX 4090 / L40S pods
(driver 595.91.07). It is **mostly executed**:

| Component | Path | Status |
| --- | --- | --- |
| Isaac Sim backend | `src/isaac_starter_lab/sim/isaac_backend.py` | executed on Isaac Sim 6.0: runtime 7-DOF arm, seed-7 pick SUCCESS, 100-seed PhysX sweep 40/100 |
| Isaac Lab task | `src/isaac_starter_lab/isaac_lab/pick_place_task.py` | executed on Isaac Lab 3.0.0 / Isaac Sim 6.0.1: 1500 PPO iterations, 2,304,000 env steps |
| Isaac Lab dataclass config | `src/isaac_starter_lab/isaac_lab/pick_place_env_cfg.py` | CPU-only mirror; validated on CPU, not used by the run |
| `rclpy` transport | `src/isaac_starter_lab/bridge/ros2_bridge.py` | executed on ROS 2 Jazzy: 60 Hz joint states, 8.2 Hz RGB, recorded bag |
| ROS 2 ament package | `ros2_ws/src/starter_lab/` | executed: `colcon build` succeeded; controller, bridge and perception nodes ran |
| GPU image | `docker/Dockerfile.isaac` | built and pushed as `madridista23/isaac-sim-60-root:latest`; starts on this driver |

### What failed, in order

- **Isaac Sim 4.5** segfaulted in `omni.usdphysics.ui` overlays with driver
  595.91.07. With the overlay patched and the main viewport disabled, the app
  started and PhysX worked (minimal articulation DOF 1), but camera frames were
  empty and the canonical arm reported 0 DOF.
- **Isaac Sim 5.1** (stock image) runs as uid 1234 with no `sudo`, `sshd` or
  `rsync`; `apt-get` fails with
  `E: List directory /var/lib/apt/lists/partial is missing - Acquire (13: Permission denied)`.
  5.1 via pip inside the 4.5 container segfaulted in `libomni.usd.so`.
- **Isaac Sim 6.0** starts and renders on driver 595.91.07. The canonical arm
  reports 5 DOF but is unstable under drives (nested rigid bodies), so the
  backend now builds a flat runtime arm (`/World/RobotIsaac`): fixed base, five
  revolute links, a fixed jaw and one moving jaw, self-collision off, 240 Hz
  physics.
  The canonical green cube is at `(0.104,-0.053)` and the RTX detection at
  `(374,252)` matches it. With a fixed jaw and one moving jaw, the seed-7
  episode **succeeds**: state DONE, 272 ticks, 4.533 s, `Cube_01` at
  `(0.214,0.113,0.775)` inside the bin. Artifacts in `results/gpu/seed_7/`.
  A 100-seed sweep with per-seed `lab-scene` stages succeeded **40/100 (40%)**;
  cycle mean 4.744 s, p95 7.733 s; failures `TIMEOUT_DESCEND` 41,
  `TIMEOUT_TRANSFER` 11, `CUBE_NOT_IN_BIN` 7, `NO_DETECTION` 1
  (`results/gpu/isaac_sweep.json`).

  The RTX perception comparison completed on 200 DR-matched scenes: one USD
  per seed (`scripts/make_rtx_scenes.py`), one RTX frame per seed
  (`scripts/render_rtx_seeds.py`) and an evaluator
  (`scripts/evaluate_rtx_perception.py`). RTX: recall 0.9551, precision 0.9521,
  pixel error mean 2.968 px (p95 4.767), 3D error mean 12.073 mm (p95 21.856).
  Pinhole: 1.0000/1.0000, 1.058 px, 3.607 mm. The RTX gap is real:
  `results/gpu/rtx_perception.json`.

RTX artifacts from the seed-7 run (start/final frame, trajectory, summary) are
committed under `results/gpu/seed_7/`; `summary.json` records
`failure_reason: null` and `Cube_01` inside the bin at
`(0.214, 0.113, 0.775)`.

The Docker and no-Docker install paths were updated (`docker/Dockerfile.isaac`,
`scripts/setup_isaac_nodocker.sh`) so they do not replace Isaac Sim's bundled
`pxr`/`numpy`. The root/SSH 6.0 image that ran is published at
`madridista23/isaac-sim-60-root:latest`.

## Isaac Lab + PPO evidence

Run on the `nvcr.io/nvidia/isaac-lab:3.0.0-beta2` image (Isaac Sim 6.0.1,
Isaac Lab 3.0.0, rsl_rl 5.0.1) on a Secure RTX 4090 (EU-RO-1).

| Command | Observed |
| --- | --- |
| `scripts/isaac_lab_smoke.py --num_envs 32 --steps 2000 --random_actions` | `SMOKE_OK`; no NaN |
| `train.py --task IsaacLabStarterLab-PickPlace-v0 --num_envs 32 --max_iterations 1500` | 1500 iterations, 2,304,000 steps, 2346.69 s, mean 986 steps/s |
| reaching reward | 0.043 at iteration 0, 0.50 by ~iteration 200, ~0.50 at 1499 |
| lifting reward | peaks 0.389, returns to 0.0 |
| success termination | 0.0 for every iteration |
| checkpoints | `model_{250,500,750,1000,1250,1499}.pt`, 1.1 MB each (not committed) |

The task uses our own arm (`usd/lab_arm.usda`) and table (`usd/lab_task_seed7.usda`),
so it is the same robot as the PhysX sweep, with fingers-only collision geometry
and joint armature added for multi-environment stability at 240 Hz.
The policy learns to reach and does not learn to grasp or place; no success
rate is claimed.

## Scene determinism evidence

Executed on the host:

```
lab-scene --seed 7 --out artifacts/scene_seed7.usda
hash: af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40
prims: 46
```

`tests/test_scene.py` (33 tests) confirms identical hashes for identical seeds,
different hashes for different seeds, cube non-overlap and containment, prim
types and the camera-intrinsics round-trip. The committed canonical stage
`usd/tabletop_seed7.usda` hashes to the pinned value above.

## Backend and renderer evidence

Executed on the host (CPU only):

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

## ROS 2, perception, controller and DR evidence

All CPU-track numbers below were produced by the commands shown and stored under
`results/`.

| Command | Observed |
| --- | --- |
| `make dr` (200 seeds) | 200 images + labels, dataset hash `e112f454d426badab50614ce74e4dcb418ad770417a62d841bf30775f9b9b4dc`, 4.8 s |
| `lab-eval perception` | 200 seeds / 1000 cubes; pixel error mean 1.058 px, p95 3.577 px; 3D error mean 3.607 mm, p95 12.885 mm; recall 1.0000, precision 1.0000; 105 centre-occluded cubes reported separately |
| `lab-eval episodes` (100 seeds) | 100/100 success; mean 5.165 s, p95 5.467 s; no failure reasons |
| `pytest -q` | 145 passed |
| `ruff check .` | clean |

The `localbus` transport, `kinematic` backend, `detect_cubes` and the full
`PickPlaceController` state machine were executed. The ROS 2 `rclpy` transport
and the `starter_lab` ament package were executed on the Isaac Sim 6.0 pod, not
on the Mac (there is no ROS 2 installation there). On the Mac only the
missing-`rclpy` guard and package-file structure are tested. The Isaac backend is
executed (see above).

## ROS 2 transport evidence (Isaac Sim 6.0 pod, ROS 2 Jazzy)

| Command | Observed |
| --- | --- |
| `ros2 node list` | `/starter_lab_controller`, `/starter_lab_controller_bridge`, `/starter_lab_perception` |
| `ros2 topic hz /lab/joint_states` | 60.001 Hz |
| `ros2 topic hz /lab/rgb` | 8.210 Hz |
| `ros2 topic hz /lab/cmd_joint` (controller active) | 6.380 Hz |
| image → `/lab/perception` latency, 20 samples | mean 31.01 ms, p95 35.48 ms |
| `ros2 bag record` (6 topics) | 9.867 s, 1975 messages: rgb 98, joint_states 593, cube_poses 593, status 592, perception 99 |
| distributed seed 7 | `TIMEOUT_HOME` at tick 181; lockstep localbus succeeds in 272 ticks / 4.533 s |

The bag's `/lab/cmd_joint` count is 0 because it was recorded after the
controller had already failed HOME; the 6.38 Hz rate was measured while the
controller was still active. Source: `results/gpu/ros2_transport.json`.

## Guide tooling evidence

| Check | Result |
| --- | --- |
| `labcheck all` on generated artifacts | PASS, 45 checks |
| `lab-quiz` with a temporary answer file | 8/8, wrote `artifacts/quiz_result.json` |
| `scripts/check_mermaid.py` | 3 diagrams parsed, no dangling ids |
| `pytest -q` | 145 passed |
| `ruff check .` | clean |
| Walkthrough recording | `demo/walkthrough.log` captured with the `script` fallback (asciinema not installed); four PNGs in `demo/frames/` |
| Reference screenshots | `docs/img/*.png` generated by `scripts/make_reference_images.py` from real scene/episode/dataset output |

The guide's troubleshooting entries were produced by triggering each error and
quoting the exact message. The GPU exercise is documentation only on the Mac.

## Full pipeline, determinism and Docker evidence

| Check | Result |
| --- | --- |
| `make lab-headless` (native) | PASS, 51.823 s total: scene 0.095, DR 4.514, episode 0.353, perception eval 12.492, episode sweep 33.702, labcheck 0.667 |
| `make test` | 145 passed, 88.20% statement coverage (threshold 85%), 154.75 s including the full determinism test |
| `scripts/check_determinism.py` (full 200-seed / 100-episode run twice) | 610 artifacts compared, hashes identical, 124.65 s |
| `scripts/extract_guide_commands.py` | all 15 marked guide blocks passed, 75.51 s |
| `make lint` / `make check` | clean / PASS 45 checks |
| Docker lab image (`linux/amd64` under emulation) | build succeeded; full `make lab-headless` passed in 949.704 s |

The Docker run exposed a real portability bug: the same seed exported
translations with a last-bit difference on Linux, so the pinned scene hash did
not match. `scene/hashing.py` now canonicalises floating-point literals to nine
decimal places before hashing
(`sha256-flattened-usda-canonical-floats-9`). The rebuilt image produces the same
scene hash as the host:
`af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40`.

The **dataset** hash is environment-specific because PNG bytes and
full-precision label floats differ between platforms; every perception metric is
identical. `labcheck ex4` recomputes against the manifest in the current
environment rather than a hardcoded dataset hash.

The pinhole perception evaluation had a ground-truth bug: a cube was marked
invisible when its projected centre pixel was hidden, even with hundreds of
rendered pixels, and precision matched only to the projected centre. The 128
"false positives" were all detections of real cubes whose visible-pixel centroid
is offset by partial occlusion; no detection was of a non-existent object. The
label now records `visible = visible_pixels > 0` and a separate `centre_visible`,
and matching accepts a detection inside the cube's visible box. Full analysis:
`results/perception_fp_analysis.json`.

CI is green on GitHub Actions. Its `gpu-isaac` job is a documented, skipped
placeholder for a self-hosted NVIDIA runner.

## Cold-run evidence

The repository owner's cold run is recorded in `learner-testing/cold_runs/`.
External human testers remain pending, as stated in
`learner-testing/TESTERS.md`.

| Run | Environment | Result | Issue(s) |
| --- | --- | --- | --- |
| owner run 1 | fresh clone, fresh venv, CPython 3.11.14 | PASS 45 checks in 67 s | — |

## Final status

The repository is self-contained on the CPU track: the scene, renderer, dataset,
evaluation, grader, tests, guide commands, Docker image and walkthrough all run.
On the GPU pods, Isaac Sim 6.0 runs a real 7-DOF PhysX arm (40/100 physical
seeds), RTX perception is compared against the pinhole renderer, ROS 2 Jazzy
carries the topics, and Isaac Lab 3.0 trains a PPO policy on the same arm. The
one open result is behavioural: the PPO policy reaches but does not grasp, and
the distributed ROS 2 pick times out. Both are stated as such in the README,
the guide and this file.
