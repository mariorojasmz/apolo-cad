"""Regla «pandeo de columna» de cualquier bastidor (F3f de puerta-sin-sobrediseno): las columnas
VERTICALES de perfil de catálogo, con la carga que les baja por el grafo de uniones. El cálculo
es de `library/engineering/columna.py` (puro); aquí se decide QUÉ es columna, CUÁNTO carga y
CÓMO se apoya. La llama `structure_rules` (checks y memoria). El llamador sostiene STATE_LOCK.

- **Columna**: pieza de catálogo cortable de un perfil estructural con sección de norma
  (`secciones.py`: tubo rectangular o redondo, ángulo, UPN, IPE), con su eje largo VERTICAL (la
  caja mide su largo de corte), en el grafo de uniones y APOYADA abajo: una unión perno/soldadura
  con una pieza más cercana a tierra en su décimo inferior, o anclada ella misma (`ground`). Lo
  que cuelga de arriba trabaja a tracción: no es columna. Las de rol «pata» son de la regla
  «pandeo de patas» (`report_estructura`); lo que gira (una junta la mueve) no es estructura.
- **Carga axial**: su peso + lo que le llega por `vigas_rules.cargas_que_bajan` (el MISMO
  recorrido de la flecha de vigas: de arriba abajo por niveles, repartido por igual, las vigas
  bajan sus reacciones con la carga útil). Sin vigas que reciban la carga útil, ésta se reparte
  por igual entre las columnas (hipótesis declarada).
- **Apoyos** (K de `columna.py`): base SOLDADA a lo que la sostiene, o anclada → empotrada;
  cabeza libre de desplazarse (K = 2,1). Una base sólo atornillada o apoyada es articulada: sin
  arriostramiento declarado el K no se determina y la columna sale NO EVALUADA (aviso con
  `no_evaluada`), igual que una pieza con rol «columna»/«poste» sin sección de norma: la puerta
  la deja SIN_EVALUAR y se justifica por escrito (`justificadas`, regla y piezas).
- Columnas con los MISMOS números salen en UNA regla que las nombra (como las vigas).
"""

from __future__ import annotations

import re
from collections import defaultdict

from . import columnas_a_medida

G = 9.81
_PERFILES = ("rect_tube", "round_tube", "angle", "channel", "i_beam")
_ZONA_BASE = 0.1      # la unión de la base cae en el décimo inferior del largo
_TOL_MM = 2.0
_ROL_COLUMNA = re.compile(r"^(columnas?|postes?)\b", re.I)
_ROL_PATA = re.compile(r"^\s*pata\b", re.I)  # = `rules_comun._LEG_RE`: la regla de las patas
REGLA = "pandeo de columna"


def _caja(f):
    try:
        b = f.shape.bounding_box()
    except Exception:  # noqa: BLE001
        return None
    return (b.min.X, b.min.Y, b.min.Z), (b.max.X, b.max.Y, b.max.Z)


def _rol(f) -> str:
    from apolo.library.materials import piece_role

    return piece_role(getattr(f, "name", "") or "")


def _vertical(f, caja) -> float | None:
    """El largo de una pieza VERTICAL que la caja mide (su largo de corte, si lo tiene); None si
    no es vertical o va inclinada."""
    lo, hi = caja
    ext = [hi[k] - lo[k] for k in range(3)]
    if max(range(3), key=lambda k: ext[k]) != 2:
        return None
    cut = getattr(f, "cut_length", None)
    if cut and abs(ext[2] - cut) > max(_TOL_MM, 0.02 * cut):
        return None
    return ext[2]


def _seccion(f, catalog):
    from apolo.library.engineering.secciones import seccion_catalogo

    comp = catalog.get(getattr(f, "component", None) or "")
    if comp is None or not comp.cuttable or comp.familia not in _PERFILES:
        return comp, None
    try:
        return comp, seccion_catalogo(comp.familia, comp.params or {})
    except (KeyError, TypeError, ValueError):
        return comp, None


def _base(fid, caja, largo, det, fasteners, anclada: bool) -> tuple[str | None, list[str]]:
    """(«soldada» | «atornillada» | None, lo que la sostiene): las uniones perno/soldadura con
    piezas más cercanas a tierra en su décimo inferior."""
    nivel, cajas = det["nivel"], det["caja"]
    tope = caja[0][2] + _ZONA_BASE * largo
    tipos, quien = set(), []
    for u in fasteners.values():
        a, b, kind = u.get("a"), u.get("b"), u.get("kind", "perno")
        if fid not in (a, b) or kind not in ("perno", "soldadura"):
            continue
        o = b if a == fid else a
        co = cajas(o) if o in det["scene"] else None
        if co is None or nivel.get(o, 1 << 30) >= nivel.get(fid, 0):
            continue
        if co[0][2] <= tope + _TOL_MM:
            tipos.add(kind)
            quien.append(o)
    if anclada:
        return "anclada", quien
    if "soldadura" in tipos:
        return "soldada", quien
    return ("atornillada" if tipos else None), quien


def _giran(doc) -> set[str]:
    return {j.get("child") for j in (doc.joints or {}).values() if j.get("type") != "fija"}


def detectar_columnas(doc, catalog: dict | None = None) -> dict:
    """{evaluables: [{fid, comp, sec, largo, base, sostiene}], no_evaluadas: [{fid, motivo}],
    patas: n (las de la regla de patas), det}: el criterio de la regla, que también usa el
    detector `columnas` de la puerta (`puerta_hechos`)."""
    from apolo.library.catalog import CATALOG

    from .vigas_rules import detectar_vigas

    catalog = catalog if catalog is not None else CATALOG
    out = {"evaluables": [], "no_evaluadas": [], "patas": 0, "det": None}
    det = detectar_vigas(doc, catalog)
    if det is None:
        return out
    out["det"] = det
    giran = _giran(doc)
    anclas = {g.get("feature") for g in (doc.grounds or {}).values()}
    from .vigas_a_medida import de_plantilla

    vertical, plantillas = doc.default_material(), de_plantilla(doc)
    for fid, f in det["scene"].items():
        caja = det["caja"](fid)
        if caja is None:
            continue
        rol = _rol(f)
        largo = _vertical(f, caja)
        if _ROL_PATA.match(rol):  # el criterio de `report_estructura._buckling_checks`
            out["patas"] += int(caja[1][2] - caja[0][2] >= 50.0)
            continue
        if fid not in giran and fid in det["nivel"]:  # D7: la columna a medida
            am = columnas_a_medida.candidata(fid, f, caja, det, catalog, vertical, plantillas)
            if am is not None:
                _a_medida(out, fid, am, caja, det, doc, anclas)
                continue
        comp, sec = _seccion(f, catalog)
        por_rol = bool(_ROL_COLUMNA.match(rol))
        if fid in giran or (sec is None and not por_rol) or (largo is None and not por_rol):
            continue
        if fid not in det["nivel"]:
            continue  # flota: lo dice la sujeción
        if sec is None or largo is None:
            out["no_evaluadas"].append({"fid": fid, "motivo": (
                "sin sección de norma (no es un perfil estructural de catálogo: tubo, ángulo, "
                "UPN o IPE)" if sec is None else "no es vertical o va inclinada")})
            continue
        base, sostiene = _base(fid, caja, largo, det, doc.fasteners, fid in anclas)
        if base is None:
            continue  # cuelga o se apoya sin unión: no trabaja como columna
        if base == "atornillada":
            out["no_evaluadas"].append({"fid": fid, "motivo": (
                "base sólo atornillada (articulada): sin arriostramiento declarado el K de pandeo "
                "no se determina")})
            continue
        out["evaluables"].append({"fid": fid, "comp": comp, "sec": sec, "largo": largo,
                                  "base": base, "sostiene": sostiene})
    return out


def _a_medida(out: dict, fid, am: dict, caja, det, doc, anclas) -> None:
    """La columna a medida (D7): evaluable con su base, o no evaluada con su motivo."""
    if "motivo" in am:
        out["no_evaluadas"].append({"fid": fid, "motivo": am["motivo"]})
        return
    base, sostiene = _base(fid, caja, am["largo"], det, doc.fasteners, fid in anclas)
    if base is None:
        return  # se apoya sin unión: no trabaja como columna
    if base == "atornillada":
        out["no_evaluadas"].append({"fid": fid, "motivo": (
            "base sólo atornillada (articulada): sin arriostramiento declarado el K de pandeo "
            "no se determina")})
        return
    out["evaluables"].append({"fid": fid, "comp": None, "sec": None, "largo": am["largo"],
                              "base": base, "sostiene": sostiene, "a_medida": am})


def _sin_evaluar(doc, fids: list[str], motivo: str) -> dict:
    nombres = [doc.scene[f].name or f for f in fids]
    lista = ", ".join(nombres[:4]) + (f" (+{len(nombres) - 4})" if len(nombres) > 4 else "")
    return {"regla": f"{REGLA} · {nombres[0]}" + (f" y {len(nombres) - 1} más"
                                                  if len(nombres) > 1 else ""),
            "estado": "aviso", "no_evaluada": True, "piezas": list(fids),
            "detalle": f"{lista}: pandeo no evaluado — {motivo}.",
            "recomendacion": "Suelda la base o declara el arriostramiento; o justifica por "
                             "escrito (set_justifications con esta regla y sus piezas) por qué "
                             "no pandea."}


def columna_rules(doc, carga_kg: float | None = None, catalog: dict | None = None) -> list[dict]:
    """Una regla por columna (las de números idénticos, agrupadas) y una por cada motivo de lo
    que no se pudo evaluar. Lista vacía sin columnas: la memoria no cambia."""
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.columna import K_EMPOTRADA_LIBRE, NORMA_K, regla_columna
    from apolo.library.materials import resolve_material, yield_strength, young_modulus

    from .vigas_rules import _masa_kg, cargas_que_bajan

    catalog = catalog if catalog is not None else CATALOG
    cols = detectar_columnas(doc, catalog)
    reglas: list[dict] = []
    por_motivo: dict = defaultdict(list)
    for x in cols["no_evaluadas"]:
        por_motivo[x["motivo"]].append(x["fid"])
    if cols["evaluables"]:
        bajan = (cargas_que_bajan(doc, carga_kg, catalog, cols["det"])
                 or {"recibido": {}, "util_en_vigas": False})
        n_col = len(cols["evaluables"])
        util_n = (float(carga_kg) * G / n_col) if carga_kg and not bajan["util_en_vigas"] else 0.0
        grupos: dict = {}
        for c in cols["evaluables"]:
            f = doc.scene[c["fid"]]
            propio = _masa_kg(f, catalog) * G
            recibido = sum(n for _, n in bajan["recibido"].get(c["fid"], ()))
            carga = propio + recibido + util_n
            material = resolve_material(f, catalog)
            sostiene = ", ".join(doc.scene[o].name or o for o in c["sostiene"][:2]) or "tierra"
            apoyos = (f"base {c['base']} ({sostiene}), cabeza libre de desplazarse: "
                      f"{NORMA_K}, caso (e)")
            hip = [
                "Carga axial = su peso + lo que le baja por el grafo de uniones (el recorrido de "
                "la flecha de vigas: repartido por igual entre los apoyos de cada pieza; las "
                "vigas bajan sus reacciones).",
                "Cabeza libre de desplazarse (K = 2,1) aunque se una a otra pieza: sin saber si "
                "el conjunto está arriostrado, suponerlo sería optimista.",
                "Sin excentricidad ni carga lateral: la flexión de la columna no se suma.",
            ]
            if util_n:
                hip.append(f"Carga útil {carga_kg:g} kg repartida por igual entre las {n_col} "
                           "columnas: ninguna viga la recibe.")
            resumen = {"peso propio": f"{propio:.0f} N", "lo que le baja": f"{recibido:.0f} N"}
            if util_n:
                resumen["carga útil"] = f"{util_n:.0f} N"
            if c.get("a_medida"):  # D7: sección medida, criterio de su material
                ref = c["a_medida"]["sec"]["forma"]
                regla = columnas_a_medida.regla(f.name or c["fid"], c["a_medida"],
                                                k=K_EMPOTRADA_LIBRE, apoyos=apoyos, carga=carga,
                                                resumen=resumen, hip=hip)
            else:
                ref = c["comp"].ref
                regla = regla_columna(
                    f.name or c["fid"], perfil=ref, area_mm2=c["sec"].area_mm2,
                    i_min_mm4=c["sec"].i_min_mm4, largo_mm=c["largo"], k=K_EMPOTRADA_LIBRE,
                    apoyos=apoyos, carga_n=carga, material=material,
                    e_mpa=young_modulus(material), fy_mpa=yield_strength(material),
                    fuente_seccion=c["sec"].norma, resumen_carga=resumen, hipotesis=hip)
            regla["piezas"] = [c["fid"]]
            clave = (ref, round(c["largo"]), round(carga), regla["estado"])
            grupos.setdefault(clave, []).append(regla)
        for lista in grupos.values():
            r = lista[0]
            if len(lista) > 1:
                nombre = r["regla"].split(" · ", 1)[1]
                etiqueta = f"{nombre} y {len(lista) - 1} igual(es)"
                r["regla"] = f"{REGLA} · {etiqueta}"
                r["detalle"] = r["detalle"].replace(nombre, etiqueta, 1)
                r["calc"]["titulo"] = f"Pandeo de la columna {etiqueta}"
                r["piezas"] = [p for x in lista for p in x["piezas"]]
            reglas.append(r)
    for motivo, fids in por_motivo.items():
        reglas.append(_sin_evaluar(doc, fids, motivo))
    return reglas
