"""Dependency-free in-process pub/sub used by the CPU lab and CI.

The bus serialises every message to a dictionary on ``publish`` and rebuilds it
on delivery, exactly like a network transport.  That keeps schema round-tripping
honest and makes the LocalBus a faithful stand-in for ROS 2 in tests.

Delivery is deterministic: the queue is drained in FIFO order, subscribers are
called in registration order, and messages published from inside a callback are
queued for the *next* ``spin_once``.
"""

from __future__ import annotations

from collections import defaultdict, deque

from ..sim.schema import MESSAGE_TYPES, TOPICS
from .base import Callback

__all__ = ["LocalBus"]


class LocalBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callback]] = defaultdict(list)
        self._queue: deque[tuple[str, dict]] = deque()
        self.published = 0

    def publish(self, topic: str, message) -> None:
        if topic not in TOPICS:
            raise ValueError(f"unknown lab topic {topic!r}; expected one of {TOPICS}")
        expected = MESSAGE_TYPES[topic]
        if not isinstance(message, expected):
            raise TypeError(
                f"topic {topic} expects {expected.__name__}, got {type(message).__name__}"
            )
        self._queue.append((topic, message.to_dict()))
        self.published += 1

    def subscribe(self, topic: str, callback: Callback) -> None:
        if topic not in TOPICS:
            raise ValueError(f"unknown lab topic {topic!r}; expected one of {TOPICS}")
        if not callable(callback):
            raise TypeError("callback must be callable")
        self._subscribers[topic].append(callback)

    def spin_once(self) -> int:
        batch = list(self._queue)
        self._queue.clear()
        for topic, payload in batch:
            message = MESSAGE_TYPES[topic].from_dict(payload)
            for callback in list(self._subscribers[topic]):
                callback(message)
        return len(batch)

    def close(self) -> None:
        self._queue.clear()
        self._subscribers.clear()
