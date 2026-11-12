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

## GPU-gated and unexecuted

| Component | Path | Why it did not run |
| --- | --- | --- |
| Isaac Sim backend | `src/isaac_starter_lab/sim/isaac_backend.py` | requires NVIDIA GPU + `nvcr.io/nvidia/isaac-sim:4.5.0`; only the import guard and message mapping are tested |
| Isaac Lab task config | `src/isaac_starter_lab/isaac_lab/pick_place_env_cfg.py` | requires Isaac Lab on a GPU host; dataclass validation is tested on CPU |
| `rclpy` transport | `src/isaac_starter_lab/bridge/ros2_bridge.py` | requires a ROS 2 installation; only the missing-`rclpy` error path is tested |
| ROS 2 ament package build | `ros2_ws/src/starter_lab/` | requires ROS 2 Humble/Jazzy; source only |
| GPU Isaac Sim image | `docker/Dockerfile.isaac` | GPU-host-only; never built |

### GPU attempt, 2026-11-12

A Secure RTX 4090 pod was created in EU-RO-1 (driver 595.91.07, 75 GB disk;
100 GB was unavailable). The Isaac Sim 4.5 image started, opened
`usd/tabletop_seed7.usda` and ran PhysX, but the RTX renderer did not work:

- The default app segfaulted in `omni.usdphysics.ui` immediate-mode overlays
  inside `_wait_for_viewport`.
- Patching that overlay and the file-menu stage handler, and disabling the main
  viewport window, let the app start and step physics; a minimal articulation
  reported DOF 1.
- With the viewport enabled, `app.update()` still segfaulted on driver
  595.91.07. With it disabled, `Camera.get_rgba()` returned an empty array and
  `rep.orchestrator.step()` hung, so no RTX frame was produced.
- The canonical arm reported 0 DOF at `/World/Robot` and `/World/Robot/base`:
  the rigid bodies are nested and the joints sit outside the articulation root.

A second pod with the Isaac Sim 5.1 image could not be used: it runs as uid 1234
(`isaac-sim`) with no `sudo`, `sshd` or `rsync`, and `apt-get` fails with
`E: List directory /var/lib/apt/lists/partial is missing - Acquire (13: Permission denied)`.
A user-space OpenSSH install did not serve SSH. Installing Isaac Sim 5.1 from pip
inside the 4.5 container completed, but `SimulationApp` segfaulted in
`libomni.usd.so` at startup because the 5.1 libraries were mixed with the 4.5
container's USD/Kit libraries.

Both pods were terminated; `list-pods` is empty. No GPU number was produced.
The remaining path is a custom 5.1 image with `USER root` and openssh/rsync, or
a host with an R580 production driver for 4.5.

The Docker and no-Docker install paths were updated (`docker/Dockerfile.isaac`,
`scripts/setup_isaac_nodocker.sh`) so they do not replace Isaac Sim's bundled
`pxr`/`numpy`, but neither was executed.

No success-rate or accuracy number in this repository comes from the GPU path.
Every measured number is produced by the CPU headless path and stored under
`results/`.

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
and the `starter_lab` ament package were **not** executed on the Mac: there is no
ROS 2 installation there. Only the missing-`rclpy` guard and package-file
structure are tested. The Isaac backend remains GPU-gated.

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
The GPU Isaac Sim path, the `rclpy` transport, the Isaac Lab environment and RTX
perception are unexecuted: Runpod had no GPU capacity for the planned run. They
are labelled as unexecuted in the README, the guide and this file.
