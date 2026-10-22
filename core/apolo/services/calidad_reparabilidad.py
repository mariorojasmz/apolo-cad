"""Reparabilidad para la puerta de publicación (plan puerta-de-publicacion, F3, D5).

Los barridos se miden con RAYOS (`calidad_sondas.Trazador.todos`): desde puntos de la superficie
de la pieza (vértices de su teselado, 0,3 mm hacia su centro para no rozar la cara en que
apoya) en la dirección de salida, hasta salir de la máquina. Un rayo es exacto donde una caja
no lo es: el eje que pasa por el agujero de una placa sale por el agujero.

- `desgaste_desmontable`: la unidad de cada pieza de desgaste (ella + lo soldado a ella) sale
  en alguna de las 6 direcciones sin cruzar el marco soldado (`library/reparabilidad.py`).
- `banda_montable`: el lazo sale a lo largo del eje de sus tambores por algún lado sin cruzar
  marco soldado que además pase por dentro del lazo.

Sin locks (el llamador sostiene `STATE_LOCK`).
"""

from __future__ import annotations

import time

ID_SIN_SOLDADURA = "reparabilidad.desgaste_sin_soldadura"
ID_DESMONTABLE = "reparabilidad.desgaste_desmontable"
ID_BANDA = "reparabilidad.banda_montable"
MAX_PUNTOS = 160
_HUNDIR_MM = 0.3


def _puntos(solidos, max_puntos: int = MAX_PUNTOS) -> list[tuple]:
    """Vértices del teselado de los sólidos (sub-muestreados, deterministas), hundidos 0,3 mm
    hacia el centro de su sólido."""
    pts = []
    for s in solidos:
        try:
            verts, _ = s.tessellate(2.0, 0.5)
            c = s.bounding_box().center()
        except Exception:  # noqa: BLE001
            continue
        for v in verts:
            d = (c.X - v.X, c.Y - v.Y, c.Z - v.Z)
            n = (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** 0.5 or 1.0
            pts.append(tuple((v.X, v.Y, v.Z)[i] + _HUNDIR_MM * d[i] / n for i in range(3)))
    if len(pts) > max_puntos:
        paso = len(pts) / max_puntos
        pts = [pts[int(k * paso)] for k in range(max_puntos)]
    return pts


def _barrer(tr, puntos, d, caja, propias: set) -> list[str]:
    """Las piezas (ajenas) que cruzan los rayos de `puntos` en la dirección `d` hasta salir."""
    lo, hi = caja
    out: set[str] = set()
    for p in puntos:
        t_max = 0.0
        for i in range(3):
            if d[i] > 0:
                t_max = max(t_max, hi[i] + 10.0 - p[i])
            elif d[i] < 0:
                t_max = max(t_max, p[i] - lo[i] + 10.0)
        for _, fid in tr.todos(p, d, t_max, 0.05):
            if fid is not None and fid not in propias:
                out.add(fid)
    return sorted(out)


def _orden_direcciones():
    from apolo.library.reparabilidad import DIRECCIONES

    return [DIRECCIONES[4], DIRECCIONES[2], DIRECCIONES[3], DIRECCIONES[0], DIRECCIONES[1],
            DIRECCIONES[5]]  # primero hacia arriba (izar), por último hacia abajo


def desgaste_desmontable(dc: dict, tr) -> dict:
    """El ítem `reparabilidad.desgaste_desmontable`."""
    from apolo.library.reparabilidad import (
        NORMA,
        camino_libre,
        marco_soldado,
        piezas_de_desgaste,
        unidad,
    )
    from apolo.library.seguridad.modelo import item

    t0 = time.perf_counter()
    piezas, uniones = dc["piezas"], dc["uniones"]
    marco = marco_soldado(piezas, uniones)
    titulo = "Cada pieza de desgaste sale quitando sólo piezas atornilladas"
    modo = "una pieza de desgaste encerrada por estructura soldada no se puede cambiar"
    desg = {i: c for i, c in piezas_de_desgaste(piezas).items() if c not in ("banda", "cadena")}
    if not desg:
        return item(ID_DESMONTABLE, titulo, "NO_APLICA", modo, NORMA,
                    {"motivo": "sin piezas de desgaste rígidas (las cadenas se abren por su "
                               "eslabón de unión; la banda tiene su propio control)"})
    vistas: dict[frozenset, dict] = {}
    fallas, ok = [], 0
    for i, clase in desg.items():
        u = frozenset(unidad(i, uniones))
        if u not in vistas:
            if u & marco:  # soldada al marco: la falla es del otro ítem, aquí no sale
                vistas[u] = {"libre": False, "soldada": True, "bloqueos": {}}
            else:
                pts = _puntos([s for m in u for s in dc["solidos"].get(m, ())])
                barridos, res = {}, None
                for d in _orden_direcciones():
                    barridos[d] = _barrer(tr, pts, d, dc["caja"], set(u))
                    res = camino_libre(barridos, set(u), marco)
                    if res["libre"]:
                        break
                vistas[u] = res
        r = vistas[u]
        if r["libre"]:
            ok += 1
        else:
            fallas.append({"id": i, "nombre": piezas[i].nombre, "clase": clase,
                           "unidad": sorted(u), **({"soldada": True} if r.get("soldada")
                                                   else {"bloqueos": r["bloqueos"]})})
    ev = {"evaluadas": len(desg), "libres": ok, "fallas": fallas[:10],
          "n_fallas": len(fallas), "rayos": tr.n_rayos,
          "ms": round((time.perf_counter() - t0) * 1000.0)}
    if fallas:
        return item(ID_DESMONTABLE, titulo, "FALLA", modo, NORMA, ev,
                    [f["id"] for f in fallas],
                    "; ".join(f"{f['nombre']}: "
                              + ("soldada" if f.get("soldada") else "encerrada por "
                                 + ", ".join(sorted({x for v in f["bloqueos"].values()
                                                     for x in v})[:4]))
                              for f in fallas[:5]))
    return item(ID_DESMONTABLE, titulo, "OK", modo, NORMA, ev,
                detalle=f"{ok} piezas de desgaste con camino de salida")


def _eje_de_tambores(dc: dict, banda: str, tambores: list[str]) -> int:
    from collections import Counter

    piezas = dc["piezas"]
    ejes = Counter(piezas[t].redondo.eje for t in tambores if piezas[t].redondo is not None)
    if ejes:
        return ejes.most_common(1)[0][0]
    lo, hi = piezas[banda].caja
    lados = sorted(range(3), key=lambda i: hi[i] - lo[i])
    return lados[1]


def banda_montable(dc: dict, tr, tambores: dict[str, list[str]]) -> dict:
    """El ítem `reparabilidad.banda_montable`."""
    from apolo.library.reparabilidad import NORMA, empalme_mecanico, marco_soldado
    from apolo.library.reparabilidad import banda_montable as decidir
    from apolo.library.seguridad.modelo import SOLDADAS, clase_flexible, componentes, item, vecinos

    t0 = time.perf_counter()
    piezas, uniones = dc["piezas"], dc["uniones"]
    titulo = "La banda sin fin se monta de costado quitando sólo piezas atornilladas"
    modo = "banda sin fin encerrada por estructura soldada: no se puede cambiar sin cortar"
    bandas = sorted(i for i, p in piezas.items() if clase_flexible(p) == "banda")
    if not bandas:
        return item(ID_BANDA, titulo, "NO_APLICA", modo, NORMA, {"motivo": "sin banda"})
    marco = marco_soldado(piezas, uniones)
    comp_de = {}
    for c in componentes(marco, vecinos(uniones, SOLDADAS)):
        for i in c:
            comp_de[i] = c
    resultados, malas = [], []
    for b in bandas:
        pb = piezas[b]
        if empalme_mecanico(pb):
            resultados.append({"banda": b, "montable": True, "modo": "empalme mecánico en sitio"})
            continue
        a = _eje_de_tambores(dc, b, tambores.get(b, []))
        lo, hi = pb.caja
        # el «adentro» del lazo: su caja en el plano del lazo, a lo ancho de la banda
        esp = 3.0
        adentro = (tuple(lo[i] + (0 if i == a else esp) for i in range(3)),
                   tuple(hi[i] - (0 if i == a else esp) for i in range(3)))

        def pasa_por_dentro(i, adentro=adentro):
            c = piezas[i].caja
            return all(c[0][k] < adentro[1][k] and adentro[0][k] < c[1][k] for k in range(3))

        pts = _puntos(dc["solidos"][b], 240)
        lados = {}
        for s, nombre in ((1, f"+{'XYZ'[a]}"), (-1, f"-{'XYZ'[a]}")):
            d = [0, 0, 0]
            d[a] = s
            cruzan = _barrer(tr, pts, tuple(d), dc["caja"], {b})
            lados[nombre] = sorted(i for i in cruzan if i in marco
                                   and any(pasa_por_dentro(m) for m in comp_de[i]))
        r = decidir(lados)
        resultados.append({"banda": b, "eje": "XYZ"[a], **r})
        if not r["montable"]:
            malas.append((b, r))
    ev = {"bandas": resultados, "ms": round((time.perf_counter() - t0) * 1000.0)}
    if malas:
        return item(ID_BANDA, titulo, "FALLA", modo, NORMA, ev,
                    [b for b, _ in malas] + [i for _, r in malas for v in r["bloqueos"].values()
                                             for i in v],
                    "; ".join(f"{piezas[b].nombre}: la abrazan "
                              + ", ".join(f"{k}: {', '.join(piezas[i].nombre for i in v[:3])}"
                                          for k, v in r["bloqueos"].items())
                              for b, r in malas[:3]))
    return item(ID_BANDA, titulo, "OK", modo, NORMA, ev,
                detalle="; ".join(f"{piezas[r['banda']].nombre}: "
                                  + (r.get("modo") or f"sale por {r['lado']}")
                                  for r in resultados))


def controles_reparabilidad(doc, dc: dict | None = None) -> dict:
    """→ {items: [sin soldadura, desmontable, banda montable], ms}."""
    from apolo.library.reparabilidad import item_sin_soldadura
    from apolo.library.seguridad.peligros import giratorias

    from .calidad_seguridad import _tambor_por_cuerpo, datos_calidad, tambores_de_banda
    from .calidad_sondas import Trazador

    t0 = time.perf_counter()
    dc = dc or datos_calidad(doc)
    tr = Trazador(dc["solidos"])
    tocan = tambores_de_banda(dc)
    gira = giratorias(dc["piezas"], dc["juntas"], dc["uniones"],
                      {i for ids in tocan.values() for i in ids})
    tambores = _tambor_por_cuerpo(tocan, dc["piezas"], gira, dc["juntas"], dc["uniones"])
    items = [item_sin_soldadura(dc["piezas"], dc["uniones"], ID_SIN_SOLDADURA),
             desgaste_desmontable(dc, tr), banda_montable(dc, tr, tambores)]
    return {"items": items, "ms": round((time.perf_counter() - t0) * 1000.0)}
