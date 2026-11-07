"""Mermaid sources must parse in the subset the lab uses."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_mermaid", ROOT / "scripts" / "check_mermaid.py"
)
check_mermaid = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_mermaid)


@pytest.mark.parametrize("name", ["architecture.mmd", "usd_scene_graph.mmd", "data_flow.mmd"])
def test_committed_diagrams_parse(name):
    nodes, edges = check_mermaid.validate(ROOT / "docs" / "diagrams" / name)
    assert nodes >= 5
    assert edges >= 4


def test_dangling_node_is_rejected(tmp_path):
    diagram = tmp_path / "bad.mmd"
    diagram.write_text("flowchart LR\n    A[\"start\"] --> MISSING\n")
    with pytest.raises(ValueError, match="dangling node id"):
        check_mermaid.validate(diagram)


def test_missing_header_is_rejected(tmp_path):
    diagram = tmp_path / "bad.mmd"
    diagram.write_text("A --> B\n")
    with pytest.raises(ValueError, match="flowchart"):
        check_mermaid.validate(diagram)


def test_cli_returns_nonzero_on_failure(tmp_path, capsys):
    diagram = tmp_path / "bad.mmd"
    diagram.write_text("flowchart LR\n    A[\"start\"] --> MISSING\n")
    assert check_mermaid.main([str(diagram)]) == 1
    assert "dangling node id" in capsys.readouterr().err
