"""Insumos del control de AGARRE (plan puerta-de-publicacion, D3): por cada perno del documento,
lo que su eje atraviesa de verdad. El control puro es `library/calidad/agarre.py`; el formato
del insumo, su docstring. El llamador sostiene STATE_LOCK (sólo se leen shapes).

Qué es un perno: tornillería de catálogo (`pernos`, `tornilleria` salvo el remache ciego, el
tornillo para madera de cabeza hexagonal), la de un `join_bolted` y la modelada a medida que
`lints.es_nombre_de_tornilleria` reconoce (un eje «roscado p/ perno» no lo es). Se mide por
SÓLIDO: un compuesto con diez pernos da diez insumos.

Cómo se mide:
- **Eje y cabeza** de la GEOMETRÍA (`fijadores_geom`: hexágono de la cabeza; Allen o cabeza
  cilíndrica: el cilindro coaxial más grueso), nunca del nombre. `t` = 0 en la cara de asiento
  de la cabeza; el largo es lo que el sólido llega más allá. Sin cabeza reconocible: no
  evaluable (SIN_EVALUAR, nunca OK).
- **Rayos** paralelos al eje (`kernel/rayo.Rayos`): seis a un radio entre el vástago y la
  cabeza (cruzan la pared alrededor de un taladro de paso, la tuerca y lo que el perno aprieta)
  y cuatro a un radio MENOR que el del vástago (sólo tocan material donde el agujero es más chico
  que el perno: una rosca —machuelo, la madera con piloto—). Una pieza con «roscado» en el
  nombre (el eje del tensor, modelado con agujero de paso) cuenta como rosca entera.
- **Esperadas**: si lo insertó un `join_bolted`, las dos piezas de su fijador `jb_{cmd}`.
"""

from __future__ import annotations

import math
import re

_TUERCA_RE = re.compile(r"\b(tuercas?|nuts?)\b", re.I)
_ROSCADO_RE = re.compile(r"\b(roscad[oa]s?|threaded)\b", re.I)
_N_AFUERA, _N_ADENTRO = 6, 4
_ALCANCE_MIN_MM = 60.0  # lo que se mira pasada la punta (o 4·d)


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b, k=1.0):
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _base_perp(eje):
    otro = (1.0, 0.0, 0.0) if abs(eje[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _unit(_cross(eje, otro))
    return u, _cross(eje, u)


def tipo_de_tornilleria(feat, catalog) -> str | None:
    """'perno' | 'madera' | None (no es un perno que el control mida)."""
    from apolo.library.lints import es_nombre_de_tornilleria

    comp = catalog.get(getattr(feat, "component", None) or "")
    if comp is not None:
        specs = comp.specs or {}
        if comp.category in ("pernos", "tornilleria"):
            return None if specs.get("herramienta") == "remachadora" else "perno"
        if comp.category == "tornilleria_madera":
            return "madera" if specs.get("llave") else None
        return None
    nombre = getattr(feat, "name", "") or ""
    if _TUERCA_RE.search(nombre) or not es_nombre_de_tornilleria(nombre):
        return None
    return "perno"


def _cilindros(solid) -> list[dict]:
    """Caras cilíndricas: {r, p (punto del eje), eje, vs (vértices)}."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder

    out = []
    for f in solid.faces():
        try:
            ad = BRepAdaptor_Surface(f.wrapped)
            if ad.GetType() != GeomAbs_Cylinder:
                continue
            c = ad.Cylinder()
            loc, dr = c.Axis().Location(), c.Axis().Direction()
            out.append({"r": c.Radius(), "p": (loc.X(), loc.Y(), loc.Z()),
                        "eje": _unit((dr.X(), dr.Y(), dr.Z())),
                        "vs": [(v.X, v.Y, v.Z) for v in f.vertices()]})
        except Exception:  # noqa: BLE001
            continue
    return out


def _coaxiales(cils, punto, eje) -> list[dict]:
    out = []
    for c in cils:
        if abs(abs(_dot(c["eje"], eje)) - 1.0) > 1e-3:
            continue
        w = _sub(c["p"], punto)
        perp = _sub(w, (eje[0] * _dot(w, eje), eje[1] * _dot(w, eje), eje[2] * _dot(w, eje)))
        if math.sqrt(_dot(perp, perp)) < 0.3:
            out.append(c)
    return out


def geometria_perno(solid) -> dict | None:
    """{asiento, dir (hacia la punta), cabeza, d, s (Ø o entrecaras de cabeza), largo,
    tuercas: [(t0, t1)]} o None si no se reconoce una cabeza."""
    from apolo.library.fijadores_geom import reconocer_fijadores

    fjs = reconocer_fijadores(solid)
    cils = _cilindros(solid)
    cab = next((f for f in fjs if f.tipo in ("cabeza_hex", "allen")), None)
    if cab is not None:
        dir_ = (-cab.eje[0], -cab.eje[1], -cab.eje[2])
        coax = _coaxiales(cils, cab.base, dir_)
        if cab.tipo == "cabeza_hex":
            asiento, s, cabeza = cab.base, cab.s, "hex"
        else:  # Allen: `base` es la cara de ARRIBA; la cabeza es el cilindro coaxial más grueso
            if not coax:
                return None
            gordo = max(coax, key=lambda c: c["r"])
            alto = max(_dot(_sub(v, cab.base), dir_) for v in gordo["vs"])
            asiento, s, cabeza = _add(cab.base, dir_, alto), 2.0 * gordo["r"], "allen"
        finos = [c for c in coax if c["r"] < s / 2.0 - 0.3]
        if not finos:
            return None
        d = 2.0 * min(c["r"] for c in finos)
    else:  # sin hexágono: cabeza cilíndrica = el cilindro más grueso, vástago = uno coaxial fino
        if not cils:
            return None
        gordo = max(cils, key=lambda c: c["r"])
        coax = _coaxiales(cils, gordo["p"], gordo["eje"])
        finos = [c for c in coax if c["r"] < gordo["r"] - 0.3]
        if not finos:
            return None
        fino = min(finos, key=lambda c: c["r"])
        e = gordo["eje"]
        tg = [_dot(_sub(v, gordo["p"]), e) for v in gordo["vs"]]
        tf = [_dot(_sub(v, gordo["p"]), e) for v in fino["vs"]]
        if sum(tf) / len(tf) > sum(tg) / len(tg):
            dir_, asiento = e, _add(gordo["p"], e, max(tg))
        else:
            dir_, asiento = (-e[0], -e[1], -e[2]), _add(gordo["p"], e, min(tg))
        d, s, cabeza = 2.0 * fino["r"], 2.0 * gordo["r"], "allen"
    largo = max(_dot(_sub((v.X, v.Y, v.Z), asiento), dir_) for v in solid.vertices())
    tuercas = []
    for f in fjs:
        if f.tipo == "tuerca" and abs(abs(_dot(f.eje, dir_)) - 1.0) < 1e-3:
            t = _dot(_sub(f.base, asiento), dir_)
            tuercas.append((min(t, t + f.altura * _dot(f.eje, dir_)),
                            max(t, t + f.altura * _dot(f.eje, dir_))))
    return {"asiento": asiento, "dir": dir_, "cabeza": cabeza, "d": d, "s": s,
            "largo": largo, "tuercas": tuercas}


def _metrica(d: float) -> tuple[float, float]:
    """(Ø nominal, paso grueso) más cercanos a `d` medido."""
    from apolo.library.engineering.threads import COARSE

    mejor = min(COARSE, key=lambda m: abs(float(m.lstrip("M")) - d))
    dn = float(mejor.lstrip("M"))
    if abs(dn - d) <= 0.35:
        return dn, COARSE[mejor][0]
    return d, 0.125 * d


def _union(tramos: list) -> list[list[float]]:
    out: list[list[float]] = []
    for a, b in sorted(tramos):
        if out and a <= out[-1][1] + 0.05:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


class _Escena:
    """Sólidos de la escena con su caja y su `Rayos` (cargado una vez por corrida)."""

    def __init__(self, scene) -> None:
        self.solidos = []
        for fid, feat in scene.items():
            if getattr(feat, "is_guide", False) or feat.shape is None:
                continue
            try:
                sols = list(feat.shape.solids())
            except Exception:  # noqa: BLE001
                continue
            for s in sols:
                try:
                    bb = s.bounding_box()
                except Exception:  # noqa: BLE001
                    continue
                self.solidos.append((fid, feat, s, (bb.min.X, bb.min.Y, bb.min.Z),
                                     (bb.max.X, bb.max.Y, bb.max.Z), None))

    def cerca(self, lo, hi):
        for i, (fid, feat, s, mn, mx, rayos) in enumerate(self.solidos):
            if all(mn[k] <= hi[k] and mx[k] >= lo[k] for k in range(3)):
                if rayos is None:
                    from apolo.kernel.rayo import Rayos

                    rayos = Rayos(s)
                    self.solidos[i] = (fid, feat, s, mn, mx, rayos)
                yield fid, feat, s, rayos


def _medir(esc: _Escena, solid, g: dict, alcance: float) -> dict:
    """{fid: {"afuera": [[a, b]], "adentro": [[a, b]], "feat"}} a lo largo del eje."""
    from apolo.library.engineering.bolts import CLEARANCE_HOLE_MM

    d, s = g["d"], g["s"]
    dn, paso = _metrica(d)
    paso_libre = CLEARANCE_HOLE_MM.get(f"M{dn:g}", 1.1 * d) / 2.0
    r_afuera = max((d / 2.0 + s / 2.0) / 2.0, paso_libre + 0.4)
    r_adentro = d / 2.0 - 0.3 * paso
    u, v = _base_perp(g["dir"])
    t1 = g["largo"] + alcance
    a, b = _add(g["asiento"], g["dir"], -0.5), _add(g["asiento"], g["dir"], t1)
    lo = tuple(min(a[k], b[k]) - r_afuera for k in range(3))
    hi = tuple(max(a[k], b[k]) + r_afuera for k in range(3))
    out: dict = {}
    for fid, feat, otro, rayos in esc.cerca(lo, hi):
        if otro.wrapped.IsSame(solid.wrapped):  # el propio perno (mismo TShape y ubicación)
            continue
        reg = {"afuera": [], "adentro": [], "feat": feat}
        for radio, n, clave in ((r_afuera, _N_AFUERA, "afuera"), (r_adentro, _N_ADENTRO, "adentro")):
            for k in range(n):
                ang = 2.0 * math.pi * k / n
                off = _add(_add((0.0, 0.0, 0.0), u, radio * math.cos(ang)), v, radio * math.sin(ang))
                reg[clave] += rayos.tramos(_add(g["asiento"], off), g["dir"], -0.5, t1)
        if reg["afuera"] or reg["adentro"]:
            prev = out.setdefault(fid, {"afuera": [], "adentro": [], "feat": feat})
            prev["afuera"] += reg["afuera"]
            prev["adentro"] += reg["adentro"]
    return out


def insumo_perno(esc: _Escena, fid: str, feat, solid, tipo: str, esperadas: list[str],
                 catalog) -> dict:
    """El insumo de agarre de UN sólido-perno (formato en `library/calidad/agarre.py`)."""
    from apolo.library.materials import resolve_material

    base = {"fid": fid, "nombre": getattr(feat, "name", fid), "ref": feat.component,
            "madera_screw": tipo == "madera", "esperadas": esperadas}
    try:
        g = geometria_perno(solid)
    except Exception:  # noqa: BLE001 — geometría rara: no evaluable, nunca rompe la puerta
        g = None
    if g is None:
        return {**base, "evaluable": False, "cabeza": "hex",
                "motivo": "sin cabeza ni vástago reconocibles en la geometría"}
    dn, paso = _metrica(g["d"])
    alcance = max(4.0 * dn, _ALCANCE_MIN_MM)
    medidas = _medir(esc, solid, g, alcance)
    tramos, mas_alla = [], []
    largo = g["largo"]
    for ofid, m in medidas.items():
        ofeat = m["feat"]
        comp = catalog.get(getattr(ofeat, "component", None) or "")
        es_tuerca = ((comp is not None and comp.category == "tuercas")
                     or bool(_TUERCA_RE.search(getattr(ofeat, "name", "") or "")))
        adentro = _union(m["adentro"])
        # rosca declarada en el NOMBRE (como los fits): el eje «roscado p/ perno» del tensor se
        # modela con agujero de paso, pero el perno enrosca en él
        roscada = bool(_ROSCADO_RE.search(getattr(ofeat, "name", "") or ""))
        for a, b in _union(m["afuera"] + m["adentro"]):
            if a > largo + 0.05:
                mas_alla.append({"fid": ofid, "t0": round(a, 2),
                                 "rol": "tuerca" if es_tuerca else "pieza"})
                continue
            rosca = ([(a, b)] if roscada and not es_tuerca else
                     [(x, y) for x, y in adentro if x < b + 0.05 and y > a - 0.05])
            tramos.append({
                "fid": ofid, "nombre": getattr(ofeat, "name", ofid), "t0": round(a, 2),
                "t1": round(b, 2), "rol": "tuerca" if es_tuerca else "pieza",
                "material": resolve_material(ofeat, catalog),
                "rosca": [(round(x, 2), round(y, 2)) for x, y in rosca],
            })
    for a, b in g["tuercas"]:  # tuerca fundida en el mismo sólido del perno
        tramos.append({"fid": fid, "nombre": base["nombre"], "t0": round(a, 2),
                       "t1": round(b, 2), "rol": "tuerca", "material": "acero", "rosca": []})
    tramos.sort(key=lambda t: t["t0"])
    mas_alla.sort(key=lambda m: m["t0"])
    return {**base, "evaluable": True, "motivo": "", "cabeza": g["cabeza"], "d": dn,
            "paso": paso, "largo": round(largo, 2), "tramos": tramos, "mas_alla": mas_alla,
            "eje": {"asiento": [round(x, 3) for x in g["asiento"]],
                    "dir": [round(x, 6) for x in g["dir"]]}}


def esperadas_por_union(doc) -> dict[str, list[str]]:
    """{command_id de un join_bolted: [a, b]} de su fijador declarado."""
    tipo = {c["id"]: c.get("type") for c in doc.commands}
    out = {}
    for f in doc.fasteners.values():
        cid = f.get("command_id")
        if tipo.get(cid) == "join_bolted":
            out[cid] = [x for x in (f.get("a"), f.get("b")) if isinstance(x, str)]
    return out


def insumos_pernos(doc, ids: set[str] | None = None,
                   escena: _Escena | None = None) -> list[dict]:
    """Los insumos de agarre de todos los pernos del documento (o de los `ids`). `escena` (la
    misma `_Escena` del documento) se comparte con quien mida después sobre esos pernos (los
    bordes de sus agujeros): sus `Rayos` se cargan una vez."""
    from apolo.library.catalog import CATALOG

    esc = escena if escena is not None else _Escena(doc.scene)
    esperadas = esperadas_por_union(doc)
    out = []
    for fid, feat in doc.scene.items():
        if ids is not None and fid not in ids:
            continue
        if getattr(feat, "is_guide", False) or feat.shape is None:
            continue
        tipo = tipo_de_tornilleria(feat, CATALOG)
        if tipo is None:
            continue
        try:
            solidos = list(feat.shape.solids())
        except Exception:  # noqa: BLE001
            solidos = []
        esp = esperadas.get(getattr(feat, "command_id", None), [])
        for s in solidos:
            out.append(insumo_perno(esc, fid, feat, s, tipo, esp, CATALOG))
    return out
