# IsaacLabStarterLab

A reproducible, learner-tested teaching lab that takes a developer from a clean
Linux machine to a working tabletop pick-and-place robot workflow: a generated
OpenUSD scene, a ROS 2 perception/control stack, a seeded domain-randomization
synthetic-dataset exercise, knowledge checks, and a self-check grader that
validates every artifact.

The lab ships two interchangeable runtimes on one message schema:

- **CPU headless track** (`kinematic` + `localbus`): deterministic, dependency-free,
  runs on any laptop and in CI without a GPU.
- **GPU Isaac Sim track** (`isaac` + `ros2`): the same learner code against
  NVIDIA Isaac Sim 4.5.0 and Isaac Lab on an NVIDIA host.

Start with [`docs/LAB_GUIDE.md`](docs/LAB_GUIDE.md). Verification scope, including
which paths were actually executed on the build machine, is recorded in
[`docs/VERIFICATION.md`](docs/VERIFICATION.md).

## Results

<!-- RESULTS:START -->
Run `make results` to populate this section from measured artifacts.
<!-- RESULTS:END -->
