"""Insumos del EJE DE GIRO trabado (plan hallazgos-del-revisor-en-la-puerta, D8): qué perno o
pasador es el eje de una junta `giratoria`/`continua` y qué lo traba. Las reglas puras (nombres,
recta, qué cuenta como traba) están en `library/ejes_giro.py`; el control, en
`library/calidad/agarre.py` (`agarre.retencion`). El llamador sostiene STATE_LOCK.

**Qué es el eje de una junta.** Las juntas que giran son las de `calidad_juntas.GIRO`. Un perno
de `calidad_pernos` (con su eje y su cabeza medidos de la GEOMETRÍA) es eje de la junta si:

1. su recta es la de la junta: paralela y a ≤ 1 mm (`ejes_giro.coaxial`);
2. toca el cuerpo PADRE y el cuerpo HIJO de la junta (la pieza y lo que cuelga de ella por juntas
   `fija`, en los dos sentidos). Tocar = el perno es del cuerpo, lo cruza (sus `tramos`) o el
   cuerpo tiene material a ≤ `R_GIRO`·d del eje dentro del largo del perno (anillo de rayos
   paralelos): la pieza que gira sobre un BUJE no la cruzan los rayos del perno, pero su agujero
   abraza el buje. Un tubo de rodillo (radio ≫ d) alrededor de un perno que entra en la punta de
   su eje fijo no lo toca: ese perno no es el eje (el rodillo gira en sus rodamientos).

Un pasador o bulón SIN cabeza que lo haga perno (rol «Pasador…», «Bulón…») y la tornillería de
madera sin llave de catálogo (que `calidad_pernos` no mide) entran por sus caras CILÍNDRICAS
coaxiales con la junta y tocan los cuerpos por caja; sus tuercas son las coaxiales que tocan su
caja (el tramo, la proyección de la caja sobre el eje).

**Qué lo traba**, medido: la tuerca autoblocante (`tramos[*].autoblocante`, de la ficha o del
rol), dos tuercas a tope en el eje (contratuerca) y, por el rol de su nombre, el pasador de aletas
o el anillo de retención cuya caja toca la del perno. Un perno no evaluable (sin cabeza
reconocida) ya sale SIN_EVALUAR: no se le busca junta.
"""

from __future__ import annotations

R_GIRO = 1.2        # radio del anillo de rayos, en diámetros del perno (buje hasta Ø ≈ 2,4·d)
_N_GIRO = 8


def juntas_de_giro(doc) -> list[dict]:
    """[{"nombre", "origen", "eje" (unitario), "padre": set, "hijo": set}] de las juntas que giran
    con origen y eje legibles."""
    from apolo.library import ejes_giro as E

    from .calidad_juntas import GIRO

    joints = doc.joints or {}
    vecinos: dict[str, set[str]] = {}
    for j in joints.values():
        if j.get("type") == "fija":
            a, b = j.get("parent"), j.get("child")
            vecinos.setdefault(a, set()).add(b)
            vecinos.setdefault(b, set()).add(a)

    def cuerpo(fid) -> set[str]:
        out, pila = set(), [fid]
        while pila:
            n = pila.pop()
            if n is None or n in out:
                continue
            out.add(n)
            pila.extend(vecinos.get(n, ()))
        return out

    out = []
    for nombre, j in joints.items():
        if j.get("type") not in GIRO:
            continue
        try:
            origen, eje = E.vec(j.get("origin")), E.unit(E.vec(j.get("axis")))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if eje is None:
            continue
        out.append({"nombre": nombre, "origen": origen, "eje": eje,
                    "padre": cuerpo(j.get("parent")), "hijo": cuerpo(j.get("child"))})
    return out


def _caja_eje(asiento, dire, largo: float, radio: float):
    p1 = tuple(asiento[k] + largo * dire[k] for k in range(3))
    lo = tuple(min(asiento[k], p1[k]) - radio for k in range(3))
    hi = tuple(max(asiento[k], p1[k]) + radio for k in range(3))
    return lo, hi


def _se_tocan(lo, hi, mn, mx, holgura: float = 0.0) -> bool:
    return all(mn[k] <= hi[k] + holgura and mx[k] >= lo[k] - holgura for k in range(3))


def _retenes(esc, lo, hi, propio: str) -> list[dict]:
    from apolo.library.ejes_giro import tipo_reten

    out = []
    for fid, feat, _s, mn, mx, _r in esc.solidos:
        if fid == propio or not _se_tocan(lo, hi, mn, mx, 0.5):
            continue
        tipo = tipo_reten(getattr(feat, "name", "") or "")
        if tipo and not any(r["fid"] == fid for r in out):
            out.append({"fid": fid, "nombre": getattr(feat, "name", fid), "tipo": tipo})
    return out


def _anillo(esc, p: dict, propio: str) -> set[str]:
    """Las piezas con material a `R_GIRO`·d del eje del perno, dentro de su largo."""
    import math

    from .calidad_pernos import _add, _base_perp

    a, e = tuple(p["eje"]["asiento"]), tuple(p["eje"]["dir"])
    largo, r = float(p["largo"]), R_GIRO * float(p["d"])
    u, v = _base_perp(e)
    lo, hi = _caja_eje(a, e, largo, r + 0.5)
    out = set()
    for fid, _feat, _otro, rayos in esc.cerca(lo, hi):
        if fid == propio or fid in out:
            continue
        for k in range(_N_GIRO):
            ang = 2.0 * math.pi * k / _N_GIRO
            o = _add(_add(a, u, r * math.cos(ang)), v, r * math.sin(ang))
            if rayos.tramos(o, e, -0.5, largo):
                out.add(fid)
                break
    return out


def _marcar_perno(esc, p: dict, juntas: list[dict]) -> None:
    from apolo.library import ejes_giro as E

    eje = p.get("eje")
    if not p.get("evaluable", True) or not eje:
        return
    a, e = tuple(eje["asiento"]), tuple(eje["dir"])
    candidatas = [j for j in juntas if E.coaxial(a, e, j["origen"], j["eje"])]
    if not candidatas:
        return
    cruza = {t["fid"] for t in p.get("tramos", [])} | {p["fid"]}
    anillo = None  # el anillo de rayos sólo si lo que cruza no alcanza (lo caro, una vez)
    for j in candidatas:
        toca = cruza
        if not (toca & j["padre"] and toca & j["hijo"]):
            if anillo is None:
                anillo = _anillo(esc, p, p["fid"])
            toca = cruza | anillo
            if not (toca & j["padre"] and toca & j["hijo"]):
                continue
        lo, hi = _caja_eje(a, e, float(p["largo"]), float(p["d"]))
        p["giro"] = {"junta": j["nombre"]}
        p["retenes"] = _retenes(esc, lo, hi, p["fid"])
        p["tirafondo"] = bool(p.get("madera_screw")) or E.es_tirafondo(p.get("nombre"))
        return


def _candidato_pasador(feat, catalog) -> str | None:
    """'pasador' | 'madera' | None: lo que `calidad_pernos` no mide y puede ser eje."""
    from apolo.library import ejes_giro as E

    comp = catalog.get(getattr(feat, "component", None) or "")
    if comp is not None:
        return "madera" if comp.category == "tornilleria_madera" else None
    nombre = getattr(feat, "name", "") or ""
    if E.es_tirafondo(nombre):
        return "madera"
    return "pasador" if E.es_pasador(nombre) else None


def _pasador(esc, fid, feat, solid, mn, mx, juntas, clase, catalog) -> dict | None:
    from apolo.library import ejes_giro as E

    from .calidad_pernos import _cilindros, _es_tuerca, es_autoblocante

    try:
        cils = _cilindros(solid)
    except Exception:  # noqa: BLE001 — geometría rara: no se juzga como eje
        return None
    for j in juntas:
        if not any(E.coaxial(c["p"], c["eje"], j["origen"], j["eje"]) for c in cils):
            continue
        cuerpos = {"padre": False, "hijo": False}
        for ofid, _f, _s, omn, omx, _r in esc.solidos:
            for lado in cuerpos:
                if ofid in j[lado] and (ofid == fid or _se_tocan(mn, mx, omn, omx, 0.5)):
                    cuerpos[lado] = True
        if not all(cuerpos.values()):
            continue
        o, w = j["origen"], j["eje"]
        tuercas = []
        for ofid, ofeat, _s, omn, omx, _r in esc.solidos:
            if ofid == fid or not _es_tuerca(ofeat, catalog) or not _se_tocan(mn, mx, omn, omx, 0.5):
                continue
            centro = tuple((omn[k] + omx[k]) / 2.0 for k in range(3))
            if E.distancia_a_recta(centro, o, w) > E.COAXIAL_MM:
                continue
            ts = [sum((c[k] - o[k]) * w[k] for k in range(3))
                  for c in ((x, y, z) for x in (omn[0], omx[0]) for y in (omn[1], omx[1])
                            for z in (omn[2], omx[2]))]
            tuercas.append({"fid": ofid, "nombre": getattr(ofeat, "name", ofid),
                            "t0": round(min(ts), 2), "t1": round(max(ts), 2),
                            "autoblocante": es_autoblocante(ofeat, catalog)})
        return {"fid": fid, "nombre": getattr(feat, "name", fid), "pasador": True,
                "tirafondo": clase == "madera", "giro": {"junta": j["nombre"]},
                "tuercas": tuercas, "retenes": _retenes(esc, mn, mx, fid)}
    return None


def marcar_ejes(doc, pernos: list[dict], esc) -> list[dict]:
    """Marca en los insumos de `pernos` (en sitio) el que es eje de una junta de giro (`giro`,
    `retenes`, `tirafondo`) y devuelve los insumos de los PASADORES y la tornillería de madera
    sin llave que son eje (formato en `library/calidad/agarre.py`). Sin juntas de giro: nada."""
    from apolo.library.catalog import CATALOG

    juntas = juntas_de_giro(doc)
    if not juntas:
        return []
    for p in pernos:
        _marcar_perno(esc, p, juntas)
    medidos = {p["fid"] for p in pernos}
    out = []
    for fid, feat, solid, mn, mx, _r in list(esc.solidos):
        if fid in medidos or getattr(feat, "is_guide", False):
            continue
        clase = _candidato_pasador(feat, CATALOG)
        if clase is None:
            continue
        ins = _pasador(esc, fid, feat, solid, mn, mx, juntas, clase, CATALOG)
        if ins is not None:
            out.append(ins)
    return out
