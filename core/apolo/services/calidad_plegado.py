"""Las posiciones de un producto PLEGABLE (plan plegables-en-la-puerta, F1: D2 y D3): el insumo de
`plegado.posiciones` y `plegado.espesor` (`library/calidad/plegado.py`, donde está el criterio) y
el TRÁNSITO uso → guardado que `delivery_check` avisa. Sólo con el requisito `plegable`
(`requisitos.es_plegable`): sin él, nada. El llamador sostiene STATE_LOCK.

- **Posiciones**: cada estudio de `doc.motion` con sus fotogramas `posicion: "uso" | "guardado"`,
  los valores fuera de los límites de su junta (`lower`/`upper`; una `continua` no tiene), las
  juntas que el modelo no declara y las que CAMBIAN entre las dos (una `fija` no cambia).
- **Caja del guardado**: el producto posado en el guardado del primer estudio válido (las
  restricciones del lazo resueltas, como el estudio en la UI y en `scan_motion`): la caja alineada
  con los ejes del modelo de todo sólido que no es guía, con sus tres lados de menor a mayor.
- **Tránsito** (`transito`): `PASOS` instantes entre el uso y el guardado (los dos incluidos). En
  cada uno sólo se miden los pares que se MUEVEN uno respecto del otro (los de una misma
  ubicación de FK quedan como en diseño: no pueden dar un choque nuevo) y un choque es NUEVO si
  su solape pasa el de la pose de diseño en más de `EXCESS_TOL_MM3`. Por eso no cuentan los
  tornillos en su pretaladro ni los nudillos de una bisagra (F0 § 2.4: las 56 interferencias por
  paso de la mesa de 1,8 m eran de diseño). El herraje de catálogo se excluye como en
  `scan_collisions`.
"""

from __future__ import annotations

import time

#: Instantes del tránsito (intervalos entre el uso y el guardado). F0 midió 6, 12 y 24 en la mesa
#: de 1,8 m con la interferencia entera; con sólo los pares que se mueven, 6 bastan para avisar.
PASOS = 6


def requiere(doc) -> bool:
    from apolo.library.requisitos import es_plegable

    return es_plegable(getattr(doc, "requirements", None))


def _cuadro(kf: dict | None) -> dict | None:
    if kf is None:
        return None
    vals = kf.get("values") if isinstance(kf.get("values"), dict) else {}
    try:
        return {"t": float(kf.get("t", 0.0)), "values": {str(k): float(v) for k, v in vals.items()}}
    except (TypeError, ValueError):
        return {"t": float(kf.get("t") or 0.0), "values": {}, "error": "valores no numéricos"}


def _etiquetado(kfs, posicion: str) -> dict | None:
    return next((kf for kf in kfs or [] if isinstance(kf, dict)
                 and str(kf.get("posicion") or "").lower() == posicion), None)


def estudios(doc) -> list[dict]:
    """Una fila por estudio de movimiento (formato en `calidad/plegado.posiciones`)."""
    juntas = doc.joints or {}
    out = []
    for nombre, kfs in sorted((doc.motion or {}).items()):
        e = {"estudio": nombre, "uso": _cuadro(_etiquetado(kfs, "uso")),
             "guardado": _cuadro(_etiquetado(kfs, "guardado"))}
        if e["uso"] and e["guardado"]:
            fuera, desconocidas = [], set()
            for pos in ("uso", "guardado"):
                for j, v in e[pos]["values"].items():
                    spec = juntas.get(j)
                    if spec is None:
                        desconocidas.add(j)
                    elif spec.get("type") != "continua" and not (
                            float(spec.get("lower", -180)) - 1e-6 <= v
                            <= float(spec.get("upper", 180)) + 1e-6):
                        fuera.append({"junta": j, "valor": v, "posicion": pos,
                                      "lower": float(spec.get("lower", -180)),
                                      "upper": float(spec.get("upper", 180))})
            vu, vg = e["uso"]["values"], e["guardado"]["values"]
            e["fuera_de_limites"] = fuera
            e["desconocidas"] = sorted(desconocidas)
            e["cambian"] = [j for j in sorted(set(vu) | set(vg))
                            if j in juntas and juntas[j].get("type") != "fija"
                            and abs(vu.get(j, 0.0) - vg.get(j, 0.0)) > 1e-6]
        out.append(e)
    return out


#: Un fotograma cuyos lazos ya cierran a esto (mm) no se re-resuelve (plegables F3): arrancando
#: EN la solución, cerca del punto muerto de la rodilla, `least_squares` se pasea por residuos no
#: derivables (normas en 0) y gasta todas sus evaluaciones: 14,7 s de CPU el uso de la mesa de
#: 1,8 m con sus dos lazos A, para volver a donde estaba.
YA_CIERRA_MM = 0.01


def _valores_resueltos(doc, vals: dict) -> dict:
    """Los valores con las restricciones del lazo resueltas (si las hay), como el estudio."""
    if getattr(doc, "constraints", None):
        from apolo.assembly.constraints import _residual, solve_constraints

        vals = {str(k): float(v) for k, v in vals.items()}
        activas = [c for c in doc.constraints.values() if c.get("joint") in doc.joints]
        try:
            if activas and max(_residual(doc.joints, vals, c) for c in activas) <= YA_CIERRA_MM:
                return dict(vals)
        except Exception:  # noqa: BLE001 — una restricción que no se evalúa: que resuelva
            pass
        return solve_constraints(doc.joints, doc.constraints, vals)
    return dict(vals)


def _posadas(doc, vals: dict) -> dict:
    """{fid: forma posada} de todo sólido que no es guía (también los ocultos: un cálculo no
    filtra por la vista)."""
    from apolo.robotics.pose import feature_location, posed_shapes

    override, _ = posed_shapes(doc, vals)
    by_child = {j["child"]: j for j in doc.joints.values()}
    cache: dict = {}
    out = {}
    for fid, f in doc.scene.items():
        if getattr(f, "is_guide", False) or getattr(f, "shape", None) is None:
            continue
        if fid in override:
            out[fid] = override[fid]
        else:
            loc = feature_location(doc.joints, vals, fid, by_child, cache)
            out[fid] = (loc * f.shape) if loc is not None else f.shape
    return out


def caja_guardado(doc, e: dict) -> dict:
    """{estudio, t, dims_mm (de menor a mayor), bbox [xmin, ymin, zmin, xmax, ymax, zmax]} del
    producto en el guardado del estudio `e`; {estudio, error} si OCCT no pudo."""
    try:
        formas = _posadas(doc, _valores_resueltos(doc, e["guardado"]["values"]))
        lo, hi = [float("inf")] * 3, [float("-inf")] * 3
        for s in formas.values():
            bb = s.bounding_box()
            for k, (a, b) in enumerate(((bb.min.X, bb.max.X), (bb.min.Y, bb.max.Y),
                                        (bb.min.Z, bb.max.Z))):
                lo[k], hi[k] = min(lo[k], a), max(hi[k], b)
        if lo[0] == float("inf"):
            return {"estudio": e["estudio"], "error": "el modelo no tiene sólidos"}
    except Exception as exc:  # noqa: BLE001 — no se pudo medir: SIN_EVALUAR, nunca OK
        return {"estudio": e["estudio"], "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"estudio": e["estudio"], "t": e["guardado"]["t"],
            "dims_mm": sorted(round(b - a, 1) for a, b in zip(lo, hi)),
            "bbox": [round(x, 1) for x in (*lo, *hi)]}


def plegado(doc) -> dict | None:
    """El insumo de `plegado.posiciones` y `plegado.espesor`, o None sin el requisito."""
    if not requiere(doc):
        return None
    from apolo.library.calidad.plegado import es_valido
    from apolo.library.requisitos import espesor_plegado

    filas = estudios(doc)
    elegido = next((e for e in filas if es_valido(e)), None)
    moviles = sum(1 for j in (doc.joints or {}).values() if j.get("type") != "fija")
    return {"juntas": moviles, "estudios": filas,
            "elegido": elegido["estudio"] if elegido else None,
            "caja_guardado": caja_guardado(doc, elegido) if elegido else None,
            "espesor_pedido_mm": espesor_plegado(doc.requirements)}


def _clave_loc(loc) -> tuple | None:
    if loc is None:
        return None
    p, o = loc.position, loc.orientation
    return tuple(round(float(x), 4) for x in (p.X, p.Y, p.Z, o.X, o.Y, o.Z))


def transito(doc, pasos: int = PASOS) -> dict | None:
    """El tránsito uso → guardado del primer estudio válido: {estudio, desde_t, hasta_t, pasos,
    choques: [{t, a, b, nombre_a, nombre_b, volumen_mm3 (el exceso), diseno_mm3}], cpu_s}; o
    {estudio?, error}; None sin el requisito o sin un estudio válido (lo dice
    `plegado.posiciones`)."""
    if not requiere(doc):
        return None
    from apolo.library.calidad.plegado import es_valido

    e = next((x for x in estudios(doc) if es_valido(x)), None)
    if e is None:
        return None
    c0 = time.process_time()
    try:
        choques = _recorrer(doc, e, max(1, min(int(pasos), 48)))
    except Exception as exc:  # noqa: BLE001 — no se pudo recorrer: AVISO, nunca verde
        return {"estudio": e["estudio"], "error": f"{type(exc).__name__}: {exc}"[:200]}
    return {"estudio": e["estudio"], "desde_t": e["uso"]["t"], "hasta_t": e["guardado"]["t"],
            "pasos": max(1, min(int(pasos), 48)), "choques": choques,
            "cpu_s": round(time.process_time() - c0, 2)}


def _recorrer(doc, e: dict, pasos: int) -> list[dict]:
    from apolo.library import interference_report
    from apolo.library.checks import EXCESS_TOL_MM3, _overlap_volume, hardware_ids
    from apolo.robotics.motion import values_at
    from apolo.robotics.pose import feature_location

    kfs = doc.motion[e["estudio"]]
    t0, t1 = e["uso"]["t"], e["guardado"]["t"]
    hw = hardware_ids(doc)
    diseno: dict[frozenset, float] = {}
    peores: dict[frozenset, dict] = {}
    by_child = {j["child"]: j for j in doc.joints.values()}
    for i in range(pasos + 1):
        t = t0 + (t1 - t0) * i / pasos
        vals = _valores_resueltos(doc, values_at(kfs, t))
        cache: dict = {}
        grupos: dict = {}
        for fid in doc.scene:
            grupos.setdefault(_clave_loc(feature_location(doc.joints, vals, fid, by_child, cache)),
                              []).append(fid)
        if len(grupos) < 2:
            continue  # nada se mueve respecto de nada: como en diseño
        quietos = {frozenset((a, b)) for fids in grupos.values()
                   for k, a in enumerate(fids) for b in fids[k + 1:]}
        posadas = _posadas(doc, vals)
        desde = 0
        while True:
            rep = interference_report(doc.scene, shapes_override=posadas, exclude_pairs=quietos,
                                      exclude_ids=hw, desde=desde)
            for c in rep["interferencias"]:
                par = frozenset((c["a"], c["b"]))
                if par not in diseno:
                    diseno[par] = _overlap_volume(doc.scene[c["a"]].shape, doc.scene[c["b"]].shape)
                exceso = float(c["volumen_mm3"]) - diseno[par]
                if exceso > EXCESS_TOL_MM3 and exceso > peores.get(par, {}).get("volumen_mm3", 0):
                    peores[par] = {"t": round(t, 3), "a": c["a"], "b": c["b"],
                                   "nombre_a": c.get("nombre_a"), "nombre_b": c.get("nombre_b"),
                                   "volumen_mm3": round(exceso, 1),
                                   "diseno_mm3": round(diseno[par], 1)}
            if not rep["truncado"]:
                break
            desde = rep["desde_siguiente"]
    return sorted(peores.values(), key=lambda c: -c["volumen_mm3"])
