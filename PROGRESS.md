# Fix progress — fix/isaaclabstarterlab

Branch: `fix/isaaclabstarterlab` (target `main`). Update this file after every
phase so a new session can resume. Status values: **done**, **in progress**,
**blocked**, **not started**.

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Remove AI-agent tells and stale claims | done | Docs cleaned; owner cold run recorded (67 s, PASS 45). |
| 2. Isaac Sim GPU track for real | blocked | No GPU pod could be created: Runpod returned `no longer any instances available` for every in-spec GPU. Docker/no-Docker install path updated but unrun. |
| 3. Real physics (PhysX) instead of attach rule | blocked | Same GPU blocker. Also the canonical arm has no gripper DOF; the approved fix (runtime prismatic joint in `isaac_backend`) is designed but unrun. |
| 4. Real Isaac Lab task + PPO | blocked | Same GPU blocker; no Isaac Lab install or training was possible. |
| 5. ROS 2 nodes on real rclpy | blocked | Same GPU blocker; ROS 2 and the Isaac Sim bridge need that host. |
| 6. Perception on RTX frames | blocked | Pinhole ground-truth bug fixed and measured; the RTX half needs the GPU pod. |
| 7. Restructure README | done | Restructured with committed CPU results only; GPU headline is absent because no GPU result exists. |

## GPU blocker (exact)

Every `create-pod` attempt for an NVIDIA L40S, RTX 4090, RTX A6000, RTX A5000,
RTX 3090 or RTX A4000 (Community and Secure, container disk 20/50/100 GB) returned:

```text
400 Bad Request
There are no longer any instances available with the requested specifications.
Please refresh and try again.
```

A 2-vCPU CPU pod was created successfully and deleted immediately, so the
account and API work; GPU capacity (or a GPU quota on the account) is the
blocker. No pod named `fix-isaaclabstarterlab-*` was left running. The Runpod
MCP surface has no credit-balance read; billing showed $0.016 total before the
attempts.

## Environment facts

- Mac: macOS 27.2.1 arm64, Python 3.11.14 in `.venv`; `pxr`, NumPy, Pillow work.
- `gh` is authenticated as `AbhiramCommits`; pushes and the PR work from the Mac.
- Pod spec: L40S / RTX 4090 / RTX A6000, Isaac Sim 4.5 image, 100 GB container
  disk, no network volume, TCP 22, name `fix-isaaclabstarterlab-<yyyymmdd>`.
- Never fake a GPU number. A blocked phase stays blocked.

## Session log

- Started from `main` at `a5ef9e5`; branch created.
- Phase 1: removed build-agent/session claims from README, TESTERS, PROTOCOL,
  LAB_GUIDE, VERIFICATION; dropped AI-authored cold runs 2/3; replaced the
  quickstart placeholder; corrected the CI statement; recorded the owner cold
  run.
- Phase 6 (Mac part): the 128 false positives were a ground-truth bug, not
  spurious detections. `dr.py` now sets `visible = visible_pixels > 0` and records
  `centre_visible`; `evaluation.py` matches a detection inside the cube's visible
  box, and reports pixel/3D error only where the projected centre is unoccluded.
  Dataset regenerated (hash `e112f454...`); analysis in
  `results/perception_fp_analysis.json`.
- Phase 2 prep: `docker/Dockerfile.isaac` no longer installs `usd-core`/`numpy`
  over Isaac Sim's bundled copies; `scripts/setup_isaac_nodocker.sh` adds the
  no-Docker route. Both are unrun.
- GPU attempts: see the blocker above. All GPU phases marked blocked.
- Phase 7: README restructured, shorter, with the CPU logic check clearly
  labelled and the GPU/ROS 2 paths under "Not validated".

## To resume

1. Confirm GPU capacity or the GPU quota on the Runpod account.
2. Start a pod from the `fix-isaaclabstarterlab` branch with the spec above.
3. Run Phase 2, then 3, 6, 5, 4 in that order; copy results back and commit.
4. Add the runtime prismatic finger joint in `isaac_backend` before
   `Articulation.initialize()` (approved), then the 100-seed PhysX sweep.
