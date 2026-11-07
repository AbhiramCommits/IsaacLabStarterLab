# ISSUE-004: Exercise 2 passed before the learner wrote any code

- **Status:** fixed
- **Severity:** major — the assessment could be completed without doing the exercise
- **Guide step:** Exercise 2, "render a frame and write detect_cubes"
- **Track:** CPU fresh venv (Python 3.10) and fresh clone (Python 3.11)
- **Found in:** `0871aa8`

## Symptom

On a fresh clone, `labcheck ex2` reported PASS with a 0.375 px error before the
cold-run operator changed a single line of `perception.py`. The repository ships
the tested reference implementation, and the grader can only execute what is
installed.

## Exact message

```text
ex2   PASS    detection_count              1 detections
ex2   PASS    pixel_error                  0.375 px (threshold 2.0)
ex2   PASS    error_3d                     1.519 mm (threshold 20.0)
----------------------------------------------------------------------------------------------------
RESULT: PASS (5 checks)
```

## Cause

The exercise asks the learner to write `detect_cubes`, but the package must ship
a working implementation for CI and for the measured results. There was no
statement that `labcheck` grades behavior rather than authorship, so a learner
could tick Exercise 2 without implementing the detector.

## Fix

The guide now carries an explicit authorship note in Exercise 2: the shipped
function is the reference; for credit the learner must replace `detect_cubes`
(from `exercises/ex2_perception_stub.py`) and explain their HSV thresholds and
component filter. `solutions/README.md` repeats the warning. This is a guide and
assessment fix, not a detector change; the reference implementation remains the
one measured by `lab-eval perception`.

**Verification:** the updated note appears before the `labcheck ex2` command in
`docs/LAB_GUIDE.md`; the cold-run logs record that the PASS was observed on a
fresh clone before any edit.
