"""`higiene.limpiable` (plan hallazgos-del-revisor-en-la-puerta, D9): en equipo HIGIÉNICO no quedan
rendijas ni tubos abiertos. Puro: juzga lo que mide `services/calidad_higiene.py`.

El defecto: la mesa inox (dos rondas de revisor) soldaba la repisa al larguero con 240 mm de cordón
en 1 100 mm de contacto, y la cubierta quedaba 3 mm sobre el tope ABIERTO de la pata: la rendija
junta suciedad con el lavado a presión y el agua entra al tubo, que está cerrado abajo.

Aplica SÓLO con el requisito `higienico: true` (`library/requisitos.py`, la ficha del encargo lo
declara): una mesa de taller no paga la regla. Entonces:

- **Cada soldadura con contacto LINEAL medido** (`forma` «linea» o «perimetro» de
  `kernel/contacto.py`; lo que no se toca en una línea lo juzga `union.contacto_real`) es CONTINUA:
  sin largo declarado (ISO 2553: un cordón sin largo corre toda la junta) o con un largo
  declarado ≥ la línea de contacto medida (`TOL_LARGO_MM` de redondeo). El largo es lo que el plano
  rotula y el soldador deposita: menos que la línea deja una rendija. Se acepta intermitente sólo
  si la unión DECLARA su sellado sanitario en la nota del `fasten` («sellado sanitario con silicona
  FDA», `sellado_sanitario`).
- **Todo tubo abierto de la estructura se cierra soldado**: cada extremo hueco de una pieza que se
  fabrica tiene que quedar a < `HOLGURA_LIMPIABLE_MM` de una pieza SOLDADA a él en todo el borde de
  su hueco (una tapa, la cara a la que llega a tope, el otro tubo de un inglete). Una pieza que no
  está soldada no cierra nada: el agua entra por la junta.

Por debajo de 3 mm una holgura es rendija, no se limpia (criterio de diseño del plan, D9: EN 1672-2
y EN ISO 14159 piden uniones continuas, sin rendijas ni cavidades). Lo que no se pudo medir sale
SIN_EVALUAR y se JUSTIFICA por escrito (`justificadas.py`, regla `REGLA_SIN_MEDIR`), nunca OK.
"""

from __future__ import annotations

import re

from .entrada import Entrada, hecho
from .item import FALLA, OK, SIN_EVALUAR, recortar
from .justificadas import citar, del_aviso

#: Por debajo, una holgura es una rendija que no se limpia (criterio de diseño, D9).
HOLGURA_LIMPIABLE_MM = 3.0
#: El redondeo entre el largo declarado y el medido (`cordon_mm` sale a 0,1 mm).
TOL_LARGO_MM = 1.0
NORMA = ("EN 1672-2:2020 y EN ISO 14159:2004 (uniones continuas, sin rendijas ni cavidades "
         "abiertas); ISO 2553 (un cordón sin largo es continuo); la holgura limpiable de 3 mm es "
         "criterio de diseño")
#: La regla que se justifica por escrito (`justificadas`): el texto EXACTO de la evidencia.
REGLA_SIN_MEDIR = "higiene sin medir"
FORMAS_LINEALES = ("linea", "perimetro")

_SELLADO = re.compile(r"\bsell(?:ad[oa]s?|os?)\b[^.;]{0,40}?\bsanitari[oa]s?\b", re.I)


def sellado_sanitario(nota: str | None) -> bool:
    """¿La nota de la unión declara su sellado sanitario («sellado sanitario con silicona FDA»,
    «sello sanitario en el borde del ala»)?"""
    return bool(_SELLADO.search(nota or ""))


def juzgar_soldadura(f: dict) -> tuple[str, str]:
    """(estado, por qué) de una soldadura {union, cordon_mm, largo_declarado_mm, sellado}."""
    cordon = float(f["cordon_mm"])
    decl = f.get("largo_declarado_mm")
    if decl is None:
        return OK, f"continua: sin largo declarado corre los {cordon:g} mm de la junta (ISO 2553)"
    decl = float(decl)
    if decl >= cordon - TOL_LARGO_MM:
        return OK, f"continua: {decl:g} mm declarados ≥ {cordon:g} mm de contacto"
    if f.get("sellado"):
        return OK, (f"{decl:g} de {cordon:g} mm soldados, el resto con sellado sanitario declarado "
                    f"(«{(f.get('nota') or '')[:60]}»)")
    return FALLA, (f"{decl:g} mm de cordón en {cordon:g} mm de contacto: quedan {cordon - decl:.0f} "
                   "mm de rendija sin soldar")


def _texto_soldadura(f: dict, motivo: str) -> str:
    return (f"{f['union']}: {f.get('nombre_a') or f['a']} ({f['a']}) ↔ "
            f"{f.get('nombre_b') or f['b']} ({f['b']}): {motivo}")


def _texto_tubo(t: dict) -> str:
    n = len(t["abiertos"])
    return f"{t.get('nombre') or t['id']} ({t['id']}): {n} extremo(s) abierto(s)"


COMO = ("en equipo higiénico, declara cada soldadura CONTINUA (sin length_mm, o con el largo de su "
        "línea de contacto) o su sellado sanitario en la nota del fasten («sellado sanitario con "
        "silicona FDA»); cierra cada tubo con una tapa soldada o llévalo a tope contra la pieza a "
        "la que se suelda (que el hueco quede a < 3 mm de ella en todo su borde)")


def limpiable(ins: dict) -> dict:
    """El control del ítem: `ins["higiene"]` = {soldaduras: [{union, a, b, nombre_a, nombre_b,
    cordon_mm, largo_declarado_mm, sellado, nota}], otras_formas: n, tubos: [{id, nombre,
    extremos, abiertos: [{centro, normal, ancho_mm, holgura_mm}]}], sin_medir: [{que, piezas,
    motivo}]} (None: no se midió); `ins["justificadas"]` = el metadato."""
    datos = ins.get("higiene")
    if datos is None or datos.get("error"):
        return {"estado": SIN_EVALUAR, "detalle": "no se midieron las rendijas ni los tubos"
                + (f" ({datos['error']})" if datos else "")}
    malas, casos = [], []
    for f in datos.get("soldaduras") or []:
        estado, motivo = juzgar_soldadura(f)
        casos.append({k: f.get(k) for k in ("union", "a", "b", "cordon_mm", "largo_declarado_mm")}
                     | {"estado": estado, "motivo": motivo})
        if estado != OK:
            malas.append((f, motivo))
    tubos = datos.get("tubos") or []
    abiertos = [t for t in tubos if t.get("abiertos")]
    js_usadas, sin_medir = [], []
    for s in datos.get("sin_medir") or []:
        js = del_aviso(REGLA_SIN_MEDIR, s.get("piezas"), ins.get("justificadas"))
        if js:
            js_usadas += js
        else:
            sin_medir.append(s)
    rec = recortar(sorted(casos, key=lambda c: c["estado"] == OK))  # las que fallan, primero
    ev = {"holgura_limpiable_mm": HOLGURA_LIMPIABLE_MM, "con_rendija": len(malas),
          "soldaduras": rec["casos"],
          **({"soldaduras_omitidas": rec["casos_omitidos"]} if "casos_omitidos" in rec else {}),
          "otras_formas": datos.get("otras_formas", 0),
          "tubos": len(tubos), "extremos": sum(int(t.get("extremos", 0)) for t in tubos),
          "tubos_abiertos": [{k: t.get(k) for k in ("id", "nombre", "abiertos")}
                             for t in abiertos[:20]]}
    if sin_medir:
        ev["sin_medir"] = [{**s, "regla": REGLA_SIN_MEDIR} for s in sin_medir[:20]]
    if js_usadas:
        ev["justificadas"] = citar(js_usadas)
    if malas or abiertos:
        partes = [_texto_soldadura(f, m) for f, m in malas[:4]] + \
                 [_texto_tubo(t) for t in abiertos[:4]]
        resto = len(malas) + len(abiertos) - len(partes)
        piezas = [p for f, _ in malas for p in (f["a"], f["b"])] + [t["id"] for t in abiertos]
        return {"estado": FALLA, "evidencia": ev, "piezas": list(dict.fromkeys(piezas))[:40],
                "detalle": f"{len(malas)} soldadura(s) con rendija y {len(abiertos)} tubo(s) "
                           f"abierto(s) en equipo higiénico: {'; '.join(partes)}"
                           f"{f' (+{resto} más en la evidencia)' if resto > 0 else ''}. "
                           f"{COMO[0].upper()}{COMO[1:]}"}
    if sin_medir:
        texto = "; ".join(f"{s.get('que')}: {s.get('motivo')}" for s in sin_medir[:4])
        return {"estado": SIN_EVALUAR, "evidencia": ev,
                "piezas": [p for s in sin_medir for p in s.get("piezas") or []][:40],
                "detalle": f"{len(sin_medir)} elemento(s) sin medir ({texto}): mídelo o "
                           f"justifícalo por escrito (regla «{REGLA_SIN_MEDIR}» y sus piezas)"}
    return {"estado": OK, "evidencia": ev,
            "detalle": f"{len(casos)} soldadura(s) continuas o selladas y {len(tubos)} tubo(s) con "
                       "cada extremo cerrado por una pieza soldada"}


ENTRADA = Entrada(
    "higiene.limpiable",
    "En equipo higiénico, cada unión soldada es continua y cada tubo está cerrado",
    "una soldadura intermitente deja una rendija y un tubo abierto una cavidad: con el lavado la "
    "suciedad y el agua se juntan donde nada se limpia (contaminación del producto)",
    NORMA, "función",
    hecho("higienico", "el encargo no pide equipo higiénico (requisito higienico)"),
    limpiable)
