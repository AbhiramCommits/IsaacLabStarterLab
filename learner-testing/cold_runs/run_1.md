# Cold run 1 — owner, fresh clone and fresh venv

- **Status:** pending — to be completed by the repository owner on their own Mac.
- **Date:** —
- **Commit:** —
- **Machine:** —
- **Track:** CPU, fresh clone + fresh venv
- **Operator:** repository owner, no help during the run

## What to run

Follow the README quickstart exactly, from a directory outside this checkout:

```bash
git clone https://github.com/AbhiramCommits/IsaacLabStarterLab.git IsaacLabStarterLab-cold
cd IsaacLabStarterLab-cold
python3.11 -m venv .venv && source .venv/bin/activate
make install
make lab-headless
labcheck all
```

Record the real wall-clock time for each command, the Python version
(`python --version`), the commit (`git rev-parse HEAD`), every command you type,
and the exact text of any failure. Do not work around a failure silently; note
it here and file an issue if it is a real defect.

## Log

| Time | Command | Result | Wall clock |
| --- | --- | --- | --- |
| — | — | — | — |

## Failures and confusion

_None recorded yet._

## Outcome

_Pending._
