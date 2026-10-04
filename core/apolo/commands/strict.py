"""Entrada ESTRICTA de params: una clave que el comando no declara se rechaza y se corrige.

Plan `estado-regen-y-params-estrictos` (D6–D8). Antes `_validate_model` DESCARTABA en silencio
toda clave desconocida: el agente mandaba `pattern_linear.name` creyendo que nombraba las copias
(102 veces en el proyecto 38) y un typo pasaba verde con el default.

- **El mismo modelo, dos modos** (D6): la ENTRADA de un cliente se valida con `extra="forbid"`
  POR LLAMADA (pydantic ≥ 2.12) contando sólo los `extra_forbidden`; el REPLAY del log valida
  con `extra="ignore"` explícito, así los comandos guardados con claves viejas regeneran igual.
  Los modelos y el JSON Schema publicado no cambian.
- **Sólo se rechaza lo que el cliente INTRODUCE** (D7): un edit resta las claves desconocidas
  que ya estaban guardadas, por ruta. La UI reenvía los params enteros: el `name` viejo de un
  `pattern_linear` guardado pasa y se queda (el replay lo sigue ignorando).
- **El rechazo enseña** (D8): el comando, la ruta de cada clave, las válidas de ese nivel y
  «¿quisiste decir…?»; `material`/`color` apuntan a `set_material`/`set_color`.

La detección no necesita las variables (un `=expr` sin resolver da `float_parsing`, no
`extra_forbidden`): por eso sirve ANTES del regenerate de un lote, cuando las variables que el
propio lote define todavía no existen.
"""

from __future__ import annotations

import difflib
import types
from typing import TYPE_CHECKING, Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

from .errors import CommandError

if TYPE_CHECKING:
    from .spec import CommandSpec

Ruta = tuple  # ruta de pydantic: ("position", "q") · ("flaps", 0, "child", "k")

# Claves que son METADATO de la pieza, no params de un comando: el rechazo apunta a la tool.
_METADATO = {
    "material": "el material no es un parámetro; asígnalo con set_material a la pieza ya creada",
    "color": "el color no es un parámetro; asígnalo con set_color a la pieza ya creada",
}


def unknown_paths(model: type[BaseModel], params: Any) -> set[Ruta]:
    """Rutas de las claves que `model` no declara, en TODOS los niveles (anidadas, en listas,
    dentro de un `X | None`), en una sola pasada de pydantic."""
    try:
        model.model_validate(params or {}, extra="forbid")
    except ValidationError as exc:
        return {tuple(e["loc"]) for e in exc.errors() if e["type"] == "extra_forbidden"}
    return set()


def reject_unknown(spec: CommandSpec | None, params: Any, previous: Any = None) -> None:
    """Lanza `CommandError` si `params` trae claves que el comando no declara. Con `previous`
    (los params GUARDADOS de un edit) sólo cuentan las que no estaban ya guardadas (D7).
    `spec` None (tipo desconocido) no hace nada: ese error lo da quien valida el tipo."""
    if spec is None:
        return
    nuevas = unknown_paths(spec.model, params)
    if nuevas and previous is not None:
        nuevas -= unknown_paths(spec.model, previous)
    if nuevas:
        raise CommandError(rejection_text(spec.type, spec.model, nuevas))


def rejection_text(cmd_type: str, model: type[BaseModel], paths: set[Ruta]) -> str:
    """El texto del rechazo (D8), en tuteo neutro: una línea por clave desconocida."""
    lineas = []
    for ruta in sorted(paths, key=ruta_txt):
        clave = ruta[-1]
        nivel = model_at(model, ruta[:-1])
        validos = list(_campos(nivel)) if nivel is not None else []
        txt = f"- «{ruta_txt(ruta)}»"
        if clave in _METADATO:
            txt += f": {_METADATO[clave]}."
        else:
            parecida = difflib.get_close_matches(str(clave), validos, n=1, cutoff=0.6)
            sugerencia = ruta_txt(ruta[:-1] + tuple(parecida))
            txt += f" no existe; ¿quisiste decir «{sugerencia}»?" if parecida else " no existe."
        if validos:
            txt += f" Válidos en ese nivel: {', '.join(validos)}."
        lineas.append(txt)
    n = len(lineas)
    cabeza = "Parámetro desconocido" if n == 1 else f"{n} parámetros desconocidos"
    return "\n".join([f"{cabeza} en {cmd_type} (no se aplicó nada):", *lineas])


def ruta_txt(ruta: Ruta) -> str:
    """("flaps", 0, "child", "k") → "flaps[0].child.k"."""
    out = ""
    for parte in ruta:
        out += f"[{parte}]" if isinstance(parte, int) else (f".{parte}" if out else str(parte))
    return out


def model_at(model: type[BaseModel], ruta: Ruta) -> type[BaseModel] | None:
    """El modelo que valida el nivel al que lleva `ruta` (None si ahí no hay un modelo)."""
    tp: Any = model
    for parte in ruta:
        tp = _paso(tp, parte)
        if tp is None:
            return None
    tp = _desenvuelve(tp)
    return tp if _es_modelo(tp) else None


def field_paths(model: type[BaseModel], prefijo: str = "", _vistos: tuple = ()) -> list[str]:
    """Todas las rutas de campos que declara `model`, en orden de declaración: `position.x`,
    `flaps[].child.lado`, `mapa{}.k` (trinquete D12: `tests/test_contrato_comandos.py`)."""
    out: list[str] = []
    for nombre, campo in _campos(model).items():
        ruta = f"{prefijo}.{nombre}" if prefijo else nombre
        out.append(ruta)
        sufijo, sub = _contenido(campo.annotation)
        if sub is not None and sub not in _vistos:
            out += field_paths(sub, ruta + sufijo, (*_vistos, model))
    return out


def _es_modelo(tp: Any) -> bool:
    return isinstance(tp, type) and issubclass(tp, BaseModel)


def _campos(model: type[BaseModel]) -> dict[str, Any]:
    """`model_fields` con las referencias adelantadas YA resueltas: un modelo que anota con un
    string una clase definida más abajo (`cara: "EdgeSelector | None"` de `snap_to`) queda
    incompleto hasta su primera validación y, mientras tanto, su anotación es un ForwardRef."""
    if not getattr(model, "__pydantic_complete__", True):
        model.model_rebuild()
    return model.model_fields


def _desenvuelve(tp: Any) -> Any:
    """`X | None`, `Optional[X]`, `Annotated[X, …]` → X (si queda UN solo tipo no-None)."""
    while True:
        origen = get_origin(tp)
        if origen is Annotated:
            tp = get_args(tp)[0]
        elif origen in (Union, types.UnionType):
            args = [a for a in get_args(tp) if a is not type(None)]
            if len(args) != 1:
                return tp
            tp = args[0]
        else:
            return tp


def _paso(tp: Any, parte: Any) -> Any:
    """El tipo al que lleva un elemento de ruta de pydantic dentro de `tp` (None: no se sabe)."""
    tp = _desenvuelve(tp)
    if _es_modelo(tp):
        campo = _campos(tp).get(parte) if isinstance(parte, str) else None
        return campo.annotation if campo is not None else None
    origen, args = get_origin(tp), get_args(tp)
    if origen in (list, tuple, set, frozenset) and isinstance(parte, int) and args:
        return args[0]
    if origen is dict and len(args) == 2:
        return args[1]
    return None


def _contenido(tp: Any) -> tuple[str, type[BaseModel] | None]:
    """Si el campo contiene un modelo (directo, en lista o valor de dict): (sufijo, modelo)."""
    tp = _desenvuelve(tp)
    if _es_modelo(tp):
        return "", tp
    origen, args = get_origin(tp), get_args(tp)
    if origen in (list, tuple, set, frozenset) and args:
        _, sub = _contenido(args[0])
        return "[]", sub
    if origen is dict and len(args) == 2:
        _, sub = _contenido(args[1])
        return "{}", sub
    return "", None
