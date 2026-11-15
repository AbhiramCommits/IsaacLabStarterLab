# Cold-run testing protocol

The purpose of this round is to find places where the lab guide or code fails a
learner who has **no help from the author**. The repository owner's cold run is
recorded in `cold_runs/`; external human testers are still needed and are tracked
in `TESTERS.md`.

## Recruit 3–5 testers

Look for developers who can use a terminal and Python but have not seen this
repository. A useful mix is:

- one comfortable with Linux/ROS 2,
- one comfortable with Python but not robotics,
- one comfortable with 3D/OpenUSD or graphics but not ROS,
- one who has used Docker but not Isaac Sim.

Record their background in `TESTERS.md`, not their employer or other personal
details.

## Ground rules

1. Give the tester the repository URL and `docs/LAB_GUIDE.md` only. Do not answer
   questions during the run.
2. Use a fresh machine, VM or container with no prior checkout, no warmed Python
   environment and no Isaac Sim cache.
3. Ask the tester to screen-record the whole session and keep a timestamped log.
4. The tester follows the guide verbatim. If a command fails, they paste the
   exact terminal text into the log; they do not silently work around it.
5. Stop at the end of Exercise 4 (CPU track) or Exercise 5 (GPU track if the
   tester has the hardware). Run `labcheck all` and save the report.
6. Send the log, recording and a filled issue form (below) to the maintainer.

## What to log

| Field | Example |
| --- | --- |
| Start/end wall clock | 2026-11-06 14:02–14:41 UTC |
| Commit | `git rev-parse HEAD` |
| Track | fresh venv / fresh clone / Docker / GPU |
| OS, Python, Docker | Ubuntu 24.04, 3.12.4, Docker 27.1 |
| Every command | copy the block, note the timestamp |
| Every failure | exact stderr/stdout, guide section, whether retry helped |
| Every confusion | "I did not know whether to activate the venv again" |
| Final labcheck | `RESULT: PASS/FAIL`, report path |
| Wall-clock per exercise | 0:00–0:12 setup, 0:12–0:26 Exercise 1, … |

## Issue filing

Open the **Lab feedback** issue form
(`.github/ISSUE_TEMPLATE/lab_feedback.yml`) or create
`learner-testing/issues/ISSUE-00N.md` using this shape:

```markdown
# ISSUE-00N: short title

- **Status:** open | fixed
- **Severity:** blocker | major | minor
- **Guide step:** Exercise N, "section"
- **Track:** CPU venv / fresh clone / Docker / GPU
- **Found in:** commit hash

## Symptom
What the tester saw.

## Exact message
```text
paste the terminal output
```

## Cause
The real cause, once reproduced.

## Fix
What changed in the guide or code, with the commit or file.
```

## After the round

Every genuine problem becomes an issue and a `CHANGELOG.md` entry. Update the
guide, rerun the affected exercise, and record the fix in the cold-run log. Only
then add the tester's row to `TESTERS.md`. Do not publish a tester's name or
recording without explicit consent.

**STATUS: awaiting external human testers — rows to be added by the repo owner.**
