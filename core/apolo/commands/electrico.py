"""Los comandos del tablero eléctrico (plan V8.1, D2–D4 y D9; `add_program`, V8.3 D3): sus
`CommandSpec`, la materialización de designaciones y el prefijo de función de `insert_project`.

Son del CARRIL (`kind="electrico"`, `doc/carril.py`): no entran a la firma encadenada, no corren
en el bucle del regenerate (su executor lo dice si alguien lo llama) y se evalúan después, todos
juntos, en `electrico_eval.evaluar_carril`. `registry.py` (congelado por el trinquete) sólo
suma `SPECS_ELECTRICO` a su `REGISTRY`.

- **D3, la designación se MATERIALIZA al entrar** (`materializar`): un `add_device` o un
  `add_cable` sin designación recibe la siguiente libre de su letra (la `funcion` de su ficha;
  W para los cables) y se ESCRIBE en los params guardados, como el attachment de
  `insert_project`. Numerar por orden en el regenerate renombraría -Q2 al borrar -Q1 y rompería
  sus cables.
- **D9, `insert_project` trae el carril del origen** con el aspecto de función de la instancia
  (`prefijar`): «-Q1» → «=Faja1-Q1», «=Sub-K1» → «=Faja1.Sub-K1»; la pieza ligada sigue el
  prefijo de ids `{cmd}_{orig}`.
"""

from __future__ import annotations

import re
import unicodedata

from .errors import CommandError
from .models_electrico import AddCableParams, AddDeviceParams, AddProgramParams, AddWireParams
from .spec import CommandSpec
from .state import ExecContext

#: Los tipos que designan (D3): su designación es el nombre que referencian los cables.
DESIGNAN = ("add_device", "add_cable")
LETRA_CABLE = "W"  # IEC 81346-2: W = conducir energía o señales (cables, conductores)


def _exec_carril(ctx: ExecContext, cmd_id: str, p) -> None:
    """Un comando del carril no corre en el bucle del regenerate: lo evalúa `doc/carril.py`."""
    raise CommandError(f"{cmd_id}: un comando eléctrico no se ejecuta en la escena (es del carril)")


#: Una designación o referencia IEC 81346 empieza con «=» cuando lleva aspecto de función
#: («=Faja1-Q1:2»): esos campos son texto, nunca `=expr` (`CommandSpec.literales`).
SPECS_ELECTRICO = [
    CommandSpec("add_device", "Dispositivo eléctrico", "electrico", AddDeviceParams,
                _exec_carril, kind="electrico", literales=("designacion",)),
    CommandSpec("add_wire", "Conductor", "electrico", AddWireParams, _exec_carril,
                kind="electrico", literales=("puntos", "cable")),
    CommandSpec("add_cable", "Cable multipolar", "electrico", AddCableParams, _exec_carril,
                kind="electrico", literales=("designacion", "desde", "hasta")),
    # V8.3 D3: el programa del PLC, compilado por el evaluador (`electrico_eval`)
    CommandSpec("add_program", "Programa del PLC", "electrico", AddProgramParams, _exec_carril,
                kind="electrico", literales=("plc", "nombre", "fuente")),
]


# ── D3: designaciones materializadas ─────────────────────────────────────────────────────


def _letra(cmd_type: str, params: dict) -> str | None:
    if cmd_type == "add_cable":
        return LETRA_CABLE
    from apolo.library.catalog import CATALOG

    comp = CATALOG.get(params.get("ref")) if isinstance(params.get("ref"), str) else None
    if comp is None or comp.electrico is None:
        return None  # el evaluador dirá qué falla, con sus sugerencias
    return comp.electrico.funcion


def materializar(commands: list[dict], cmd_type: str, params, excluir: str | None = None):
    """Los `params` con la designación materializada (una copia), o los mismos si no hace falta.

    Sólo para `add_device`/`add_cable` con `designacion` vacía: la siguiente libre de su letra
    (la MENOR que nadie usa: -Q1, -Q2…) entre las designaciones SIN aspecto de función de los
    dispositivos y cables del log (`excluir` = el comando que se edita, que no se cuenta)."""
    if cmd_type not in DESIGNAN or not isinstance(params, dict):
        return params
    if str(params.get("designacion") or "").strip():
        return params
    letra = _letra(cmd_type, params)
    if letra is None:
        return params
    patron = re.compile(rf"^-{re.escape(letra)}(\d+)$")
    usados = set()
    for c in commands:
        if c.get("type") in DESIGNAN and c.get("id") != excluir:
            m = patron.match(str((c.get("params") or {}).get("designacion") or "").strip())
            if m:
                usados.add(int(m.group(1)))
    n = next(k for k in range(1, len(usados) + 2) if k not in usados)
    return {**params, "designacion": f"-{letra}{n}"}


# ── D9: el carril de un proyecto insertado ───────────────────────────────────────────────


def aspecto(nombre: str, respaldo: str) -> str:
    """El aspecto de función de una instancia: su `name` sin lo que IEC 81346 no admite en un
    aspecto («Faja 1» → «Faja1», tildes fuera). Vacío → `respaldo` (el command_id)."""
    plano = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^A-Za-z0-9_.]", "", plano).strip(".")
    return limpio or respaldo


def _con_funcion(texto, funcion: str):
    """«-K1:A1» → «=F-K1:A1»; «=Sub-K1» → «=F.Sub-K1». Lo que no se lee queda igual (el
    evaluador lo reporta con la forma correcta)."""
    from apolo.library.electrico.referencias import ReferenciaError, formatear, parse_referencia

    if not isinstance(texto, str) or not texto.strip():
        return texto
    try:
        ref = parse_referencia(texto)
    except ReferenciaError:
        return texto
    nueva = f"{funcion}.{ref.funcion}" if ref.funcion else funcion
    return formatear(type(ref)(ref.dispositivo, ref.borne, nueva, ref.ubicacion))


def prefijar(cmd_type: str, params, funcion: str, prefijo: str):
    """Los params de un comando del carril de un proyecto INSERTADO, con el aspecto de función
    de la instancia en designaciones y referencias y la pieza con el prefijo de ids."""
    if not isinstance(params, dict):
        return params
    out = dict(params)
    if cmd_type in DESIGNAN and out.get("designacion"):
        out["designacion"] = _con_funcion(out["designacion"], funcion)
    if cmd_type == "add_device" and out.get("pieza"):
        out["pieza"] = f"{prefijo}_{out['pieza']}"
    if cmd_type == "add_program" and out.get("plc"):  # el ST nombra bornes, no designaciones
        out["plc"] = _con_funcion(out["plc"], funcion)
    if cmd_type == "add_cable":
        for k in ("desde", "hasta"):
            if isinstance(out.get(k), str) and out[k].strip()[:1] in ("-", "="):
                out[k] = _con_funcion(out[k], funcion)
    if cmd_type == "add_wire":
        if isinstance(out.get("puntos"), list):
            out["puntos"] = [_con_funcion(p, funcion) for p in out["puntos"]]
        if out.get("cable"):
            out["cable"] = _con_funcion(out["cable"], funcion)
    return out
