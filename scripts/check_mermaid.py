#!/usr/bin/env python3
"""Validate the committed Mermaid sources without a Node.js toolchain.

The check is intentionally small and strict about the subset used in this
repository:

* ``flowchart``/``graph`` header with a direction
* node ids declared with a shape (``ID["label"]``, ``ID(label)``, ...)
* edges using ``-->``, ``---``, ``-.->`` or ``==>``
* every edge endpoint must be a declared node id

It catches the failure this repository actually cares about: a diagram edited
until it has a dangling node id and no longer renders on GitHub.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HEADER = re.compile(r"^(?:flowchart|graph)\s+(TD|TB|BT|LR|RL)\s*;?\s*$")
NODE_DECL = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[|\(|\{)")
EDGE_SPLIT = re.compile(r"\s*(?:-->|---|-\.->|==>)\s*")
EDGE_LABEL = re.compile(r"\|[^|]*\|")


def validate(path: Path) -> tuple[int, int]:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("%%")
    ]
    if not lines or not HEADER.match(lines[0]):
        raise ValueError("missing 'flowchart <direction>' or 'graph <direction>' header")
    declared: set[str] = set()
    edges: list[tuple[str, str]] = []
    for line in lines[1:]:
        if line.startswith(("subgraph", "end", "classDef", "class ", "linkStyle", "style ")):
            continue
        match = NODE_DECL.match(line)
        if match and not EDGE_SPLIT.search(line):
            declared.add(match.group(1))
            continue
        if not EDGE_SPLIT.search(line):
            raise ValueError(f"unparseable line: {line!r}")
        parts = EDGE_SPLIT.split(EDGE_LABEL.sub("", line))
        references: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                raise ValueError(f"empty edge endpoint in: {line!r}")
            node = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)", part)
            if not node:
                raise ValueError(f"invalid node reference {part!r}")
            value = node.group(1)
            if value not in declared:
                # A node may be declared inline in an edge; accept it and add it.
                if re.search(r"[\[\(\{]", part):
                    declared.add(value)
                else:
                    raise ValueError(f"dangling node id {value!r} (declare it before use)")
            references.append(value)
        for left, right in zip(references, references[1:], strict=False):
            edges.append((left, right))
    if len(declared) < 2:
        raise ValueError("a diagram needs at least two nodes")
    if not edges:
        raise ValueError("a diagram needs at least one edge")
    return len(declared), len(edges)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = args.paths or sorted(Path("docs/diagrams").glob("*.mmd"))
    if not paths:
        print("no .mmd files found", file=sys.stderr)
        return 1
    failed = False
    for path in paths:
        try:
            nodes, edges = validate(path)
            print(f"OK {path} ({nodes} nodes, {edges} edges)")
        except Exception as exc:
            failed = True
            print(f"FAIL {path}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
