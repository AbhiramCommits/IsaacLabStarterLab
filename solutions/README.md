# Reference solutions

**Stop here if you have not finished the matching exercise.** The point of the
lab is to reason about prim paths, intrinsics, connected components and the
state machine; reading the solution first removes that practice.

The package ships a tested reference for every exercise so the measured results
and CI remain reproducible:

| Exercise | Reference | Why it is not duplicated here |
| --- | --- | --- |
| 2 — perception | `src/isaac_starter_lab/perception.py` | one implementation keeps the pixel-error numbers and the guide honest |
| 3 — episode loop | `src/isaac_starter_lab/episode.py` | the reviewed loop is also the one used by `lab-eval episodes` |
| 4 — domain randomisation | `src/isaac_starter_lab/datasets/dr.py` | the manifest hash must match the generator exactly |
| 5 — GPU track | `src/isaac_starter_lab/sim/isaac_backend.py` | GPU-gated; the CPU stand-in is the tested path |

`ex2_perception_solution.py` and `ex3_loop_solution.py` re-export those tested
functions so a learner can compare signatures without a second copy drifting.
