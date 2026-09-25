"""Deterministic employment calculator — no LLM as calculation engine.

Pipeline: User Input → Validation → Rule Selection → Regulation Version →
Deterministic Formula → Result → Legal Basis → Optional LLM Explanation.

Rules are versioned in code (effective_from/until + legal source). If a
future DB-backed rule table is needed, it must remain additive and keep
Neon as source of truth.
"""

from app.services.calculator.engine import (
    CALCULATOR_RULES,
    CalculationInput,
    CalculationResult,
    calculate,
    get_rule,
)

__all__ = [
    "CALCULATOR_RULES",
    "CalculationInput",
    "CalculationResult",
    "calculate",
    "get_rule",
]
