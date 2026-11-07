# Measured results

| Metric | Measured value |
| --- | --- |
| Scene hash (seed 7) | `af653ff61a3791440124a0af7067aaabe5a483f9084ef00370c6fe92c7abab40` |
| Scene prim count | 46 |
| DR dataset | 200 frames, hash `9f14c0388aafd557c4325ebbc47319198c3fd1dac8786c9b9f106723b3b90c96` |
| Perception pixel error | mean 1.058 px, p95 3.577 px |
| Perception 3D error | mean 3.607 mm, p95 12.885 mm |
| Detection recall / precision | 96.11% / 86.93% |
| Episode success (100 seeds) | 100/100 (100.00%); failures: none |
| Cycle time | mean 5.165 s, p95 5.467 s |
| Per-stage timings | scene 0.09 s, dr 4.51 s, episode 0.35 s, perception_eval 12.49 s, episode_eval 33.70 s, labcheck 0.67 s |
| Determinism | 2 runs, 610 artifacts, hashes identical |
| Test suite | 145 tests, 0 failures, 88.20% statement coverage |
| CI jobs | test, lab, determinism, docker, gpu-isaac |
| Labcheck | PASS, 45 checks |
| Learner testing | 0 cold runs, 0 issues filed, 0 fixed |

All values are read from the JSON files under `results/` and the committed dataset manifest by `scripts/collect_results.py`; the GPU track is not included.
