# ISSUE-001: Scene hash differed between macOS and the Docker Linux image

- **Status:** fixed
- **Severity:** major — the Docker cold run failed two labcheck checks
- **Guide step:** Exercise 1, "generate and inspect the OpenUSD scene"
- **Track:** Docker (`linux/amd64` under emulation)
- **Found in:** `7353fda` (pre-0.2.0 hashing)

## Symptom

The native build pinned
`ea579b2f4ed56d1b68134217e1645aac5602d6b883f4bb8c25bffa72f3587f04`, but the
same seed inside the Docker image produced a different stage hash. The full
`make lab-headless` inside Docker failed at the final `labcheck` stage with two
failed checks.

## Exact message

```text
ex1   FAIL    meta_hash      meta hash=f89029eb0a0d3a3bfb86b1f7d2ebfd1f9f262bd1970351df45906fe39e415ae5
ex1   FAIL    stage_hash     hash=f89029eb0a0d3a3bfb86b1f7d2ebfd1f9f262bd1970351df45906fe39e415ae5 expected=ea579b2f4ed56d1b68134217e1645aac5602d6b883f4bb8c25bffa72f3587f04
             FIX:    Hash mismatch. Regenerate with --force; never hand-edit the .usda.
```

## Cause

The flattened `.usda` text is not byte-identical across CPU/libm platforms. The
diff showed only last-bit float spelling:

```diff
- double3 xformOp:translate = (0.04728608637656412, 0.052759780553192935, 0.775)
+ double3 xformOp:translate = (0.04728608637656412, 0.05275978055319294, 0.775)
```

Hashing that raw text made the pin machine-specific even though the geometry was
identical to nanometre precision.

## Fix

`scene/hashing.py` now canonicalises floating-point literals to nine decimal
places before sha256 (`SHA256-FLATTENED-USDA-CANONICAL-FLOATS-9`). The canonical
scene was re-pinned to
`af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40`, a
regression test perturbs a translation by 1e-12 and asserts the hash is unchanged,
and the rebuilt Docker image produces the same pin as the host. See
`tests/test_scene.py::test_tiny_float_noise_does_not_change_hash`.

**Verification:** `docker run --rm isaac-starter-lab:ci lab-scene --seed 7 ...`
printed `hash: af653ff6...`; the full Docker `make lab-headless` then passed
`labcheck` (45 checks).
