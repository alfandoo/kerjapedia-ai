from app.services.calculator import CalculationInput, calculate, get_rule


def test_thr_full_year():
    result = calculate(CalculationInput("thr", 5_000_000, 12))
    assert result.amount == 5_000_000
    assert "36" in result.legal_basis


def test_thr_pro_rata():
    result = calculate(CalculationInput("thr", 6_000_000, 6))
    assert result.amount == 3_000_000


def test_pesangon_deterministic_and_versioned():
    first = calculate(CalculationInput("pesangon", 4_000_000, 30))
    second = calculate(CalculationInput("pesangon", 4_000_000, 30))
    assert first.amount == second.amount
    assert first.rule.version == "pp-35-2021-v1"


def test_invalid_inputs_rejected():
    import pytest

    with pytest.raises(ValueError):
        calculate(CalculationInput("thr", -1, 6))
    with pytest.raises(ValueError):
        calculate(CalculationInput("unknown", 1_000_000, 6))


def test_rule_lookup():
    assert get_rule("thr").formula_identifier.startswith("thr_")
