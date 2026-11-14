# Fix progress — fix/isaaclabstarterlab

Branch: `fix/isaaclabstarterlab` (target `main`). Update this file after every
phase so a new session can resume. Status values: **done**, **in progress**,
**blocked**, **not started**.

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Remove AI-agent tells and stale claims | done | Docs cleaned; owner cold run recorded (67 s, PASS 45). |
| 2. Isaac Sim GPU track for real | done | Isaac Sim 6.0 seed-7 episode **SUCCESS**: a real 7-DOF PhysX arm with a fixed jaw + one moving jaw places green `Cube_01` in the bin in 272 ticks / 4.533 s. Artifacts in `results/gpu/seed_7/`. |
| 3. Real physics (PhysX) instead of attach rule | done | Real 100-seed PhysX sweep: **40/100 (40%)**, cycle mean 4.744 s/p95 7.733 s. Failures: `TIMEOUT_DESCEND` 41, `TIMEOUT_TRANSFER` 11, `CUBE_NOT_IN_BIN` 7, `NO_DETECTION` 1. No further tuning; the numbers are in `results/gpu/isaac_sweep.json`. |
| 4. Real Isaac Lab task + PPO | done (trains; does not solve) | Isaac Lab 3.0.0 on Isaac Sim 6.0.1, real `ManagerBasedRLEnv` task `IsaacLabStarterLab-PickPlace-v0` (our arm, table, bin and a 50 mm cube). PPO, 32 envs, **2,304,000 steps**, **986 steps/s**, 1500 iterations in 2346.69 s. Reaching reward **0.043 → 0.50** then plateau; lifting peaks 0.389 and returns to 0; success termination **0** for the whole run. `results/gpu/isaac_lab_ppo.json`. The policy does not learn pick-and-place; no success rate is claimed. |
| 5. ROS 2 nodes on real rclpy | done | ROS 2 Jazzy installed in the 6.0 pod; ament package built; `/starter_lab_controller`, `/starter_lab_controller_bridge` and `/starter_lab_perception` ran on real `rclpy`. `/lab/joint_states` **60.0 Hz**, `/lab/rgb` **8.2 Hz**, `/lab/cmd_joint` **6.38 Hz** while active, perception latency **31.01 ms** mean / **35.48 ms** p95, bag **9.867 s / 1975 msgs**. Distributed seed 7 fails `TIMEOUT_HOME` at 181 ticks; the lockstep localbus succeeds. `results/gpu/ros2_transport.json`. |
| 6. Perception on RTX frames | done | 200 DR-matched RTX frames rendered; RTX recall **95.51%**, precision **95.21%**, pixel mean **2.968 px**, 3D mean **12.073 mm** vs pinhole 100%/100%, 1.058 px, 3.607 mm. `results/gpu/rtx_perception.json`. |
| 7. Restructure README | done | Restructured with committed CPU results only. |

## GPU attempt, 2026-11-12 (exact)

**Capacity.** Community Cloud refused every in-spec GPU with
`400 ... no longer any instances available`. A 75 GB disk on Secure Cloud
succeeded; the same request with 100 GB did not, and 100 GB was the original
spec. A 2-vCPU CPU pod created instantly, so the account and API work.

**Pod 1 — Isaac Sim 4.5, Secure RTX 4090, EU-RO-1, driver 595.91.07, 75 GB.**

- With the default app, `SimulationApp` segfaulted in
  `omni.usdphysics.ui` immediate-mode overlays inside `_wait_for_viewport`.
- Patching that overlay and the file-menu stage handler, and disabling the main
  viewport window, let the app start, open `usd/tabletop_seed7.usda` and step
  physics. A minimal articulation reported **DOF 1**.
- With the main viewport enabled, the app still segfaulted during `app.update()`
  with driver 595.91.07 (no Python frame; Kit shut down).
- With the viewport disabled, `Camera.get_rgba()` returned an empty array and
  `rep.orchestrator.step()` hung, so no RTX frame was produced.
- The canonical arm reported **0 DOF** at both `/World/Robot` and
  `/World/Robot/base`: the rigid bodies are nested (`base` contains `link0` …)
  and the joints are outside the articulation root.

**Pod 2 — Isaac Sim 5.1 image.** The container runs as `isaac-sim` (uid 1234),
has no `sudo`, no `sshd`, no `rsync`, and `apt-get` fails with
`E: List directory /var/lib/apt/lists/partial is missing - Acquire (13: Permission denied)`.
The user-space OpenSSH install exited before serving SSH. The pod was deleted.

**Isaac Sim 5.1 via pip in pod 1.** `pip install "isaacsim[all]==5.1.0"` completed
(7 GB venv, Python 3.11.0rc1), but `SimulationApp` segfaulted in
`libomni.usd.so` at startup: the 5.1 pip libraries were mixed with the 4.5
container's USD/Kit libraries. No clean 5.1 environment was available without a
custom root image or a registry to push it to.

**Cost.** Pod 1 ran about 55 minutes and pod 2 about 13 minutes at $0.89/hr:
roughly **$1.00** total including disk. Both pods were terminated; `list-pods`
is empty.

**Isaac Sim 6.0 attempt (the furthest run).** Built and pushed
`madridista23/isaac-sim-60-root:latest` (`FROM nvcr.io/nvidia/isaac-sim:6.0.0`,
`USER root`, openssh-server, rsync). On the same driver 595.91.07, 6.0 starts,
opens the stage and renders: `APP_OK`, `PXR_OK`, `Camera.get_rgba()` returns
480x640 RGB.

- The canonical arm reports 5 DOF in 6.0 but is unstable under drives (nested
  rigid bodies), so `isaac_backend.py` now builds a **flat 7-DOF runtime arm**
  under `/World/RobotIsaac`: fixed base, five revolute links, two prismatic
  fingers, self-collision off, light masses, USD drives, 240 Hz physics.
- The canonical USD green cube is at `(0.104,-0.053)`, and the RTX detection
  `(374,252)` matches it; the earlier camera-pose alarm was a wrong comparison
  against the CPU sim's *re-sampled* layout. The runtime arm now matches the CPU
  kinematics (valid `Y` axes, sign-mapped joints, negated limits, tool-tip
  convergence). HOME, LOCATE, APPROACH and DESCEND pass. At GRASP the jaws
  contact the cube and push it from `(0.104,-0.053)` to `(0.072,-0.024)` — real
  PhysX contact — but the grip does not retain it. The final run completes the
  whole state machine and ends `CUBE_NOT_IN_BIN` with the cube at
  `(0.095,-0.043,0.775)`; wider jaws (0.055 m), 0.04 m travel, friction 1.2,
  a 50 N close force and a slow close were all tried.
- RTX artifacts (start/final frames, trajectory, summary) are committed under
  `results/gpu/seed_7/`; the episode failed at APPROACH, not at startup.

**Cost.** MCP billing for 2026-11-12: **$2.29** (GPU $2.26 + disk $0.03).
Recorded runtimes: 4.5 ~56 min, 5.1 ~13 min, 6.0 ~111 min at $0.89/hr, and the
L40S ~60 min at $1.09/hr. A follow-up 4090 run on 2026-11-13 lasted ~27 min at
$0.89/hr (~$0.40; billing had not posted at teardown). All pods terminated;
`list-pods` is empty.

## Environment facts

- Mac: macOS 27.2.1 arm64, Python 3.11.14 in `.venv`; `pxr`, NumPy, Pillow work.
- `gh` is authenticated as `AbhiramCommits`; pushes and the PR work from the Mac.
- Pod spec: L40S / RTX 4090 / RTX A6000, Isaac Sim 4.5 image, 100 GB container
  disk, no network volume, TCP 22, name `fix-isaaclabstarterlab-<yyyymmdd>`.
- Never fake a GPU number. A blocked phase stays blocked.

## Session log

- Phase 1: removed build-agent/session claims; owner cold run recorded.
- Phase 6 (Mac): fixed the pinhole ground truth (`visible = visible_pixels > 0`,
  `centre_visible`, occlusion-aware matching); dataset hash `e112f454...`;
  analysis in `results/perception_fp_analysis.json`.
- Phase 2 prep: `docker/Dockerfile.isaac` no longer replaces Isaac Sim's
  `pxr`/`numpy`; it was built and pushed as
  `madridista23/isaac-sim-60-root:latest`. `scripts/setup_isaac_nodocker.sh`
  adds the no-Docker route and is unrun.
- GPU attempts: see above. All GPU pods ran Isaac Sim 6.0 on driver 595.91.07.
- Phase 2: seed-7 PhysX pick succeeds after the fixed jaw + single moving jaw;
  `results/gpu/seed_7/`.
- Phase 3: real 100-seed PhysX sweep 40/100; no tuning past the recorded run.
- Phase 6: 200 RTX frames rendered from DR-matched USD; pinhole vs RTX gap
  measured and written to `results/gpu/rtx_perception.json`.
- Phase 5: ROS 2 Jazzy in the 6.0 pod; the ament package built, three nodes ran
  on real `rclpy`, topic rates/latency/bag recorded in
  `results/gpu/ros2_transport.json`. Distributed seed 7 fails `TIMEOUT_HOME`;
  the explanation (wall-clock controller + DDS latency) is in that file.
- Phase 7: README restructured, shorter, CPU logic check clearly labelled.
- Cost: billed **$5.47** through Nov 14 before Phase 4. The Phase 4 pods were a
  stuck isaac-lab pull (~40 min, ~$0.59) and the working 4090 in EU-RO-1
  (2.1 h, ~$1.89). Billed total from `list-billing` is **$7.27** so far and the
  Nov-14 bucket may still settle; the $6.50 cap was waived by the owner for this
  run.
- Phase 4: Isaac Lab 3.0.0-beta2 image, our arm exported to `usd/lab_arm.usda`,
  task `IsaacLabStarterLab-PickPlace-v0`, 1500-iteration PPO run. NaNs under
  random actions were fixed with 240 Hz physics, joint armature, extra solver
  iterations and fingers-only collision geometry in the RL export. The policy
  reaches but does not grasp; recorded as-is.

## To resume

1. Use the committed `madridista23/isaac-sim-60-root:latest` image (Isaac Sim
   6.0 + root + openssh + rsync). It starts on driver 595.91.07.
2. Phase 4 is implemented and runs; the open work is learning, not plumbing.
   The next changes worth trying are a grasp-first curriculum (close the jaw
   near the cube before rewarding lift), a smaller initial policy std, and an
   observation that includes the gripper-to-cube vector. Use the committed
   `scripts/isaac_lab_smoke.py`, `scripts/parse_isaac_lab_log.py` and the
   `--external_callback` hook on Isaac Lab's `train.py`.
3. The distributed ROS 2 pick fails `TIMEOUT_HOME`; the transport is fine. The
   next step there is controller gains/latency compensation, not a transport
   fix.
4. Keep the canonical `usd/tabletop_seed7.usda` and its pinned hash untouched.
