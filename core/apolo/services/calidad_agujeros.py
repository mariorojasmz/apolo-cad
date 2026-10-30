"""Insumos del control de AGUJEROS de las uniones atornilladas DECLARADAS (F3c de
puerta-sin-sobrediseno): por cada `fasten kind=perno` del modelador (un comando `fasten` o un
`join_bolted`) y cada `ground` con pernos de anclaje en su nota, cuántos agujeros compatibles tiene
cada pieza que une en la zona donde se une. El control puro es `library/calidad/agujeros.py` (el
formato del insumo, en su docstring). El llamador sostiene STATE_LOCK (sólo se leen shapes).

- **Agujero** = cara CILÍNDRICA INTERIOR (su normal mira al eje), de la geometría, nunca del
  nombre; los cilindros coaxiales de una misma pieza son UN agujero (las dos paredes de un tubo).
  Un COLISO (`calidad_colisos.py`, F3e) es agujero por su ANCHO y recibe los pernos que le caben
  (`agujeros.pernos_en_coliso`). Se extraen una vez por pieza.
- **Zona**: la intersección de las cajas de las dos piezas, ensanchada 1 mm (el agujero de una
  placa bajo la huella de la chumacera, no el de la otra punta). Con tornillería de un lado (un
  espárrago, un perno modelado a mano), sólo se juzga la pieza que ATRAVIESA (las cajas se solapan
  > 1 mm en los tres ejes): la base sobre la que va soldado el espárrago no lleva agujero. Un
  anclaje: la pieza entera.
- **No llegan**: las uniones internas de una plantilla (su command_id es de `create_belt_conveyor`,
  `layout_tablero`, `insert_project`…: las responde la plantilla), lo que no es `perno` y la unión
  con «sin perno» en la nota.
- **No se juzga** (motivo en el insumo): catálogo, «(compra…)», tornillería y pasadores (por el
  ROL anclado), cadena o banda, chapa perforada, el eje de una unión con prisionero.
"""

from __future__ import annotations

import math
import re

_COMANDOS_DEL_MODELADOR = ("fasten", "join_bolted")
_METRICA_RE = re.compile(r"\bM(\d{1,2})\b")
_BASTA_UNA_RE = re.compile(r"punta\s+roscada", re.I)
_PRISIONERO_RE = re.compile(r"prisioner", re.I)
_SIN_PERNO_RE = re.compile(r"sin\s+perno", re.I)
#: Lo que entra en el agujero sin ser tornillería por el catálogo ni por `lints`: un pasador, un
#: remache (por el ROL, anclado: «Pasador de amarre superior cadena 1 (eslabón de unión…)»).
_MACHO_RE = re.compile(r"^\s*(pasador(es)?|pin(es)?|clavijas?|remaches?|chavetas?)\b", re.I)
_FLEXIBLE_RE = re.compile(r"^\s*(cadenas?|bandas?|correas?)\b", re.I)
_EJE_RE = re.compile(r"^\s*(eje|árbol|arbol)\b", re.I)
#: Un ítem del paréntesis que EMPIEZA por «compra» («(compra)», «(compra: interruptor …)»,
#: «(M10 DIN 934, compra)»): la pieza se compra y trae sus agujeros de fábrica.
_COMPRA_RE = re.compile(r"\((?:[^()]*?[,;]\s*)?(?:de\s+)?compra(?:d[oa]s?)?\b", re.I)
#: La perforación de una chapa perforada no se modela (es su designación: «R8 T12»).
_PERFORADA_RE = re.compile(r"\bperforad[ao]s?\b", re.I)
_PERNOS_ANCLAJE_RE = re.compile(r"\b(pernos?|esp[aá]rragos?|tornillos?|tacos?|tarugos?|"
                                r"tirafondos?|expansi[oó]n|qu[ií]micos?|bulones?)\b|\bM\d{1,2}\b",
                                re.I)
_CUANTOS_RE = re.compile(r"\b(\d{1,2})\s*(pernos?|esp[aá]rragos?|tornillos?|tacos?|tarugos?|"
                         r"tirafondos?|bulones?|anclajes?)\b", re.I)
_MARGEN_MM = 1.0


def _metrica(texto) -> float | None:
    m = _METRICA_RE.search(str(texto or ""))
    return float(m[1]) if m else None


def agujeros_de(shape, colisos: bool = True) -> list[dict]:
    """Los agujeros de una forma: [{d, p (punto del eje), eje, lo, hi (caja de sus caras)}], uno
    por línea de eje y Ø (coaxiales del mismo Ø ±0,3 mm = el mismo agujero), más sus COLISOS
    (`calidad_colisos`: {tipo: "coliso", d = el ancho, largo, p0, p1, …}), que absorben los
    medios cilindros de sus extremos redondos."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_REVERSED

    out: list[dict] = []
    for f in shape.faces():
        try:
            ad = BRepAdaptor_Surface(f.wrapped)
            if ad.GetType() != GeomAbs_Cylinder:
                continue
            c = ad.Cylinder()
            u = (ad.FirstUParameter() + ad.LastUParameter()) / 2.0
            v = (ad.FirstVParameter() + ad.LastVParameter()) / 2.0
            pr = BRepLProp_SLProps(ad, u, v, 1, 1e-6)
            if not pr.IsNormalDefined():
                continue
            n, q = pr.Normal(), pr.Value()
            s = -1.0 if f.wrapped.Orientation() == TopAbs_REVERSED else 1.0
            loc, dr = c.Axis().Location(), c.Axis().Direction()
            p, e = (loc.X(), loc.Y(), loc.Z()), (dr.X(), dr.Y(), dr.Z())
            w = (q.X() - p[0], q.Y() - p[1], q.Z() - p[2])
            k = sum(w[i] * e[i] for i in range(3))
            radial = tuple(w[i] - k * e[i] for i in range(3))
            if s * (n.X() * radial[0] + n.Y() * radial[1] + n.Z() * radial[2]) >= 0.0:
                continue  # la normal mira hacia afuera del eje: un vástago, no un agujero
            bb = f.bounding_box()
        except Exception:  # noqa: BLE001 — una cara rara no es un agujero
            continue
        nuevo = {"d": 2.0 * c.Radius(), "p": p, "eje": e,
                 "lo": (bb.min.X, bb.min.Y, bb.min.Z), "hi": (bb.max.X, bb.max.Y, bb.max.Z)}
        mismo = next((a for a in out if _mismo_eje(a, nuevo)), None)
        if mismo is None:
            out.append(nuevo)
        else:
            mismo["lo"] = tuple(min(mismo["lo"][i], nuevo["lo"][i]) for i in range(3))
            mismo["hi"] = tuple(max(mismo["hi"][i], nuevo["hi"][i]) for i in range(3))
    if not colisos:
        return out
    from .calidad_colisos import absorbe, colisos_de

    try:
        cs = colisos_de(shape)
    except Exception:  # noqa: BLE001 — sin la medida del coliso, los agujeros redondos de siempre
        return out
    # los medios cilindros de un coliso de extremos redondos son ESE coliso, no dos agujeros
    return [a for a in out if not any(absorbe(c, a) for c in cs)] + cs


def agujeros_de_corrida(shape) -> list[dict]:
    """`agujeros_de(shape)`, medido UNA vez por forma en la corrida de la puerta (plan
    maquinas-grandes, D3: la entrega, las reglas de ingeniería y `union.agujeros` piden las mismas
    piezas): memo por `is` de `engineering/memo_corrida`; fuera de una corrida, se mide siempre.
    El acierto exige además el mismo `wrapped` y su `Location` (`move`/`locate` mueven en sitio:
    `kernel/caja.py`). Cada llamada recibe sus propios dicts (nadie ensucia el memo)."""
    from apolo.library.engineering.memo_corrida import por_forma

    w = getattr(shape, "wrapped", None)

    def medir():
        return w, (None if w is None else w.Location()), tuple(agujeros_de(shape))

    hecho = por_forma("agujeros", shape, medir)
    if w is not None and (hecho[0] is not w or not hecho[1].IsEqual(w.Location())):
        hecho = medir()  # movida en sitio tras medirla: lo de ahora, sin el memo
    return [dict(a) for a in hecho[2]]


def _mismo_eje(a: dict, b: dict) -> bool:
    if abs(a["d"] - b["d"]) > 0.3:
        return False
    if abs(abs(sum(a["eje"][i] * b["eje"][i] for i in range(3))) - 1.0) > 1e-3:
        return False
    w = tuple(b["p"][i] - a["p"][i] for i in range(3))
    k = sum(w[i] * a["eje"][i] for i in range(3))
    return math.dist(w, tuple(k * a["eje"][i] for i in range(3))) < 0.5


def _caja(feat):
    from apolo.kernel.caja import caja

    try:
        bb = caja(feat.shape)
    except Exception:  # noqa: BLE001
        return None
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def _cruce(a, b, margen: float = 0.0):
    lo = tuple(max(a[0][i], b[0][i]) - margen for i in range(3))
    hi = tuple(min(a[1][i], b[1][i]) + margen for i in range(3))
    return (lo, hi) if all(lo[i] <= hi[i] for i in range(3)) else None


def _en_zona(ag: dict, zona) -> bool:
    return zona is None or all(ag["lo"][i] <= zona[1][i] and ag["hi"][i] >= zona[0][i]
                               for i in range(3))


class _Medidor:
    """Agujeros por pieza (una extracción por pieza y corrida)."""

    def __init__(self, doc) -> None:
        from apolo.library.catalog import CATALOG
        from apolo.library.lints import _is_bolt
        from apolo.library.materials import piece_role

        self.doc, self._ag, self._caja = doc, {}, {}
        #: fid → los agujeros que contó para un `fasten` perno (`agujeros_atribuidos`)
        self.atribuidos: dict[str, list[dict]] = {}
        self.catalogo = lambda f: CATALOG.get(getattr(f, "component", None) or "") is not None
        self.rol = lambda f: piece_role(getattr(f, "name", "") or "")
        self.tornilleria = lambda f: _is_bolt(f, CATALOG) or bool(_MACHO_RE.match(self.rol(f)))

    def caja(self, fid):
        if fid not in self._caja:
            self._caja[fid] = _caja(self.doc.scene[fid])
        return self._caja[fid]

    def agujeros(self, fid: str, d: float | None, zona) -> list[dict]:
        """Los agujeros de `fid` que sirven a un perno M`d` en la `zona` (los que se cuentan)."""
        from apolo.library.calidad.agujeros import compatible

        if fid not in self._ag:
            try:
                self._ag[fid] = agujeros_de_corrida(self.doc.scene[fid].shape)
            except Exception:  # noqa: BLE001
                self._ag[fid] = []
        return [a for a in self._ag[fid] if compatible(a["d"], d) and _en_zona(a, zona)]

    def pieza(self, fid: str, d, zona, otra: str | None = None, prisionero: bool = False,
              registrar: bool = False) -> dict:
        f = self.doc.scene.get(fid)
        base = {"fid": fid, "nombre": getattr(f, "name", fid)}
        if f is None or getattr(f, "is_guide", False) or f.shape is None:
            return {**base, "juzgada": False, "motivo": "sin sólido"}
        nombre, rol = getattr(f, "name", "") or "", self.rol(f)
        motivo = ("tornillería o pasador" if self.tornilleria(f) else
                  "de catálogo (agujeros del fabricante)" if self.catalogo(f) else
                  "de compra (trae sus agujeros de fábrica)" if _COMPRA_RE.search(nombre) else
                  "cadena o banda" if _FLEXIBLE_RE.match(rol) else
                  "chapa perforada (la perforación no se modela)" if _PERFORADA_RE.search(nombre)
                  else "el prisionero aprieta el eje sin taladrarlo"
                  if prisionero and _EJE_RE.match(rol) else None)
        if motivo:
            return {**base, "juzgada": False, "motivo": motivo}
        if otra is not None:
            ca, cb = self.caja(fid), self.caja(otra)
            cruce = _cruce(ca, cb) if ca and cb else None
            if cruce is None or min(cruce[1][i] - cruce[0][i] for i in range(3)) <= 1.0:
                return {**base, "juzgada": False,
                        "motivo": "base de la tornillería (no la atraviesa: va soldada o roscada)"}
            zona = _cruce(ca, cb, _MARGEN_MM)
        from apolo.library.calidad.agujeros import cuenta

        suyos = self.agujeros(fid, d, zona)
        if registrar:
            self.atribuidos.setdefault(fid, []).extend(suyos)
        colisos = sum(1 for a in suyos if a.get("tipo") == "coliso")
        return {**base, "juzgada": True, "agujeros": sum(cuenta(a) for a in suyos),
                **({"colisos": colisos} if colisos else {})}


def _tipos(doc) -> dict:
    return {c["id"]: c.get("type") for c in doc.commands}


def agujeros_atribuidos(doc) -> dict[str, list[dict]]:
    """fid → los agujeros que `union.agujeros` atribuye a un `fasten` perno DECLARADO de esa pieza
    (los que cuenta, con la métrica y la zona de la unión: la MISMA medida). Lo inyectan los
    llamadores de `lints.predelivery_lints`: la tornillería que la nota del fasten declara y nadie
    modeló (la compra la suma `tornilleria_declarada.py`) no deja esos agujeros «sin perno»."""
    med = _Medidor(doc)
    insumos_agujeros(doc, med, anclajes=False)
    return med.atribuidos


def insumos_agujeros(doc, medidor: _Medidor | None = None, *, anclajes: bool = True) -> list[dict]:
    """Los insumos de `controlar_agujeros` de todas las uniones declaradas y los anclajes."""
    tipo, med, out = _tipos(doc), medidor or _Medidor(doc), []
    for nombre, f in doc.fasteners.items():
        if f.get("kind", "perno") != "perno":
            continue
        if tipo.get(str(f.get("command_id") or "")) not in _COMANDOS_DEL_MODELADOR:
            continue  # la unión interna de una plantilla: la responde la plantilla
        a, b = f.get("a"), f.get("b")
        if not (isinstance(a, str) and isinstance(b, str)) or a not in doc.scene or b not in doc.scene:
            continue
        nota = str(f.get("nota") or "")
        if _SIN_PERNO_RE.search(nota):
            continue  # un cierre de palanca, una pieza que se aprieta sin perno: no taladra
        d = _metrica(f.get("size"))
        fa, fb = doc.scene[a], doc.scene[b]
        piezas = []
        for x, y, fy in ((a, b, fb), (b, a, fa)):
            otra = y if med.tornilleria(fy) else None
            ca, cb = med.caja(x), med.caja(y)
            zona = _cruce(ca, cb, _MARGEN_MM) if ca and cb else None
            piezas.append(med.pieza(x, d, zona, otra, bool(_PRISIONERO_RE.search(nota)),
                                    registrar=True))
        out.append({"union": f.get("name") or nombre, "tipo": "fasten", "d": d,
                    "pide": int(f.get("qty") or 1), "basta_una": bool(_BASTA_UNA_RE.search(nota)),
                    "piezas": piezas})
    for nombre, g in (doc.grounds.items() if anclajes else ()):
        fid = g.get("feature") or g.get("a") if isinstance(g, dict) else None
        nota = str((g or {}).get("nota") or "")
        if fid not in doc.scene or not _PERNOS_ANCLAJE_RE.search(nota):
            continue
        n = _CUANTOS_RE.search(nota)
        out.append({"union": g.get("name") or nombre, "tipo": "anclaje", "d": _metrica(nota),
                    "pide": int(n[1]) if n else 1, "basta_una": False,
                    "piezas": [med.pieza(fid, _metrica(nota), None)]})
    return out
