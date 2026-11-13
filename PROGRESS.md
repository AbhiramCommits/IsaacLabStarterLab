# Fix progress — fix/isaaclabstarterlab

Branch: `fix/isaaclabstarterlab` (target `main`). Update this file after every
phase so a new session can resume. Status values: **done**, **in progress**,
**blocked**, **not started**.

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Remove AI-agent tells and stale claims | done | Docs cleaned; owner cold run recorded (67 s, PASS 45). |
| 2. Isaac Sim GPU track for real | done | Isaac Sim 6.0 seed-7 episode **SUCCESS**: a real 7-DOF PhysX arm with a fixed jaw + one moving jaw places green `Cube_01` in the bin in 272 ticks / 4.533 s. Artifacts in `results/gpu/seed_7/`. |
| 3. Real physics (PhysX) instead of attach rule | done | Real 100-seed PhysX sweep: **40/100 (40%)**, cycle mean 4.744 s/p95 7.733 s. Failures: `TIMEOUT_DESCEND` 41, `TIMEOUT_TRANSFER` 11, `CUBE_NOT_IN_BIN` 7, `NO_DETECTION` 1. No further tuning; the numbers are in `results/gpu/isaac_sweep.json`. |
| 4. Real Isaac Lab task + PPO | blocked | Not reached; the 6.0 pip stack is available but no Isaac Lab task/training was run. |
| 5. ROS 2 nodes on real rclpy | blocked | Not reached. |
| 6. Perception on RTX frames | blocked | RTX frames exist in `results/gpu/seed_7/`; the camera-pose mismatch prevents a valid side-by-side perception evaluation. |
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
  `pxr`/`numpy`; `scripts/setup_isaac_nodocker.sh` adds the no-Docker route.
  Both are unrun.
- GPU attempts: see above. All GPU phases marked blocked.
- Phase 7: README restructured, shorter, CPU logic check clearly labelled.

## To resume

1. Use the committed `madridista23/isaac-sim-60-root:latest` image (Isaac Sim
   6.0 + root + openssh + rsync). It starts on driver 595.91.07.
2. Fix the camera pose: the canonical `/World/Camera` USD transform does not
   match the CPU look-at, so RTX back-projection is wrong. Either author the
   correct USD camera matrix at runtime and recreate the render product, or
   derive the controller pose from the actual rendered camera (the current
   `camera_pose()` guess is not yet consistent). Validate by back-projecting a
   known green cube pixel to its stage position.
3. Then re-run the seed-7 episode; it should pass APPROACH and reach GRASP.
4. Tune grasp friction/close speed, then the 100-seed PhysX sweep (Phase 3),
   RTX perception (Phase 6), ROS 2 (Phase 5) and Isaac Lab (Phase 4).
5. The runtime 7-DOF arm is implemented in `isaac_backend.py`; keep the
   canonical `usd/tabletop_seed7.usda` and its hash untouched.
