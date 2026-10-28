"""`seguridad.resguardo_abre` (plan lo-que-se-mueve, D3): cada resguardo con interruptor abre por
su junta. Puro: juzga el insumo `resguardos` que resuelve `services/resguardos.py`.

Un resguardo con interruptor (un `add_device` de `modelo.tipo` resguardo) se abre: es lo que su
interruptor vigila. Si su hoja no cuelga de una junta que se mueva, nadie puede verificar que abre
sin chocar (las poses de la puerta de entrega salen de esa junta) ni que la lengüeta sale de la
ranura, y en el visor «Puerta abierta» no abre nada. Es FALLA y no agrega piezas: una junta no es
una pieza. Un resguardo FIJO (se quita con herramienta, sin interruptor) no entra.
"""

from __future__ import annotations

from .entrada import Entrada, hay
from .item import FALLA, NO_APLICA, OK, SIN_EVALUAR

#: Por qué un resguardo no tiene junta que lo abra (el `motivo` de `services/resguardos.py`).
MOTIVOS = {
    "sin_pieza": "no tiene pieza 3D ligada (add_device pieza): no se sabe qué hoja cierra",
    "sin_lengueta": ("su interruptor no tiene su lengüeta modelada (insert_component del interruptor "
                     "y de su lengüeta, de catálogo, con la lengüeta en la hoja): sin ella no se sabe "
                     "qué hoja cierra"),
    "sin_junta": "su hoja no cuelga de ninguna junta",
    "fija": "su hoja sólo cuelga de juntas fijas",
    "misma_junta": "el interruptor y su lengüeta se mueven con la misma junta: ninguna abre el resguardo",
}
COMO = ("declara una junta de revolución (add_joint type=giratoria) en el eje de las bisagras —o "
        "prismática si es corredera— con la hoja como hija, lower/upper de cerrado a abierto, y la "
        "lengüeta colgada de la hoja (add_joint fija con padre la hoja, o arrastrar=true en la junta)")


def _r(estado: str, detalle: str, evidencia: dict, piezas=()) -> dict:
    return {"estado": estado, "detalle": detalle, "evidencia": evidencia,
            "piezas": [p for p in dict.fromkeys(piezas) if p][:40]}


def resguardo_abre(ins: dict) -> dict:
    """`ins["resguardos"]` = [{designacion, ref, interruptor, lengueta, junta, cerrado?, abierto?,
    motivo?}] (`services/resguardos.resguardos`)."""
    filas = ins.get("resguardos")
    if filas is None:
        return _r(SIN_EVALUAR, "no se resolvieron los resguardos del modelo", {})
    if not filas:  # sólo interruptores de posición (FC-2NC-RODILLO) o ninguno: no hay hoja
        return _r(NO_APLICA, "sin resguardos con interruptor de actuador separado", {})
    ev = {"resguardos": [dict(f) for f in filas[:40]]}
    malos = [f for f in filas if not f.get("junta")]
    if malos:
        partes = [f"{f['designacion']} ({f.get('interruptor') or 'sin pieza'}): "
                  f"{MOTIVOS.get(f.get('motivo'), f.get('motivo'))}" + (
                      f"; además su interruptor se mueve con la junta {f['se_mueve_con']}: si no es "
                      "el de un resguardo (un final de carrera, un detector de cadena floja), no va "
                      "con la ref de un interruptor de resguardo" if f.get("se_mueve_con") else "")
                  for f in malos[:4]]
        ev["sin_junta"] = [f["designacion"] for f in malos]
        return _r(FALLA, f"{len(malos)} resguardo(s) con interruptor que no abren por una junta: "
                         f"{'; '.join(partes)}. Nadie puede verificar que abren sin chocar ni que el "
                         f"interruptor ve la apertura; {COMO}", ev,
                  [p for f in malos for p in (f.get("interruptor"), f.get("lengueta"))])
    juntas = ", ".join(f"{f['designacion']} por {f['junta']} ({f['cerrado']:g} → {f['abierto']:g})"
                       for f in filas[:6])
    return _r(OK, f"{len(filas)} resguardo(s), cada uno abre por su junta: {juntas}", ev)


ENTRADA = Entrada(
    "seguridad.resguardo_abre",
    "Cada resguardo con interruptor abre por una junta",
    "un resguardo enclavado sin junta: nadie verificó que abre sin chocar ni que su interruptor ve "
    "la apertura, y en el visor el mando «Puerta abierta» no abre nada",
    "criterio de diseño (D3 de lo-que-se-mueve)", "seguridad",
    hay("resguardos_con_interruptor", "sin resguardos con interruptor"),
    resguardo_abre, "resguardos_con_interruptor")
