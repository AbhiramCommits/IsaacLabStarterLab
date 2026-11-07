# Cold run 3 — Docker lab image

- **Date:** 2026-11-07
- **Image:** `isaac-starter-lab:final` (built from the working tree after the
  Step 6 fixes), `linux/amd64` emulated on macOS arm64
- **Track:** Docker lab image; no host Python, venv or ROS install
- **Operator:** build agent, no help from the guide author

## What was run

The first command a Docker learner sees in the guide was the old one-shot form:

```bash
docker run --rm -it isaac-starter-lab:local
```

It runs the image CMD (`make lab-headless`) and exits. The next guide line,
`cd IsaacLabStarterLab`, fails:

```text
$ docker run --rm isaac-starter-lab:final bash -lc 'pwd; cd IsaacLabStarterLab'
/lab
bash: line 1: cd: IsaacLabStarterLab: No such file or directory
```

That confusion became [ISSUE-005](../issues/ISSUE-005.md). The guided mode was
then used:

```bash
docker run --rm -it isaac-starter-lab:final bash
# inside:
cd /lab
labcheck env
python scripts/extract_guide_commands.py
```

`labcheck env` passed 13 checks. `extract_guide_commands.py` executes every
`<!-- test:run -->` block from `docs/LAB_GUIDE.md` in order, so it is the guide
run verbatim rather than a hand-picked subset.

## Exercise pass (Docker)

| Stage | Result | Wall clock |
| --- | --- | --- |
| `labcheck env` in `/lab` | PASS, 13 checks | a few seconds |
| Guide blocks 2–5 (scene, prim graph, pinned hash, ex1) | PASS; `af653ff6...` matches the host pin | included below |
| Guide blocks 6–10 (detect snippet, ex2, episode, summary, ex3) | PASS; 294 ticks, 4.900 s | included below |
| Guide block 11 (`make dr`, 200 seeds) | dataset hash `f868fa8b...` | 69.16 s |
| Guide block 12 (`lab-eval perception`) | mean 1.058 px, p95 3.577 px, recall 0.9611 | 286.89 s |
| Guide block 13 (`lab-eval episodes`, 100 seeds) | 100/100 success, mean 5.165 s | included below |
| Guide blocks 14–15 (`labcheck ex4`, `labcheck all`) | PASS 45 checks | 12.39 s for the final block |
| All 15 marked blocks | **passed** | **896.66 s total** |

The emulated image is roughly 15× slower than native for the Python-heavy
detector and sweep, which is expected under QEMU; the CPU work is identical and
the metrics match the host to the printed precision.

## Failures and confusion

| ID | Symptom | Guide step | Issue |
| --- | --- | --- | --- |
| F1 | One-shot `docker run` exits and `cd IsaacLabStarterLab` fails; the package is preinstalled | Exercise 0, Docker alternative | [ISSUE-005](../issues/ISSUE-005.md) |
| F2 | `make dr` prints `f868fa8b...`, while the guide's example value is `9f14c038...`; `labcheck ex4` passes | Exercise 4 | [ISSUE-003](../issues/ISSUE-003.md) |
| F3 | Earlier Docker verification had failed the scene-hash pin before floats were canonicalised | Exercise 1 | [ISSUE-001](../issues/ISSUE-001.md) |

F1 and F2 are documentation ambiguities, not code failures. F3 was a real bug
found during the Step 6 Docker run; this run verifies the fix: the Docker scene
hash is now `af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40`,
identical to the host and the CI pin.

## Outcome

After the guide was corrected, all 15 marked CPU-track blocks and the full
`labcheck all` passed inside the image, in 14 min 57 s including emulation
overhead. The Docker track is therefore reproducible from the documented
commands; the only caveat is the platform-specific dataset hash, now documented.
