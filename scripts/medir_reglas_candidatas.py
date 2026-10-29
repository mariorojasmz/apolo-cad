"""Cuántas piezas fallarían con las reglas CANDIDATAS de la puerta (plan
hallazgos-del-revisor-en-la-puerta, F0): sólo lectura, nada se escribe en los `.apolo`.

    python -B scripts/medir_reglas_candidatas.py <a.apolo> [<b.apolo> …] [--json salida.json]

Por cada `.apolo` (cargado con `Document.from_apolo_bytes`):

- **D1** `material.conocido`: piezas a medida (sin ref de catálogo) cuyo material resuelto no
  conoce `materials.known_material` (y, aparte, las que no tienen resistencia tabulada).
- **D4** `bom.comprable`: filas de `bom_from_scene` que no alcanzan para comprar o cortar, hoy y
  con D3 simulada (la pieza a medida de metal toma la norma genérica de `NORMA_CHAPA`). Una ref
  de catálogo con otro material («pedir la equivalente», R2) alcanza.
- **D6** `apoyo.capacidad`: los apoyos a tierra que se compran (ref de catálogo o «(compra)»),
  su capacidad (`carga_kg`/`capacidad_kg` de la ficha o «N kg» en el nombre) contra la reacción
  de `installation_data` × 1,5.
- **D7** distancias en madera: por cada perno o tirafondo MODELADO (insumos de
  `calidad_pernos`) en una pieza de madera, la distancia del eje a la testa y al canto (rayos en
  el plano medio del tramo; la veta = el eje largo de la pieza) contra EN 1995-1-1 tablas 8.2 y
  8.4 (extremo y borde cargados y descargados) y contra la alternativa 4d testa / 3d canto.
  Aparte, el tornillo cuyo eje va A LO LARGO de la veta (metido en la testa).
- **D8** eje que gira: por cada junta de giro, los pernos coaxiales (± 1 mm) y si llevan traba
  (autoblocante, contratuerca, pasador de aletas o anillo) o son tornillo de madera.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "core") not in sys.path:  # mide ESTE árbol (en un worktree el venv apunta al principal)
    sys.path.insert(0, str(RAIZ / "core"))

FS_APOYO = 1.5
_KG_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg\b", re.I)
_TRABA_RE = re.compile(r"autoblocante|din\s*985|iso\s*7040|nyloc|contratuerca|aletas|din\s*94\b|"
                       r"iso\s*1234|anillo|din\s*471|din\s*6799|seeger|circlip|chaveta|"
                       r"pasador\s+(?:el[aá]stico|de\s+seguridad)|clip", re.I)
_LARGO_RE = re.compile(r"\b(varilla|barra|perfil|tubo|pletina|platina|angular|[áa]ngulo|"
                       r"cable|cadena)\b", re.I)
_APOYO_RE = re.compile(r"\b(pie|pies|pata|patas|garrucha|garruchas|rueda|ruedas|regat[oó]n|"
                       r"zapata|nivelador)\b", re.I)
_GRADO_RE = re.compile(r"\b(astm\s*a\d+|aisi\s*\d{3}|en\s*10\d{3}|s(235|275|355)|a(36|572|500)\b)",
                       re.I)
#: una norma escrita en el material o en el nombre («clase C16 (EN 338)», «triplay EN 636-1»)
_NORMA_TXT_RE = re.compile(r"\b(EN|ISO|DIN|ASTM|AISI|UNE|NTP|JIS)\s*[A-Z]?\s*\d", re.I)
#: una medida comercial en el nombre (M8, Ø25,4, 32x5, 12in, 1½″)
_MEDIDA_RE = re.compile(r"\bM\d|Ø\s*\d|\d\s*[x×]\s*\d|\d\s*(in\b|″|\")", re.I)
_SIN_LARGO_RE =re.compile(r"\b(arandelas?|tuercas?|remaches?|insertos?|pasadores?)\b", re.I)
_CAT_APOYO = ("pies_niveladores", "garruchas", "patas", "ruedas")


def _v(p) -> tuple[float, float, float]:
    if isinstance(p, dict):
        return (float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0)))
    return (float(p[0]), float(p[1]), float(p[2]))


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def _comp(feat, catalog):
    return catalog.get(getattr(feat, "component", None) or "")


# ------------------------------------------------------------------ D1
def d1(doc) -> dict:
    from apolo.library.catalog import CATALOG
    from apolo.library.materials import has_yield, known_material, resolve_material

    falla, sin_fy = [], []
    for fid, feat in doc.scene.items():
        if getattr(feat, "is_guide", False) or _comp(feat, CATALOG) is not None:
            continue
        mat = resolve_material(feat, CATALOG, doc.default_material())
        fila = {"pieza": fid, "nombre": feat.name, "material": mat}
        if not known_material(mat):
            falla.append(fila)
        elif not has_yield(mat):
            sin_fy.append(fila)
    return {"falla": falla, "sin_resistencia": sin_fy}


# ------------------------------------------------------------------ D4
def d4(doc, bom: list[dict]) -> dict:
    from apolo.library.bom_compra import NORMA_CHAPA
    from apolo.library.catalog import CATALOG
    from apolo.library.designacion_comercial import norma_del_nombre

    hoy, con_d3, sin_largo = [], [], []
    for row in bom:
        ref, desc = row.get("ref") or "", row.get("descripcion") or ""
        mat = (row.get("material") or "").strip().lower()
        motivo = None
        if ref == "A-MEDIDA":
            if not row.get("norma"):
                motivo = "a medida sin norma de material"
        elif ref == "COMPRA":
            if not (row.get("norma") or norma_del_nombre(desc)):
                motivo = "compra sin norma, designación ni código"
            elif _LARGO_RE.search(desc) and not row.get("longitud_mm"):
                motivo = "barra o varilla de compra sin largo"
        else:
            comp = CATALOG.get(ref)
            if comp is not None and getattr(comp, "cuttable", False) and not row.get("longitud_mm"):
                motivo = "perfil de catálogo sin largo"
        if (motivo is None and row.get("categoria") in ("pernos", "tornilleria", "tornilleria_madera")
                and not row.get("longitud_mm") and not _SIN_LARGO_RE.search(desc)):
            sin_largo.append({"fila": desc, "ref": ref, "cantidad": row.get("cantidad")})
        if motivo is None:
            continue
        texto = f"{mat} {desc}"
        fila = {"fila": desc, "ref": ref, "material": row.get("material"),
                "cantidad": row.get("cantidad"), "motivo": motivo,
                "norma_en_texto": bool(_NORMA_TXT_RE.search(texto)),
                "medida_comercial": bool(_MEDIDA_RE.search(desc))}
        hoy.append(fila)
        d3 = motivo.startswith("a medida") and (mat in NORMA_CHAPA or _GRADO_RE.search(texto))
        if not d3:  # D3: la norma genérica del metal, o el grado que el modelador declaró
            con_d3.append(fila)
    return {"filas": len(bom), "falla_hoy": hoy, "falla_con_d3": con_d3,
            "tornilleria_sin_largo": sin_largo}


# ------------------------------------------------------------------ D6
def _capacidad(feat, comp) -> float | None:
    if comp is not None:
        specs = {**(getattr(comp, "params", None) or {}), **(comp.specs or {})}
        for k in ("capacidad_kg", "carga_kg"):
            if specs.get(k):
                return float(specs[k])
    m = _KG_RE.search(getattr(feat, "name", "") or "")
    return float(m.group(1).replace(",", ".")) if m else None


def d6(doc) -> dict:
    from apolo.library.catalog import CATALOG
    from apolo.library.designacion_comercial import compra_declarada
    from apolo.services.installation_data import installation_data

    try:
        datos, _ = installation_data(doc)
    except Exception as e:  # noqa: BLE001 — sólo se mide
        return {"error": repr(e)}
    filas = (datos.get("anclaje") or {}).get("apoyos") or []
    out = []
    for f in filas:
        feat = doc.scene.get(f["id"])
        comp = _comp(feat, CATALOG)
        nombre = getattr(feat, "name", f["id"])
        compra = (comp is not None and (comp.category in _CAT_APOYO or _APOYO_RE.search(nombre))
                  ) or (comp is None and compra_declarada(nombre))
        if not compra:
            out.append({"pieza": f["id"], "nombre": nombre, "estado": "fabricado (no aplica)"})
            continue
        cap = _capacidad(feat, comp)
        pide = f["carga_kg"] * FS_APOYO
        estado = ("sin capacidad" if cap is None else
                  "cumple" if pide <= cap else "no alcanza")
        out.append({"pieza": f["id"], "nombre": nombre, "ref": getattr(feat, "component", None),
                    "reaccion_kg": f["carga_kg"], "pide_kg": round(pide, 1), "capacidad_kg": cap,
                    "estado": estado})
    return {"apoyos": out, "masa_kg": datos.get("masa_kg"), "carga_kg": datos.get("carga_kg")}


# ------------------------------------------------------------------ D7
def _veta(solid):
    """El eje largo de la pieza (la veta): el vector propio mayor de sus vértices."""
    import numpy as np

    pts = np.array([[v.X, v.Y, v.Z] for v in solid.vertices()])
    if len(pts) < 3:
        return (1.0, 0.0, 0.0)
    w, vec = np.linalg.eigh(np.cov((pts - pts.mean(axis=0)).T))
    return tuple(float(x) for x in vec[:, int(np.argmax(w))])


def _exterior(rayos, centro, w, alcance, otros) -> float | None:
    """Distancia del eje a donde se acaba el material según `w` (salta los agujeros de otros
    pernos de la misma pieza); None si no se acaba dentro del alcance."""
    from apolo.library.borde_agujero import distancia_a_eje

    cs = rayos.cortes(centro, w, 0.0, alcance)
    dentro = rayos.dentro(centro)
    i = 0 if dentro else 1  # en el hueco del taladro, el primer corte es su pared
    while i < len(cs):
        q = tuple(centro[k] + w[k] * cs[i] for k in range(3))
        if any(distancia_a_eje(q, p, e) <= r + 1.0 for p, e, r in otros):
            i += 2  # el agujero de otro perno: sigue después de cruzarlo
            continue
        return cs[i]
    return None


def minimos(d: float, tipo: str) -> dict:
    """Mínimos (mm) de EN 1995-1-1 para el tornillo de Ø `d`: perno, tirafondo y tornillo
    d > 6 por la tabla 8.4 (§8.5.1, §8.7.1(3)); tornillo d ≤ 6 como clavo pretaladrado, tabla
    8.2. Cargado = α más desfavorable (testa α = 0°, canto α = 90°); descargado = a3,c, a4,c."""
    if tipo == "madera" and d <= 6.0:
        return {"testa_cargada": 12 * d, "testa_descargada": 7 * d,
                "canto_cargado": 7 * d, "canto_descargado": 3 * d,
                "testa_4d": 4 * d, "canto_3d": 3 * d}
    return {"testa_cargada": max(7 * d, 80.0), "testa_descargada": 4 * d,
            "canto_cargado": 4 * d, "canto_descargado": 3 * d,
            "testa_4d": 4 * d, "canto_3d": 3 * d}


def d7(doc, pernos, esc) -> dict:
    from apolo.library.catalog import CATALOG
    from apolo.library.materials import es_madera, resolve_material

    from apolo.services.calidad_bordes import _ARANDELA_RE, _r_taladro, _rayos_de

    por_pieza: dict[str, list] = {}
    for p in pernos:
        if not p.get("evaluable") or not p.get("eje"):
            continue
        for t in p.get("tramos") or []:
            if t["rol"] == "pieza" and t["fid"] != p["fid"]:
                por_pieza.setdefault(t["fid"], []).append((p, t))
    filas, veta_cache = [], {}
    for fid, ejes in por_pieza.items():
        feat = doc.scene.get(fid)
        if (feat is None or _comp(feat, CATALOG) is not None or _ARANDELA_RE.search(feat.name or "")
                or not es_madera(resolve_material(feat, CATALOG, doc.default_material()))):
            continue  # sólo la pieza de madera del taller (una arandela «de madera» es el vertical)
        for i, (p, t) in enumerate(ejes):
            punto, eje = tuple(p["eje"]["asiento"]), _unit(tuple(p["eje"]["dir"]))
            otros = [(tuple(q["eje"]["asiento"]), tuple(q["eje"]["dir"]), _r_taladro(q))
                     for j, (q, _t) in enumerate(ejes) if j != i]
            tm = (t["t0"] + t["t1"]) / 2.0
            centro = tuple(punto[k] + eje[k] * tm for k in range(3))
            d, tipo = float(p["d"]), ("madera" if p.get("madera_screw") else "perno")
            fila = {"pieza": fid, "nombre": feat.name, "perno": p["fid"],
                    "perno_nombre": p.get("nombre"), "d": d, "tipo": tipo}
            rayos_l = list(_rayos_de(esc, fid, centro))
            if not rayos_l:
                filas.append({**fila, "estado": "sin_medida"})
                continue
            rayos = rayos_l[0]
            key = id(rayos)
            if key not in veta_cache:
                veta_cache[key] = _unit(_veta(next(s for f, _ft, s, r in esc.cerca(
                    centro, centro) if r is rayos)))
            g = veta_cache[key]
            if abs(_dot(eje, g)) > 0.7:
                filas.append({**fila, "estado": "en_testa"})
                continue
            u = _unit(tuple(g[k] - eje[k] * _dot(g, eje) for k in range(3)))  # veta en el plano
            v = (eje[1] * u[2] - eje[2] * u[1], eje[2] * u[0] - eje[0] * u[2],
                 eje[0] * u[1] - eje[1] * u[0])
            alcance = max(10.0 * d, 150.0)
            testa = canto = None
            for k in range(36):
                a = 2.0 * math.pi * k / 36
                w = tuple(u[m] * math.cos(a) + v[m] * math.sin(a) for m in range(3))
                b = _exterior(rayos, centro, w, alcance, otros)
                if b is None:
                    continue
                if abs(math.cos(a)) >= 0.94:
                    testa = b if testa is None else min(testa, b)
                elif abs(math.cos(a)) <= 0.35:
                    canto = b if canto is None else min(canto, b)
            m = minimos(d, tipo)
            fila.update({"estado": "medido", "testa": None if testa is None else round(testa, 1),
                         "canto": None if canto is None else round(canto, 1), **m})
            filas.append(fila)
    sin_medir = [fid for fid, f in doc.scene.items()
                 if (c := _comp(f, CATALOG)) is not None and c.category == "tornilleria_madera"
                 and not (c.specs or {}).get("llave")]  # el tornillo sin hexágono: no hay insumo
    return {"filas": filas, "tornillos_sin_medir": len(sin_medir)}


def resumen_d7(filas: list[dict]) -> dict:
    med = [f for f in filas if f["estado"] == "medido"]

    def cuenta(clave_t, clave_c):
        return sum(1 for f in med if (f["testa"] is not None and f["testa"] < f[clave_t] - 0.05)
                   or (f["canto"] is not None and f["canto"] < f[clave_c] - 0.05))

    return {"agujeros": len(filas), "medidos": len(med),
            "en_testa": sum(1 for f in filas if f["estado"] == "en_testa"),
            "falla_norma_cargada": cuenta("testa_cargada", "canto_cargado"),
            "falla_norma_descargada": cuenta("testa_descargada", "canto_descargado"),
            "falla_4d_3d": cuenta("testa_4d", "canto_3d")}


# ------------------------------------------------------------------ D8
def d8(doc, pernos) -> dict:
    from apolo.library.borde_agujero import distancia_a_eje

    from apolo.services.calidad_juntas import GIRO

    out = []
    for nombre, j in (doc.joints or {}).items():
        if j.get("type") not in GIRO:
            continue
        o, ax = _v(j.get("origin") or (0, 0, 0)), _unit(_v(j.get("axis") or (0, 0, 1)))
        coax = []
        for p in pernos:
            if not p.get("evaluable") or not p.get("eje"):
                continue
            e = _unit(tuple(p["eje"]["dir"]))
            if abs(abs(_dot(e, ax)) - 1.0) > 1e-3 or distancia_a_eje(
                    tuple(p["eje"]["asiento"]), o, ax) > 1.0:
                continue
            tuercas = [t for t in (p.get("tramos") or []) + (p.get("mas_alla") or [])
                       if t.get("rol") == "tuerca"]
            nombres = [doc.scene[t["fid"]].name for t in tuercas if t["fid"] in doc.scene]
            cruzan = [t.get("nombre") or "" for t in p.get("tramos") or []]
            traba = (len(tuercas) >= 2 or any(_TRABA_RE.search(n) for n in nombres + cruzan
                                              + [p.get("nombre") or ""]))
            estado = ("tornillo de madera" if p.get("madera_screw") else
                      "con traba" if traba else "tuerca simple" if tuercas else "sin tuerca")
            coax.append({"perno": p["fid"], "nombre": p.get("nombre"), "tuercas": nombres,
                         "estado": estado})
        out.append({"junta": nombre, "pernos": coax})
    return {"juntas": out}


# ------------------------------------------------------------------ CLI
def medir(ruta: Path) -> dict:
    from apolo.doc import Document
    from apolo.library.bom import bom_from_scene

    from apolo.services.calidad_pernos import _Escena, insumos_pernos

    doc = Document.from_apolo_bytes(ruta.read_bytes())
    esc = _Escena(doc.scene)
    pernos = insumos_pernos(doc, escena=esc)
    bom = bom_from_scene(doc.scene, doc.default_material())
    r7 = d7(doc, pernos, esc)
    nombre = ruta.name if ruta.parent.name != "rondas" else f"{ruta.parent.parent.name}/{ruta.name}"
    return {"apolo": nombre, "piezas": len(doc.scene), "vertical": doc.default_material(),
            "pernos": len(pernos), "pernos_evaluables": sum(bool(p.get("evaluable"))
                                                            for p in pernos),
            "d1": d1(doc), "d4": d4(doc, bom), "d6": d6(doc),
            "d7": {**r7, "resumen": resumen_d7(r7["filas"])}, "d8": d8(doc, pernos)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("apolos", nargs="+")
    ap.add_argument("--json", help="escribe el detalle aquí")
    a = ap.parse_args(argv)
    todo = []
    for r in a.apolos:
        m = medir(Path(r))
        todo.append(m)
        s7 = m["d7"]["resumen"]
        d6c = [x for x in m["d6"].get("apoyos", []) if x["estado"] in ("sin capacidad",
                                                                      "no alcanza")]
        d8f = [p for j in m["d8"]["juntas"] for p in j["pernos"] if p["estado"] != "con traba"]
        print(f"{m['apolo']}: D1 {len(m['d1']['falla'])} · D4 hoy {len(m['d4']['falla_hoy'])}"
              f" / con D3 {len(m['d4']['falla_con_d3'])} de {m['d4']['filas']} filas · D6 "
              f"{len(d6c)} · D7 {s7['medidos']} medidos: norma {s7['falla_norma_cargada']}"
              f" (descargada {s7['falla_norma_descargada']}), 4d/3d {s7['falla_4d_3d']}, en "
              f"testa {s7['en_testa']} · D8 {len(d8f)} de "
              f"{sum(len(j['pernos']) for j in m['d8']['juntas'])} ejes", flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(todo, ensure_ascii=False, indent=1, default=str),
                                encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
