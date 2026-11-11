"""A minimal discrete-event simulation kernel (SimPy-style processes on a heap).

Processes are generators that yield Events; the kernel resumes them when the
event fires. Everything runs on one virtual clock, so the root model's decode,
sub-calls, tools and the agent's own scheduling interleave deterministically.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Generator, Iterable
from typing import Any


class Event:
    __slots__ = ("sim", "callbacks", "triggered", "value")

    def __init__(self, sim: Sim) -> None:
        self.sim = sim
        self.callbacks: list[Callable[[Event], None]] | None = []
        self.triggered = False
        self.value: Any = None

    def succeed(self, value: Any = None) -> Event:
        if self.triggered:
            return self
        self.triggered = True
        self.value = value
        cbs, self.callbacks = self.callbacks, None
        for cb in cbs or ():
            self.sim._call_soon(cb, self)
        return self

    def add_callback(self, cb: Callable[[Event], None]) -> None:
        if self.triggered:
            self.sim._call_soon(cb, self)
        else:
            self.callbacks.append(cb)  # type: ignore[union-attr]


class Process(Event):
    """An Event that fires when its generator returns (value = return value)."""

    __slots__ = ("gen",)

    def __init__(self, sim: Sim, gen: Generator[Event, Any, Any]) -> None:
        super().__init__(sim)
        self.gen = gen
        sim._call_soon(self._resume, None)

    def _resume(self, ev: Event | None) -> None:
        try:
            nxt = self.gen.send(None if ev is None else ev.value)
        except StopIteration as stop:
            self.succeed(stop.value)
            return
        nxt.add_callback(self._resume)


class Sim:
    def __init__(self) -> None:
        self.now = 0.0
        self._heap: list[tuple[float, int, Callable, Any]] = []
        self._seq = 0

    # -- scheduling ---------------------------------------------------------
    def _push(self, t: float, fn: Callable, arg: Any) -> None:
        self._seq += 1
        heapq.heappush(self._heap, (t, self._seq, fn, arg))

    def _call_soon(self, fn: Callable, arg: Any) -> None:
        self._push(self.now, fn, arg)

    def call_at(self, t: float, fn: Callable[[], None]) -> None:
        self._push(max(t, self.now), lambda _a: fn(), None)

    # -- event constructors ---------------------------------------------------
    def event(self) -> Event:
        return Event(self)

    def timeout(self, dt: float, value: Any = None) -> Event:
        ev = Event(self)
        self._push(self.now + max(0.0, dt), lambda _a: ev.succeed(value), None)
        return ev

    def at(self, t: float) -> Event:
        return self.timeout(t - self.now)

    def process(self, gen: Generator[Event, Any, Any]) -> Process:
        return Process(self, gen)

    def all_of(self, events: Iterable[Event]) -> Event:
        evs = list(events)
        done = Event(self)
        if not evs:
            return done.succeed([])
        left = [len(evs)]

        def one(_e: Event) -> None:
            left[0] -= 1
            if left[0] == 0:
                done.succeed([e.value for e in evs])

        for e in evs:
            e.add_callback(one)
        return done

    # -- run ----------------------------------------------------------------
    def run(self, until: float | Event | None = None) -> None:
        stop_ev = until if isinstance(until, Event) else None
        t_stop = until if isinstance(until, (int, float)) else float("inf")
        while self._heap:
            if stop_ev is not None and stop_ev.triggered:
                return
            t, _, fn, arg = self._heap[0]
            if t > t_stop:
                self.now = t_stop
                return
            heapq.heappop(self._heap)
            self.now = t
            fn(arg)


class Resource:
    """A counting semaphore with a FIFO queue (e.g. spec-ptc's 16-worker pool)."""

    def __init__(self, sim: Sim, capacity: int) -> None:
        self.sim = sim
        self.capacity = capacity
        self.in_use = 0
        self._q: list[Event] = []

    def acquire(self) -> Event:
        ev = self.sim.event()
        if self.in_use < self.capacity:
            self.in_use += 1
            ev.succeed()
        else:
            self._q.append(ev)
        return ev

    def release(self) -> None:
        if self._q:
            self._q.pop(0).succeed()
        else:
            self.in_use -= 1
