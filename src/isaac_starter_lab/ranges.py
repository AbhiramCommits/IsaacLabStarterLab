"""Small parsing helpers for inclusive seed ranges."""

from __future__ import annotations

__all__ = ["parse_seed_range"]


def parse_seed_range(spec: str) -> list[int]:
    """Parse ``"0-199"``, ``"7"`` or ``"0,2,4-6"`` into an ordered seed list.

    Duplicates are removed while preserving first-seen order, so a command line
    is deterministic even if a range overlaps a single value.
    """
    if not spec or not spec.strip():
        raise ValueError("seed range must not be empty")
    seeds: list[int] = []
    seen: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            raise ValueError(f"empty seed entry in {spec!r}")
        if "-" in chunk:
            parts = chunk.split("-")
            if len(parts) != 2:
                raise ValueError(f"invalid seed range {chunk!r}")
            start, end = int(parts[0]), int(parts[1])
            if start < 0 or end < 0:
                raise ValueError("seeds must be non-negative")
            if end < start:
                raise ValueError(f"seed range {chunk!r} ends before it starts")
            values = range(start, end + 1)
        else:
            value = int(chunk)
            if value < 0:
                raise ValueError("seeds must be non-negative")
            values = (value,)
        for value in values:
            if value not in seen:
                seen.add(value)
                seeds.append(value)
    return seeds
