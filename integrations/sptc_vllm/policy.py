"""The sptc 'agent' scheduling policy as plain functions. Pure: no vLLM import.

Mirrors sptc_sim/server.py (policy "agent" with reject_bets):
- SptcConfig        ~ ServerConfig.spec_* knobs (free window as a sequence count, not a knee)
- admit_bet         ~ Server.admits_bet_now / _spec_admissible
- bets_last         ~ Server._order for "agent": bets behind all certain work, so the FCFS
                      preemption victim (running[-1]) is the newest bet (order_by_rank is the
                      general stable reorder it is built on)
- PrefillAllowance  ~ Server._spec_left in _chunk/_schedule (shared bet+early prefill allowance;
                      prefill_allowance mode ~ ServerConfig.spec_prefill_mode)
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, fields
from enum import Enum
from typing import TypeVar

CLASS_KEY = "sptc_class"  # SamplingParams.extra_args key (OpenAI API: vllm_xargs)
CONFIG_KEY = "sptc"  # vllm_config.additional_config key
STOP_REASON_REJECTED = "sptc_bet_rejected"  # bet refused at admission
STOP_REASON_DROPPED = "sptc_bet_dropped"  # running bet dropped instead of preempted
# When the prefill allowance applies: in every step (fixed); only while a more certain
# stream is decoding (adaptive: a bet yields to any non-bet decoder, early work only to an
# untagged one); or never (off).
ALLOWANCE_MODES = ("fixed", "adaptive", "off")


# --------------------------------------------------------------------------- config
@dataclass(frozen=True)
class SptcConfig:
    free_window: int = 8  # bets admitted only while len(running) + 1 <= free_window
    kv_reserve: float = 0.10  # ... and KV usage <= 1 - kv_reserve
    spec_prefill_budget: int = 512  # prefill tokens per step shared by bet+early; <= 0: unlimited
    prefill_allowance: str = "fixed"  # ALLOWANCE_MODES: when spec_prefill_budget applies
    # A waiting bet that passes the gate but is not admitted (token budget, allowance, a
    # transient vLLM skip) is re-gated each step; after this many such steps it is rejected.
    bet_hold_steps: int = 16

    def __post_init__(self) -> None:
        if type(self.free_window) is not int or self.free_window < 0:
            raise ValueError(f"sptc.free_window must be an int >= 0, got {self.free_window!r}")
        kv = self.kv_reserve
        if isinstance(kv, bool) or not isinstance(kv, (int, float)) or not 0.0 <= kv < 1.0:
            raise ValueError(f"sptc.kv_reserve must be a number in [0, 1), got {kv!r}")
        if type(self.spec_prefill_budget) is not int:
            raise ValueError(
                f"sptc.spec_prefill_budget must be an int, got {self.spec_prefill_budget!r}"
            )
        if type(self.bet_hold_steps) is not int or self.bet_hold_steps < 0:
            raise ValueError(
                f"sptc.bet_hold_steps must be an int >= 0, got {self.bet_hold_steps!r}"
            )
        if not isinstance(self.prefill_allowance, str) or (
            self.prefill_allowance not in ALLOWANCE_MODES
        ):
            raise ValueError(
                f"sptc.prefill_allowance must be one of {list(ALLOWANCE_MODES)}, "
                f"got {self.prefill_allowance!r}"
            )

    @property
    def allowance_budget(self) -> int:
        """spec_prefill_budget, or 0 (unlimited) when the allowance is off."""
        return 0 if self.prefill_allowance == "off" else self.spec_prefill_budget

    @classmethod
    def from_mapping(cls, raw: object) -> SptcConfig:
        if raw is None:
            return cls()
        if not isinstance(raw, Mapping):
            raise ValueError(
                f'additional_config["{CONFIG_KEY}"] must be a JSON object, '
                f"got {type(raw).__name__}"
            )
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown sptc knob(s) {sorted(unknown)}; known: {sorted(known)}")
        return cls(**dict(raw))


def config_from_additional(additional_config: object) -> SptcConfig:
    """additional_config is a dict or an opaque SupportsHash object (vllm/config/vllm.py)."""
    if not isinstance(additional_config, Mapping):
        return SptcConfig()
    return SptcConfig.from_mapping(additional_config.get(CONFIG_KEY))


# --------------------------------------------------------------------------- classes
class SptcClass(str, Enum):
    NORMAL = "normal"
    EARLY = "early"  # dispatched ahead of the real run, almost surely used
    BET = "bet"  # may never be used


_BY_TAG = {"bet": SptcClass.BET, "early": SptcClass.EARLY}


def classify(extra_args: object) -> SptcClass:
    """Absent, unknown or malformed tags mean NORMAL, i.e. vanilla vLLM behaviour."""
    if not isinstance(extra_args, Mapping):
        return SptcClass.NORMAL
    tag = extra_args.get(CLASS_KEY)
    return _BY_TAG.get(tag, SptcClass.NORMAL) if isinstance(tag, str) else SptcClass.NORMAL


def is_prefill(num_tokens: int, num_computed_tokens: int) -> bool:
    """More than one known token not yet computed: prompt (or recompute) work, not a decode.
    Sync decode: num_tokens - computed == 1. Async decode: <= 0 (output placeholders)."""
    return num_tokens - num_computed_tokens > 1


def scan_decoders(decoding: Iterable[tuple[SptcClass, bool]]) -> tuple[bool, bool]:
    """(an untagged request is decoding, a non-bet request is decoding) from (class,
    is decoding) pairs. Stops at the first untagged decoder."""
    nonbet = False
    for cls, dec in decoding:
        if dec and cls is not SptcClass.BET:
            if cls is SptcClass.NORMAL:
                return True, True
            nonbet = True
    return False, nonbet


def finishes_in_flight(
    *, num_output_placeholders: int, num_computed_tokens: int, num_prompt_tokens: int,
    max_tokens: int, num_tokens: int | None = None, num_in_flight_tokens: int = 0,
) -> bool:
    """The step already in flight reaches max_tokens, so the request finishes on output that
    is already being computed.
    - Async scheduling (placeholders > 0): vLLM's own running-loop test.
    - Sync scheduling with steps in flight (pipeline parallelism's batch queue): there are
      no placeholders, but computed tokens already include the step in flight. That step
      samples at least one token if it covers every known token (num_tokens)."""
    if num_output_placeholders > 0:
        return num_computed_tokens + 2 - num_output_placeholders >= num_prompt_tokens + max_tokens
    return (
        num_in_flight_tokens > 0
        and num_tokens is not None
        and num_computed_tokens >= num_tokens
        and num_tokens + 1 >= num_prompt_tokens + max_tokens
    )


# --------------------------------------------------------------------------- gate
@dataclass(frozen=True)
class BetVerdict:
    admit: bool
    reason: str  # "ok" | "nonbet_waiting" | "free_window" | "kv_reserve"


def admit_bet(
    *, num_running: int, nonbet_waiting: bool, kv_usage: float, cfg: SptcConfig
) -> BetVerdict:
    """Spare capacity right now: no certain work waiting, one more decoding sequence stays
    inside the free window, and KV usage is at most 1 - kv_reserve. Like the simulator's
    headroom check, KV is measured before the bet's own allocation: the reserve is an
    admission threshold, not a cap on how far an admitted bet may grow (a bet that grows
    into the reserve is the first victim when vLLM runs out of KV)."""
    if nonbet_waiting:
        return BetVerdict(False, "nonbet_waiting")
    if num_running + 1 > cfg.free_window:
        return BetVerdict(False, "free_window")
    if kv_usage > 1.0 - cfg.kv_reserve:
        return BetVerdict(False, "kv_reserve")
    return BetVerdict(True, "ok")


# --------------------------------------------------------------------------- ordering
T = TypeVar("T")


def order_by_rank(items: list[T], rank: Callable[[T], int]) -> list[T]:
    """Stable sort by rank (each item's rank is computed once). Returns `items` itself when
    it is already in order, so callers can skip rebuilding."""
    ranks = [rank(x) for x in items]
    if all(a <= b for a, b in zip(ranks, ranks[1:])):
        return items
    order = sorted(range(len(items)), key=ranks.__getitem__)  # sorted() is stable
    return [items[i] for i in order]


def bets_last(items: list[T], is_bet: Callable[[T], bool]) -> list[T]:
    """Stable partition: non-bets keep their order, then bets in their order. Returns `items`
    itself when it is already partitioned, so callers can skip rebuilding."""
    return order_by_rank(items, lambda x: 1 if is_bet(x) else 0)


# --------------------------------------------------------------------------- allowance
class PrefillAllowance:
    """Prefill tokens per step shared by all bet and early requests. budget <= 0: unlimited.

    adaptive: the allowance limits a tagged prefill only while a more certain stream is
    decoding, so there is something to protect: a bet while any non-bet request decodes,
    an early request while an untagged one decodes. Callers ask applies(cls, decoders)
    before limiting a tagged prefill; `decoders` returns scan_decoders(...) for the step
    and is called at most once per step, never in a step without tagged prefill, so
    untagged-only traffic pays nothing for it."""

    def __init__(self, budget: int, adaptive: bool = False) -> None:
        self.budget = budget
        self.left = budget
        self.adaptive = adaptive
        self._decoders: tuple[bool, bool] | None = None  # this step; None: not scanned yet

    @property
    def unlimited(self) -> bool:
        """Never limits (budget <= 0), whatever the step."""
        return self.budget <= 0

    def applies(self, cls: SptcClass, decoders: Callable[[], tuple[bool, bool]]) -> bool:
        """Whether the allowance limits a prefill of class cls (bet or early) in this step."""
        if self.adaptive and self._decoders is None and not self.unlimited:
            self._decoders = decoders()
        return self.applied(cls)

    def applied(self, cls: SptcClass) -> bool:
        """applies() as decided so far in this step, without scanning: False in adaptive
        mode if no tagged prefill asked yet (then nothing was limited)."""
        if self.unlimited:
            return False
        if not self.adaptive:
            return True
        if self._decoders is None:
            return False
        untagged, nonbet = self._decoders
        return nonbet if cls is SptcClass.BET else untagged

    @property
    def exhausted(self) -> bool:
        return self.short_of(1)

    def short_of(self, n: int) -> bool:
        """Fewer than n (at least 1) tokens left. With vLLM's multi-module MTP prefill
        lookahead L > 1, a chunk capped to fewer than L tokens can be cut to 0."""
        return not self.unlimited and self.left < max(1, n)

    def reset(self) -> None:
        self.left = self.budget
        self._decoders = None

    def cap(self, n: int, keep: int = 0) -> int:
        """At most n tokens, leaving `keep` of what is left for later requests in the step."""
        return n if self.unlimited else max(0, min(n, self.left - keep))

    def charge(self, n: int) -> None:
        if not self.unlimited:
            self.left -= n
