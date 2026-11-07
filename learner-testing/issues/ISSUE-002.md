# ISSUE-002: requirements.lock.txt could not install on Python 3.10

- **Status:** fixed
- **Severity:** blocker — Exercise 0 cannot start on the lowest supported Python
- **Guide step:** Exercise 0, "environment and labcheck env"
- **Track:** CPU fresh venv, CPython 3.10.19
- **Found in:** `0871aa8`

## Symptom

The pinned install failed immediately on Python 3.10, so `make install` never
reached `labcheck env`. The same lock installed on Python 3.11, which is how the
bad transitive pin escaped the build machine.

## Exact message

```text
ERROR: Ignored the following versions that require a different python version: 1.3.3 Requires-Python >=3.11; 1.4.0 Requires-Python >=3.12
ERROR: Could not find a version that satisfies the requirement contourpy==1.3.3 (from versions: 0.0.1, 0.0.2, 0.0.3, 0.0.4, 0.0.5, 1.0.0, 1.0.1, 1.0.2, 1.0.3, 1.0.4, 1.0.5, 1.0.6, 1.0.7, 1.1.0, 1.1.1rc1, 1.2.0, 1.2.1rc1, 1.2.1, 1.3.0, 1.3.1, 1.3.2)
ERROR: No matching distribution found for contourpy==1.3.3
```

## Cause

The lock was generated from a Python 3.11 `pip freeze`. Matplotlib pulled
`contourpy 1.3.3`, whose metadata requires Python ≥ 3.11. Several other
transitive pins (`coverage`, `fonttools`, `python-dateutil`) were also newer than
the Python 3.10-compatible set. The project claimed 3.10–3.12 support.

## Fix

Regenerated `requirements.lock.txt` in a clean CPython 3.10.19 venv with
`pip install -e ".[dev]"`. The compatible set includes `contourpy==1.3.2`,
`coverage==7.16.2`, `fonttools==4.65.0`, `python-dateutil==3.0.0`, plus
`six`, `tomli`, `typing_extensions` and `exceptiongroup`.

**Verification:** the lock installed in fresh CPython 3.10.19, 3.11.14 and 3.12
environments; the main suite (145 tests) passes on 3.11 and the full guide
completed in the 3.10 cold run after the fix. Python 3.12 imported
`isaac_starter_lab`, NumPy, Pillow and `pxr` successfully.
