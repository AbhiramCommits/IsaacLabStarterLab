# Walkthrough — 2 minutes 30 seconds

A narrated walkthrough of the CPU headless track. Each timestamp maps to a real
command in `scripts/demo_session.sh` and to a committed frame in `demo/frames/`.
The recording is `demo/walkthrough.log` (the `script` fallback) because
`asciinema` is not installed on the build machine.

**Owner note (voiceover):** record one clean audio track reading the narration
below; the terminal log already contains the on-screen timing and captions.

| Time | Narration | Command | Committed frame |
| --- | --- | --- | --- |
| 00:00 | "This is IsaacLabStarterLab. The same learner code runs on a deterministic CPU backend and on Isaac Sim 4.5; only the backend and bridge change." | `python -c "import isaac_starter_lab; ..."` | — |
| 00:20 | "First, prove the environment: real `pxr`, the pinned wheels, and the CPU backend." | `labcheck env` | — |
| 00:40 | "The scene builder samples five non-overlapping cubes from seed 7 and hashes the flattened stage. The hash is the contract: same seed, same bytes." | `lab-scene --seed 7 ... --render demo/frames/scene_seed7.png` | `demo/frames/scene_seed7.png` |
| 01:05 | "Now one episode. Perception projects the cube centroid onto the table, analytic IK drives the arm, and the state machine carries the cube into the bin." | `lab-episode --seed 7 ...` | `demo/frames/episode_seed7_start.png`, `demo/frames/episode_seed7_final.png` |
| 01:30 | "Across 200 randomised frames, the detector is within about one pixel mean error. The labels and manifest are hashed, so the dataset is auditable." | `lab-eval perception` | `demo/frames/dr_seed_0000.png` |
| 01:55 | "A ten-seed sweep is enough for the recording; the committed 100-seed result is 100 percent." | `lab-eval episodes --seeds 0-9 ...` | — |
| 02:15 | "Finally, grade the artifacts themselves, not the terminal output. `labcheck` fails non-zero if any hash, frame or summary is wrong." | `labcheck all` | — |
| 02:30 | "That is the loop: generate, perceive, act, randomise, grade. The GPU track reuses every module behind the Isaac Sim adapter." | — | — |

The recording was produced by:

```bash
bash scripts/record_demo.sh
```

`demo/walkthrough.log` is the raw session transcript, including the timing
banners. The PNGs under `demo/frames/` are the frames the lab actually rendered
during that session.
