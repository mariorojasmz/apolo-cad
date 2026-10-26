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


def _centros_cadena(*args: float) -> float:
    """centros_cadena(paso, z_a, z_b, eslabones): la distancia EXACTA entre centros de una
    cadena de ese largo (inversa de Tsubaki, `library/transmision.centros_para_eslabones`), para
    colocar los piñones antes de `create_chain` (plan plantilla-rodillos-cadena, D2)."""
    from apolo.library.transmision import centros_para_eslabones

    if len(args) != 4:
        raise ExpressionError("centros_cadena(paso, z_a, z_b, eslabones) lleva 4 argumentos")
    paso, za, zb, eslabones = args
    if paso <= 0 or za != int(za) or zb != int(zb) or eslabones != int(eslabones):
        raise ExpressionError("centros_cadena: paso > 0; dientes y eslabones enteros")
    try:
        return centros_para_eslabones(paso, int(za), int(zb), int(eslabones))
    except ValueError as exc:
        raise ExpressionError(f"centros_cadena: {exc}") from None


ALLOWED_FUNCS: dict[str, Callable] = {
    "centros_cadena": _centros_cadena,
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

# Comparadores para condicionales de tablas de diseño (V6.4a). Devuelven True/False; el
# nodo Compare los colapsa a 1.0/0.0 para que el resto del motor siga siendo numérico.
_CMPOPS = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
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
        # Condicionales para tablas de diseño (V6.4a): ternario perezoso + comparadores +
        # and/or. Nada de strings/in/is/lambda: los constantes no numéricas siguen rechazadas.
        if isinstance(node, ast.IfExp):  # a if cond else b — evalúa SOLO la rama tomada
            return ev(node.body) if ev(node.test) != 0 else ev(node.orelse)
        if isinstance(node, ast.Compare):  # a<b, a<=b<c (encadenado), a==b… → 1.0/0.0
            if any(type(op) not in _CMPOPS for op in node.ops):  # rechaza in/is aunque corto-circuite
                raise ExpressionError(f"Comparador no permitido en '{expr}'")
            left = ev(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = ev(comparator)
                if not _CMPOPS[type(op)](left, right):
                    return 0.0  # corto-circuito como Python (a<b<c = a<b and b<c)
                left = right
            return 1.0
        if isinstance(node, ast.BoolOp):  # and/or con corto-circuito → 1.0/0.0
            if isinstance(node.op, ast.And):
                return 1.0 if all(ev(v) != 0 for v in node.values) else 0.0
            if isinstance(node.op, ast.Or):
                return 1.0 if any(ev(v) != 0 for v in node.values) else 0.0
            raise ExpressionError(f"Operador booleano no permitido en '{expr}'")
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


_TRIG = ("sin", "cos", "tan")
#: Lo que la gramática dice de los ángulos (plan trabas-de-modelado, D1).
ANGULOS = ("sin/cos/tan toman GRADOS: tan(30) = 0,577. No conviertas a radianes con pi/180: "
           "tan(a*pi/180) es la tangente de a·π/180 GRADOS (≈ 0).")


def _lleva_pi(nodo: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "pi" for n in ast.walk(nodo))


def _es_180(nodo: ast.AST) -> bool:
    return isinstance(nodo, ast.Constant) and nodo.value in (180, 180.0)


def avisos_expresion(expr: str) -> list[str]:
    """Avisos (no errores) de una expresión que se evalúa bien pero casi seguro dice otra cosa:
    un argumento de sin/cos/tan que divide por 180 algo que lleva `pi` (`tan(a*pi/180)`) es un
    ángulo convertido a RADIANES, y las trigonométricas toman GRADOS (plan trabas-de-modelado,
    D1: el modelador obtuvo 0,0009 en vez de 0,052). Una expresión mal escrita no avisa: su error
    es el de la evaluación."""
    texto = str(expr).strip()
    if texto.startswith(EXPR_PREFIX):
        texto = texto[1:]
    try:
        arbol = ast.parse(texto, mode="eval")
    except SyntaxError:
        return []
    out = []
    for nodo in ast.walk(arbol):
        if not (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name)
                and nodo.func.id in _TRIG):
            continue
        for arg in nodo.args:
            if any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div) and _es_180(n.right)
                   and _lleva_pi(n.left) for n in ast.walk(arg)):
                out.append(f"{nodo.func.id}() toma GRADOS: «{ast.unparse(arg)}» convierte a radianes "
                           f"con pi/180 y da el {nodo.func.id} de un ángulo casi nulo; pasa el ángulo "
                           "en grados tal cual (tan(30) = 0,577)")
                break
    return out


def resolve_params(value: Any, resolved_vars: dict[str, float],
                   literales: tuple[str, ...] = ()) -> Any:
    """Sustituye recursivamente las cadenas '=expr' por su valor numérico. `literales` = claves
    de PRIMER nivel cuyo valor es texto literal aunque empiece con '=' (`CommandSpec.literales`:
    la designación IEC 81346 «=Faja1-Q1» no es una expresión, plan V8.1 D4)."""
    if literales and isinstance(value, dict):
        return {k: v if k in literales else resolve_params(v, resolved_vars)
                for k, v in value.items()}
    if isinstance(value, str) and value.startswith(EXPR_PREFIX):
        result = eval_expression(value[1:], resolved_vars)
        return round(result, 9)
    if isinstance(value, list):
        return [resolve_params(v, resolved_vars) for v in value]
    if isinstance(value, dict):
        return {k: resolve_params(v, resolved_vars) for k, v in value.items()}
    return value
