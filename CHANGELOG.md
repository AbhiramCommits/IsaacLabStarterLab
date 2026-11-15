# Changelog

All notable changes to IsaacLabStarterLab are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
semantic versioning.

## [0.2.0] - 2026-11-06

Feedback-driven release from the cold reproduction round.

### Fixed

- Canonicalised floating-point literals to nine decimal places in the stage hash
  so the OpenUSD pin is identical on macOS and Linux
  ([ISSUE-001](learner-testing/issues/ISSUE-001.md)).
- Regenerated `requirements.lock.txt` on CPython 3.10 so the lowest supported
  interpreter can install the lab; `contourpy==1.3.3` required Python ≥ 3.11
  ([ISSUE-002](learner-testing/issues/ISSUE-002.md)).
- Split the Docker instructions into a one-shot lab command and a guided
  `bash` shell rooted at `/lab`, and removed the unnecessary in-container venv
  and `make install` steps.

### Changed

- Documented the dataset-level hash as a same-environment self-consistency hash,
  with both measured platform values, instead of presenting one value as a
  universal constant.
- Added an explicit authorship note to Exercise 2: the shipped detector is the
  tested reference, so `labcheck ex2` passes out of the box; learners must replace
  it for credit.

### Added

- Cold-run protocol, the owner cold-run log, the issue records that remain real
  code defects, the tester table and the GitHub lab-feedback issue form, linking
  the feedback → revision chain
  ([ISSUE-001](learner-testing/issues/ISSUE-001.md),
  [ISSUE-002](learner-testing/issues/ISSUE-002.md)).

## [0.1.0] - 2026-11-06

Initial lab: deterministic OpenUSD scene and hash, CPU kinematic backend and
pinhole renderer, Isaac Sim/Isaac Lab adapters, ROS 2 and local-bus transports,
perception/controller, domain-randomization dataset, evaluation, knowledge
checks, `labcheck`, Mermaid diagrams, walkthrough, CI and measured results.
