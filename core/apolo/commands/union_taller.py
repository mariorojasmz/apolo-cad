"""Criterio de TALLER de `join_bolted` (plan `union-en-perfil-hueco`, D1–D4): el de todo
comando nuevo (`criterio` 2; el 1 de los logs viejos vive en `exec_union.py`).

Por cada punto del patrón se tira un RAYO por el eje del taladro (`kernel/rayo.py`) y se mide
lo que el perno atraviesa de verdad:

- **base** = la pieza más gruesa en el eje de la unión (empate → `a`); la otra se AGREGA;
- la pared de la base que toca a la pieza agregada, su espesor y lo que hay DETRÁS: si el rayo
  vuelve a entrar en la base (la pared de enfrente de un tubo) es un perfil cerrado; si otra
  pieza ocupa el espacio de la tuerca y su llave (alto de tuerca + 3 filetes + el largo libre
  de la copa), hay obstáculo. Cualquiera de los dos = sin acceso por detrás (D1);
- D2: el agarre es la suma de los dos espesores; D3: la cabeza va del lado de la pieza que se
  agrega y la tuerca detrás de la pared de la base; D4: base de madera → tornillo para madera.

La elección (y sus tablas) es de `library/fijacion.py`; aquí sólo se mide, se taladra y se
colocan las piezas. Todas las fijaciones del patrón son iguales (el mayor agarre manda).
"""

from __future__ import annotations

import math

from .errors import CommandError
from .exec_union import exigir_asiento, huella, patron, rotacion_hacia, terminar
from .models_union import JoinBoltedParams
from .state import ExecContext

_TOL_CONTACTO = 0.6  # mm: la pared de la base empieza donde termina la pieza agregada
_MARGEN = 5.0        # mm: el taladro arranca fuera de la cara de la cabeza


def _medir(h: dict, base, anadida, pt: list[float], otros: list, acceso: float) -> dict:
    """Lo que atraviesa el eje que pasa por `pt` (coordenada `stack` libre)."""
    from apolo.kernel.rayo import tramos_en_eje

    st = h["stack"]
    lo = min(h["amin"][st], h["bmin"][st]) - 1.0
    hi = max(h["amax"][st], h["bmax"][st]) + 1.0
    t_add = tramos_en_eje(anadida.shape, st, pt, lo, hi)
    t_base = tramos_en_eje(base.shape, st, pt, lo, hi)
    par = None
    for sa in t_add:
        for sb in t_base:
            if abs(sa[1] - sb[0]) <= _TOL_CONTACTO:
                par = (sa, sb, 1.0)
            elif abs(sb[1] - sa[0]) <= _TOL_CONTACTO:
                par = (sa, sb, -1.0)
    if par is None:
        donde = ", ".join(f"{c:.0f}" for c in pt)
        raise CommandError(
            f"En el punto ({donde}) el eje de la unión no cruza material de las dos piezas en "
            "contacto (un hueco, una ranura o una pieza curva): mueve las piezas o cambia "
            "count/patron/spacing."
        )
    sa, sb, s = par  # s: sentido de la pieza agregada hacia la base
    cabeza = sa[0] if s > 0 else sa[1]
    contacto = sa[1] if s > 0 else sa[0]
    atras = sb[1] if s > 0 else sb[0]
    # lo que hay detrás de la pared: la propia base (perfil cerrado) u otra pieza
    reentradas = [x[0] - atras if s > 0 else atras - x[1] for x in t_base
                  if (x[0] > atras + 1e-3 if s > 0 else x[1] < atras - 1e-3)]
    cerrado = bool(reentradas)
    libre = min(reentradas) if reentradas else math.inf
    tramo = (atras, atras + s * acceso)
    for o in otros:
        for x in tramos_en_eje(o.shape, st, pt, min(tramo), max(tramo)):
            libre = min(libre, x[0] - atras if s > 0 else atras - x[1])
    return {
        "s": s, "cabeza": cabeza, "contacto": contacto, "atras": atras,
        "t_add": sa[1] - sa[0], "t_base": sb[1] - sb[0],
        "cerrado": cerrado, "libre": libre, "sin_acceso": cerrado or libre < acceso,
    }


def _en_camino(scene, excluir: set, h: dict, us, vs, u, v, alcance: float) -> list:
    """Las piezas cuya caja toca la zona de la unión (candidatas a obstáculo detrás)."""
    st = h["stack"]
    lo = [0.0, 0.0, 0.0]
    hi = [0.0, 0.0, 0.0]
    lo[u], hi[u] = min(us) - 1.0, max(us) + 1.0
    lo[v], hi[v] = min(vs) - 1.0, max(vs) + 1.0
    lo[st] = min(h["amin"][st], h["bmin"][st]) - alcance
    hi[st] = max(h["amax"][st], h["bmax"][st]) + alcance
    out = []
    for fid, f in scene.items():
        if fid in excluir or f.shape is None:
            continue
        try:
            bb = f.shape.bounding_box()
        except Exception:  # noqa: BLE001
            continue
        mn, mx = (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)
        if all(mn[k] <= hi[k] and mx[k] >= lo[k] for k in range(3)):
            out.append(f)
    return out


def _elegir(p: JoinBoltedParams, h: dict, base, anadida, medidas: list[dict]):
    """D1/D2/D4 → la `Fijacion` de la unión (ValueError de la biblioteca → CommandError)."""
    from apolo.library import fijacion as fj

    size = h["size"]
    try:
        if base.id in p.madera:
            return fj.tornillo_madera(size, max(m["t_add"] for m in medidas),
                                      min(m["t_base"] for m in medidas))
        if any(m["sin_acceso"] for m in medidas):
            if anadida.id in p.madera:
                raise CommandError(
                    "La base no tiene acceso por detrás y la pieza que agregas es de madera: un "
                    "remache ciego no sujeta madera. Une la madera a una cara con acceso por "
                    "detrás o a una ménsula."
                )
            return fj.remache_ciego(size, max(m["t_add"] + m["t_base"] for m in medidas),
                                    min(m["libre"] for m in medidas))
        return fj.perno_pasante(size, max(m["t_add"] + m["t_base"] for m in medidas), p.norma)
    except (KeyError, ValueError) as exc:
        raise CommandError(str(exc).strip("'\"")) from exc


def _pieza(fij, m: dict):
    """La fijación colocada en su marco local (origen = asiento de la cabeza, cabeza en +Z)."""
    from apolo.library.builders import hex_bolt
    from apolo.library.builders_fijacion import hex_wood_screw, remache_colocado

    if fij.tipo == "perno":
        return hex_bolt(fij.d, fij.cabeza_s, fij.cabeza_k)(fij.largo)
    if fij.tipo == "remache":
        return remache_colocado(fij.d, fij.cabeza_s, fij.cabeza_k, m["t_add"] + m["t_base"],
                                fij.largo)
    return hex_wood_screw(fij.d, fij.cabeza_s, fij.cabeza_k)(fij.largo)


def _taladrar(base, anadida, fij, m: dict, h: dict, pt: list[float]) -> None:
    """Taladro de paso por la pieza agregada y la pared de la base (perno, remache) o paso en
    la agregada + piloto en la madera (tornillo). Nunca toca la pared de enfrente."""
    from .registry import _drill_tool

    st, s = h["stack"], m["s"]
    eje = [0.0, 0.0, 0.0]
    eje[st] = s

    def herramienta(diam: float, desde: float, hasta: float):
        entrada = list(pt)
        entrada[st] = desde
        return _drill_tool(diam, abs(hasta - desde), tuple(entrada), tuple(eje))

    inicio = m["cabeza"] - s * _MARGEN
    if fij.tipo == "tornillo_madera":
        anadida.shape = anadida.shape - herramienta(fij.broca_anadida, inicio,
                                                    m["contacto"] + s * 0.5)
        fondo = m["contacto"] + s * (fij.largo - m["t_add"])
        base.shape = base.shape - herramienta(fij.broca_base, m["contacto"] - s * 0.5, fondo)
        return
    holgura = min(1.0, m["libre"] / 2.0)
    tool = herramienta(fij.broca_base, inicio, m["atras"] + s * holgura)
    anadida.shape = anadida.shape - tool
    base.shape = base.shape - tool


def criterio_taller(ctx: ExecContext, cmd_id: str, p: JoinBoltedParams, a, b) -> None:
    from build123d import Pos, Rotation

    from apolo.assembly.connectivity import ConnectivityError, register_fastener
    from apolo.library.builders import hex_nut
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.bolts import hex_nut_mm
    from apolo.library.fijacion import paso_grueso
    from apolo.library.herramientas import LARGO_LIBRE_COPA_MM

    from .registry import Feature

    h = huella(a.shape, b.shape, p.size)
    st, size = h["stack"], h["size"]
    try:
        nut_m = hex_nut_mm(size)[1]
    except KeyError as exc:
        raise CommandError(str(exc)) from exc
    # contacto cara a cara en el plano donde se tocan las cajas (V6.5c Fix 2): una pieza rotada
    # o curva se rechaza pidiendo mates antes de tirar rayos
    a_abajo = (h["amin"][st] + h["amax"][st]) <= (h["bmin"][st] + h["bmax"][st])
    exigir_asiento(a.shape, h, h["amax"][st] if a_abajo else h["amin"][st], "contacto")
    exigir_asiento(b.shape, h, h["bmin"][st] if a_abajo else h["bmax"][st], "contacto")
    grueso = {f.id: f.shape.bounding_box().size.to_tuple()[st] for f in (a, b)}
    base, anadida = (b, a) if grueso[b.id] > grueso[a.id] + 1e-6 else (a, b)
    u, v, us, vs = patron(h, p)
    acceso = nut_m + 3.0 * paso_grueso(size) + LARGO_LIBRE_COPA_MM
    otros = _en_camino(ctx.scene, {a.id, b.id}, h, us, vs, u, v, acceso)
    puntos = []
    for pu in us:
        for pv in vs:
            pt = [0.0, 0.0, 0.0]
            pt[u], pt[v] = pu, pv
            puntos.append(pt)
    medidas = [_medir(h, base, anadida, pt, otros, acceso) for pt in puntos]
    fij = _elegir(p, h, base, anadida, medidas)
    for ref in (fij.ref, fij.tuerca):
        if ref is not None and ref not in CATALOG:
            raise CommandError(f"Sin ficha de catálogo '{ref}' para {size}.")
    vistos = set()  # asientos planos (V6.5c Fix 2) en las cotas REALES de cada cara
    for m in medidas:
        clave = tuple(round(m[k], 2) for k in ("cabeza", "contacto", "atras"))
        if clave in vistos:
            continue
        vistos.add(clave)
        exigir_asiento(anadida.shape, h, m["contacto"], "contacto")
        exigir_asiento(base.shape, h, m["contacto"], "contacto")
        exigir_asiento(anadida.shape, h, m["cabeza"], "asiento de la cabeza")
        if fij.tipo == "perno":
            exigir_asiento(base.shape, h, m["atras"], "asiento de la tuerca")
    nombre_tuerca = f"Tuerca {size} DIN 934"
    tuerca = hex_nut(fij.d, fij.tuerca_s, fij.tuerca_m)() if fij.tuerca else None
    rol = {"perno": "perno", "remache": "remache", "tornillo_madera": "tornillo"}[fij.tipo]
    for n, (pt, m) in enumerate(zip(puntos, medidas, strict=True), start=1):
        _taladrar(base, anadida, fij, m, h, pt)
        rot = rotacion_hacia(st, -m["s"])  # la cabeza mira hacia afuera de la pieza agregada
        origen = list(pt)
        origen[st] = m["cabeza"]
        fid = f"{cmd_id}_{rol}{n}"
        ctx.scene[fid] = Feature(fid, fij.nombre, Pos(*origen) * Rotation(*rot) * _pieza(fij, m),
                                 cmd_id, component=fij.ref)
        if tuerca is not None:
            centro = list(pt)
            centro[st] = m["atras"] + m["s"] * fij.tuerca_m / 2.0
            ctx.scene[f"{cmd_id}_tuerca{n}"] = Feature(
                f"{cmd_id}_tuerca{n}", nombre_tuerca, Pos(*centro) * Rotation(*rot) * tuerca,
                cmd_id, component=fij.tuerca,
            )
    fijador = {"kind": "perno", "size": size if fij.tipo == "perno" else None,
               "qty": len(puntos), "nota": p.name}
    if fij.tipo != "perno":
        fijador["fijacion"] = fij.nombre
    terminar(ctx, cmd_id, p, a, b, fijador, ConnectivityError, register_fastener)
