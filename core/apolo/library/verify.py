"""Aserciones numéricas en lote (V6.5c): el agente declara sus INVARIANTES y las
verifica en UNA llamada, en vez de encadenar N `measure` + aritmética mental.

Read-only y puro: la resolución de nombres de grupo → ids y el cálculo de
interferencias se INYECTAN (`expand`, `interference_fn`) para no violar la frontera
de capas (library no ve el Document ni la API). Cada aserción es un dict con `tipo`;
el retorno es una lista de ``{check, tipo, ok, actual, esperado}`` (o ``error``).

Tipos v1:
  - ``distancia`` {a, b, min|max|entre} — gap OCCT entre dos sólidos.
  - ``volumen``   {id|grupo|ids, min|max|entre} — volumen (suma si son varios).
  - ``bbox``      {id|grupo|ids, eje:x|y|z, min|max|entre} — tamaño de la caja conjunta.
  - ``sin_interferencia`` {ids?} — 0 colisiones (acotado a `ids`; sin ids = global).
  - ``existe``    {id|name} — el id existe / hay piezas cuyo nombre contiene `name`.
"""

from __future__ import annotations

from apolo.kernel.measure import measure_distance

_AXIS = {"x": 0, "y": 1, "z": 2}


def _cmp(actual: float, spec: dict) -> tuple[bool, dict | None]:
    """Compara `actual` contra los límites de `spec` (min / max / entre). Devuelve
    (ok, esperado). Sin límites declarados → informativo (ok=True, esperado=None)."""
    esperado: dict = {}
    ok = True
    entre = spec.get("entre")
    if entre is not None:
        lo, hi = float(entre[0]), float(entre[1])
        ok = ok and lo <= actual <= hi
        esperado["entre"] = [lo, hi]
    if spec.get("min") is not None:
        ok = ok and actual >= float(spec["min"])
        esperado["min"] = float(spec["min"])
    if spec.get("max") is not None:
        ok = ok and actual <= float(spec["max"])
        esperado["max"] = float(spec["max"])
    return ok, (esperado or None)


def _ids_of(spec: dict, scene: dict, expand) -> list[str]:
    """Resuelve id | grupo | ids (nombres de grupo se expanden) a feature_ids presentes."""
    if spec.get("grupo"):
        return [fid for fid in expand([spec["grupo"]]) if fid in scene]
    if spec.get("ids"):
        return [fid for fid in expand(spec["ids"]) if fid in scene]
    if spec.get("id"):
        return [spec["id"]] if spec["id"] in scene else []
    return []


def _combined_bbox(scene: dict, fids: list[str]) -> tuple[list[float], list[float]]:
    gmin = [float("inf")] * 3
    gmax = [float("-inf")] * 3
    for fid in fids:
        bb = scene[fid].shape.bounding_box()
        mn = [bb.min.X, bb.min.Y, bb.min.Z]
        mx = [bb.max.X, bb.max.Y, bb.max.Z]
        for k in range(3):
            gmin[k] = min(gmin[k], mn[k])
            gmax[k] = max(gmax[k], mx[k])
    return gmin, gmax


def run_verify(scene: dict, checks: list[dict], *, expand, interference_fn) -> list[dict]:
    """Ejecuta cada aserción. `expand(tokens) -> list[str]` resuelve grupos→ids;
    `interference_fn(focus_ids | None) -> {interferencias, truncado, ...}` corre la
    interferencia acotada (focus=None = global) y devuelve el REPORTE completo."""
    out: list[dict] = []
    for spec in checks:
        tipo = spec.get("tipo")
        label = spec.get("nombre") or tipo or "?"
        try:
            if tipo == "distancia":
                a, b = spec.get("a"), spec.get("b")
                if a not in scene or b not in scene:
                    falta = a if a not in scene else b
                    out.append({"check": label, "tipo": tipo, "ok": False,
                                "error": f"sólido inexistente '{falta}'"})
                    continue
                dist = measure_distance(scene[a].shape, scene[b].shape)["dist_mm"]
                ok, esperado = _cmp(dist, spec)
                out.append({"check": label, "tipo": tipo, "ok": ok,
                            "actual": dist, "esperado": esperado})

            elif tipo == "volumen":
                fids = _ids_of(spec, scene, expand)
                if not fids:
                    out.append({"check": label, "tipo": tipo, "ok": False, "error": "sin piezas"})
                    continue
                vol = round(sum(float(scene[f].shape.volume) for f in fids), 1)
                ok, esperado = _cmp(vol, spec)
                out.append({"check": label, "tipo": tipo, "ok": ok, "actual": vol,
                            "esperado": esperado, "n_piezas": len(fids)})

            elif tipo == "bbox":
                fids = _ids_of(spec, scene, expand)
                if not fids:
                    out.append({"check": label, "tipo": tipo, "ok": False, "error": "sin piezas"})
                    continue
                eje = spec.get("eje", "x")
                if eje not in _AXIS:
                    out.append({"check": label, "tipo": tipo, "ok": False,
                                "error": f"eje inválido '{eje}' (usa x|y|z)"})
                    continue
                gmin, gmax = _combined_bbox(scene, fids)
                i = _AXIS[eje]
                size = round(gmax[i] - gmin[i], 3)
                ok, esperado = _cmp(size, spec)
                out.append({"check": label, "tipo": tipo, "ok": ok, "actual": size,
                            "esperado": esperado, "eje": eje, "n_piezas": len(fids)})

            elif tipo == "sin_interferencia":
                # ids/grupo DECLARADOS que no resuelven a nada (typo) → error, NO degradar
                # SILENCIOSAMENTE al chequeo global O(n²) (contradice la doctrina de escala).
                # Sin scope declarado = global explícito (comportamiento documentado).
                declarado = spec.get("ids") or spec.get("grupo") or spec.get("id")
                fids = _ids_of(spec, scene, expand)
                if declarado and not fids:
                    out.append({"check": label, "tipo": tipo, "ok": False, "error": "sin piezas"})
                    continue
                rep = interference_fn(fids or None)
                cols = rep["interferencias"]
                entry = {"check": label, "tipo": tipo, "ok": len(cols) == 0,
                         "actual": len(cols), "esperado": {"max": 0},
                         "colisiones": cols[:10]}
                if rep.get("truncado"):
                    entry["truncado"] = True  # NO caps silenciosos: se declara el recorte
                out.append(entry)

            elif tipo == "existe":
                if spec.get("id"):
                    ok = spec["id"] in scene
                    out.append({"check": label, "tipo": tipo, "ok": ok, "actual": ok})
                else:
                    nm = (spec.get("name") or "").lower()
                    matches = [fid for fid, f in scene.items() if nm and nm in (f.name or "").lower()]
                    out.append({"check": label, "tipo": tipo, "ok": bool(matches),
                                "actual": len(matches), "ids": matches[:20]})

            else:
                out.append({"check": label, "tipo": tipo, "ok": False,
                            "error": f"tipo desconocido '{tipo}' (usa distancia|volumen|bbox|"
                                     "sin_interferencia|existe)"})
        except Exception as exc:  # noqa: BLE001 — una aserción rota no tumba el lote
            out.append({"check": label, "tipo": tipo, "ok": False, "error": str(exc)})
    return out
