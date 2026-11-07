#!/usr/bin/env python3
"""Aggregate measured results and inject the README results section.

The README is never edited by hand between the ``RESULTS`` markers: this script
reads the JSON under ``results/``, writes ``results/summary.json`` and
``results/RESULTS.md``, then replaces the marked block in ``README.md``.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
START = "<!-- RESULTS:START -->"
END = "<!-- RESULTS:END -->"


def _json(relative: str) -> dict | None:
    path = ROOT / relative
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _coverage() -> dict:
    data = _json("results/coverage.json")
    if not data:
        return {"percent": None}
    return {"percent": float(data["totals"]["percent_covered"])}


def _pytest() -> dict:
    path = ROOT / "results" / "pytest.xml"
    if not path.exists():
        return {"tests": None, "failures": None, "errors": None}
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    tests = sum(int(suite.get("tests", 0)) for suite in suites)
    failures = sum(int(suite.get("failures", 0)) for suite in suites)
    errors = sum(int(suite.get("errors", 0)) for suite in suites)
    return {"tests": tests, "failures": failures, "errors": errors}


def _ci_jobs() -> list[str]:
    path = ROOT / ".github" / "workflows" / "ci.yml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list((data.get("jobs") or {}).keys())


def _learner_testing() -> dict:
    cold_dir = ROOT / "learner-testing" / "cold_runs"
    issue_dir = ROOT / "learner-testing" / "issues"
    cold_runs = len(list(cold_dir.glob("run_*.md"))) if cold_dir.exists() else 0
    issues = sorted(issue_dir.glob("ISSUE-*.md")) if issue_dir.exists() else []
    fixed = 0
    for issue in issues:
        text = issue.read_text(encoding="utf-8", errors="ignore").lower()
        if re.search(r"status:\s*fixed|status:\s*\*\*fixed\*\*", text):
            fixed += 1
    return {"cold_runs": cold_runs, "issues_filed": len(issues), "issues_fixed": fixed}


def build_summary() -> dict:
    scene_meta = _json("artifacts/scene_seed7.meta.json") or _json(
        "usd/tabletop_seed7.meta.json"
    )
    dataset = _json("datasets/dr/manifest.json")
    perception = _json("results/perception_eval.json")
    episodes = _json("results/episode_sweep.json")
    determinism = _json("results/determinism.json")
    timings = _json("results/timings.json")
    labcheck = _json("results/labcheck.json")
    coverage = _coverage()
    pytest = _pytest()
    return {
        "schema": "isaac_starter_lab.results_summary.v1",
        "scene": (
            {
                "hash": scene_meta.get("hash"),
                "prim_count": scene_meta.get("prim_count"),
                "seed": scene_meta.get("seed"),
            }
            if scene_meta
            else {}
        ),
        "dataset": (
            {
                "count": dataset.get("count"),
                "dataset_hash": dataset.get("dataset_hash"),
                "n_cubes": dataset.get("n_cubes"),
                "image_size": dataset.get("image_size"),
            }
            if dataset
            else {}
        ),
        "perception": (
            {
                "seeds": perception.get("seeds"),
                "visible_cubes": perception.get("visible_cubes"),
                "pixel": perception.get("pixel_error"),
                "error_3d_mm": perception.get("error_3d_mm"),
                "recall": perception.get("recall"),
                "precision": perception.get("precision"),
            }
            if perception
            else {}
        ),
        "episodes": (
            {
                "count": episodes.get("count"),
                "successes": episodes.get("successes"),
                "success_rate": episodes.get("success_rate"),
                "cycle_time_s": episodes.get("cycle_time_s"),
                "ticks": episodes.get("ticks"),
                "failure_histogram": episodes.get("failure_histogram"),
            }
            if episodes
            else {}
        ),
        "determinism": determinism or {},
        "timings": timings or {},
        "coverage": coverage,
        "tests": pytest,
        "labcheck": labcheck or {},
        "ci_jobs": _ci_jobs(),
        "learner_testing": _learner_testing(),
    }


def _pct(value) -> str:
    return "not measured" if value is None else f"{100.0 * value:.2f}%"


def _num(value, digits=3, suffix="") -> str:
    return "not measured" if value is None else f"{value:.{digits}f}{suffix}"


def _ms(value) -> str:
    return "not measured" if value is None else f"{value:.3f}"


def render_markdown(summary: dict) -> str:
    scene = summary["scene"]
    dataset = summary["dataset"]
    perception = summary["perception"]
    episodes = summary["episodes"]
    determinism = summary["determinism"]
    timings = summary["timings"]
    tests = summary["tests"]
    coverage = summary["coverage"]
    labcheck = summary["labcheck"]
    learner = summary["learner_testing"]

    pixel = perception.get("pixel") or {}
    error_3d = perception.get("error_3d_mm") or {}
    cycle = episodes.get("cycle_time_s") or {}
    failures = episodes.get("failure_histogram") or {}
    failure_text = ", ".join(f"{reason}: {count}" for reason, count in sorted(failures.items())) or "none"
    stages = timings.get("stages") or []
    timing_text = ", ".join(
        f"{stage['name']} {stage['seconds']:.2f} s" for stage in stages
    ) or "not measured"
    artifacts = determinism.get("artifact_count")
    determinism_text = (
        f"{determinism.get('runs', 0)} runs, {artifacts} artifacts, "
        + ("hashes identical" if determinism.get("artifacts_identical") else "MISMATCH")
        if determinism
        else "not measured"
    )
    tests_text = (
        f"{tests.get('tests')} tests"
        if tests.get("tests") is not None
        else "not measured"
    )
    if tests.get("failures") is not None:
        tests_text += f", {tests['failures']} failures"
    if coverage.get("percent") is not None:
        tests_text += f", {coverage['percent']:.2f}% statement coverage"
    ci_text = ", ".join(summary.get("ci_jobs") or []) or "not measured"

    rows = [
        ("Scene hash (seed 7)", f"`{scene.get('hash')}`"),
        ("Scene prim count", str(scene.get("prim_count"))),
        ("DR dataset", f"{dataset.get('count')} frames, hash `{dataset.get('dataset_hash')}`"),
        ("Perception pixel error", f"mean {_num(pixel.get('mean'), 3, ' px')}, p95 {_num(pixel.get('p95'), 3, ' px')}"),
        ("Perception 3D error", f"mean {_num(error_3d.get('mean'), 3, ' mm')}, p95 {_num(error_3d.get('p95'), 3, ' mm')}"),
        ("Detection recall / precision", f"{_pct(perception.get('recall'))} / {_pct(perception.get('precision'))}"),
        (
            "Episode success (100 seeds)",
            f"{episodes.get('successes')}/{episodes.get('count')} "
            f"({_pct(episodes.get('success_rate'))}); failures: {failure_text}",
        ),
        (
            "Cycle time",
            f"mean {_num(cycle.get('mean'), 3, ' s')}, p95 {_num(cycle.get('p95'), 3, ' s')}",
        ),
        ("Per-stage timings", timing_text),
        ("Determinism", determinism_text),
        ("Test suite", tests_text),
        ("CI jobs", ci_text),
        (
            "Labcheck",
            f"{'PASS' if labcheck.get('passed') else 'FAIL'}, "
            f"{labcheck.get('count', 'not measured')} checks",
        ),
        (
            "Learner testing",
            f"{learner.get('cold_runs', 0)} cold runs, "
            f"{learner.get('issues_filed', 0)} issues filed, "
            f"{learner.get('issues_fixed', 0)} fixed",
        ),
    ]
    lines = [
        "| Metric | Measured value |",
        "| --- | --- |",
    ]
    lines.extend(f"| {name} | {value} |" for name, value in rows)
    lines.append("")
    lines.append(
        "All values are read from the JSON files under `results/` and the committed "
        "dataset manifest by `scripts/collect_results.py`; the GPU track is not included."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    if START not in readme or END not in readme:
        raise SystemExit(f"README.md is missing {START} / {END} markers")

    summary = build_summary()
    summary_path = ROOT / "results" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    table = render_markdown(summary)
    (ROOT / "results" / "RESULTS.md").write_text("# Measured results\n\n" + table, encoding="utf-8")

    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    replacement = f"{START}\n{table}\n{END}"
    readme_path.write_text(pattern.sub(replacement, readme, count=1), encoding="utf-8")
    print(f"wrote {summary_path}")
    print(f"wrote {ROOT / 'results' / 'RESULTS.md'}")
    print(f"injected results into {readme_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
