# ISSUE-005: Docker instructions dropped the learner into a one-shot command

- **Status:** fixed
- **Severity:** major — a Docker learner could not follow the exercises
- **Guide step:** Exercise 0, "Docker alternative"
- **Track:** Docker lab image
- **Found in:** `0871aa8`

## Symptom

`docker run --rm -it isaac-starter-lab:local` started the image CMD
(`make lab-headless`), printed the whole lab and exited. The guide's next line,
`cd IsaacLabStarterLab`, failed because the image workdir is `/lab`; creating a
venv and running `make install` inside the image was also unnecessary and would
reinstall into the container.

## Exact message

```text
$ docker run --rm -it isaac-starter-lab:local bash -lc 'pwd; cd IsaacLabStarterLab'
/lab
bash: line 1: cd: IsaacLabStarterLab: No such file or directory
```

## Cause

The image has two legitimate uses — a one-shot full-lab run and an interactive
guided shell — but the guide documented one command as if it did both. The
container also already contains the pinned environment, unlike a host checkout.

## Fix

The guide now separates the two modes:

```bash
docker run --rm isaac-starter-lab:local                 # one-shot lab
docker run --rm -it isaac-starter-lab:local bash        # guided shell
# inside: cd /lab, skip venv/make install, run labcheck env
```

It states that `/lab` replaces `IsaacLabStarterLab` inside the container and that
the package is already installed. The GPU section keeps its own explicit
`docker run --gpus all` command.

**Verification:** the cold-run operator ran the guided shell and exercises from
`/lab`; the container's `src/`, `usd/` and `lab/` paths are rooted there.
