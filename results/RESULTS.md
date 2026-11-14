# Measured results

| Metric | Measured value |
| --- | --- |
| Scene hash (seed 7) | `af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40` |
| Scene prim count | 46 |
| DR dataset | 200 frames, hash `e112f454d426badab50614ce74e4dcb418ad770417a62d841bf30775f9b9b4dc` |
| Pinhole pixel error (logic check) | mean 1.058 px, p95 3.577 px |
| Pinhole 3D error (logic check) | mean 3.607 mm, p95 12.885 mm |
| Pinhole recall / precision (logic check) | 100.00% / 100.00% |
| Kinematic episode success, 100 seeds (no physics) | 100/100 (100.00%); failures: none |
| Kinematic cycle time (no physics) | mean 5.165 s, p95 5.467 s |
| Per-stage timings | scene 0.06 s, dr 4.36 s, episode 0.33 s, perception_eval 11.20 s, episode_eval 30.16 s, labcheck 0.50 s |
| Determinism | 2 runs, 610 artifacts, hashes identical |
| Test suite | 145 tests, 0 failures, 88.20% statement coverage |
| CI jobs | test, lab, determinism, docker, gpu-isaac |
| Labcheck | PASS, 45 checks |
| Learner testing | 1 cold run, 2 issues filed, 2 fixed |

All values are read from the JSON files under `results/` and the committed dataset manifest by `scripts/collect_results.py`; the GPU track is not included.
