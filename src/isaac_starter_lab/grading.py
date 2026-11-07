"""The `labcheck` self-check grader.

Each exercise is graded from the learner's *real artifacts*, never from a log
line.  Failures print a remediation hint and make the process exit non-zero.
The machine-readable report is written to ``results/labcheck.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .config import CameraIntrinsics, SceneConfig
from .perception import detect_cubes
from .render.pinhole import CameraPose, project_point, render_scene
from .scene.build_scene import sample_cube_layout
from .scene.hashing import stage_hash_from_file

__all__ = [
    "CheckResult",
    "PERCEPTION_MEAN_PIXEL_THRESHOLD",
    "PERCEPTION_P95_PIXEL_THRESHOLD",
    "run_checks",
    "run_check_command",
]

PERCEPTION_MEAN_PIXEL_THRESHOLD = 2.0
PERCEPTION_P95_PIXEL_THRESHOLD = 5.0
DR_MIN_COUNT = 200
EXPECTED_SEED = 7


@dataclass
class CheckResult:
    step: str
    name: str
    passed: bool
    detail: str
    hint: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "hint": self.hint,
        }


def _fail(step: str, name: str, detail: str, hint: str) -> CheckResult:
    return CheckResult(step, name, False, detail, hint)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# env
# ---------------------------------------------------------------------------
def check_env(root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    version = sys.version_info
    in_range = (3, 10) <= (version.major, version.minor) <= (3, 12)
    results.append(
        CheckResult(
            "env",
            "python_version",
            in_range,
            f"Python {platform.python_version()}",
            "Install Python 3.10, 3.11 or 3.12 and recreate the venv.",
        )
    )

    modules = {
        "pxr": "usd-core",
        "numpy": "numpy",
        "PIL": "pillow",
        "yaml": "PyYAML",
        "matplotlib": "matplotlib",
    }
    for module, package in modules.items():
        try:
            imported = __import__(module)
            version_text = getattr(imported, "__version__", "imported")
            results.append(
                CheckResult("env", f"import_{module}", True, f"{package}: {version_text}")
            )
        except Exception as exc:  # pragma: no cover - environment dependent
            results.append(
                _fail(
                    "env",
                    f"import_{module}",
                    f"{type(exc).__name__}: {exc}",
                    "Install the pinned environment: python -m pip install -r requirements.lock.txt",
                )
            )

    required = [
        "pyproject.toml",
        "requirements.lock.txt",
        "usd/EXPECTED_HASHES.json",
        "usd/tabletop_seed7.usda",
        "lab/knowledge_checks.yaml",
        "docs/VERIFICATION.md",
    ]
    for relative in required:
        path = root / relative
        results.append(
            CheckResult(
                "env",
                f"file_{relative}",
                path.exists(),
                str(path.relative_to(root)) if path.exists() else "missing",
                f"Restore {relative} from the repository (are you inside the repo root?).",
            )
        )

    try:
        from .sim.kinematic import KinematicSim

        sim = KinematicSim(seed=EXPECTED_SEED)
        results.append(
            CheckResult(
                "env",
                "kinematic_backend",
                sim.joint_positions.shape == (5,),
                "5-DOF KinematicSim instantiated",
            )
        )
    except Exception as exc:
        results.append(
            _fail("env", "kinematic_backend", f"{type(exc).__name__}: {exc}", "Reinstall the package.")
        )
    return results


# ---------------------------------------------------------------------------
# exercise 1: scene
# ---------------------------------------------------------------------------
def _expected_scene(root: Path) -> dict:
    data = _load_json(root / "usd" / "EXPECTED_HASHES.json")
    return data["scenes"]["tabletop_seed7"]


def check_ex1(root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    scene_path = root / "artifacts" / "scene_seed7.usda"
    meta_path = root / "artifacts" / "scene_seed7.meta.json"
    hint = "Run: lab-scene --seed 7 --out artifacts/scene_seed7.usda --force"
    for path in (scene_path, meta_path):
        results.append(
            CheckResult(
                "ex1",
                f"file_{path.name}",
                path.exists(),
                str(path) if path.exists() else "missing",
                hint,
            )
        )
    if not scene_path.exists() or not meta_path.exists():
        return results

    expected = _expected_scene(root)
    try:
        meta = _load_json(meta_path)
    except Exception as exc:
        results.append(_fail("ex1", "meta_json", f"invalid JSON: {exc}", hint))
        return results

    results.append(
        CheckResult(
            "ex1",
            "meta_schema",
            meta.get("schema") == "isaac_starter_lab.scene_meta.v1",
            str(meta.get("schema")),
            "Regenerate the metadata with lab-scene.",
        )
    )
    results.append(
        CheckResult(
            "ex1",
            "seed",
            meta.get("seed") == EXPECTED_SEED,
            f"seed={meta.get('seed')}",
            "The teaching seed is 7. Regenerate with --seed 7.",
        )
    )
    results.append(
        CheckResult(
            "ex1",
            "meta_hash",
            meta.get("hash") == expected["hash"],
            f"meta hash={meta.get('hash')}",
            hint,
        )
    )
    try:
        actual_hash = stage_hash_from_file(scene_path)
    except Exception as exc:
        results.append(_fail("ex1", "stage_hash", f"could not hash stage: {exc}", hint))
        actual_hash = None
    results.append(
        CheckResult(
            "ex1",
            "stage_hash",
            actual_hash == expected["hash"],
            f"hash={actual_hash} expected={expected['hash']}",
            "Hash mismatch. Regenerate with --force; never hand-edit the .usda.",
        )
    )
    results.append(
        CheckResult(
            "ex1",
            "prim_count",
            meta.get("prim_count") == expected["prim_count"],
            f"prims={meta.get('prim_count')} expected={expected['prim_count']}",
            hint,
        )
    )
    cubes = meta.get("cube_poses") or []
    results.append(
        CheckResult(
            "ex1",
            "cube_poses",
            len(cubes) == expected["n_cubes"] and all("position" in c for c in cubes),
            f"{len(cubes)} cube poses",
            hint,
        )
    )
    return results


# ---------------------------------------------------------------------------
# exercise 2: perception
# ---------------------------------------------------------------------------
def check_ex2(root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    frame_path = root / "artifacts" / "ex2_frame.png"
    hint = "Run: lab-scene --seed 7 --out artifacts/scene_seed7.usda --render artifacts/ex2_frame.png --force"
    if not frame_path.exists():
        results.append(_fail("ex2", "file_ex2_frame.png", "missing", hint))
    else:
        try:
            with Image.open(frame_path) as image:
                size = image.size
                array = np.asarray(image.convert("RGB"))
            results.append(
                CheckResult(
                    "ex2",
                    "frame_size",
                    size == (640, 480),
                    f"{size[0]}x{size[1]}",
                    "Render a 640x480 PNG with lab-scene --render.",
                )
            )
            results.append(
                CheckResult(
                    "ex2",
                    "frame_not_blank",
                    len(np.unique(array.reshape(-1, 3), axis=0)) > 10,
                    f"{len(np.unique(array.reshape(-1, 3), axis=0))} unique colours",
                    "The frame looks blank; re-render it.",
                )
            )
        except Exception as exc:
            results.append(_fail("ex2", "frame_readable", f"{type(exc).__name__}: {exc}", hint))

    # Grade the learner's detect_cubes on a fresh, known reference frame.
    cfg = SceneConfig(n_cubes=1)
    placement = sample_cube_layout(cfg, EXPECTED_SEED)[0]
    image = render_scene([(placement.position, placement.rgb)], cfg, CameraIntrinsics())
    pose = CameraPose.from_look_at(cfg.camera_position, cfg.camera_look_at, cfg.camera_up)
    u, v, _ = project_point(placement.position, pose, CameraIntrinsics())
    try:
        detections = detect_cubes(image, placement.color_name)
    except NotImplementedError as exc:
        results.append(
            _fail(
                "ex2",
                "detect_cubes",
                f"NotImplementedError: {exc}",
                "Implement detect_cubes in src/isaac_starter_lab/perception.py (stub: exercises/ex2_perception_stub.py).",
            )
        )
        return results
    except Exception as exc:
        results.append(
            _fail("ex2", "detect_cubes", f"{type(exc).__name__}: {exc}", "Fix detect_cubes.")
        )
        return results

    results.append(
        CheckResult(
            "ex2",
            "detection_count",
            len(detections) == 1,
            f"{len(detections)} detections",
            "The reference frame contains exactly one cube of the target colour.",
        )
    )
    if detections:
        detection = detections[0]
        pixel_error = float(np.hypot(detection.u - u, detection.v - v))
        error_3d_mm = 1000.0 * float(
            np.linalg.norm(np.asarray(detection.position) - np.asarray(placement.position))
        )
        results.append(
            CheckResult(
                "ex2",
                "pixel_error",
                pixel_error <= PERCEPTION_MEAN_PIXEL_THRESHOLD,
                f"{pixel_error:.3f} px (threshold {PERCEPTION_MEAN_PIXEL_THRESHOLD:.1f})",
                "Project the centroid, not the bounding-box centre. Threshold hue/saturation first.",
            )
        )
        results.append(
            CheckResult(
                "ex2",
                "error_3d",
                error_3d_mm <= 20.0,
                f"{error_3d_mm:.3f} mm (threshold 20.0)",
                "Back-project to z = table_top + cube_size/2.",
            )
        )
    else:
        results.append(
            _fail(
                "ex2",
                "pixel_error",
                "no detection, cannot compute error",
                "Threshold the palette hue with saturation >= 0.35 and value >= 0.12.",
            )
        )
    return results


# ---------------------------------------------------------------------------
# exercise 3: episode
# ---------------------------------------------------------------------------
def check_ex3(root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    episode = root / "artifacts" / "episodes" / "seed_7"
    summary_path = episode / "summary.json"
    trajectory_path = episode / "trajectory.jsonl"
    hint = "Run: lab-episode --seed 7 --backend kinematic --bridge localbus --out artifacts/episodes/seed_7"
    for path in (summary_path, trajectory_path, episode / "frame_000.png", episode / "frame_final.png"):
        results.append(
            CheckResult(
                "ex3",
                f"file_{path.name}",
                path.exists(),
                "present" if path.exists() else "missing",
                hint,
            )
        )
    if not summary_path.exists():
        return results

    try:
        summary = _load_json(summary_path)
    except Exception as exc:
        results.append(_fail("ex3", "summary_json", f"invalid JSON: {exc}", "Delete the stale episode and rerun."))
        return results

    results.append(
        CheckResult(
            "ex3",
            "schema",
            summary.get("schema") == "isaac_starter_lab.episode_summary.v1",
            str(summary.get("schema")),
            "Stale episode artifact. Delete artifacts/episodes/seed_7 and rerun.",
        )
    )
    results.append(
        CheckResult(
            "ex3",
            "success",
            summary.get("success") is True and summary.get("state") == "DONE",
            f"success={summary.get('success')} state={summary.get('state')} reason={summary.get('failure_reason')}",
            "Inspect the failure reason, rerun lab-episode and check frame_final.png.",
        )
    )
    ticks = summary.get("ticks")
    results.append(
        CheckResult(
            "ex3",
            "ticks",
            isinstance(ticks, int) and ticks > 0,
            f"ticks={ticks}",
            hint,
        )
    )
    cycle_time = summary.get("cycle_time_s")
    results.append(
        CheckResult(
            "ex3",
            "cycle_time",
            isinstance(cycle_time, (int, float)) and cycle_time > 0,
            f"{cycle_time} s",
            hint,
        )
    )

    if trajectory_path.exists() and isinstance(ticks, int):
        try:
            lines = trajectory_path.read_text(encoding="utf-8").splitlines()
            parsed = [json.loads(line) for line in lines]
            messages_ok = all("messages" in record and "tick" in record for record in parsed)
            results.append(
                CheckResult(
                    "ex3",
                    "trajectory_lines",
                    len(lines) == ticks and messages_ok,
                    f"{len(lines)} lines, summary ticks={ticks}",
                    "The trajectory is stale or truncated. Rerun the episode.",
                )
            )
        except Exception as exc:
            results.append(_fail("ex3", "trajectory_json", f"invalid JSONL: {exc}", hint))

    target = summary.get("target_cube")
    final_positions = summary.get("final_cube_positions") or {}
    if target and target in final_positions:
        position = final_positions[target]
        cfg = SceneConfig()
        (lo_x, lo_y, _), (hi_x, hi_y, _) = cfg.bin_inner_aabb
        in_bin = (
            lo_x <= position[0] <= hi_x
            and lo_y <= position[1] <= hi_y
            and abs(position[2] - cfg.cube_center_z) <= 2e-3
        )
        results.append(
            CheckResult(
                "ex3",
                "cube_in_bin",
                in_bin,
                f"{target} at {position}",
                "The cube did not land inside the bin. Check TRANSFER/RELEASE targets.",
            )
        )
    else:
        results.append(
            _fail("ex3", "cube_in_bin", f"target cube {target!r} missing from summary", hint)
        )
    return results


# ---------------------------------------------------------------------------
# exercise 4: dataset
# ---------------------------------------------------------------------------
def check_ex4(root: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    dataset = root / "datasets" / "dr"
    manifest_path = dataset / "manifest.json"
    hint = "Run: make dr (or lab-dr --seeds 0-199 --out datasets/dr --overwrite)"
    if not manifest_path.exists():
        return [_fail("ex4", "manifest", "missing datasets/dr/manifest.json", hint)]
    try:
        manifest = _load_json(manifest_path)
    except Exception as exc:
        return [_fail("ex4", "manifest_json", f"invalid JSON: {exc}", hint)]

    entries = manifest.get("entries") or []
    results.append(
        CheckResult(
            "ex4",
            "schema",
            manifest.get("schema") == "isaac_starter_lab.dr_dataset.v1",
            str(manifest.get("schema")),
            hint,
        )
    )
    results.append(
        CheckResult(
            "ex4",
            "count",
            manifest.get("count", 0) >= DR_MIN_COUNT and len(entries) >= DR_MIN_COUNT,
            f"count={manifest.get('count')} entries={len(entries)}",
            f"Generate at least {DR_MIN_COUNT} seeds.",
        )
    )
    unique_seeds = {entry.get("seed") for entry in entries}
    results.append(
        CheckResult(
            "ex4",
            "unique_seeds",
            len(unique_seeds) == len(entries),
            f"{len(unique_seeds)} unique seeds",
            "Delete the dataset and regenerate; duplicate seed entries mean a corrupt manifest.",
        )
    )

    payload = {
        "n_cubes": manifest.get("n_cubes"),
        "entries": entries,
    }
    expected_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    results.append(
        CheckResult(
            "ex4",
            "dataset_hash",
            expected_hash == manifest.get("dataset_hash"),
            f"computed={expected_hash} manifest={manifest.get('dataset_hash')}",
            "The manifest was edited or files changed. Regenerate with --overwrite.",
        )
    )

    missing = []
    hash_mismatch = []
    for entry in entries:
        image_path = dataset / entry["image"]
        label_path = dataset / entry["label"]
        if not image_path.exists() or not label_path.exists():
            missing.append(entry["seed"])
            continue
        if _sha256_file(image_path) != entry["image_sha256"]:
            hash_mismatch.append((entry["seed"], "image"))
        if _sha256_file(label_path) != entry["label_sha256"]:
            hash_mismatch.append((entry["seed"], "label"))
    results.append(
        CheckResult(
            "ex4",
            "files_present",
            not missing,
            f"{len(entries) - len(missing)}/{len(entries)} pairs present"
            + (f", missing seeds {missing[:5]}" if missing else ""),
            "The bulk images are gitignored by design. Run make dr to regenerate them.",
        )
    )
    results.append(
        CheckResult(
            "ex4",
            "file_hashes",
            not hash_mismatch,
            f"{len(entries) - len(hash_mismatch)}/{len(entries)} hashes match"
            + (f", first mismatch {hash_mismatch[:3]}" if hash_mismatch else ""),
            "Image or label changed after manifest generation. Regenerate with --overwrite.",
        )
    )
    eval_path = root / "results" / "perception_eval.json"
    if not eval_path.exists():
        results.append(
            _fail(
                "ex4",
                "perception_eval",
                "missing results/perception_eval.json",
                "Run: lab-eval perception",
            )
        )
    else:
        try:
            evaluation = _load_json(eval_path)
            pixel = evaluation["pixel_error"]
            results.append(
                CheckResult(
                    "ex4",
                    "perception_pixel",
                    pixel["mean"] <= PERCEPTION_MEAN_PIXEL_THRESHOLD
                    and pixel["p95"] <= PERCEPTION_P95_PIXEL_THRESHOLD,
                    f"mean={pixel['mean']:.3f} px p95={pixel['p95']:.3f} px",
                    "Improve detect_cubes or regenerate the dataset, then rerun lab-eval perception.",
                )
            )
            results.append(
                CheckResult(
                    "ex4",
                    "perception_recall_precision",
                    evaluation["recall"] >= 0.90 and evaluation["precision"] >= 0.80,
                    f"recall={evaluation['recall']:.4f} precision={evaluation['precision']:.4f}",
                    "Check hue separation and occlusion handling; rerun lab-eval perception.",
                )
            )
        except Exception as exc:
            results.append(
                _fail("ex4", "perception_eval", f"invalid evaluation JSON: {exc}", "Run: lab-eval perception")
            )

    if entries:
        try:
            label = _load_json(dataset / entries[0]["label"])
            with Image.open(dataset / entries[0]["image"]) as image:
                size = image.size
            results.append(
                CheckResult(
                    "ex4",
                    "label_schema",
                    label.get("schema") == "isaac_starter_lab.dr_label.v1"
                    and size == (640, 480)
                    and len(label.get("cubes", [])) == manifest.get("n_cubes"),
                    f"label schema={label.get('schema')} image={size}",
                    hint,
                )
            )
        except Exception as exc:
            results.append(_fail("ex4", "label_schema", f"{type(exc).__name__}: {exc}", hint))
    return results


CHECKERS = {
    "env": check_env,
    "ex1": check_ex1,
    "ex2": check_ex2,
    "ex3": check_ex3,
    "ex4": check_ex4,
}


def run_checks(root: str | Path, step: str = "all") -> dict:
    root_path = Path(root).resolve()
    steps = list(CHECKERS) if step == "all" else [step]
    if step not in CHECKERS and step != "all":
        raise ValueError(f"unknown check step {step!r}")
    checks: list[CheckResult] = []
    for name in steps:
        try:
            checks.extend(CHECKERS[name](root_path))
        except Exception as exc:  # a corrupted artifact must never crash the grader
            checks.append(
                _fail(
                    name,
                    "unexpected_error",
                    f"{type(exc).__name__}: {exc}",
                    "Inspect the artifacts and rerun the exercise.",
                )
            )
    passed = all(check.passed for check in checks)
    return {
        "schema": "isaac_starter_lab.labcheck.v1",
        "step": step,
        "root": str(root_path),
        "passed": passed,
        "count": len(checks),
        "failed": sum(1 for check in checks if not check.passed),
        "checks": [check.to_dict() for check in checks],
    }


def _print_report(report: dict) -> None:
    print(f"labcheck {report['step']} @ {report['root']}")
    print(f"{'STEP':<5} {'STATUS':<7} {'CHECK':<28} DETAIL")
    print("-" * 100)
    for check in report["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"{check['step']:<5} {status:<7} {check['name']:<28} {check['detail']}")
        if not check["passed"] and check["hint"]:
            print(f"{'':<13}{'FIX:':<7} {check['hint']}")
    print("-" * 100)
    if report["passed"]:
        print(f"RESULT: PASS ({report['count']} checks)")
    else:
        print(f"RESULT: FAIL ({report['failed']} of {report['count']} checks failed)")


def run_check_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    report = run_checks(root, args.step)
    _print_report(report)
    out = Path(args.json_out)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"report: {out}")
    return 0 if report["passed"] else 1
