# Learner testers

**STATUS: awaiting external human testers — rows to be added by repo owner.**

The three rows below are the cold reproduction runs performed by the build agent
in this session. They are honest test evidence, not external human feedback. No
human names, quotes or backgrounds have been invented. The owner should replace
or supplement these rows after the human round described in `PROTOCOL.md`.

| Tester | Background | Date | Track | Issues filed |
| --- | --- | --- | --- | --- |
| Build agent — cold run 1 | AI coding agent; first cold exposure to the repository; comfortable with Python/Linux, not the author of the guide | 2026-11-06 | CPU fresh clone + fresh venv, CPython 3.10.19 (lowest supported) | [ISSUE-002](issues/ISSUE-002.md), [ISSUE-004](issues/ISSUE-004.md) |
| Build agent — cold run 2 | Same agent; fresh clone and fresh venv, no reuse of run 1's environment | 2026-11-06 | CPU fresh clone + fresh venv, CPython 3.11.14 | [ISSUE-004](issues/ISSUE-004.md) |
| Build agent — cold run 3 | Same agent; Docker image, no host Python or venv | 2026-11-07 | Docker lab image, `linux/amd64` emulated on arm64 | [ISSUE-001](issues/ISSUE-001.md), [ISSUE-003](issues/ISSUE-003.md), [ISSUE-005](issues/ISSUE-005.md) |

## What "cold" meant here

Each run started from a fresh directory with no artifacts, no warmed package
environment and no author help during the run. Run 1 and run 2 used
`git clone`; run 3 used the built Docker image. The operator logged commands,
failures and wall-clock durations in `cold_runs/`. A failure was not silently
worked around: it became an issue, was fixed, and the run was resumed and
recorded.

## External round

The repository still needs 3–5 human testers with varied backgrounds. Their rows
belong in this table only after they submit a filled
`.github/ISSUE_TEMPLATE/lab_feedback.yml` form and consent to publication.
