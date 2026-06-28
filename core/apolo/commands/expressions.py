"""Motor de expresiones paramétricas.

Evalúa expresiones como ``2*ancho + 40`` o ``=L/2`` de forma segura
(AST con lista blanca de nodos: nada de atributos, índices ni eval).
Las variables de proyecto se definen con el comando ``set_variable`` y
cualquier parámetro numérico de un comando acepta una cadena ``"=expr"``.
"""

from __future__ import annotations

import ast
import math
from typing import Any, Callable

EXPR_PREFIX = "="

ALLOWED_FUNCS: dict[str, Callable] = {
    "sqrt": math.sqrt,
    "sin": lambda d: math.sin(math.radians(d)),
    "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
    "abs": abs,
    "min": min,
    "max": max,
    "floor": math.floor,
    "ceil": math.ceil,
    "round": lambda x, n=0: round(x, int(n)),
}

ALLOWED_CONSTANTS: dict[str, float] = {"pi": math.pi}

_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}


class ExpressionError(Exception):
    pass


def eval_expression(expr: str, variables: dict[str, float] | Any) -> float:
    """Evalúa una expresión aritmética contra un diccionario de variables."""
    expr = str(expr).strip()
    if expr.startswith("="):  # tolera el prefijo '=' opcional (igual que los campos numéricos)
        expr = expr[1:].strip()
    if not expr:
        raise ExpressionError("Expresión vacía")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Expresión inválida '{expr}': {exc.msg}") from exc

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return float(node.value)
            raise ExpressionError(f"Constante no numérica en '{expr}'")
        if isinstance(node, ast.Name):
            if node.id in ALLOWED_CONSTANTS:
                return ALLOWED_CONSTANTS[node.id]
            try:
                return float(variables[node.id])
            except KeyError:
                raise ExpressionError(f"Variable '{node.id}' no definida") from None
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            try:
                return float(_BINOPS[type(node.op)](ev(node.left), ev(node.right)))
            except ZeroDivisionError:
                raise ExpressionError(f"División por cero en '{expr}'") from None
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = ev(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCS:
                raise ExpressionError(f"Función no permitida en '{expr}'")
            if node.keywords:
                raise ExpressionError(f"Argumentos con nombre no permitidos en '{expr}'")
            return float(ALLOWED_FUNCS[node.func.id](*[ev(a) for a in node.args]))
        raise ExpressionError(f"Elemento no permitido en la expresión '{expr}'")

    return ev(tree)


def resolve_all(raw_variables: dict[str, Any]) -> dict[str, float]:
    """Resuelve todas las variables, permitiendo referencias entre ellas,
    con detección de ciclos."""
    resolved: dict[str, float] = {}
    visiting: set[str] = set()

    class _Lazy:
        def __getitem__(self, name: str) -> float:
            return get(name)

    lazy = _Lazy()

    def get(name: str) -> float:
        if name in resolved:
            return resolved[name]
        if name not in raw_variables:
            raise KeyError(name)
        if name in visiting:
            raise ExpressionError(f"Referencia circular en la variable '{name}'")
        visiting.add(name)
        try:
            value = eval_expression(str(raw_variables[name]), lazy)
        except ExpressionError as exc:
            raise ExpressionError(f"Variable '{name}': {exc}") from None
        finally:
            visiting.discard(name)
        resolved[name] = value
        return value

    for name in raw_variables:
        get(name)
    return resolved


def resolve_params(value: Any, resolved_vars: dict[str, float]) -> Any:
    """Sustituye recursivamente las cadenas '=expr' por su valor numérico."""
    if isinstance(value, str) and value.startswith(EXPR_PREFIX):
        result = eval_expression(value[1:], resolved_vars)
        return round(result, 9)
    if isinstance(value, list):
        return [resolve_params(v, resolved_vars) for v in value]
    if isinstance(value, dict):
        return {k: resolve_params(v, resolved_vars) for k, v in value.items()}
    return value
