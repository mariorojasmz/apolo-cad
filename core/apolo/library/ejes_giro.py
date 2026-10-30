"""El EJE de una junta de giro, trabado (plan hallazgos-del-revisor-en-la-puerta, D8). Puro: las
reglas de nombre y la geometría de línea que comparten el insumo (`services/calidad_ejes_giro.py`)
y el control (`calidad/agarre.py`, ítem `agarre.retencion` → `union.retencion`).

Un perno o pasador cuyo eje es el de una junta `giratoria`/`continua` (paralelo y a ≤ 1 mm de su
recta) gira con la pieza en cada maniobra: una tuerca simple DIN 934 se afloja sola (la escalera de
tijera y la silla plegable de los pilotos). Cumple sólo si lleva

- tuerca AUTOBLOCANTE (DIN 985 / ISO 7040 / ISO 10511, o todo-metal DIN 980 / ISO 7042), por su
  ficha de catálogo o por el ROL de su nombre;
- CONTRATUERCA: dos tuercas en el eje, a tope (≤ `TOPE_CONTRATUERCA_MM`), medidas en la geometría;
- pasador de aletas (DIN 94 / ISO 1234) o anillo de retención (DIN 471 / DIN 6799), por el rol de
  su nombre (el catálogo no los tiene), tocando el perno;

y es un perno o pasador: un TIRAFONDO o tornillo de madera (DIN 571, ficha `tornilleria_madera`)
no es eje de giro (gira contra la madera, la agranda y se sale), ni un REMACHE CIEGO (DIN 7337,
ISO 15973–15984, «pop»; ficha con `herramienta: remachadora`): al colocarlo prensa las chapas y la
articulación queda dura o, dejado flojo, se ovaliza con los ciclos (la mesa plegable de 1,8 m,
re-revisión 2; D7 de plegables-en-la-puerta). Su salida de mercado es el remache de HOMBRO o el
perno de hombro ISO 7379 con tuerca autoblocante.

Los matchers de nombre van ANCLADOS al rol (`materials.piece_role`): «Arandela de la tuerca
autoblocante» no es una tuerca autoblocante ni «Placa del pasador de aletas» un pasador.
"""

from __future__ import annotations

import math
import re

COAXIAL_MM = 1.0              # el perno a ≤ 1 mm de la recta de la junta (D8)
COS_PARALELO = math.cos(math.radians(1.0))
TOPE_CONTRATUERCA_MM = 1.0    # dos tuercas a tope = contratuerca

#: Tuerca autoblocante: en la ficha (`tipo`/`norma`) o en el rol de una tuerca a medida.
ES_AUTOBLOCANTE = re.compile(
    r"\b(autoblocantes?|autofrenantes?|nyloc|nylstop)\b"
    r"|\bDIN\s*-?\s*(985|982|980)\b|\bISO\s*-?\s*(7040|7042|10511|10512|10513)\b", re.I)

#: Retén de un pasador o perno: el rol EMPIEZA por él, o lleva su norma.
_RETEN_ROL = re.compile(
    r"^\s*(pasador(es)?\s+(de\s+aletas|hendid[oa]s?|partid[oa]s?|abiert[oa]s?|en\s+r|r)\b"
    r"|chavetas?\s+(partidas?|de\s+aletas|hendidas?)\b|clips?\s+r\b|cotter\b"
    r"|anillos?\s+(de\s+retenci[oó]n|el[aá]sticos?|seeger|de\s+seguridad)\b|seeger\b|circlips?\b"
    r"|arandelas?\s+de\s+(retenci[oó]n|seguridad)\s+(din\s*6799|en\s+e)\b)", re.I)
_RETEN_NORMA = re.compile(r"\b(DIN\s*-?\s*(94|471|6799|11024)|ISO\s*-?\s*1234)\b", re.I)
#: … y la norma sólo cuenta en un rol de herraje («Eje … (con anillos DIN 471)» es un eje).
_HERRAJE_ROL = re.compile(r"^\s*(pasador|chaveta|anillo|arandela|clip|seguro|seeger|circlip|"
                          r"ret[eé]n)", re.I)

#: Tirafondo o tornillo de madera a medida (la ficha `tornilleria_madera` lo dice sola).
ES_TIRAFONDO = re.compile(
    r"^\s*(tirafondos?|tornillos?\s+(para|de)\s+madera|tornillos?\s+autorroscantes?|"
    r"lag\s*screws?|wood\s*screws?)\b|\bDIN\s*-?\s*(571|96|97|7997|7998)\b", re.I)

#: Pasador o bulón a medida (sin cabeza que lo haga perno): candidato a eje.
ES_PASADOR = re.compile(r"^\s*(pasador(es)?|bul[oó]n(es)?)\b", re.I)

#: Remache CIEGO a medida: el rol lo dice («Remache ciego…», «Remache pop…», «Blind rivet…») o
#: un rol de remache lleva su norma (DIN 7337, ISO 15973–15984). El remache de HOMBRO, el macizo
#: (DIN 660) y la remache-tuerca no lo son.
_REMACHE_ROL = re.compile(r"^\s*(remaches?|rivets?|blind\s+rivets?|pop\s+rivets?)\b", re.I)
_REMACHE_CIEGO = re.compile(
    r"^\s*(remaches?\s+(ciegos?|pop|de\s+tracci[oó]n|tipo\s+pop)|blind\s+rivets?|pop\s+rivets?)\b"
    r"|\bDIN\s*-?\s*7337\b|\bISO\s*-?\s*159(7[3-9]|8[0-4])\b", re.I)
_NO_CIEGO = re.compile(
    r"^\s*remaches?(\s+(de\s+hombro|macizos?|s[oó]lidos?)|\s*-?\s*tuercas?)\b", re.I)

#: Lo que se pide en vez de un remache ciego como eje (mensaje de `agarre.retencion`).
SALIDA_REMACHE = ("es un remache ciego (DIN 7337 / ISO 15977): al colocarse prensa las chapas y la "
                  "articulación queda dura o, floja, se ovaliza con los ciclos; va un remache de "
                  "hombro (pivote) o un perno de hombro ISO 7379 con tuerca autoblocante")


def rol(nombre: str | None) -> str:
    from .materials import piece_role

    return piece_role(nombre)


def tipo_reten(nombre: str | None) -> str | None:
    """'pasador de aletas' | 'anillo de retención' | None, por el rol del nombre."""
    r = rol(nombre)
    if not (_RETEN_ROL.search(r) or (_RETEN_NORMA.search(r) and _HERRAJE_ROL.search(r))):
        return None
    return ("anillo de retención" if re.search(r"anillo|seeger|circlip|471|6799|arandela", r, re.I)
            else "pasador de aletas")


def es_tirafondo(nombre: str | None) -> bool:
    return bool(ES_TIRAFONDO.search(rol(nombre)))


def es_remache_ciego(nombre: str | None, specs: dict | None = None) -> bool:
    """¿Remache ciego? Por la ficha (`specs.herramienta: remachadora` o `tipo` «remache ciego»)
    o, a medida, por el ROL de su nombre."""
    if specs is not None:
        return (specs.get("herramienta") == "remachadora"
                or "remache ciego" in str(specs.get("tipo") or "").lower())
    r = rol(nombre)
    return bool(_REMACHE_ROL.search(r) and _REMACHE_CIEGO.search(r) and not _NO_CIEGO.search(r))


def es_pasador(nombre: str | None) -> bool:
    r = rol(nombre)
    return bool(ES_PASADOR.search(r)) and tipo_reten(nombre) is None


def vec(v) -> tuple[float, float, float]:
    """Un punto o dirección de junta: lista [x, y, z] o dict {"x", "y", "z"}."""
    if isinstance(v, dict):
        return (float(v.get("x", 0.0)), float(v.get("y", 0.0)), float(v.get("z", 0.0)))
    return (float(v[0]), float(v[1]), float(v[2]))


def unit(a) -> tuple[float, float, float] | None:
    n = math.sqrt(sum(x * x for x in a))
    return None if n < 1e-12 else (a[0] / n, a[1] / n, a[2] / n)


def distancia_a_recta(p, origen, eje) -> float:
    """Distancia del punto `p` a la recta (origen, eje unitario)."""
    w = (p[0] - origen[0], p[1] - origen[1], p[2] - origen[2])
    t = w[0] * eje[0] + w[1] * eje[1] + w[2] * eje[2]
    q = (w[0] - t * eje[0], w[1] - t * eje[1], w[2] - t * eje[2])
    return math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2)


def coaxial(punto, direccion, origen, eje, tol: float = COAXIAL_MM) -> bool:
    """¿La recta (punto, dirección) es la de la junta (paralela y a ≤ `tol`)?"""
    d = unit(direccion)
    if d is None:
        return False
    if abs(d[0] * eje[0] + d[1] * eje[1] + d[2] * eje[2]) < COS_PARALELO:
        return False
    return distancia_a_recta(punto, origen, eje) <= tol


def traba(tuercas: list[dict], retenes: list[dict]) -> tuple[str, str] | None:
    """(clase, texto) de lo que traba el eje, o None. `tuercas`: [{"t0", "t1", "autoblocante",
    "nombre"?}] sobre el eje; `retenes`: [{"tipo", "nombre"}]."""
    for t in tuercas:
        if t.get("autoblocante"):
            return "autoblocante", f"tuerca autoblocante ({t.get('nombre') or 'DIN 985'})"
    orden = sorted(tuercas, key=lambda t: t["t0"])
    for a, b in zip(orden, orden[1:]):
        if b["t0"] - a["t1"] <= TOPE_CONTRATUERCA_MM:
            return "contratuerca", f"contratuerca (dos tuercas a tope: {b['t0'] - a['t1']:.1f} mm)"
    for r in retenes:
        return "reten", f"{r['tipo']} ({r.get('nombre')})"
    return None


PIDE = ("tuerca autoblocante (DIN 985 / ISO 7040: join_bolted con tuerca=\"din985\"), "
        "contratuerca, pasador de aletas (DIN 94) o anillo de retención (DIN 471)")
