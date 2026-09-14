"""Cleaning report records: tiered gates with explicit severity."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Gate:
    """One check. ``block`` gates fail the build; ``warn`` gates advise."""

    gate_id: str
    severity: str  # block | warn
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class CleaningReport:
    """Outcome of the cleaning stage: status plus every gate and warning."""

    status: str  # passed | review_required
    gates: tuple[Gate, ...] = ()
    warnings: tuple[str, ...] = ()
    stats: dict = field(default_factory=dict)
