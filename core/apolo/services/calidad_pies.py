"""Los PIES NIVELADORES del documento y lo que rodea a su vástago (plan pie-nivelador, D1–D4 y D8):
el insumo de `apoyo.nivelador` (`library/calidad/pie_nivelador.py`, donde están el formato y el
criterio) y su detector en `puerta_hechos`. El llamador sostiene STATE_LOCK.

**Qué es un pie (D1, con la F0)**: una ref de la categoría `pies_niveladores` (también el de base
de anclaje, que sólo así se reconoce), o una pieza a medida con ROL de pie (`apoyos.clase_de_rol`)
cuya geometría lo confirma: un vástago cilíndrico CONVEXO con una base coaxial de Ø mayor en un
extremo (sin el rol, las garruchas y los caladrillos de una pata —cilindros cóncavos— pasaban la
prueba). El ROL es de pie NIVELADOR: «Pie…» o «Nivelador…» que nombra su regulación (nivelador,
rosca, M10, husillo, vástago…); un «Pie (1)» de una mesa de madera, con o sin espiga, no es un pie
nivelador y no se mira. Vale anclado o no. Lo candidato que no se reconoce sale en
`no_reconocidos` (SIN_EVALUAR justificable).

**Cómo se mide**: rayos paralelos al eje (`kernel/rayo.Rayos`, la `_Escena` del agarre), con `t` = 0
en la cara de apoyo de la base y hacia la punta: en el eje y a 0,25·d (material en el eje del
vástago, lo que la punta tiene encima), a un radio MENOR que el del vástago (la rosca: material
donde el agujero es más chico que el vástago, como `calidad_pernos`), a uno entre el vástago y la
tuerca (tuercas, placas y tapas que lo rodean) y cerca del borde de la base. La rosca MEDIDA manda
(es el anillo de D8); sin solape, una pieza con «roscado» en el nombre o una tuerca alta («DIN
6334», «tuerca alta», «manguito roscado», o m ≥ 1,5·d) cuenta como rosca entera. Lo que BAJA es lo
que la base (con su hexágono) sube hasta tocar la pila, menos lo que ocupa la tuerca de bloqueo
del propio pie, o lo que la punta sube hasta lo que tiene encima.
La tuerca de bloqueo incluida de un pie de catálogo se lee de su ficha (`tuerca_incluida`,
`tuerca_m`), no de la geometría (F1: dos hexágonos coaxiales en un sólido no se reconocen); el
parche DIN 267-28, de la nota de una unión del pie.

La diagonal (lo que pide el piso, DIN 18202) es la mayor distancia entre pies reconocidos; con uno
solo, la diagonal en planta de todo el modelo.
"""

from __future__ import annotations

import math
import re

from .calidad_pernos import (
    _ROSCADO_RE,
    _add,
    _base_perp,
    _dot,
    _Escena,
    _es_tuerca,
    _metrica,
    _sub,
    _union,
    _unit,
    es_autoblocante,
)

_ALTA_RE = re.compile(r"\bDIN\s*6334\b|\btuercas?\s+altas?\b|\bmanguitos?\s+roscad", re.I)
_CONTRA_RE = re.compile(r"\bcontratuercas?\b", re.I)
#: un pie con rol que NOMBRA su regulación (si no se reconoce, se dice; si no la nombra, no es pie)
_REGULA_RE = re.compile(r"nivel|regulab|ajustab|rosca|husillo|esp[aá]rrago|v[aá]stago|"
                        r"\bM\d{1,2}\b|M\d{1,2}\s*[x×]", re.I)
_PARCHE_RE = re.compile(r"267[\s-]*28|parche|microencapsul|nylok|precote|fija\s*roscas|"
                        r"fijador\s+de\s+roscas|traba\s*roscas|loctite", re.I)
_ALCANCE_MM = 200.0      # lo que se mira pasada la punta
_COAX_MM = 0.3
_N_AFUERA, _N_ADENTRO, _N_PUNTA, _N_BASE = 6, 4, 4, 8


def _cilindros_convexos(solid) -> list[dict]:
    """Caras cilíndricas con su convexidad: {r, p, eje, vs, convexo}."""
    from build123d import GeomType
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    out = []
    for f in solid.faces():
        try:
            if f.geom_type != GeomType.CYLINDER:
                continue
            c = BRepAdaptor_Surface(f.wrapped).Cylinder()
            loc, dr = c.Axis().Location(), c.Axis().Direction()
            p, e = (loc.X(), loc.Y(), loc.Z()), _unit((dr.X(), dr.Y(), dr.Z()))
            q = f.position_at(0.5, 0.5)
            n = f.normal_at(q)
            w = _sub((q.X, q.Y, q.Z), p)
            radial = _sub(w, tuple(e[k] * _dot(w, e) for k in range(3)))
            out.append({"r": c.Radius(), "p": p, "eje": e, "convexo":
                        _dot(radial, (n.X, n.Y, n.Z)) > 0,
                        "vs": [(v.X, v.Y, v.Z) for v in f.vertices()]})
        except Exception:  # noqa: BLE001
            continue
    return out


def _coaxial(a: dict, b: dict) -> bool:
    if abs(abs(_dot(a["eje"], b["eje"])) - 1.0) > 1e-3:
        return False
    w = _sub(b["p"], a["p"])
    perp = _sub(w, tuple(a["eje"][k] * _dot(w, a["eje"]) for k in range(3)))
    return math.sqrt(_dot(perp, perp)) < _COAX_MM


def geometria_pie(shape, catalogo: bool) -> dict | None:
    """{origen (eje en la cara de apoyo), dir (hacia la punta), d_medido, vastago [t0, t1],
    r_base} o None si no hay vástago con base. De catálogo basta el vástago (el cilindro convexo
    más fino: la base de anclaje es una placa); a medida, la base coaxial de Ø mayor en un
    extremo lo confirma."""
    solidos = list(shape.solids())
    cils = [c for s in solidos for c in _cilindros_convexos(s) if c["convexo"] and c["vs"]]
    verts = [(v.X, v.Y, v.Z) for s in solidos for v in s.vertices()]
    for c in sorted(cils, key=lambda c: c["r"]):
        e = c["eje"]
        # el vástago entero: las caras del mismo cilindro que una tuerca fundida parte en dos
        mismo = [o for o in cils if abs(o["r"] - c["r"]) < 0.01 and _coaxial(c, o)]
        tv = [_dot(_sub(v, c["p"]), e) for o in mismo for v in o["vs"]]
        s0, s1 = min(tv), max(tv)
        bases = []
        for o in cils:
            if o["r"] <= c["r"] + 2.0 or not _coaxial(c, o):
                continue
            to = [_dot(_sub(v, c["p"]), e) for v in o["vs"]]
            if max(to) <= s0 + 1.0:
                bases.append((o["r"], -1))
            elif min(to) >= s1 - 1.0:
                bases.append((o["r"], 1))
        lados = {lado for _r, lado in bases}
        if not catalogo and len(lados) != 1:
            continue
        ts = [_dot(_sub(v, c["p"]), e) for v in verts]
        t_min, t_max = min(ts), max(ts)
        abajo = (-1 in lados) if lados else (s0 - t_min > t_max - s1)
        dir_ = e if abajo else (-e[0], -e[1], -e[2])
        origen = _add(c["p"], e, t_min if abajo else t_max)
        largo = t_max - t_min
        v0, v1 = ((s0 - t_min, s1 - t_min) if abajo else (t_max - s1, t_max - s0))
        return {"origen": origen, "dir": dir_, "d_medido": 2.0 * c["r"], "vastago": [v0, v1],
                "punta": largo, "r_base": max([r for r, _l in bases], default=None)}
    return None


def _anillo(origen, dir_, radio: float, n: int):
    u, v = _base_perp(dir_)
    if radio <= 0:
        return [origen]
    return [_add(_add(origen, u, radio * math.cos(2 * math.pi * k / n)), v,
                 radio * math.sin(2 * math.pi * k / n)) for k in range(n)]


def radio_afuera(d: float) -> float:
    """Entre el vástago y la cara plana de su tuerca (el de `calidad_pernos._medir`): cruza la
    tuerca, la placa de paso y la tapa que lo rodean."""
    from apolo.library.engineering.bolts import CLEARANCE_HOLE_MM, HEX_NUT_MM

    s = HEX_NUT_MM.get(f"M{d:g}", (1.6 * d, 0.0))[0]
    return max((d / 2.0 + s / 2.0) / 2.0, CLEARANCE_HOLE_MM.get(f"M{d:g}", 1.1 * d) / 2.0 + 0.4)


def _rayos(esc: _Escena, g: dict, radios: dict, t1: float) -> dict:
    """{fid: {"feat", clave: [[(a, b)] por rayo]}} de los sólidos cerca del eje (el pie también,
    con su fid)."""
    rmax = max(r for r, _n in radios.values())
    a, b = _add(g["origen"], g["dir"], -1.0), _add(g["origen"], g["dir"], t1)
    lo = tuple(min(a[k], b[k]) - rmax for k in range(3))
    hi = tuple(max(a[k], b[k]) + rmax for k in range(3))
    out: dict = {}
    for fid, feat, _solido, rayos in esc.cerca(lo, hi):
        reg = out.setdefault(fid, {"feat": feat, **{k: [[] for _ in range(n)]
                                                    for k, (_r, n) in radios.items()}})
        for clave, (radio, n) in radios.items():
            for k, o in enumerate(_anillo(g["origen"], g["dir"], radio, n)):
                reg[clave][k] += rayos.tramos(o, g["dir"], -1.0, t1)
    return out


def _juntar(por_rayo: list) -> list[list[float]]:
    return _union([tuple(t) for r in por_rayo for t in r])


def _tramos_maquina(reg: dict, fid: str, d: float, catalog) -> list[dict]:
    from apolo.library.materials import resolve_material

    feat = reg["feat"]
    nombre = getattr(feat, "name", fid) or fid
    tuerca = _es_tuerca(feat, catalog) or bool(_CONTRA_RE.search(nombre))
    por_nombre = bool(_ALTA_RE.search(nombre)) or (not tuerca and bool(_ROSCADO_RE.search(nombre)))
    adentro, eje = _juntar(reg["adentro"]), _juntar(reg["eje"] + reg["punta"])
    out = []
    for a, b in _union([tuple(t) for t in _juntar(reg["afuera"]) + adentro + eje]):
        # rosca entera: «roscado», la tuerca alta por su nombre (DIN 6334) o por su altura
        entera = por_nombre and (not tuerca or (b - a) >= 1.5 * d - 0.05) or (
            tuerca and (b - a) >= 1.5 * d - 0.05)
        # la rosca MEDIDA (el anillo de D8) manda; sin solape, la declarada por el nombre o la altura
        medida = [(max(x, a), min(y, b)) for x, y in adentro if x < b + 0.05 and y > a - 0.05]
        rosca = medida or ([(a, b)] if entera else [])
        out.append({"fid": fid, "nombre": nombre, "rol": "tuerca" if tuerca else "pieza",
                    "material": resolve_material(feat, catalog), "t0": round(a, 2),
                    "t1": round(b, 2), "rosca": [[round(x, 2), round(y, 2)] for x, y in rosca],
                    "rosca_medida": bool(medida),
                    "en_eje": [[round(x, 2), round(y, 2)] for x, y in eje
                               if x < b + 0.05 and y > a - 0.05],
                    **({"autoblocante": es_autoblocante(feat, catalog)} if tuerca else {})})
    return out


def _cuerpo_y_fundidas(propios: dict, punta: float) -> tuple[list[float], list[list[float]]]:
    """(techo de la base por rayo del anillo exterior y del de la base, tuercas fundidas): lo
    del propio pie FUERA del vástago es la base (desde t ≈ 0) y, separado de ella, su tuerca."""
    techos, fundidas = [], []
    for clave in ("afuera", "base"):
        for rayo in propios.get(clave) or []:
            tr = _union([tuple(t) for t in rayo])
            base = [t for t in tr if t[0] <= 1.0]
            techo = base[0][1] if base else 0.0
            techos.append(techo)
            if clave == "afuera":
                fundidas += [t for t in tr if t[0] > techo + 0.5 and t[0] < punta]
    return techos, _union([tuple(t) for t in fundidas])


def _baja(regs: dict, propios: dict, punta: float, fundidas) -> tuple[float | None, str, bool]:
    """(lo que el pie puede entrar, qué lo limita, abierta: nada en el alcance)."""
    mejor, limita = None, ""
    for clave in ("afuera", "base"):
        for k, rayo in enumerate(propios.get(clave) or []):
            tr = _union([tuple(t) for t in rayo])
            base = [t for t in tr if t[0] <= 1.0]
            techo = base[0][1] if base else 0.0
            for fid, reg in regs.items():
                for a, b in _union([tuple(t) for t in reg[clave][k]]):
                    if b <= techo + 0.05 or a < techo - 0.5:
                        continue
                    # la tuerca de bloqueo del pie va entre la base y lo que la para
                    fund = sum(y - x for x, y in fundidas if y <= a + 0.5) if clave == "afuera" \
                        else 0.0
                    gap = max(0.0, a - techo - fund)
                    if mejor is None or gap < mejor:
                        mejor, limita = gap, f"la base toca {reg['feat'].name} ({fid})"
    for fid, reg in regs.items():
        for a, _b in _juntar(reg["eje"] + reg["punta"]):
            if a >= punta - 0.5 and (mejor is None or a - punta < mejor):
                mejor, limita = max(0.0, a - punta), f"la punta toca {reg['feat'].name} ({fid})"
    if mejor is None:
        return _ALCANCE_MM, f"nada lo limita en {_ALCANCE_MM:g} mm", True
    return mejor, limita, False


def _ficha(comp) -> dict:
    return {**(getattr(comp, "params", None) or {}), **(comp.specs or {})} if comp else {}


def _uniones(doc, fid: str):
    """[(unión, el otro id)] de las uniones declaradas del pie."""
    for f in doc.fasteners.values():
        ids = [x for k in ("a", "b") for x in (f.get(k) if isinstance(f.get(k), list)
                                                else [f.get(k)])]
        if fid in ids:
            yield f, next((x for x in ids if x != fid), None)


def _parche(doc, fid: str) -> str | None:
    return next((str(f.get("nota")) for f, _o in _uniones(doc, fid)
                 if _PARCHE_RE.search(str(f.get("nota") or ""))), None)


def _base_soldada(doc, fid: str, comp) -> str | None:
    """El nombre de lo que la base del pie tiene SOLDADO (el disco a la placa de piso tras
    nivelar: el vástago, fijo al disco, ya no gira); None si su base es articulada."""
    if comp is not None and (comp.specs or {}).get("base") == "articulada":
        return None
    for f, otro in _uniones(doc, fid):
        if f.get("kind") == "soldadura" and otro in doc.scene:
            return f"{doc.scene[otro].name} ({otro})"
    return None


def medir_pie(doc, esc: _Escena, fid: str, feat, comp, catalog) -> dict | None:
    """El insumo de UN pie (formato de `pie_nivelador`) o None si la geometría no lo confirma."""
    g = geometria_pie(feat.shape, comp is not None)
    if g is None:
        return None
    d, paso = _metrica(g["d_medido"])
    v0, punta = g["vastago"][0], g["punta"]
    r_afuera = radio_afuera(d)
    r_base = 0.9 * g["r_base"] if g.get("r_base") else r_afuera
    radios = {"eje": (0.0, 1), "punta": (0.25 * d, _N_PUNTA),
              "adentro": (d / 2.0 - 0.3 * paso, _N_ADENTRO), "afuera": (r_afuera, _N_AFUERA),
              "base": (max(r_base, r_afuera), _N_BASE)}
    regs = _rayos(esc, g, radios, punta + _ALCANCE_MM)
    propios = regs.pop(fid, {})
    techos, fundidas = _cuerpo_y_fundidas(propios, punta)
    tramos = [t for ofid, reg in regs.items() for t in _tramos_maquina(reg, ofid, d, catalog)]
    tramos = [t for t in tramos if t["t1"] > min(techos or [0.0]) - 0.5 and t["t0"] < punta + 0.5]
    baja, limita, abierta = _baja(regs, propios, punta, fundidas)
    s = _ficha(comp)
    ficha = ({"tuerca": s.get("tuerca"), "m": s.get("tuerca_m"), "sw": s.get("tuerca_sw")}
             if s.get("tuerca_incluida") else None)
    return {"id": fid, "nombre": getattr(feat, "name", fid), "ref": getattr(feat, "component", None),
            "por": "catalogo" if comp is not None else "geometria", "d": d, "paso": paso,
            "pos": [round(x, 2) for x in g["origen"]], "dir": [round(x, 4) for x in g["dir"]],
            "vastago": [round(v0, 2), round(punta, 2)],
            "cuerpo_mm": round(max(techos or [0.0]), 2), "tramos": sorted(tramos,
                                                                         key=lambda t: t["t0"]),
            "fundidas": [[round(a, 2), round(b, 2)] for a, b in fundidas],
            "tuerca_ficha": ficha, "parche": _parche(doc, fid),
            "base_soldada": _base_soldada(doc, fid, comp),
            "baja_mm": round(baja, 2), "baja_limita": limita, "baja_abierta": abierta}


def _diagonal(doc, pies: list[dict]) -> float | None:
    def plano(p, up):
        return _sub(p, tuple(up[k] * _dot(p, up) for k in range(3)))

    up = pies[0]["dir"] if pies else (0.0, 0.0, 1.0)
    if len(pies) >= 2:
        pts = [plano(p["pos"], up) for p in pies]
        return max(math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:])
    try:  # un solo pie: la diagonal en planta del modelo entero
        cajas = [f.shape.bounding_box() for f in doc.scene.values()
                 if f.shape is not None and not getattr(f, "is_guide", False)]
        lo = plano((min(b.min.X for b in cajas), min(b.min.Y for b in cajas),
                    min(b.min.Z for b in cajas)), up)
        hi = plano((max(b.max.X for b in cajas), max(b.max.Y for b in cajas),
                    max(b.max.Z for b in cajas)), up)
        return math.dist(lo, hi) or None
    except Exception:  # noqa: BLE001 — sin cajas: lo dice el ítem
        return None


def candidatos(doc) -> list[tuple]:
    """[(fid, feat, comp | None)]: las refs de `pies_niveladores` y lo a medida con rol de pie."""
    from apolo.library.calidad.apoyos import clase_de_rol
    from apolo.library.catalog import CATALOG

    out = []
    for fid, f in doc.scene.items():
        if getattr(f, "is_guide", False) or f.shape is None:
            continue
        comp = CATALOG.get(getattr(f, "component", None) or "")
        if comp is not None:
            if comp.category == "pies_niveladores":
                out.append((fid, f, comp))
        elif clase_de_rol(getattr(f, "name", "")) == "pie" and _REGULA_RE.search(f.name or ""):
            out.append((fid, f, None))
    return out


def pies_niveladores(doc, escena: _Escena | None = None) -> dict:
    """El insumo de `apoyo.nivelador`: {pies, no_reconocidos, diagonal_mm, nivelacion_mm}."""
    from apolo.library.catalog import CATALOG

    cands = candidatos(doc)
    pies, no = [], []
    esc = None
    for fid, f, comp in cands:
        if esc is None:
            esc = escena if escena is not None else _Escena(doc.scene)
        try:
            p = medir_pie(doc, esc, fid, f, comp, CATALOG)
        except Exception as exc:  # noqa: BLE001 — geometría rara: no reconocido, nunca rompe
            p, motivo = None, f"no se pudo medir ({type(exc).__name__}: {exc})"[:200]
        else:
            motivo = ("de catálogo sin vástago cilíndrico reconocible" if comp is not None else
                      "con rol de pie que nombra su regulación, sin vástago cilíndrico convexo "
                      "con base coaxial de Ø mayor en un extremo")
        if p is not None:
            pies.append(p)
        else:
            no.append({"id": fid, "nombre": getattr(f, "name", fid), "motivo": motivo})
    req = (getattr(doc, "requirements", None) or {}).get("nivelacion_mm")
    diagonal = _diagonal(doc, pies) if pies else None
    return {"pies": pies, "no_reconocidos": no,
            "diagonal_mm": round(diagonal, 1) if diagonal else None,
            "nivelacion_mm": float(req) if req else None}


def elementos(datos: dict | None) -> dict:
    """{catalogo, a_medida, no_reconocido}: el detector de `puerta_hechos`."""
    if datos is None:
        return {"sin_detectar": 1}
    out = {"catalogo": sum(1 for p in datos["pies"] if p["por"] == "catalogo"),
           "a_medida": sum(1 for p in datos["pies"] if p["por"] != "catalogo"),
           "no_reconocido": len(datos["no_reconocidos"])}
    return {k: v for k, v in out.items() if v}
