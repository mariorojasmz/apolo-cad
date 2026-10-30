"""`union.contacto_no_cuelga` (plan lo-fijo-que-gira-y-lo-que-cuelga, D2; ajustes D2a–D2c de su
F0): un `contacto` no sostiene lo que cuelga. Puro: juzga lo que mide `services/calidad_cuelga.py`.

El defecto: en la lavadora de bandejas dos cuchillas de aire de 22 kg (56 kg con su ducto) colgaban
sólo de un `contacto` (una abrazadera rápida), con su centro de masa bajo la abrazadera. La sujeción
declarada las daba por sujetas: el grafo cuenta un contacto como camino a tierra, igual que un perno
o una soldadura. Un contacto transmite COMPRESIÓN (lo que apoya), no TRACCIÓN (lo que cuelga).

Cada unión `contacto` con carga colgada (`loads.piezas_colgadas`: lo que pierde tierra al quitarla),
salvo las que no se juzgan —tornillería (`lints._is_bolt`), lo colgado de menos de `KG_MIN`, el par
que además lleva otra unión o una junta, o la cadena que asienta su comando—, por el centro de masa
(CM) de TODO lo colgado contra la caja de la zona de contacto medida (`kernel/contacto`):

1. **Unión de tubería declarada** (D2c): la nota del `fasten` dice que es ROSCADA («roscada», «se
   desenrosca», «NPT», «BSP») o de ABRAZADERA SANITARIA con férula («tri-clamp», DIN 32676,
   ISO 2852, con su presión nominal): una válvula, un niple, un racor o una boquilla aguantan
   tracción → OK. Una abrazadera de unión rápida de ducto (anillo con palanca, sin norma) NO: es
   el defecto de las cuchillas.
2. **Abraza** (D2b): la zona envuelve el CM a su altura y sobre su vertical (una rueda en su eje,
   un resguardo en su boca) → OK.
3. **Cuelga**: el CM queda más de `TOL_MM` bajo la cota más baja de la zona → FALLA.
4. **Apoya**: el CM sobre la cota más alta de la zona (una bandeja en sus zapatas, un tanque en sus
   largueros) → OK.
5. **Costado**: lo demás (colgado al costado de un poste, inclinado) → AVISO justificable por
   escrito (`justificadas.py`, regla `REGLA_AVISO` y la pieza), nunca FALLA: la tolerancia sólo
   afloja «cuelga».

Sin zona medida (las piezas no se tocan: lo juzga `union.contacto_real`) → SIN_EVALUAR.
Corrige: un apoyo debajo, una ménsula o un perno (`fasten` perno o soldadura en lugar del contacto).
"""

from __future__ import annotations

import math
import re

from .entrada import Entrada, hay
from .item import FALLA, OK, SIN_EVALUAR, recortar
from .justificadas import citar, del_aviso

NORMA = ("criterio de diseño (D2 de lo-fijo-que-gira-y-lo-que-cuelga: un apoyo transmite "
         "compresión, no tracción)")
#: D2b: el CM puede quedar hasta esto bajo la cota más baja de la zona sin «colgar» (mm).
TOL_MM = 25.0
#: D2a: lo colgado más liviano no se juzga (silenciadores, aparatos en riel DIN, insertos).
KG_MIN = 0.5
#: D2b: la zona ABRAZA el CM si éste cae sobre su vertical a menos de esto (mm).
ABRAZA_MM = 1.0
#: La regla que se justifica por escrito (`justificadas`): el texto EXACTO de la evidencia.
REGLA_AVISO = "carga al costado de un contacto"
COMO = ("sostén lo colgado desde abajo (un apoyo o una ménsula) o une con perno o soldadura en "
        "lugar del contacto; si es una unión de tubería ROSCADA (válvula, niple, racor) o con "
        "abrazadera sanitaria tri-clamp (DIN 32676), decláralo en la nota del fasten («roscada NPT», "
        "«tri-clamp DIN 32676»); lo que cuelga al costado y se sostiene por roce se justifica por "
        f"escrito (regla «{REGLA_AVISO}» y la pieza)")
_TRACCION = re.compile(r"\b(?:des)?(?:en)?rosc(?:a|ad[oa]s?)\b|\bNPTF?\b|\bBSP[PT]?\b"
                       r"|\btri-?\s?clamp\b|\bDIN\s?32676\b|\bISO\s?2852\b", re.IGNORECASE)


def traccion_declarada(nota: str | None) -> bool:
    """¿La nota del `fasten` declara una unión de tubería que transmite tracción (roscada o con
    abrazadera sanitaria de férula)? (D2c)"""
    return bool(_TRACCION.search(nota or ""))


def juzgar(c: dict) -> tuple[str, str]:
    """(estado, motivo) de un caso {kg, cm, zona, traccion}. Estado OK | FALLA | SIN_EVALUAR |
    «aviso»."""
    if c.get("traccion"):
        return OK, "unión de tubería roscada o tri-clamp declarada: transmite tracción"
    z, cm = c.get("zona"), c["cm"]
    if z is None:
        return SIN_EVALUAR, "no se halló la zona de contacto (no se tocan: union.contacto_real)"
    dh = math.hypot(max(z[0] - cm[0], 0.0, cm[0] - z[3]), max(z[1] - cm[1], 0.0, cm[1] - z[4]))
    if z[2] <= cm[2] <= z[5] and dh <= ABRAZA_MM:
        return OK, "la zona de contacto abraza el centro de masa"
    bajo = z[2] - cm[2]
    if bajo > TOL_MM:
        return FALLA, (f"{c['kg']:g} kg cuelgan con su centro de masa {bajo:.0f} mm bajo el "
                       f"contacto y {dh:.0f} mm al costado")
    if cm[2] >= z[5]:
        return OK, "apoya: el centro de masa está sobre el contacto"
    altura = (f"{bajo:.0f} mm bajo el contacto (dentro de la tolerancia de {TOL_MM:g} mm)"
              if bajo > 0 else "a la altura del contacto")
    return "aviso", (f"{c['kg']:g} kg al costado del contacto: su centro de masa está {altura} y "
                     f"{dh:.0f} mm al costado, sin apoyo debajo")


def _texto(c: dict, motivo: str) -> str:
    otras = f" (+{c['piezas'] - 1} pieza(s) que cuelgan con ella)" if c.get("piezas", 1) > 1 else ""
    return (f"{c['union']}: {c.get('nombre_colgada') or c['colgada']} ({c['colgada']}){otras} de "
            f"{c.get('nombre_apoyo') or c['apoyo']} ({c['apoyo']}): {motivo}")


def no_cuelga(ins: dict) -> dict:
    """El control del ítem: `ins["cuelga"]` = {contactos: n, casos: [{union, colgada, apoyo,
    nombre_colgada, nombre_apoyo, piezas, kg, cm: [x, y, z], zona: [x0, y0, z0, x1, y1, z1] |
    None, traccion}], no_juzgadas: {motivo: n}} (None: no se midió); `ins["justificadas"]` = el
    metadato."""
    datos = ins.get("cuelga")
    if datos is None or datos.get("error"):
        return {"estado": SIN_EVALUAR, "detalle": "no se midieron los contactos con carga colgada"
                + (f" ({datos['error']})" if datos else "")}
    filas, malas, avisos, sin_medir, js_usadas = [], [], [], [], []
    for c in datos.get("casos") or []:
        estado, motivo = juzgar(c)
        if estado == "aviso":
            js = del_aviso(REGLA_AVISO, [c["colgada"]], ins.get("justificadas"))
            if js:
                js_usadas += js
                estado = OK
            else:
                avisos.append((c, motivo))
        elif estado == FALLA:
            malas.append((c, motivo))
        elif estado == SIN_EVALUAR:
            sin_medir.append((c, motivo))
        filas.append({k: c.get(k) for k in ("union", "colgada", "apoyo", "kg")}
                     | {"estado": estado, "motivo": motivo})
    rec = recortar(sorted(filas, key=lambda f: f["estado"] == OK))  # lo malo, primero
    ev = {"contactos": datos.get("contactos", 0), "con_carga": len(filas),
          "no_juzgadas": datos.get("no_juzgadas") or {}, "casos": rec["casos"],
          **({"casos_omitidos": rec["casos_omitidos"]} if "casos_omitidos" in rec else {})}
    if avisos:
        ev["avisos"] = [{"regla": REGLA_AVISO, "piezas": [c["colgada"]]} for c, _m in avisos[:20]]
    if js_usadas:
        ev["justificadas"] = citar(js_usadas)
    como = f"{COMO[0].upper()}{COMO[1:]}"
    if malas:
        partes = [_texto(c, m) for c, m in malas[:4]]
        resto = f" (+{len(malas) - 4} más en la evidencia)" if len(malas) > 4 else ""
        return {"estado": FALLA, "evidencia": ev,
                "piezas": list(dict.fromkeys(p for c, _m in malas for p in (c["colgada"],
                                                                            c["apoyo"])))[:40],
                "detalle": f"{len(malas)} contacto(s) sostienen lo que cuelga: "
                           f"{'; '.join(partes)}{resto}. {como}"}
    if avisos or sin_medir:
        partes = [_texto(c, m) for c, m in (avisos + sin_medir)[:4]]
        return {"estado": SIN_EVALUAR, "evidencia": ev,
                "piezas": list(dict.fromkeys(c["colgada"] for c, _m in avisos + sin_medir))[:40],
                "detalle": f"{len(avisos)} aviso(s) y {len(sin_medir)} sin medir: "
                           f"{'; '.join(partes)}. {como}"}
    return {"estado": OK, "evidencia": ev,
            "detalle": (f"{len(filas)} contacto(s) con carga, todos apoyan, abrazan o son uniones de tubería" if filas else
                        f"{datos.get('contactos', 0)} contacto(s) y ninguno sostiene una carga "
                        "colgada que juzgar")}


ENTRADA = Entrada(
    "union.contacto_no_cuelga",
    "Ningún contacto sostiene lo que cuelga: lo colgado va con perno, soldadura o un apoyo debajo",
    "una pieza pesada colgada de un simple contacto (una abrazadera rápida, un apoyo declarado): "
    "la sujeción la da por sujeta y en el taller se suelta o se cae",
    NORMA, "estructura",
    hay("uniones_contacto", "sin uniones de contacto declaradas"),
    no_cuelga, "uniones_contacto")
