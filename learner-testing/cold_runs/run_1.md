# Cold run 1 — fresh venv on the lowest supported Python

- **Date:** 2026-11-06
- **Commit:** `0871aa8` (`git rev-parse HEAD` of the clone)
- **Machine:** macOS 27.2 arm64 (build machine), no GPU
- **Track:** CPU fresh clone + fresh venv, CPython 3.10.19
- **Operator:** build agent, no help from the guide author

## What was run

```bash
git clone <local repository> /tmp/cold1
cd /tmp/cold1
python3.10 -m venv .venv
source .venv/bin/activate
make install
```

The first `make install` **failed** after 1.102 s. This is the real blocker that
became [ISSUE-002](../issues/ISSUE-002.md):

```text
ERROR: Ignored the following versions that require a different python version:
1.3.3 Requires-Python >=3.11; 1.4.0 Requires-Python >=3.12
ERROR: Could not find a version that satisfies the requirement contourpy==1.3.3
ERROR: No matching distribution found for contourpy==1.3.3
```

The lock had been generated on Python 3.11 and pinned `contourpy 1.3.3`, which
cannot install on 3.10. I regenerated the lock in this 3.10 venv with
`pip install -e ".[dev]"`, copied it into the clone, and reran. The fixed
install completed in **10 s**.

## Exercise pass (fresh venv)

Timestamps come from the shell timer and are rounded to the second.

| Time | Command | Result | Wall clock |
| --- | --- | --- | --- |
| 00:10 | `labcheck env` | PASS, 13 checks | 5 s |
| 00:15 | `lab-scene --seed 7 --out artifacts/scene_seed7.usda --render artifacts/ex2_frame.png --force` | hash `af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40`, 46 prims | <1 s |
| 00:16 | `labcheck ex1` | PASS, 8 checks | 1 s |
| 00:17 | `labcheck ex2` | PASS, 5 checks — **before any learner edit** | <1 s |
| 00:17 | `make episode` | SUCCESS, green/Cube_01, 294 ticks, 4.900 s | <1 s |
| 00:18 | `labcheck ex3` | PASS, 9 checks | 1 s |
| 00:19 | `make dr` | 200 seeds, dataset hash `9f14c038...` | 5 s |
| 00:24 | `lab-eval perception` | mean 1.058 px, p95 3.577 px, recall 0.9611 | 13 s |
| 00:37 | `lab-eval episodes` | 100/100 success, mean 5.165 s | 31 s |
| 01:08 | `labcheck ex4` | PASS | <1 s |
| 01:09 | `labcheck all` | **RESULT: PASS (45 checks)** | <1 s |

Total measured exercise pass: **56 s** after the 10 s fixed install.

## Failures and confusion

| ID | Symptom | Guide step | Issue |
| --- | --- | --- | --- |
| F1 | `make install` could not resolve `contourpy==1.3.3` on Python 3.10 | Exercise 0 | [ISSUE-002](../issues/ISSUE-002.md) |
| F2 | `labcheck ex2` passed with 0.375 px without the learner writing `detect_cubes` | Exercise 2 | [ISSUE-004](../issues/ISSUE-004.md) |

F2 is not a terminal failure but a real assessment gap: the repository ships the
reference implementation, so `labcheck` cannot tell whether the learner wrote it.
The guide now states this explicitly and requires replacement for credit.

## Outcome

After the lock fix, every exercise and `labcheck all` passed on CPython 3.10.19.
This run directly validates the lowest supported Python claim and caused
ISSUE-002 and ISSUE-004.
