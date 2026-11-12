# Fix progress — fix/isaaclabstarterlab

Branch: `fix/isaaclabstarterlab` (target `main`). Update this file after every
phase so a new session can resume. Status values: **done**, **in progress**,
**blocked**, **not started**.

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Remove AI-agent tells and stale claims | done | Docs cleaned; owner cold run recorded (67 s, PASS 45). |
| 2. Isaac Sim GPU track for real | blocked | A Secure RTX 4090 pod was created and Isaac Sim 4.5 started, opened the stage and ran PhysX, but the RTX renderer segfaulted with host driver 595.91.07. Isaac Sim 5.1 could not be made usable on that host (image runs as a non-root user with no sshd/rsync/sudo). |
| 3. Real physics (PhysX) instead of attach rule | blocked | Same renderer blocker. Separately, the canonical arm is not a valid PhysX articulation (rigid bodies nested under `base`, joints outside the root), so `Articulation` reports 0 DOF. The approved runtime physics arm was not built. |
| 4. Real Isaac Lab task + PPO | blocked | Same host/version blocker; no Isaac Lab install or training was completed. |
| 5. ROS 2 nodes on real rclpy | blocked | Same host/version blocker; ROS 2 and the Isaac Sim bridge were not installed. |
| 6. Perception on RTX frames | blocked | Pinhole ground-truth bug fixed and measured on the Mac; RTX frames were not produced because the renderer failed. |
| 7. Restructure README | done | Restructured with committed CPU results only; GPU headline absent because no GPU result exists. |

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

1. Provide a registry the agent can push to, then build
   `FROM nvcr.io/nvidia/isaac-sim:5.1.0` with `USER root` and
   `RUN apt-get update && apt-get install -y openssh-server rsync`.
   (The stock 5.1 image runs as uid 1234 and cannot install them.)
2. Or use a host with an R580 production driver for the 4.5 image.
3. Start the pod from this branch, then run Phase 2, 3, 6, 5, 4 in that order.
4. Build the runtime physics arm in `isaac_backend` (approved), including the
   prismatic finger joints, before the 100-seed PhysX sweep.
