"""Transport abstraction shared by the CPU and ROS 2 tracks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

__all__ = ["Bridge", "Callback"]


Callback = Callable[[Any], None]


@runtime_checkable
class Bridge(Protocol):
    """Minimal publish/subscribe contract.

    Implementations must deliver messages in publish order and must round-trip
    every message through the schema's ``to_dict``/``from_dict`` methods so the
    two bridges cannot drift.
    """

    def publish(self, topic: str, message: Any) -> None: ...

    def subscribe(self, topic: str, callback: Callback) -> None: ...

    def spin_once(self) -> int: ...

    def close(self) -> None: ...
