"""`union.contacto_real` (plan uniones-que-tocan, D1/D1b/D2): lo que se declara unido se toca de
verdad. Puro: juzga las filas que mide `services/calidad_contacto.py` (una por `fasten`, con la
distancia OCCT y la línea de contacto de `kernel/contacto.py`).

Antes, la conectividad, la sujeción, el dimensionado y la gravedad creían lo DECLARADO: una
riostra girada a mano a 5 mm de sus postes, con dos soldaduras declaradas, pasaba como «sujeta» (la
plataforma de mantenimiento aprobó la puerta v17 y siete revisiones a ciegas). Criterio por tipo:

- `soldadura`: las dos piezas se tocan (≤ `TOL_MM`) y la línea de contacto da un cordón de largo
  eficaz l_eff = l − 2·a ≥ max(30 mm, 6·a): EN 1993-1-8:2005 §4.5.2(2) («un cordón de filete con
  un largo eficaz menor que 30 mm o que 6 veces su garganta, el mayor, no se diseña para llevar
  carga»; l_eff = l − 2a es §4.5.2(1)). Sin garganta declarada, 30 mm. Un punto o una arista (la
  esquina de un extremo a escuadra apoyada en la cara) no es un cordón: l = 0.
- `contacto`/`pegado`: se tocan en un área o al menos en una LÍNEA (ni separadas ni un punto: el
  separador sobre el eje hexagonal de los rodillos apoya en un canto del hexágono, y eso es un
  apoyo, no un cordón); lo que gira (rodamiento, eje, rodillo:
  `assembly.autodetect.piezas_que_giran`) sólo tiene que tocar. La
  tornillería (perno, tuerca, arandela) pasa por su agujero con la holgura de ISO 273 (serie
  gruesa M24: Ø28, 2 mm radial): basta que esté a ≤ `TOL_TORNILLERIA_MM`. Una banda apoya en su
  cama por su comba (≤ 2 % del largo de la cama, CEMA: `COMBA_BANDA`; la faja deja 2 mm de cama
  a banda). Lo que une una cadena lo asienta su comando (`de_su_comando`, no se mide).
- `perno`: lo que aprieta está a ≤ el largo de su tornillería (la nota «M8x40», o el perno que
  insertó su `join_bolted`; sin dato, `LARGO_PERNO_SIN_DATO_MM`, el tope que `join_bolted` usaba
  antes de exigir catálogo): más allá, el perno no llega a cruzar el hueco de aire.

La evidencia nombra el par, la distancia y el largo medido. La misma regla corre en la puerta de
entrega (`regla_entrega`, ROJO) para que el modelador la vea antes de la puerta.
"""

from __future__ import annotations

from .entrada import Entrada, hecho
from .item import FALLA, OK, SIN_EVALUAR

#: Tolerancia de modelado (mm): hasta aquí dos piezas se tocan.
TOL_MM = 0.5
#: La tornillería en su agujero de paso (ISO 273 serie gruesa, M24 → Ø28: 2 mm de holgura radial).
TOL_TORNILLERIA_MM = 2.0
#: EN 1993-1-8:2005 §4.5.2(2): el largo eficaz mínimo de un cordón de filete.
LARGO_MIN_ABS_MM = 30.0
FACTOR_GARGANTA = 6.0
NORMA = "EN 1993-1-8:2005 §4.5.2 (largo eficaz mínimo del cordón de filete)"
#: Sin largo de tornillería conocido: el tope de `join_bolted` antes del criterio 3.
LARGO_PERNO_SIN_DATO_MM = 200.0
#: Una banda (lazo flexible) apoya en su cama o en sus rodillos por su COMBA: CEMA admite el 2 %
#: del vano entre apoyos (el mismo tope de la comba de `ruta_faja_modelo.py`).
COMBA_BANDA = 0.02

COMO = ("un miembro inclinado entre dos piezas (riostra, diagonal, pasamanos que llega a un poste, "
        "zanca) se crea con create_brace: corta cada extremo a ras de la cara que recibe (a_tope, "
        "boca_de_pescado o inglete) y declara su soldadura con el cordón medido; si no, corta el "
        "extremo a ras o mueve la pieza hasta que asiente, o declara la unión que de verdad hay")

_FORMA = {"separadas": "no se tocan", "punto": "se tocan en un punto",
          "arista": "se tocan por una arista (el canto de un extremo, no su cara)",
          "contenida": "una está entera dentro de la otra"}


def largo_minimo(garganta_mm: float | None) -> float:
    """El largo eficaz mínimo del cordón (EN 1993-1-8 §4.5.2(2))."""
    return max(LARGO_MIN_ABS_MM, FACTOR_GARGANTA * float(garganta_mm or 0.0))


def largo_eficaz(cordon_mm: float, garganta_mm: float | None) -> float:
    """l_eff = l − 2·a (EN 1993-1-8 §4.5.2(1)), nunca negativo."""
    return max(0.0, float(cordon_mm) - 2.0 * float(garganta_mm or 0.0))


def juzgar(f: dict) -> tuple[bool, str]:
    """(cumple, por qué) de una fila de `services/calidad_contacto.uniones_medidas`."""
    if f.get("error"):
        return False, f"no se pudo medir ({f['error']})"
    if f.get("forma") == "de_su_comando":
        return True, "la asienta su comando de cadena, diente a diente"
    kind, dist, forma = f["kind"], float(f["dist_mm"]), f.get("forma")
    if kind == "perno":
        largo = float(f.get("largo_perno_mm") or LARGO_PERNO_SIN_DATO_MM)
        if dist <= largo:
            return True, f"a {dist:g} mm (la tornillería mide {largo:g})"
        return False, (f"hay {dist:g} mm de aire entre las piezas y la tornillería mide {largo:g} "
                       f"mm ({f.get('origen_largo') or 'sin largo declarado'})")
    if kind == "soldadura":
        if forma in ("separadas", "contenida"):
            return False, f"{_FORMA[forma]} (a {dist:g} mm): no hay dónde soldar"
        a = f.get("garganta_mm")
        cordon = float(f.get("cordon_mm") or 0.0)
        l_eff, minimo = largo_eficaz(cordon, a), largo_minimo(a)
        if l_eff >= minimo:
            return True, f"cordón de {cordon:g} mm (l_eff {l_eff:g} ≥ {minimo:g})"
        if forma in ("punto", "arista"):
            return False, f"{_FORMA[forma]}: no hay cordón (mínimo {minimo:g} mm)"
        return False, (f"la línea de contacto da {cordon:g} mm de cordón (l_eff {l_eff:g} mm < "
                       f"{minimo:g} mm)")
    # contacto / pegado
    if f.get("tornilleria"):
        if dist <= TOL_TORNILLERIA_MM:
            return True, f"tornillería a {dist:g} mm (holgura de su agujero)"
        return False, f"la tornillería está a {dist:g} mm: no asienta en lo que declara"
    comba = COMBA_BANDA * float(f.get("vano_mm") or 0.0)
    if f.get("vano_mm") is not None and dist <= max(TOL_MM, comba):
        return True, f"la banda apoya por su comba (a {dist:g} mm ≤ {comba:.0f} mm)"
    if forma == "separadas":
        return False, f"{_FORMA[forma]} (a {dist:g} mm)"
    if f.get("gira") or forma != "punto":
        return True, f"se tocan ({forma})"
    return False, f"{_FORMA[forma]}: no es un apoyo"


def _texto(f: dict, motivo: str) -> str:
    return (f"{f['union']} ({f['kind']}): {f.get('nombre_a') or f['a']} ({f['a']}) ↔ "
            f"{f.get('nombre_b') or f['b']} ({f['b']}): {motivo}")


def malas(filas: list[dict]) -> list[tuple[dict, str]]:
    """Las uniones que no cumplen, con su motivo."""
    out = []
    for f in filas:
        cumple, motivo = juzgar(f)
        if not cumple:
            out.append((f, motivo))
    return out


def contacto_real(ins: dict) -> dict:
    """El control del ítem: `ins["uniones"]` = las filas medidas (None: no se midió)."""
    filas = ins.get("uniones")
    if filas is None:
        return {"estado": SIN_EVALUAR, "detalle": "no se midieron las uniones declaradas"}
    por_tipo: dict[str, int] = {}
    for f in filas:
        por_tipo[f["kind"]] = por_tipo.get(f["kind"], 0) + 1
    ev = {"uniones": len(filas), "por_tipo": por_tipo, "tolerancia_mm": TOL_MM}
    m = malas(filas)
    if m:
        ev["malas"] = [{"union": f["union"], "kind": f["kind"], "a": f["a"], "b": f["b"],
                        "dist_mm": f.get("dist_mm"), "cordon_mm": f.get("cordon_mm"),
                        "forma": f.get("forma"), "motivo": motivo} for f, motivo in m[:40]]
        if len(m) > 40:
            ev["malas_omitidas"] = len(m) - 40
        casos = "; ".join(_texto(f, motivo) for f, motivo in m[:6])
        resto = f" (+{len(m) - 6} más en la evidencia)" if len(m) > 6 else ""
        return {"estado": FALLA, "evidencia": ev,
                "piezas": [p for f, _ in m for p in (f["a"], f["b"])][:40],
                "detalle": f"{len(m)} de {len(filas)} unión(es) declaradas no se tocan como "
                           f"declaran: {casos}{resto}. La sujeción, el dimensionado y la gravedad "
                           f"creen lo declarado; {COMO}"}
    return {"estado": OK, "evidencia": ev,
            "detalle": f"{len(filas)} unión(es) declaradas, todas se tocan como declaran (cada "
                       f"soldadura con su cordón ≥ {LARGO_MIN_ABS_MM:g} mm o 6·a)"}


REGLA_ENTREGA = "uniones · lo declarado no se toca"


def regla_entrega(filas: list[dict] | None) -> dict | None:
    """El bloqueante del semáforo de la entrega (ROJO) con cada par y su cifra, o None si todo se
    toca (o no hay uniones)."""
    m = malas(filas or [])
    if not m:
        return None
    casos = "; ".join(_texto(f, motivo) for f, motivo in m[:8])
    resto = f" (+{len(m) - 8} más)" if len(m) > 8 else ""
    return {"regla": REGLA_ENTREGA,
            "piezas": list(dict.fromkeys(p for f, _ in m for p in (f["a"], f["b"]))),
            "detalle": f"{len(m)} unión(es) declaradas que no se tocan como declaran: {casos}"
                       f"{resto}. {COMO[0].upper()}{COMO[1:]}."}


ENTRADA = Entrada(
    "union.contacto_real",
    "Lo que se declara unido se toca: cada soldadura con su cordón, cada apoyo con su área",
    "una soldadura, un apoyo o un perno declarados entre piezas que no se tocan (una riostra a 5 "
    "mm de su poste): la sujeción, el dimensionado y la gravedad dan «sujeto» lo que en el taller "
    "no tiene cómo unirse",
    NORMA, "estructura",
    hecho("uniones_declaradas", "sin uniones declaradas (fasten)"),
    contacto_real)
