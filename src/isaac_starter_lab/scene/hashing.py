"""Reproducible hashing of an OpenUSD stage.

The hash is computed over the flattened ``.usda`` text after removing everything
that is not scene description:

* ``#`` comments (including the ``#usda`` header)
* ``doc`` / ``documentation`` / ``comment`` metadata, including multi-line
  triple-quoted blocks
* blank-line runs and trailing whitespace

Timestamps and layer identifiers are not written by the scene builder, so the
remaining text is a pure function of the code version, the seed and the
configuration.  The same stage therefore hashes identically across machines,
which is what makes ``usd/EXPECTED_HASHES.json`` meaningful.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pxr import Usd

__all__ = ["canonical_stage_text", "stage_hash", "stage_hash_from_file"]

_DOC_BLOCK = re.compile(
    r'(?ms)^[ \t]*(?:doc|documentation|comment)[ \t]*=[ \t]*""".*?"""[ \t]*\n?'
)
_DOC_LINE = re.compile(r'^[ \t]*(?:doc|documentation|comment)[ \t]*=.*$', re.MULTILINE)
_EMPTY_METADATA = re.compile(r"[ \t]*\(\s*\)[ \t]*\n")
_BARE_LAYER_COMMENT = re.compile(r'^[ \t]*"(?:[^"\\]|\\.)*"[ \t]*\n', re.MULTILINE)


def canonical_stage_text(stage: Usd.Stage) -> str:
    """Flatten ``stage`` and return the normalised scene-description text."""
    flattened = stage.Flatten()
    layer = flattened.GetRootLayer() if isinstance(flattened, Usd.Stage) else flattened
    text = layer.ExportToString()
    text = _DOC_BLOCK.sub("", text)
    text = _DOC_LINE.sub("", text)
    # ``Layer.comment`` is exported as a bare quoted string in the metadata block.
    text = _BARE_LAYER_COMMENT.sub("", text)
    # Removing a doc leaves an empty prim metadata block; drop it so the hash is
    # independent of whether documentation was ever attached.
    text = _EMPTY_METADATA.sub("\n", text)
    lines: list[str] = []
    blank = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("subLayers"):
            continue
        if not stripped:
            if blank:
                continue
            blank = True
            lines.append("")
            continue
        blank = False
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def stage_hash(stage: Usd.Stage) -> str:
    """Return the sha256 of ``canonical_stage_text(stage)``."""
    return hashlib.sha256(canonical_stage_text(stage).encode("utf-8")).hexdigest()


def stage_hash_from_file(path: str | Path) -> str:
    stage = Usd.Stage.Open(str(path))
    if stage is None:
        raise FileNotFoundError(f"could not open USD stage: {path}")
    return stage_hash(stage)
