# Learner testers

**STATUS: awaiting external human testers — rows to be added by the repo owner.**

The table records real people who completed a cold run under
[`PROTOCOL.md`](PROTOCOL.md). No names, quotes or backgrounds are invented. The
repository owner's own cold run is logged separately in
[`cold_runs/run_1.md`](cold_runs/run_1.md); it is not an external-tester row.

| Tester | Background | Date | Track | Issues filed |
| --- | --- | --- | --- | --- |
| _pending_ | External tester 1 | — | — | — |
| _pending_ | External tester 2 | — | — | — |
| _pending_ | External tester 3 | — | — | — |

## What "cold" means here

A cold run starts from a fresh directory with no artifacts, no warmed package
environment and no author help during the run. The operator logs commands,
failures and wall-clock durations in `cold_runs/`. A failure is not silently
worked around: it becomes an issue, is fixed, and the run is resumed and
recorded.

## External round

The repository needs 3–5 human testers with varied backgrounds. Their rows
belong in this table only after they submit a filled
`.github/ISSUE_TEMPLATE/lab_feedback.yml` form and consent to publication.
