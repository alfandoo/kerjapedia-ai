"""Deterministic THR / severance helpers with versioned legal basis.

Formulas are intentionally simplified and require caller-supplied monthly
wage and tenure; they never infer law from LLM output. Each rule carries
its legal source, effective dates, and formula identifier for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CalculatorRule:
    rule_type: str
    version: str
    legal_source: str
    effective_from: str
    effective_until: str | None
    formula_identifier: str
    status: str = "active"


CALCULATOR_RULES: dict[str, CalculatorRule] = {
    "thr": CalculatorRule(
        rule_type="thr",
        version="pp-36-2021-v1",
        legal_source="PP Nomor 36 Tahun 2021 tentang Pengupahan",
        effective_from="2021-02-02",
        effective_until=None,
        formula_identifier="thr_proportional_months_over_12",
    ),
    "pesangon": CalculatorRule(
        rule_type="pesangon",
        version="pp-35-2021-v1",
        legal_source="PP Nomor 35 Tahun 2021 tentang PKWT, Alih Daya, Waktu Kerja, dan PHK",
        effective_from="2021-02-02",
        effective_until=None,
        formula_identifier="pesangon_tenure_table_simplified",
    ),
}


@dataclass(frozen=True)
class CalculationInput:
    rule_type: str
    monthly_wage: float
    tenure_months: int


@dataclass(frozen=True)
class CalculationResult:
    amount: float
    rule: CalculatorRule
    legal_basis: str
    breakdown: dict


def get_rule(rule_type: str, session=None) -> CalculatorRule:
    """Code default, overridden by the active DB `calculation_rules` row.

    `session` is optional: without one (or on any DB failure) the versioned
    code constants below apply, so the calculator stays deterministic offline.
    """
    if session is not None:
        try:
            from app.models.business import CalculationRule as CalculationRuleRow

            row = (
                session.query(CalculationRuleRow)
                .filter(
                    CalculationRuleRow.rule_type == rule_type,
                    CalculationRuleRow.status == "active",
                )
                .order_by(CalculationRuleRow.effective_from.desc())
                .first()
            )
            if row is not None:
                return CalculatorRule(
                    rule_type=row.rule_type,
                    version=row.version,
                    legal_source=row.legal_source,
                    effective_from=row.effective_from.isoformat(),
                    effective_until=(
                        row.effective_until.isoformat() if row.effective_until else None
                    ),
                    formula_identifier=row.formula_identifier,
                    status=row.status,
                )
        except Exception:
            pass
    try:
        return CALCULATOR_RULES[rule_type]
    except KeyError as exc:
        raise ValueError(f"Unknown calculator rule: {rule_type!r}.") from exc


def _validate(payload: CalculationInput) -> None:
    if payload.monthly_wage <= 0:
        raise ValueError("monthly_wage must be positive.")
    if payload.monthly_wage > 1_000_000_000:
        raise ValueError("monthly_wage exceeds plausible bounds.")
    if payload.tenure_months < 0 or payload.tenure_months > 600:
        raise ValueError("tenure_months must be between 0 and 600.")


def calculate(payload: CalculationInput, session=None) -> CalculationResult:
    """Deterministic calculation; raises ValueError on invalid input."""
    rule = get_rule(payload.rule_type, session)
    _validate(payload)
    if payload.rule_type == "thr":
        # THR: 1 month continuous service => 1x wage; otherwise pro-rata.
        if payload.tenure_months >= 12:
            amount = float(payload.monthly_wage)
            basis = "masa kerja >= 12 bulan: 1x upah sebulan"
        else:
            amount = float(payload.monthly_wage) * payload.tenure_months / 12.0
            basis = f"masa kerja {payload.tenure_months} bulan: pro-rata months/12 x upah"
        return CalculationResult(
            amount=round(amount, 2),
            rule=rule,
            legal_basis=rule.legal_source,
            breakdown={"formula": rule.formula_identifier, "detail": basis},
        )
    # Pesangon (simplified tenure table for deterministic estimates only).
    years = payload.tenure_months / 12.0
    if years < 1:
        multiplier = 1.0
    elif years < 2:
        multiplier = 2.0
    elif years < 3:
        multiplier = 3.0
    elif years < 4:
        multiplier = 4.0
    elif years < 5:
        multiplier = 5.0
    elif years < 6:
        multiplier = 6.0
    elif years < 7:
        multiplier = 7.0
    elif years < 8:
        multiplier = 8.0
    else:
        multiplier = 9.0
    return CalculationResult(
        amount=round(float(payload.monthly_wage) * multiplier, 2),
        rule=rule,
        legal_basis=rule.legal_source,
        breakdown={
            "formula": rule.formula_identifier,
            "tenure_years": round(years, 2),
            "multiplier_months": multiplier,
            "note": "Estimasi indikatif; rujuk pasal PHK yang berlaku.",
        },
    )
