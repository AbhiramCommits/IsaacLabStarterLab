# Cold run 2 — fresh git clone, fresh venv

- **Date:** 2026-11-06
- **Commit:** `0871aa8` (`git rev-parse HEAD` of the clone)
- **Machine:** macOS 27.2 arm64 (build machine), no GPU
- **Track:** CPU fresh clone + fresh venv, CPython 3.11.14
- **Operator:** build agent, no help from the guide author

## What was run

```bash
git clone <local repository> /tmp/cold2
cd /tmp/cold2
python3.11 -m venv .venv
source .venv/bin/activate
make install
```

`make install` completed in **7.484 s** on Python 3.11. This run did not hit the
Python 3.10 lock blocker from run 1, which is exactly why that blocker needed a
3.10-specific cold run.

## Exercise pass

| Time | Command | Result | Wall clock |
| --- | --- | --- | --- |
| 00:08 | `labcheck env` | PASS, 13 checks | 5 s |
| 00:13 | `lab-scene --seed 7 ... --render artifacts/ex2_frame.png --force` | hash `af653ff6...`, 46 prims | <1 s |
| 00:14 | `labcheck ex1` | PASS | 1 s |
| 00:15 | `labcheck ex2` | PASS — **still before any learner edit** | <1 s |
| 00:15 | `make episode` | SUCCESS, 294 ticks, 4.900 s | 1 s |
| 00:16 | `labcheck ex3` | PASS | 1 s |
| 00:17 | `make dr` | 200 seeds, dataset hash `9f14c038...` | 4 s |
| 00:21 | `lab-eval perception` | mean 1.058 px, p95 3.577 px | 13 s |
| 00:34 | `lab-eval episodes` | 100/100 success, mean 5.165 s | 32 s |
| 01:06 | `labcheck ex4` | PASS | <1 s |
| 01:07 | `labcheck all` | **RESULT: PASS (45 checks)** | 1 s |

Total measured exercise pass: **58 s**.

## Failures and confusion

| ID | Symptom | Guide step | Issue |
| --- | --- | --- | --- |
| F1 | `labcheck ex2` passed on the unmodified clone; no code was written for the exercise | Exercise 2 | [ISSUE-004](../issues/ISSUE-004.md) |

No command in the guide failed on Python 3.11. The clone's `make install` used
the old lock but was not affected because the offending wheel supports 3.11.
The authoring gap in Exercise 2 is the same as run 1 and remains the main
pedagogical finding.

## Outcome

Every exercise passed in 58 s of measured work on a fresh clone. The detector
authorship note added for ISSUE-004 is the only fix this run required.
