"""Segunda llave de D6: el Python generado se re-lee con `ast` y sólo pasa si usa la forma
que el compilador sabe emitir.

La primera llave es el propio compilador (sólo emite lo que la gramática permite y renombra
todo identificador de ST a `v_<nombre>`). Ésta no confía en él: lista blanca de nodos, de
nombres, de atributos y de constantes. Sin importaciones, sin clases, sin lambdas, sin
atributos con `_` delante ni llamadas a algo que no sea una función conocida por su nombre.
El código, además, corre con `__builtins__` vacío (runtime).
"""

from __future__ import annotations

import ast
import math
import re

from .ayudas import AYUDAS

_NODOS = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign,
    ast.AugAssign, ast.If, ast.While, ast.Break, ast.Pass, ast.Expr, ast.BoolOp, ast.BinOp,
    ast.UnaryOp, ast.Compare, ast.Call, ast.Name, ast.Attribute, ast.Subscript, ast.Constant,
    ast.IfExp, ast.List, ast.Load, ast.Store, ast.And, ast.Or, ast.Add, ast.Sub, ast.Mult,
    ast.Div, ast.FloorDiv, ast.Mod, ast.BitAnd, ast.USub, ast.UAdd, ast.Not, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
    ast.Gt, ast.GtE,
)

_RE_NOMBRE = re.compile(
    r"^(s|t|e|o|_G|_wd|_i|_[cnfp]\d+|v_[a-z0-9_]+|_b_[a-z_]+|_fb_[a-z0-9_]+|_f_[a-z0-9_]+)$")
_RE_FUNCION = re.compile(r"^(_p_[a-z0-9_]+|_fb_[a-z0-9_]+|_f_[a-z0-9_]+|_entradas|_salidas)$")
_RE_LLAMABLE = re.compile(r"^(_b_[a-z_]+|_fb_[a-z0-9_]+|_f_[a-z0-9_]+)$")
_RE_ATRIBUTO = re.compile(r"^(v_[a-z0-9_]+|d_[iq][xw]\d+(_\d+)?|resto)$")
_RE_BORNE = re.compile(r"^(I|Q)\d+\.\d$|^AI\d+$")


class CodigoInseguro(Exception):
    """El Python generado no tiene la forma permitida: es un bug del compilador."""


def verificar(fuente_py: str) -> None:
    """Lanza `CodigoInseguro` si el código se sale de la lista blanca."""
    arbol = ast.parse(fuente_py, mode="exec")
    for n in ast.walk(arbol):
        if not isinstance(n, _NODOS):
            raise CodigoInseguro(f"nodo no permitido: {type(n).__name__}")
        if isinstance(n, ast.FunctionDef):
            a = n.args
            if (n.decorator_list or n.returns or a.vararg or a.kwarg or a.kwonlyargs
                    or a.defaults or a.kw_defaults or a.posonlyargs
                    or not _RE_FUNCION.match(n.name)):
                raise CodigoInseguro(f"función no permitida: {n.name}")
        elif isinstance(n, ast.arg):
            if n.annotation is not None or not _RE_NOMBRE.match(n.arg):
                raise CodigoInseguro(f"parámetro no permitido: {n.arg}")
        elif isinstance(n, ast.Name):
            if not (_RE_NOMBRE.match(n.id) or n.id in AYUDAS or _RE_FUNCION.match(n.id)):
                raise CodigoInseguro(f"nombre no permitido: {n.id}")
        elif isinstance(n, ast.Attribute):
            if not _RE_ATRIBUTO.match(n.attr) or not isinstance(n.value, (ast.Name,
                                                                          ast.Attribute)):
                raise CodigoInseguro(f"atributo no permitido: {n.attr}")
        elif isinstance(n, ast.Call):
            if (n.keywords or not isinstance(n.func, ast.Name)
                    or not (n.func.id in AYUDAS or _RE_LLAMABLE.match(n.func.id))
                    or any(isinstance(x, ast.Starred) for x in n.args)):
                raise CodigoInseguro("llamada no permitida")
        elif isinstance(n, ast.Constant):
            v = n.value
            if isinstance(v, str):
                if not _RE_BORNE.match(v):
                    raise CodigoInseguro(f"constante de texto no permitida: {v!r}")
            elif isinstance(v, float):
                if not math.isfinite(v):
                    raise CodigoInseguro("constante no finita")
            elif not isinstance(v, (bool, int)):
                raise CodigoInseguro(f"constante no permitida: {type(v).__name__}")
