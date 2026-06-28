import math

import pytest

from apolo.commands.expressions import (
    ExpressionError,
    eval_expression,
    resolve_all,
    resolve_params,
)


def test_arithmetic_and_precedence():
    assert eval_expression("2 + 3 * 4", {}) == 14
    assert eval_expression("(2 + 3) * 4", {}) == 20
    assert eval_expression("2**10", {}) == 1024
    assert eval_expression("-5 + 10", {}) == 5
    assert eval_expression("7 % 4", {}) == 3


def test_variables_and_constants():
    assert eval_expression("L / 2", {"L": 2000}) == 1000
    assert eval_expression("2 * pi", {}) == pytest.approx(2 * math.pi)
    assert eval_expression("ancho - 2*perfil", {"ancho": 1000, "perfil": 40}) == 920


def test_functions():
    assert eval_expression("sqrt(2)", {}) == pytest.approx(math.sqrt(2))
    assert eval_expression("cos(60)", {}) == pytest.approx(0.5)
    assert eval_expression("max(10, 20, 5)", {}) == 20
    assert eval_expression("round(10/3, 2)", {}) == 3.33


def test_undefined_variable():
    with pytest.raises(ExpressionError, match="no definida"):
        eval_expression("L + 1", {})


def test_division_by_zero():
    with pytest.raises(ExpressionError, match="cero"):
        eval_expression("1 / 0", {})


@pytest.mark.parametrize(
    "malicious",
    [
        "__import__('os')",
        "().__class__",
        "open('x')",
        "[1][0]",
        "'a' + 'b'",
        "lambda: 1",
        "x if 1 else 2",
    ],
)
def test_unsafe_expressions_rejected(malicious):
    with pytest.raises(ExpressionError):
        eval_expression(malicious, {"x": 1})


def test_resolve_all_with_cross_references():
    resolved = resolve_all({"b": "a * 2", "a": "10", "c": "a + b"})
    assert resolved == {"a": 10, "b": 20, "c": 30}


def test_resolve_all_detects_cycles():
    with pytest.raises(ExpressionError, match="circular"):
        resolve_all({"a": "b + 1", "b": "a + 1"})


def test_resolve_params_recursive():
    out = resolve_params(
        {"width": "=L/2", "position": {"x": "=L", "y": 5}, "name": "Caja", "tools": ["c1"]},
        {"L": 100},
    )
    assert out == {"width": 50, "position": {"x": 100, "y": 5}, "name": "Caja", "tools": ["c1"]}
