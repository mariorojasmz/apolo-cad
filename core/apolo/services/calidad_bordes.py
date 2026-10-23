"""Insumos del control de DISTANCIA AL BORDE y PASO (plan puerta-de-publicacion, F6): por cada
perno MODELADO (los insumos de agarre de `calidad_pernos`: eje de la geometría y lo que cruza),
en cada pieza que atraviesa, el agujero medido con `library/borde_agujero.medir_borde`. El
control puro es `library/calidad/bordes.py` (formato en su docstring). El llamador sostiene
STATE_LOCK (sólo se leen shapes).

Qué se mide: las piezas del TALLER (a medida, o perfil de catálogo cortable: el taller la
taladra). Una pieza de catálogo no cortable (chumacera, motor, garrucha) trae sus agujeros del
fabricante: `de_catalogo`, no se juzga. Las tuercas no son piezas unidas. El perno de una unión
declarada (`fasten` perno, `join_bolted`) y el modelado a mano se miden igual: la regla es del
agujero, no de cómo se declaró. Una unión `perno` DECLARADA sin perno modelado no tiene eje que
medir (la cuenta `tornilleria_declarada`, sin geometría): no entra.

Una BARRA maciza (`borde_agujero`: eje o barra cuadrada que el perno atraviesa) no se juzga con la
tabla de chapas; si es ROSCADA lleva su rosca enganchada (`rosca_mm` hasta la punta del perno,
`rosca_min_mm` = k·d por material, la regla de `agarre.retencion`), que el control sí juzga: con
contratuerca, `retencion` mira la tuerca y no el hilo de la barra.
"""

from __future__ import annotations

import re

_ARANDELA_RE = re.compile(r"\b(arandelas?|washers?)\b", re.I)


def _es_del_taller(feat, catalog) -> bool:
    comp = catalog.get(getattr(feat, "component", None) or "")
    return comp is None or bool(getattr(comp, "cuttable", False))


def _rayos_de(esc, fid: str, centro):
    lo = tuple(c - 0.05 for c in centro)
    hi = tuple(c + 0.05 for c in centro)
    return [r for f, _feat, _s, r in esc.cerca(lo, hi) if f == fid]


def insumos_bordes(doc, pernos: list[dict], esc) -> tuple[list[dict], list[dict]]:
    """(agujeros, pasos) de los `pernos` (insumos de `calidad_pernos.insumos_pernos` medidos
    sobre la MISMA `esc`)."""
    from apolo.library.borde_agujero import P_MIN, medir_borde, paso_entre
    from apolo.library.calidad.agarre import rosca_enganchada
    from apolo.library.catalog import CATALOG

    from .calidad_pernos import tipo_de_tornilleria

    # los ejes de cada pieza: {fid: [(perno, punto, eje, radio del taladro, t0, t1)]}
    por_pieza: dict[str, list] = {}
    for p in pernos:
        if not p.get("evaluable") or not p.get("eje"):
            continue
        punto, eje = tuple(p["eje"]["asiento"]), tuple(p["eje"]["dir"])
        radio = _r_taladro(p)
        for t in p.get("tramos") or []:
            if t["rol"] != "pieza" or t["fid"] == p["fid"]:
                continue
            por_pieza.setdefault(t["fid"], []).append(
                (p, punto, eje, radio, t["t0"], t["t1"], t))
    agujeros, pasos = [], []
    for fid, ejes in por_pieza.items():
        feat = doc.scene.get(fid)
        if feat is None:
            continue
        nombre = getattr(feat, "name", fid)
        base = {"pieza": fid, "nombre": nombre}
        if tipo_de_tornilleria(feat, CATALOG) is not None:
            continue  # otro perno en el camino (tornillería superpuesta): no es una pieza unida
        if not _es_del_taller(feat, CATALOG):
            agujeros += [{**base, "perno": p["fid"], "estado": "de_catalogo",
                          "motivo": "agujero del fabricante (pieza de catálogo)"}
                         for p, *_r in ejes]
            continue
        if _ARANDELA_RE.search(nombre or ""):
            agujeros += [{**base, "perno": p["fid"], "estado": "anillo",
                          "motivo": "arandela"} for p, *_r in ejes]
            continue
        medidos = []
        for i, (p, punto, eje, _radio, t0, t1, tramo) in enumerate(ejes):
            roscado = bool(tramo.get("rosca"))
            otros = [(q[1], q[2], q[3]) for j, q in enumerate(ejes) if j != i]
            centro = tuple(punto[k] + eje[k] * (t0 + t1) / 2.0 for k in range(3))
            r = {"estado": "sin_medida", "motivo": "la pieza no tiene sólido en el eje"}
            for rayos in _rayos_de(esc, fid, centro):
                r = medir_borde(rayos, punto, eje, t0, t1, p["d"], otros, roscado)
                if r["estado"] in ("medido", "barra"):
                    break
            if r["estado"] == "barra" and roscado:
                eng, pide = rosca_enganchada(tramo, p.get("largo") or 0.0, p["d"])
                r = {**r, "rosca_mm": round(eng, 2), "rosca_min_mm": round(pide, 2)}
            agujeros.append({**base, "perno": p["fid"], **r})
            medidos.append((p, centro, eje, r, t1 - t0))
        for i, (pa, ca, ea, ra, ta) in enumerate(medidos):
            for pb, cb, eb, rb, tb in medidos[i + 1:]:
                paralelos = abs(abs(sum(x * y for x, y in zip(ea, eb, strict=True))) - 1) <= 1e-3
                if pa["fid"] == pb["fid"] or not paralelos or "barra" in (ra["estado"],
                                                                           rb["estado"]):
                    continue  # el paso también es regla de chapa
                axial = abs(sum((cb[k] - ca[k]) * ea[k] for k in range(3)))
                if axial > (ta + tb) / 2.0 + 0.5:
                    continue  # el mismo perno de cada lado de un tubo: otro plano
                p = paso_entre(ca, ea, cb)
                if p < 0.5:
                    continue
                d0 = max(ra.get("d0") or 0.0, rb.get("d0") or 0.0,
                         2.0 * max(_r_taladro(pa), _r_taladro(pb)))
                p_min = P_MIN * d0
                pasos.append({**base, "pernos": [pa["fid"], pb["fid"]], "p": round(p, 2),
                              "p_min": round(p_min, 2), "d0": round(d0, 2),
                              "cumple": p >= p_min - 0.05})
    return agujeros, pasos


def _r_taladro(p: dict) -> float:
    from apolo.library.engineering.bolts import CLEARANCE_HOLE_MM

    return CLEARANCE_HOLE_MM.get(f"M{p['d']:g}", 1.1 * p["d"]) / 2.0

