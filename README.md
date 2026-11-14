# IsaacLabStarterLab

A tabletop pick-and-place teaching lab built on a real OpenUSD scene.
A deterministic CPU track runs anywhere; a GPU track targets Isaac Sim 6.0,
Isaac Lab and ROS 2 through the same message schema.
The CPU track is tested and measured; the GPU track runs a real 7-DOF PhysX arm
and completes 40 of 100 seeds on a physical 100-seed sweep. The CPU kinematic
100% is a logic check, not a physics result (see
[Validated vs not validated](#validated-vs-not-validated)).

Built and tested on macOS arm64 with CPython 3.11; the test host has no NVIDIA
GPU and no ROS 2 installation.

## Quickstart

Five commands from a clone to a graded `labcheck all` on the CPU track:

```bash
git clone https://github.com/AbhiramCommits/IsaacLabStarterLab.git IsaacLabStarterLab && cd IsaacLabStarterLab
python3.11 -m venv .venv && source .venv/bin/activate
make install
make lab-headless
labcheck all
```

`make lab-headless` generates the scene, a 200-seed domain-randomisation dataset,
a seed-7 episode, the perception evaluation and a 100-episode sweep, then grades
the artifacts. The owner cold run of these commands took 67 s on
CPython 3.11.14 and passed all 45 checks.

## Results

### GPU track — Isaac Sim 6.0 / PhysX (real physics)

| Metric | Measured value |
| --- | --- |
| Seed-7 episode | **SUCCESS**, 272 ticks, 4.533 s, green `Cube_01` in the bin |
| 100-seed sweep | **40/100 (40.00%)** |
| Failure codes | `TIMEOUT_DESCEND` 41, `TIMEOUT_TRANSFER` 11, `CUBE_NOT_IN_BIN` 7, `NO_DETECTION` 1 |
| Cycle time | mean 4.744 s, p95 7.733 s, max 7.833 s |
| Ticks | mean 284.66, max 470 |

These are real PhysX results: contact, friction, a physical gripper and a
rendered RGB camera. The CPU table below is the kinematic logic check; its
100/100 is not a physics claim. Source: `results/gpu/isaac_sweep.json` and
`results/gpu/seed_7/`.

### Pinhole vs RTX perception (same 200 DR scenes)

| Metric | Pinhole (CPU ray caster) | RTX (Isaac Sim 6.0) |
| --- | --- | --- |
| Pixel error, mean / p95 | 1.058 / 3.577 px | 2.968 / 4.767 px |
| 3D error, mean / p95 | 3.607 / 12.885 mm | 12.073 / 21.856 mm |
| Recall | 100.00% | 95.51% |
| Precision | 100.00% | 95.21% |
| Detections / TP / FP / FN | 979 / 979 / 0 / 0 | 982 / 935 / 47 / 44 |

Same labels, camera and cube layout; the RTX frames add shading, shadows and
anti-aliasing. The pixel/3D errors are computed on the unoccluded-centre subset
(840 pinhole, 336 RTX); many RTX visible centroids shift more than 5 px under
shading/occlusion. Source: `results/gpu/rtx_perception.json`. The gap is real and
is not hidden.

### CPU track — kinematic logic check (no physics)

<!-- RESULTS:START -->
| Metric | Measured value |
| --- | --- |
| Scene hash (seed 7) | `af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40` |
| Scene prim count | 46 |
| DR dataset | 200 frames, hash `e112f454d426badab50614ce74e4dcb418ad770417a62d841bf30775f9b9b4dc` |
| Pinhole pixel error (logic check) | mean 1.058 px, p95 3.577 px |
| Pinhole 3D error (logic check) | mean 3.607 mm, p95 12.885 mm |
| Pinhole recall / precision (logic check) | 100.00% / 100.00% |
| Kinematic episode success, 100 seeds (no physics) | 100/100 (100.00%); failures: none |
| Kinematic cycle time (no physics) | mean 5.165 s, p95 5.467 s |
| Per-stage timings | scene 0.06 s, dr 4.36 s, episode 0.33 s, perception_eval 11.20 s, episode_eval 30.16 s, labcheck 0.50 s |
| Determinism | 2 runs, 610 artifacts, hashes identical |
| Test suite | 145 tests, 0 failures, 88.20% statement coverage |
| CI jobs | test, lab, determinism, docker, gpu-isaac |
| Labcheck | PASS, 45 checks |
| Learner testing | 1 cold run, 2 issues filed, 2 fixed |

All values are read from the JSON files under `results/` and the committed dataset manifest by `scripts/collect_results.py`; the GPU track is not included.

<!-- RESULTS:END -->

The pinhole and kinematic rows are a **logic check**: they show that the scene,
message schema, detector and state machine are consistent. They are not physics
or camera-perception measurements. No Isaac Sim, PhysX, Isaac Lab, RTX or ROS 2
number exists in this repository.

## Validated vs not validated

Validated on the CPU track:

- OpenUSD scene generation with a pinned cross-platform hash (46 prims).
- `KinematicSim`, the pinhole renderer and the in-process bus.
- `detect_cubes`, `PickPlaceController`, the 200-seed dataset and the
  100-episode sweep.
- `labcheck` (45 checks), the pytest suite, the Docker lab image and CI.
- The Isaac Sim 6.0 seed-7 PhysX pick and the 100-seed physical sweep
  (40/100; `results/gpu/`).

Not validated:

- The Isaac Lab task, ROS 2 nodes and the RTX perception comparison. The
  physical sweep is done; the 60 failures are recorded in
  `results/gpu/isaac_sweep.json` and were not tuned further. The RTX comparison
  tooling is committed (`scripts/make_rtx_scenes.py`,
  `scripts/render_rtx_seeds.py`, `scripts/evaluate_rtx_perception.py`) but the
  Runpod account balance ran out before the frames were rendered.
- The Isaac Lab `ManagerBasedRLEnv` task, 64-environment throughput and PPO.
- The `rclpy` transport, the ROS 2 nodes and the Isaac Sim ROS 2 bridge.
- RTX-frame perception and the pinhole-to-RTX gap.
- The GPU image in `docker/Dockerfile.isaac`.

## How to run

### CPU track (works anywhere)

The quickstart above is the whole CPU track. `docs/LAB_GUIDE.md` walks through
the scene, the detector, the controller, the dataset and the grader.
`docs/LAB_GUIDE.md` and `docs/WALKTHROUGH.md` are the reading path.

### GPU track (partially run)

Both routes use the same code. The Docker route:

```bash
docker build -f docker/Dockerfile.isaac -t isaac-starter-lab:gpu .
docker run --rm -it --gpus all --network host \
  -e ACCEPT_EULA=Y -e PRIVACY_CONSENT=Y \
  -e LAB_BACKEND=isaac -e LAB_BRIDGE=ros2 \
  -v "$HOME/.cache/ov:/root/.cache/ov" \
  -v "$HOME/.cache/pip:/root/.cache/pip" \
  -v "$HOME/.cache/nvidia:/root/.cache/nvidia" \
  -v "$HOME/.local/share/ov:/root/.local/share/ov" \
  isaac-starter-lab:gpu
```

The no-Docker route, inside an Isaac Sim 6.0 container or pod:

```bash
bash scripts/setup_isaac_nodocker.sh
LAB_BACKEND=isaac LAB_BRIDGE=localbus lab-episode --seed 7 \
  --backend isaac --bridge localbus --out artifacts/episodes/gpu_seed_7
```

The setup script installs only Pillow and PyYAML into Isaac Sim's bundled
Python, without dependencies, so it does not replace Isaac Sim's `pxr` or
`numpy`. The canonical stage `usd/tabletop_seed7.usda` is committed.

## Limitations

- The kinematic grasp is an attach rule, not contact physics. Its 100/100 is a
  logic check; the real physics rate is 40/100 under the same controller.
- Pinhole frames use flat shading and exact material colours; 100% detection is a
  logic check, not a camera result.
- The dataset hash is a same-environment self-consistency hash. The scene hash is
  the cross-machine pin.
- The GPU track reaches APPROACH but not a pick; Isaac Lab and ROS 2 have no
  measured results. The exact errors and the 6.0 pod setup are recorded in
  [`docs/VERIFICATION.md`](docs/VERIFICATION.md).
- External human testers have not run the lab. The owner cold run is the only
  completed one.

## Learner testing

- Owner cold run: [`learner-testing/cold_runs/run_1.md`](learner-testing/cold_runs/run_1.md)
  — fresh clone, fresh venv, 67 s, `labcheck all` PASS 45.
- Protocol: [`learner-testing/PROTOCOL.md`](learner-testing/PROTOCOL.md)
- Tester table: [`learner-testing/TESTERS.md`](learner-testing/TESTERS.md) —
  external testers are listed as pending until real people complete a run.
- Remaining issue records: [`learner-testing/issues/`](learner-testing/issues/)

## Repository map

```text
src/isaac_starter_lab/   scene, sim, render, bridge, perception, controller, Isaac adapters
ros2_ws/src/starter_lab/ ROS 2 ament_python wrappers
tests/                   unit, end-to-end and determinism tests
scripts/                 headless lab, results, guide commands, GPU setup
usd/                     canonical tabletop_seed7.usda and expected hashes
results/                 measured JSON and the generated results table
docs/                    lab guide, verification status, walkthrough, diagrams
learner-testing/         protocol, cold run, issues, tester table
```

## What I learned

- TODO
- TODO
- TODO

## Docs

- [Lab guide](docs/LAB_GUIDE.md) · [Walkthrough](docs/WALKTHROUGH.md) ·
  [Verification status](docs/VERIFICATION.md) ·
  [Diagrams](docs/diagrams/) · [Changelog](CHANGELOG.md)
