"""`transmision_flexible.de_su_comando` (plan lo-que-se-mueve, D1): toda cadena de rodillos sale de
su comando. Puro: juzga el insumo `cadenas` que mide `services/calidad_cadenas.py`.

Una pieza con ref `CADENA-*` que no viene de `create_chain` (lazo cerrado entre dos piñones) ni de
`create_hoist_chain` (cadena abierta de izaje) es una cadena HECHA A MANO: tramos rectos por
`insert_component` que no envuelven sus piñones, no siguen a su junta y quedan fuera del chequeo de
tensión (los lazos se cuentan sólo desde su comando). Es FALLA y no agrega piezas: cambia cómo se
modela. Las bandas y correas quedan fuera de v1 (no hay ref de catálogo que distinga un tramo
hecho a mano; se detectan por rol).
"""

from __future__ import annotations

from .entrada import Entrada, hay
from .item import FALLA, OK, SIN_EVALUAR, recortar

#: Los comandos de los que sale una cadena de rodillos.
COMANDOS = ("create_chain", "create_hoist_chain")
USAR = ("create_chain (lazo cerrado entre dos piñones: envuelve sus dientes y entra al chequeo de "
        "tensión) o create_hoist_chain (cadena abierta de izaje: sus anclas siguen a la pieza que "
        "sube)")


def _r(estado: str, detalle: str, evidencia: dict, piezas=()) -> dict:
    return {"estado": estado, "detalle": detalle, "evidencia": evidencia,
            "piezas": list(dict.fromkeys(piezas))[:40]}


def de_su_comando(ins: dict) -> dict:
    """`ins["cadenas"]` = [{id, nombre, ref, comando, tipo, de_su_comando}] (una por pieza)."""
    cadenas = ins.get("cadenas")
    if cadenas is None:
        return _r(SIN_EVALUAR, "no se midieron las cadenas del modelo", {})
    casos = [{k: c.get(k) for k in ("id", "nombre", "ref", "comando", "tipo")}
             for c in cadenas]
    a_mano = [c for c in cadenas if not c.get("de_su_comando")]
    rec = recortar(casos)
    ev = {"cadenas": rec["casos"],
          **({"cadenas_omitidas": rec["casos_omitidos"]} if "casos_omitidos" in rec else {}),
          "usar": USAR}
    if a_mano:
        nombres = ", ".join(f"{c.get('nombre')} ({c.get('tipo') or 'sin comando'} "
                            f"{c.get('comando')})" for c in a_mano[:4])
        ev["a_mano"] = [c["id"] for c in a_mano]
        return _r(FALLA, f"{len(a_mano)} cadena(s) hecha(s) a mano: {nombres}. No envuelven sus "
                         f"piñones ni siguen a su junta; modélalas con {USAR}", ev,
                  [c["id"] for c in a_mano])
    return _r(OK, f"{len(cadenas)} cadena(s), todas de su comando", ev)


ENTRADA = Entrada(
    "transmision_flexible.de_su_comando",
    "Cada cadena de rodillos sale de su comando (create_chain o create_hoist_chain)",
    "una cadena hecha a mano con tramos rectos no envuelve el piñón, no sigue a la pieza que mueve "
    "y queda fuera del chequeo de tensión: se publica una transmisión que nadie verificó",
    "criterio de diseño (D1 de lo-que-se-mueve)", "función",
    hay("cadenas_de_rodillos", "la máquina no tiene cadenas de rodillos"),
    de_su_comando, "cadenas_de_rodillos")
