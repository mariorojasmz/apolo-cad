"""Control de DISTANCIA AL BORDE y PASO de los agujeros de perno (EN 1993-1-8, tabla 3.3; plan
puerta-de-publicacion, F6). Puro: recibe lo que mide `services/calidad_bordes.py` con
`library/borde_agujero.py` y devuelve dos ítems que agregan todos los agujeros del modelo.

Insumos:

    agujeros: [{"perno", "pieza", "nombre", "estado": "medido"|"sin_agujero"|"abertura"|
                "anillo"|"barra"|"sin_medida"|"de_catalogo", "motivo", "d0", "forma", "e",
                "e_min", "cumple", "espesor", "centro"; barra: "ancho", "roscado",
                "rosca_mm", "rosca_min_mm"}]
    pasos:    [{"pieza", "nombre", "pernos": [a, b], "p", "p_min", "d0", "cumple"}]

- **borde.distancia**: e ≥ 1,2·d0 (redondo; e1, e2) o ≥ 1,5·d0 (ranura; e3, e4). Un agujero a
  1,5 mm del canto se desgarra: FALLA con la pieza, el agujero, e medido y e requerido.
- **borde.paso**: p ≥ 2,2·d0 entre dos agujeros de la misma pieza (p1; p2 ≥ 2,4·d0 pide la
  dirección de la carga, que el modelo no declara: se juzga el mínimo de la norma).

Lo que no es una chapa del taller no se juzga y se cuenta en la evidencia: anillo coaxial
(arandela, separador), BARRA maciza (eje redondo o barra cuadrada que el perno atraviesa: la tabla
es de chapas y alas; criterio en `library/borde_agujero.py`, la lista en `barras`), pieza de
catálogo no cortable (el agujero es del fabricante: chumacera, motor) y abertura mayor que el
perno. La barra ROSCADA (el perno enrosca en ella) sí se juzga, por su rosca enganchada: `rosca_mm`
≥ `rosca_min_mm` (k·d por material, VDI 2230: la regla de `agarre.retencion`, que con
contratuerca sólo mira la tuerca); poco hilo es FALLA del mismo ítem. Un perno modelado sin su
agujero (`sin_agujero`) o una pared que no se reconoce (`sin_medida`) es «no se pudo ver»: si
nada se midió, el ítem sale SIN_EVALUAR; si otros sí, cuenta y se publica con el número.
"""

from __future__ import annotations

from .item import FALLA, MAX_CASOS, NO_APLICA, OK, SIN_EVALUAR, Item, recortar

NORMA = "EN 1993-1-8, tabla 3.3"
_CONTROLES = {
    "distancia": ("borde.distancia", "Cada agujero de perno en chapa o ala a ≥ 1,2·d0 del "
                  "canto libre (≥ 1,5·d0 si es ranura); en una barra roscada, rosca ≥ k·d",
                  "el agujero queda tan cerca del canto que la chapa se desgarra al apretar o "
                  "con la carga", NORMA),
    "paso": ("borde.paso", "Agujeros de perno de una misma pieza a un paso ≥ 2,2·d0",
             "dos agujeros tan juntos que el ligamento entre ellos se rompe", NORMA),
}
_NO_JUZGADOS = ("anillo", "barra", "de_catalogo", "abertura")
_NO_VISTOS = ("sin_agujero", "sin_medida")
_TOL = 0.05


def _caso_agujero(a: dict) -> dict:
    return {"perno": a.get("perno"), "pieza": a.get("pieza"), "nombre": a.get("nombre"),
            "e_mm": a.get("e"), "e_requerido_mm": a.get("e_min"), "d0_mm": a.get("d0"),
            "forma": a.get("forma"), "centro": a.get("centro")}


def _barras(agujeros: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """(barras, roscas cortas, evidencia): la barra no se juzga con la tabla; la ROSCADA, por su
    rosca enganchada (≥ k·d, la regla de `agarre.retencion`)."""
    barras = [a for a in agujeros if a["estado"] == "barra"]
    cortas = [a for a in barras if a.get("rosca_min_mm") is not None
              and (a.get("rosca_mm") or 0.0) < a["rosca_min_mm"] - _TOL]
    if not barras:
        return barras, cortas, {}
    ev: dict = {"barras": [{"perno": a.get("perno"), "pieza": a.get("pieza"),
                            "nombre": a.get("nombre"), "espesor_mm": a.get("espesor"),
                            "ancho_mm": a.get("ancho"), "roscado": a.get("roscado"),
                            **({"rosca_mm": a["rosca_mm"], "rosca_min_mm": a["rosca_min_mm"]}
                               if a.get("rosca_min_mm") is not None else {})}
                           for a in sorted(barras, key=lambda a: a not in cortas)[:MAX_CASOS]]}
    if len(barras) > MAX_CASOS:
        ev["barras_omitidas"] = len(barras) - MAX_CASOS
    return barras, cortas, ev


def _distancia(agujeros: list[dict]) -> Item:
    iid, titulo, modo, norma = _CONTROLES["distancia"]
    if not agujeros:
        return Item(iid, titulo, NO_APLICA, modo, norma,
                    detalle="ningún perno atraviesa una pieza del taller")
    medidos = [a for a in agujeros if a["estado"] == "medido"]
    malos = [a for a in medidos if not a.get("cumple", True)]
    no_vistos = [a for a in agujeros if a["estado"] in _NO_VISTOS]
    no_juzgados = [a for a in agujeros if a["estado"] in _NO_JUZGADOS]
    barras, cortas, ev_barras = _barras(agujeros)
    roscas = [a for a in barras if a.get("rosca_min_mm") is not None]
    motivos: dict[str, int] = {}
    for a in no_vistos + no_juzgados:
        motivos[a["estado"]] = motivos.get(a["estado"], 0) + 1
    evidencia = {"evaluados": len(medidos), "fallan": len(malos), "no_juzgados": motivos,
                 **recortar([_caso_agujero(a) for a in sorted(
                     malos, key=lambda a: (a.get("e") or 0) / max(a.get("e_min") or 1, 1e-9))]),
                 **ev_barras}
    if no_vistos and not medidos and not roscas:
        ej = no_vistos[0]
        evidencia["casos"] = [{"perno": a.get("perno"), "pieza": a.get("pieza"),
                               "motivo": a.get("motivo")} for a in no_vistos[:20]]
        return Item(iid, titulo, SIN_EVALUAR, modo, norma, evidencia=evidencia,
                    piezas=list(dict.fromkeys(a["pieza"] for a in no_vistos)),
                    detalle=f"ningún agujero se pudo medir ({ej.get('motivo')})")
    if not medidos and not roscas:
        return Item(iid, titulo, NO_APLICA, modo, norma, evidencia=evidencia,
                    detalle="los pernos sólo cruzan arandelas, separadores, barras macizas o "
                           "piezas de catálogo")
    textos = []
    if malos:
        peor = min(malos, key=lambda a: (a.get("e") or 0) / max(a.get("e_min") or 1, 1e-9))
        textos.append(f"{len(malos)} de {len(medidos)} agujeros bajo el mínimo; el peor, en "
                      f"«{peor.get('nombre')}»: e = {peor.get('e')} mm < {peor.get('e_min')} mm "
                      f"({'1,5' if peor.get('forma') == 'ranura' else '1,2'}·d0, d0 = "
                      f"{peor.get('d0')} mm)")
    if cortas:
        c = min(cortas, key=lambda a: a["rosca_mm"] / max(a["rosca_min_mm"], 1e-9))
        textos.append(f"{len(cortas)} de {len(roscas)} roscas en barra con poco hilo; la peor, "
                      f"«{c.get('nombre')}»: engancha {c['rosca_mm']} mm < {c['rosca_min_mm']} "
                      "mm (≥ k·d, VDI 2230)")
    if textos:
        return Item(iid, titulo, FALLA, modo, norma, evidencia=evidencia,
                    piezas=list(dict.fromkeys(x for a in malos + cortas
                                              for x in (a["pieza"], a["perno"]))),
                    detalle="; ".join(textos))
    extra = f"; {len(no_vistos)} sin medir" if no_vistos else ""
    if barras:
        extra += (f"; {len(barras)} en barras macizas (fuera de la tabla 3.3"
                  + (f", {len(roscas)} con su rosca enganchada" if roscas else "") + ")")
    return Item(iid, titulo, OK, modo, norma, evidencia=evidencia,
                detalle=f"los {len(medidos)} agujeros medidos cumplen{extra}")


def _paso(pasos: list[dict]) -> Item:
    iid, titulo, modo, norma = _CONTROLES["paso"]
    if not pasos:
        return Item(iid, titulo, NO_APLICA, modo, norma,
                    detalle="ninguna pieza tiene dos agujeros de perno en el mismo plano")
    malos = sorted((x for x in pasos if not x["cumple"]), key=lambda x: x["p"] / x["p_min"])
    casos = [{"pieza": x["pieza"], "nombre": x.get("nombre"), "pernos": x["pernos"],
              "p_mm": x["p"], "p_requerido_mm": x["p_min"], "d0_mm": x["d0"]} for x in malos]
    evidencia = {"evaluados": len(pasos), "fallan": len(malos), **recortar(casos)}
    if malos:
        x = malos[0]
        return Item(iid, titulo, FALLA, modo, norma, evidencia=evidencia,
                    piezas=list(dict.fromkeys(y for m in malos for y in (m["pieza"], *m["pernos"]))),
                    detalle=f"{len(malos)} de {len(pasos)} pares bajo el paso mínimo; el peor, en "
                            f"«{x.get('nombre')}»: p = {x['p']} mm < {x['p_min']} mm (2,2·d0)")
    return Item(iid, titulo, OK, modo, norma, evidencia=evidencia,
                detalle=f"los {len(pasos)} pares de agujeros cumplen")


def controlar_bordes(agujeros: list[dict], pasos: list[dict]) -> list[Item]:
    return [_distancia(agujeros), _paso(pasos)]
