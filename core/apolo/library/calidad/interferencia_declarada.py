"""`union.interferencia_declarada` (plan puerta-fuera-de-catalogo, D6): una unión declarada no tapa
una interferencia de VOLUMEN. Puro: juzga los solapes que mide
`services/calidad_interferencia_declarada.py` (uno por par con `fasten` entre piezas que no son
tornillería, con el volumen común y, por cada sólido de ese volumen, los anillos coaxiales que lo
limitan).

La puerta de entrega excluye entero el par con `fasten` (es contacto FIRMADO), sin tope de volumen:
la silla plegable aprobó con 9 903 mm³ de travesaño metidos en la pata porque entre los dos había
una unión declarada. Contacto, soldadura y encolado son caras que se tocan, no volumen compartido;
un perno aprieta lo que toca. Criterio:

- un par con `fasten` (de cualquier tipo) cuyo volumen común NO intencional supera
  `EXCESS_TOL_MM3` (la misma tolerancia de asiento de los pares no declarados) FALLA, con el par,
  el volumen y la unión;
- es intencional la ROSCA ENGRANADA: un vástago roscado (perno, espárrago, pie nivelador) coaxial
  en un agujero de la broca de roscar (DIN 336, `engineering/threads.COARSE`, la que taladra
  `drill_hole.thread`) comparte un anillo π/4·(d² − d_broca²)·enganche. Se reconoce por la
  GEOMETRÍA del solape: un sólido limitado por dos cilindros coaxiales de Ø d y Ø d_broca de una
  misma métrica gruesa (± `TOL_DIAMETRO_MM`); su volumen hasta el del anillo (+ `TOL_VOLUMEN`) no
  cuenta y lo que lo supera sí (el pie nivelador M16 en su placa roscada de 12 mm deja 565,5 mm³;
  un espárrago M10 en un buje de 21 mm, 457,7);
- es intencional la pieza ENTERA dentro de un equipo de CATÁLOGO (`alojada`): el variador en su
  tablero; el sólido de catálogo es la envolvente del equipo, no material. Una pieza a medida
  maciza que encierra otra sigue fallando.

La tornillería (perno, tuerca, arandela, anillo de retención; de catálogo o a medida), el equipo de
catálogo de geometría representativa (`checks.FEA_HARDWARE_CATS`), el cable 3D y los pares de
junta no se miden: los asienta su agujero o su ranura, la envolvente del equipo no es su cota, el
cable cruza por su pasacables y la junta la mide la interpenetración en pose (el servicio). Lo que
no se pudo medir sale SIN_EVALUAR, nunca OK.
"""

from __future__ import annotations

import math

from ..checks import EXCESS_TOL_MM3
from ..engineering.threads import COARSE
from .entrada import Entrada, hecho
from .item import FALLA, OK, SIN_EVALUAR

#: Tolerancia (mm) al reconocer el Ø nominal del vástago y el de la broca de roscar.
TOL_DIAMETRO_MM = 0.2
#: Margen sobre el volumen del anillo de rosca (redondeos del modelado, chaflán de entrada).
TOL_VOLUMEN = 0.05
#: Fracción de su volumen dentro de la otra para tomar una pieza por ENTERA dentro (alojada).
CONTENIDA = 0.99
NORMA = ("criterio de diseño (D6 de puerta-fuera-de-catalogo: asiento ≤ "
         f"{EXCESS_TOL_MM3:g} mm³; rosca engranada con la broca de DIN 336)")
COMO = ("una unión declarada firma el contacto, no un volumen compartido: mueve o recorta la pieza "
        "hasta que las dos sólo se toquen (el canto a ras de la cara que lo recibe), o modela el "
        "agujero o el rebaje que la aloja; si es un vástago roscado, su agujero va a la broca de "
        "roscar de su métrica (drill_hole con `thread`)")


def rosca_de(d_ext: float, d_int: float) -> str | None:
    """La métrica gruesa cuyo Ø nominal y broca de roscar (DIN 336) son `d_ext` y `d_int`."""
    for metrica, (_paso, broca) in COARSE.items():
        nominal = float(metrica[1:])
        if abs(d_ext - nominal) <= TOL_DIAMETRO_MM and abs(d_int - broca) <= TOL_DIAMETRO_MM:
            return metrica
    return None


def anillo_mm3(metrica: str, largo_mm: float) -> float:
    """π/4·(d² − d_broca²)·enganche: el volumen de la rosca engranada de `metrica`."""
    d, broca = float(metrica[1:]), COARSE[metrica][1]
    return math.pi / 4.0 * (d * d - broca * broca) * float(largo_mm)


def _intencional(solido: dict) -> tuple[float, dict | None]:
    """(volumen intencional, la rosca que lo explica) de un sólido del solape."""
    v = float(solido.get("volumen_mm3") or 0.0)
    for an in solido.get("anillos") or ():
        metrica = rosca_de(float(an["d_ext"]), float(an["d_int"]))
        if metrica is None:
            continue
        esperado = anillo_mm3(metrica, an["largo_mm"])
        return (min(v, esperado * (1.0 + TOL_VOLUMEN)),
                {"rosca": metrica, "enganche_mm": round(float(an["largo_mm"]), 1),
                 "anillo_mm3": round(esperado, 1)})
    return 0.0, None


def alojada(fila: dict) -> str | None:
    """La pieza ENTERA (≥ `CONTENIDA` de su volumen) dentro de un equipo de CATÁLOGO, o None: un
    variador en su tablero, un aparato en su gabinete. El sólido de catálogo es la envolvente del
    equipo, no material (el TABLERO-5040 es un bloque de 500×200×400)."""
    for chica, grande in (("a", "b"), ("b", "a")):
        v = float(fila.get(f"volumen_{chica}_mm3") or 0.0)
        if (v > 0 and fila.get(f"catalogo_{grande}")
                and float(fila.get("volumen_mm3") or 0.0) >= CONTENIDA * v):
            return fila[chica]
    return None


def exceso(fila: dict) -> tuple[float, list[dict]]:
    """(volumen NO intencional, roscas engranadas reconocidas) de un solape medido."""
    if alojada(fila) is not None:
        return 0.0, []
    solidos = fila.get("solidos")
    if not solidos:  # sin el detalle por sólido: todo el volumen cuenta
        return float(fila.get("volumen_mm3") or 0.0), []
    total, roscas = 0.0, []
    for s in solidos:
        ok, rosca = _intencional(s)
        total += float(s.get("volumen_mm3") or 0.0) - ok
        if rosca:
            roscas.append(rosca)
    return max(total, 0.0), roscas


def _texto(f: dict, ex: float) -> str:
    uniones = ", ".join(f"{u} ({k})" for u, k in zip(f["uniones"], f["kinds"]))
    rosca = (f" (de {f['volumen_mm3']:g} mm³; el resto es rosca engranada)"
             if ex < float(f["volumen_mm3"]) - 0.5 else "")
    return (f"{f.get('nombre_a') or f['a']} ({f['a']}) ↔ {f.get('nombre_b') or f['b']} "
            f"({f['b']}): {ex:.1f} mm³ comunes{rosca} bajo {uniones}")


def interferencia_declarada(ins: dict) -> dict:
    """El control del ítem: `ins["interferencia_declarada"]` = {pares, solapes, errores} (None:
    no se midió; {"error"}: no corrió)."""
    datos = ins.get("interferencia_declarada")
    if datos is None:
        return {"estado": SIN_EVALUAR, "detalle": "no se midieron los pares con unión declarada"}
    if datos.get("error"):
        return {"estado": SIN_EVALUAR, "detalle": f"no se pudo medir ({datos['error']})"}
    malas, roscas, tolerados, alojadas = [], [], 0, []
    for f in datos.get("solapes") or ():
        if (dentro := alojada(f)) is not None:
            alojadas.append({"pieza": dentro, "en": f["b"] if dentro == f["a"] else f["a"]})
        ex, rs = exceso(f)
        roscas += [{"a": f["a"], "b": f["b"], **r} for r in rs]
        if ex > EXCESS_TOL_MM3:
            malas.append((f, ex))
        else:
            tolerados += 1
    malas.sort(key=lambda m: -m[1])
    errores = list(datos.get("errores") or ())
    ev = {"pares": int(datos.get("pares") or 0), "tolerancia_mm3": EXCESS_TOL_MM3,
          "tolerados": tolerados}
    if roscas:
        ev["roscas_engranadas"] = roscas[:40]
    if alojadas:
        ev["alojadas_en_catalogo"] = alojadas[:40]
    if malas:
        ev["solapes"] = [{"a": f["a"], "b": f["b"], "uniones": f["uniones"], "kinds": f["kinds"],
                          "volumen_mm3": f["volumen_mm3"], "exceso_mm3": round(ex, 1)}
                         for f, ex in malas[:40]]
        if len(malas) > 40:
            ev["solapes_omitidos"] = len(malas) - 40
        casos = "; ".join(_texto(f, ex) for f, ex in malas[:6])
        resto = f" (+{len(malas) - 6} más en la evidencia)" if len(malas) > 6 else ""
        return {"estado": FALLA, "evidencia": ev,
                "piezas": [p for f, _ in malas for p in (f["a"], f["b"])][:40],
                "detalle": f"{len(malas)} par(es) con unión declarada comparten volumen (más de "
                           f"{EXCESS_TOL_MM3:g} mm³): {casos}{resto}. {COMO[0].upper()}{COMO[1:]}"}
    if errores:
        ev["errores"] = errores[:20]
        return {"estado": SIN_EVALUAR, "evidencia": ev,
                "piezas": [p for e in errores[:20] for p in (e["a"], e["b"])],
                "detalle": f"{len(errores)} par(es) con unión declarada no se pudieron medir: "
                           + "; ".join(f"{e['a']} ↔ {e['b']} ({e['error']})" for e in errores[:4])}
    extra = f", {len(roscas)} con rosca engranada" if roscas else ""
    return {"estado": OK, "evidencia": ev,
            "detalle": f"{ev['pares']} par(es) con unión declarada, ninguno comparte más de "
                       f"{EXCESS_TOL_MM3:g} mm³ fuera de su rosca{extra}"}


ENTRADA = Entrada(
    "union.interferencia_declarada",
    "Una unión declarada no tapa una interferencia: lo unido se toca, no comparte volumen",
    "dos piezas unidas por un fasten (contacto, soldadura, perno) metidas una en la otra (un "
    "travesaño 9 903 mm³ dentro de su pata): la entrega no lo ve porque el par está declarado, y "
    "en el taller no se puede armar así",
    NORMA, "montaje",
    hecho("uniones_declaradas", "sin uniones declaradas (fasten)"),
    interferencia_declarada)
