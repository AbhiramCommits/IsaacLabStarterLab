# Cold run 1 — fresh clone and fresh venv on the owner's Mac

- **Date:** 2026-11-12
- **Commit:** `807f223` (`git rev-parse HEAD` of the clone)
- **Machine:** macOS 27.2.1 arm64, no GPU
- **Track:** CPU, fresh clone + fresh venv, CPython 3.11.14
- **Operator:** repository owner's machine, at the owner's request. The commands
  below are the README quickstart exactly as run; timings are wall-clock from
  shell timers, not estimates.

## What was run

```bash
git clone -b fix/isaaclabstarterlab \
  https://github.com/AbhiramCommits/IsaacLabStarterLab.git IsaacLabStarterLab-cold
cd IsaacLabStarterLab-cold
python3.11 -m venv .venv && source .venv/bin/activate
make install
make lab-headless
labcheck all
```

The clone was made into a temporary directory outside the working checkout, so
no artifact, cache or installed package was reused.

## Log

| Command | Result | Wall clock |
| --- | --- | --- |
| `git clone -b fix/isaaclabstarterlab …` | clean clone | 1 s |
| `python3.11 -m venv .venv` | fresh venv, CPython 3.11.14 | 1 s |
| `make install` | pinned wheels + editable package | 12 s |
| `make lab-headless` | scene, 200-seed DR, episode, perception eval, 100-episode sweep, labcheck | 52 s |
| `labcheck all` | **RESULT: PASS (45 checks)** | 1 s |
| **Total** | | **67 s** |

The pipeline reproduced the pinned values: scene hash
`af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40`, 46 prims,
200 dataset entries, seed-7 episode `success=True` in 294 ticks / 4.900 s.

## Failures and confusion

None. Every quickstart command succeeded on the first attempt, and `labcheck
all` passed 45 of 45 checks without any manual intervention.

## Outcome

The README quickstart works end to end from a fresh clone in 67 s of measured
wall-clock time on CPython 3.11.14. No issue was filed from this run.
