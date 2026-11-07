"""Domain-randomization dataset generation and manifest integrity."""

from __future__ import annotations

import hashlib
import json
import math
from types import SimpleNamespace

import pytest
from PIL import Image

from isaac_starter_lab.datasets.dr import (
    generate_dataset,
    rotate_camera,
    run_dr_command,
)
from isaac_starter_lab.ranges import parse_seed_range


def _manifest_hash(manifest: dict) -> str:
    payload = {"n_cubes": manifest["n_cubes"], "entries": manifest["entries"]}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_generate_small_dataset_is_complete_and_valid(tmp_path):
    manifest = generate_dataset(tmp_path, [0, 1, 2], overwrite=True, verbose=False)
    assert manifest["count"] == 3
    assert manifest["seeds"] == [0, 1, 2]
    assert manifest["image_size"] == [640, 480]
    assert manifest["dataset_hash"] == _manifest_hash(manifest)

    for entry in manifest["entries"]:
        image_path = tmp_path / entry["image"]
        label_path = tmp_path / entry["label"]
        assert image_path.exists() and label_path.exists()
        assert hashlib.sha256(image_path.read_bytes()).hexdigest() == entry["image_sha256"]
        assert hashlib.sha256(label_path.read_bytes()).hexdigest() == entry["label_sha256"]
        with Image.open(image_path) as image:
            assert image.size == (640, 480)
        label = json.loads(label_path.read_text())
        assert label["schema"] == "isaac_starter_lab.dr_label.v1"
        assert label["width"] == 640 and label["height"] == 480
        assert len(label["cubes"]) == 5
        assert len({cube["color"] for cube in label["cubes"]}) == 5
        assert any(cube["visible"] for cube in label["cubes"])
        for cube in label["cubes"]:
            assert len(cube["position"]) == 3
            assert cube["pixel_centroid"] is not None
            assert isinstance(cube["visible"], bool)
        assert label["camera"]["intrinsics"]["fx"] > 0
        assert 0.65 <= label["light_intensity"] <= 1.25
        assert abs(label["camera_yaw_jitter_rad"]) <= math.radians(8.0) + 1e-12


def test_dataset_is_byte_identical_across_directories(tmp_path):
    first = generate_dataset(tmp_path / "a", [7, 8], overwrite=True, verbose=False)
    second = generate_dataset(tmp_path / "b", [7, 8], overwrite=True, verbose=False)
    assert first["dataset_hash"] == second["dataset_hash"]
    for entry in first["entries"]:
        assert (tmp_path / "a" / entry["image"]).read_bytes() == (
            tmp_path / "b" / entry["image"]
        ).read_bytes()
        assert (tmp_path / "a" / entry["label"]).read_bytes() == (
            tmp_path / "b" / entry["label"]
        ).read_bytes()


def test_incremental_run_reuses_files(tmp_path):
    manifest = generate_dataset(tmp_path, [0], overwrite=True, verbose=False)
    entry = manifest["entries"][0]
    image_path = tmp_path / entry["image"]
    before = image_path.stat().st_mtime_ns
    again = generate_dataset(tmp_path, [0], overwrite=False, verbose=False)
    assert again["dataset_hash"] == manifest["dataset_hash"]
    assert image_path.stat().st_mtime_ns == before


def test_rotate_camera_quarter_turn():
    assert rotate_camera((1.0, 0.0, 1.0), (0.0, 0.0, 1.0), math.pi / 2) == pytest.approx(
        (0.0, 1.0, 1.0)
    )


def test_dr_command_writes_manifest(tmp_path):
    args = SimpleNamespace(
        root=str(tmp_path),
        out="datasets/dr",
        seeds="0-1",
        n_cubes=5,
        overwrite=True,
    )
    assert run_dr_command(args) == 0
    manifest = json.loads((tmp_path / "datasets/dr/manifest.json").read_text())
    assert manifest["count"] == 2
    assert (tmp_path / "datasets/dr/images/seed_0001.png").exists()


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("7", [7]),
        ("0-3", [0, 1, 2, 3]),
        ("0,2,4-5", [0, 2, 4, 5]),
        ("1,1,0-1", [1, 0]),
    ],
)
def test_parse_seed_range(spec, expected):
    assert parse_seed_range(spec) == expected


@pytest.mark.parametrize("spec", ["", " ", "3-1", "-1", "1-2-3", "0,,2", "a"])
def test_parse_seed_range_rejects_invalid(spec):
    with pytest.raises(ValueError):
        parse_seed_range(spec)


def test_randomisation_actually_varies(tmp_path):
    manifest = generate_dataset(tmp_path, [0, 1, 2, 3], overwrite=True, verbose=False)
    colors = []
    lights = []
    for entry in manifest["entries"]:
        label = json.loads((tmp_path / entry["label"]).read_text())
        colors.append(tuple(cube["color"] for cube in label["cubes"]))
        lights.append(label["light_intensity"])
    assert len(set(colors)) > 1
    assert len(set(lights)) > 1
    image_hashes = {entry["image_sha256"] for entry in manifest["entries"]}
    assert len(image_hashes) == len(manifest["entries"])
