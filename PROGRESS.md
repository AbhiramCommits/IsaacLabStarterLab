# Fix progress — fix/isaaclabstarterlab

Branch: `fix/isaaclabstarterlab` (target `main`). Update this file after every
phase so a new session can resume. Status values: **done**, **in progress**,
**blocked**, **not started**.

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Remove AI-agent tells and stale claims | in progress | Docs edits done; owner cold run pending. |
| 2. Isaac Sim GPU track for real | not started | Needs the GPU pod. |
| 3. Real physics (PhysX) instead of attach rule | not started | Needs the GPU pod. |
| 4. Real Isaac Lab task + PPO | not started | Needs the GPU pod. |
| 5. ROS 2 nodes on real rclpy | not started | Needs the GPU pod. |
| 6. Perception on RTX frames | in progress | False-positive cause analysis is Mac-only; RTX side needs the pod. |
| 7. Restructure README | not started | Depends on GPU results. |

## Environment facts

- Mac: macOS arm64, no CUDA, Python 3.11.14 in `.venv`; `pxr`, NumPy, Pillow work.
- `gh` is authenticated as `AbhiramCommits`; pushes and the PR work from the Mac.
- Runpod MCP is available. Pod spec: L40S / RTX 4090 / RTX A6000, Isaac Sim 4.5
  image, 100 GB container disk, no network volume, TCP 22, name
  `fix-isaaclabstarterlab-<yyyymmdd>`.
- Never fake a GPU number. If a phase cannot run, record the exact error here
  and in `docs/VERIFICATION.md`.

## Session log

- Started from `main` at `a5ef9e5`; branch created.
- Phase 1: removed build-agent/session claims from README, TESTERS, PROTOCOL,
  VERIFICATION; dropped AI-authored cold runs 2/3; replaced the quickstart
  placeholder; corrected the CI statement.
- Phase 6 (Mac part): false positives in the pinhole perception evaluation
  analysed from `datasets/dr`.
