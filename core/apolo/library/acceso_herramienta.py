"""¿Entra la LLAVE? Acceso de herramienta a tuercas y cabezas (plan acceso-de-herramienta).

`check_interference` sólo ve sólidos que existen; el espacio que necesita una llave no es un
sólido del modelo. Aquí se arma, por cada tuerca o cabeza reconocida (`fijadores_geom`), un
sólido FANTASMA por herramienta (D1: `fantasmas_herramienta.py`, medidas de `herramientas.py`)
y se cruza con los vecinos:

- **copa**: cilindro Ø copa_d coaxial, desde el asiento hasta altura + 15 mm hacia afuera;
- **anillo**: anillo plano Ø anillo_d en el plano de la tuerca + el arranque del mango, que
  debe poder barrer ±15° en alguna de 12 posiciones (llave de 12 puntas: cada 30°);
- **boca**: la cabeza abierta + el arranque del mango, barriendo ±15°, en alguna de las 6
  direcciones de las caras (cada 60°);
- **Allen** (cabeza con hueco): el brazo corto de la L, coaxial.
- **remachadora** (remache ciego de catálogo, `herramienta: remachadora`; no tiene hexágono):
  nariz y cabezal coaxiales desde la cabeza (plan union-en-perfil-hueco).
- un **espárrago** (`esparrago.py`: rol + vástago sin cabeza) no se aprieta: lo hace su TUERCA,
  que se evalúa como cualquier tuerca; se cuenta en `esparragos`, no en `no_evaluados`.

D2: basta UNA herramienta libre; libre = no corta (> 1 mm³) nada salvo el propio fijador, lo
que pasa por su agujero (su perno o su eje) y lo que queda del lado del asiento (todo fantasma
arranca a `HOLGURA_ASIENTO_MM` de la cara de asiento: la pieza donde asienta NO se excluye
entera, porque el ala que estorba suele ser de esa misma pieza — el UPN del piloto). D3: copa
o anillo libres = ok; sólo boca = aviso; nada = rojo. Un sólido que GIRA cuenta igual (se arma
parado). No se filtra por `visible` (ocultar es estado de vista) y sólo se evalúa lo
reconocido: el resto se DECLARA no evaluado.

Costo (bitácora F0 del plan): sólo cruzan los sólidos dentro del ALCANCE del fijador (caja de
bbox), los fantasmas son de pocas caras y se construyen una vez por corrida, y cada herramienta
para en el primer choque; la boca prueba primero lo COMÚN a sus 6 direcciones.

PURO: recibe la escena (dict de features), nunca un `Document`; el llamador sostiene
`STATE_LOCK` (sólo lee shapes).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .checks import MIN_VOLUME_MM3, _bboxes_overlap
from .esparrago import es_esparrago, geometria_esparrago
from .fantasmas_herramienta import Fantasmas, marco
from .fijadores_geom import FijadorGeom, reconocer_fijadores, reconocer_remache
from .herramientas import LARGO_LIBRE_COPA_MM, REMACHADORA, brazo_allen, llave_para

HOLGURA_ASIENTO_MM = 1.0  # los fantasmas arrancan a 1 mm de la cara de asiento
_CATS_LLAVE = {"tuercas", "pernos", "tornilleria"}  # se aprietan con llave (no tirafondos)


@dataclass(eq=False)  # identidad: dos sólidos iguales no son el mismo vecino
class _Solido:
    fid: str
    nombre: str
    solid: object
    bbox: object


def es_tornilleria_de_llave(feat, catalog) -> bool:
    """Tornillería que se aprieta con LLAVE (o se coloca con remachadora): catálogo
    (tuercas/pernos/tornillería) o a medida por nombre (misma convención `_is_bolt` de los
    lints). Los tirafondos avellanados no; el de cabeza hexagonal DIN 571 sí (`llave: true`)."""
    from .lints import es_nombre_de_tornilleria

    comp = catalog.get(getattr(feat, "component", None) or "") if catalog else None
    if comp is not None:
        if comp.category in _CATS_LLAVE:
            return True
        if comp.category == "tornilleria_madera":
            return bool((comp.specs or {}).get("llave"))
    return es_nombre_de_tornilleria(getattr(feat, "name", "") or "")


def _es_remache(feat, catalog) -> bool:
    comp = catalog.get(getattr(feat, "component", None) or "") if catalog else None
    return comp is not None and (comp.specs or {}).get("herramienta") == "remachadora"


def _cuello_cuadrado(feat, catalog) -> bool:
    """El perno de cuello cuadrado DIN 603 de catálogo: su cabeza de hongo no lleva llave (el
    cuello frena el giro) y lo aprieta su TUERCA, que se evalúa aparte (como el espárrago)."""
    comp = catalog.get(getattr(feat, "component", None) or "") if catalog else None
    return comp is not None and (comp.specs or {}).get("norma") == "DIN 603"


def _choque(ghost, mrc, vecinos: list[_Solido]) -> _Solido | None:
    """El primer vecino que el fantasma (local, colocado con `mrc`) corta; None si libre."""
    g = mrc * ghost
    gb = g.bounding_box(optimal=False)
    for o in vecinos:
        if not _bboxes_overlap(gb, o.bbox):
            continue
        try:
            inter = g & o.solid
            vol = float(inter.volume) if inter is not None else 0.0
        except Exception:  # noqa: BLE001 — booleana fallida = no concluyente, no choque
            vol = 0.0
        if vol > MIN_VOLUME_MM3:
            return o
    return None


def _cortan(ghost, mrc, vecinos) -> list[_Solido]:
    """Todos los vecinos que corta (sonda del agujero y sondas de asiento)."""
    out, resto = [], list(vecinos)
    while (o := _choque(ghost, mrc, resto)) is not None:
        out.append(o)
        resto = [x for x in resto if x is not o]
    return out


def _evaluar(fj: FijadorGeom, vecinos: list[_Solido], fx: Fantasmas) -> dict:
    """{estado, herramienta, bloquean: [_Solido]} para un fijador reconocido."""
    x_dir = fj.planas[0]
    m, eps = fj.altura, HOLGURA_ASIENTO_MM
    bloquean: list[_Solido] = []

    def libre(ghost, mrc) -> bool:
        o = _choque(ghost, mrc, vecinos)
        if o is not None and o not in bloquean:
            bloquean.append(o)
        return o is None

    if fj.tipo == "remache":  # la nariz y el cabezal de la remachadora, coaxiales a la cabeza
        r = REMACHADORA
        mrc = marco(fj.base, fj.eje, x_dir)
        ok = (libre(fx.cilindro(r.nariz_d / 2.0, eps, r.nariz_largo), mrc)
              and libre(fx.cilindro(r.cabezal_d / 2.0, r.nariz_largo, r.largo), mrc))
        return {"estado": "ok" if ok else "sin_herramienta",
                "herramienta": "remachadora" if ok else None, "bloquean": bloquean}
    if fj.tipo == "allen":
        largo = brazo_allen(fj.s)
        if largo is None:
            return {"estado": "no_evaluado", "motivo": f"llave Allen {fj.s:g} fuera de tabla"}
        ok = libre(fx.cilindro(fj.r_esquinas + 0.5, 0.0, largo), marco(fj.base, fj.eje, x_dir))
        return {"estado": "ok" if ok else "sin_herramienta",
                "herramienta": "allen" if ok else None, "bloquean": bloquean}

    ll = llave_para(fj.s)
    if ll is None:
        return {"estado": "no_evaluado", "motivo": f"entrecaras {fj.s:g} fuera de tabla"}
    marco_mas = marco(fj.base, fj.eje, x_dir)
    lados = [marco_mas]  # marcos con t = 0 en el ASIENTO y +z hacia afuera
    asiento_ambos = False
    if fj.tipo == "tuerca":
        # lo que pasa por el agujero (su perno o su eje) no estorba: se excluye
        propio = _cortan(fx.cilindro(0.2 * fj.s, 0.5, m - 0.5), marco_mas, vecinos)
        vecinos = [o for o in vecinos if o not in propio]
        r_in, r_out = 0.36 * fj.s, 0.5 * fj.s
        asiento_menos = bool(_cortan(fx.anillo(r_in, r_out, -1.0, 0.0), marco_mas, vecinos))
        asiento_mas = bool(_cortan(fx.anillo(r_in, r_out, m, m + 1.0), marco_mas, vecinos))
        tope = tuple(fj.base[i] + m * fj.eje[i] for i in range(3))
        marco_menos = marco(tope, tuple(-c for c in fj.eje), x_dir)
        if asiento_menos and asiento_mas:
            lados, asiento_ambos = [], True
        elif asiento_mas:
            lados = [marco_menos]
        elif not asiento_menos:
            lados = [marco_mas, marco_menos]  # sin asiento a la vista: prueba los dos lados
    for mrc in lados:
        if libre(fx.cilindro(ll.copa_d / 2.0, eps, m + LARGO_LIBRE_COPA_MM), mrc):
            return {"estado": "ok", "herramienta": "copa", "bloquean": []}

    # banda axial de la cabeza (anillo/boca): lo más lejos posible del asiento
    mrc = lados[0] if lados else marco_mas
    z0 = max(eps, m - ll.espesor)
    z1 = min(m - eps, z0 + ll.espesor) if asiento_ambos else z0 + ll.espesor
    ra = ll.anillo_d / 2.0
    if libre(fx.anillo(fj.r_esquinas + 0.3, ra, z0, z1), mrc):
        for k in range(12):
            if libre(fx.mango(ra, fj.s, 30.0 * k, z0, z1), mrc):
                return {"estado": "ok", "herramienta": "anillo", "bloquean": []}
    rb = ll.boca_b / 2.0
    if not libre(fx.boca(fj.r_esquinas, fj.s, ll.boca_b, None, z0, z1), mrc):
        return {"estado": "sin_herramienta", "herramienta": None, "bloquean": bloquean}
    for k in range(6):
        theta = 60.0 * k
        if (libre(fx.boca(fj.r_esquinas, fj.s, ll.boca_b, theta, z0, z1), mrc)
                and libre(fx.mango(rb, fj.s, theta, z0, z1), mrc)):
            return {"estado": "solo_boca", "herramienta": "boca", "bloquean": bloquean}
    return {"estado": "sin_herramienta", "herramienta": None, "bloquean": bloquean}


def _alcance(fj: FijadorGeom) -> float:
    """Radio de influencia: hasta dónde puede llegar un fantasma de este fijador."""
    if fj.tipo == "remache":
        return REMACHADORA.largo + REMACHADORA.cabezal_d + 2.0
    ll = llave_para(fj.s)
    if ll is None:
        return (brazo_allen(fj.s) or 0.0) + fj.s + 2.0
    return (max(fj.altura + LARGO_LIBRE_COPA_MM, ll.anillo_d / 2.0 + fj.s, ll.boca_b / 2.0 + fj.s)
            + fj.altura + 2.0)


def _solidos(scene) -> list[_Solido]:
    from apolo.kernel.shapes import is_surface

    out = []
    for fid, f in scene.items():
        if getattr(f, "is_guide", False) or f.shape is None or is_surface(f.shape):
            continue
        try:
            for s in f.shape.solids():
                out.append(_Solido(fid, f.name, s, s.bounding_box(optimal=False)))
        except Exception:  # noqa: BLE001
            continue
    return out


def _vecinos(propio: _Solido, todos: list[_Solido], c, r: float) -> list[_Solido]:
    """Los sólidos cuya bbox entra en la caja de alcance c ± r (riesgo «miles de pernos» del
    plan: la booleana sólo corre contra los vecinos)."""
    lo = [c[i] - r for i in range(3)]
    hi = [c[i] + r for i in range(3)]
    return [o for o in todos if o is not propio
            and o.bbox.min.X <= hi[0] and o.bbox.max.X >= lo[0]
            and o.bbox.min.Y <= hi[1] and o.bbox.max.Y >= lo[1]
            and o.bbox.min.Z <= hi[2] and o.bbox.max.Z >= lo[2]]


def tool_access_report(scene: dict, *, catalog=None) -> dict | None:
    """Acceso de herramienta de toda la tornillería de llave de la escena; None si no hay
    ninguna (la puerta de entrega queda EXACTAMENTE como antes).

    → {evaluados, ok, sin_herramienta: [...], solo_boca: [...], no_evaluados: [...], ms}; cada
    entrada {id, nombre, tipo, llave_mm, bloquean: [nombres]} (o {id, nombre, motivo})."""
    t_ini = time.perf_counter()
    candidatos = {fid for fid, f in scene.items()
                  if not getattr(f, "is_guide", False) and es_tornilleria_de_llave(f, catalog)}
    if not candidatos:
        return None
    todos = _solidos(scene)
    fx = Fantasmas()
    rep: dict = {"evaluados": 0, "ok": 0, "sin_herramienta": [], "solo_boca": [],
                 "no_evaluados": []}
    for fid in sorted(candidatos - {o.fid for o in todos}):
        rep["no_evaluados"].append({"id": fid, "nombre": scene[fid].name, "motivo": "sin sólido"})
    for propio in todos:
        if propio.fid not in candidatos:
            continue
        fjs = reconocer_fijadores(propio.solid)  # uno por hexágono (perno + tuerca fundidos: 2)
        if not fjs and _es_remache(scene[propio.fid], catalog):
            fjs = reconocer_remache(propio.solid)
        if not fjs and es_esparrago(propio.nombre) and geometria_esparrago(propio.solid):
            rep["esparragos"] = rep.get("esparragos", 0) + 1  # lo aprieta su tuerca (F3c)
            continue
        if not fjs and _cuello_cuadrado(scene[propio.fid], catalog):
            rep["cuello_cuadrado"] = rep.get("cuello_cuadrado", 0) + 1  # ídem (rodillos F9)
            continue
        if not fjs:
            rep["no_evaluados"].append({"id": propio.fid, "nombre": propio.nombre,
                                        "motivo": "sin hexágono reconocible"})
        for fj in fjs:
            res = _evaluar(fj, _vecinos(propio, todos, fj.base, _alcance(fj)), fx)
            if res["estado"] == "no_evaluado":
                rep["no_evaluados"].append({"id": propio.fid, "nombre": propio.nombre,
                                            "motivo": res["motivo"]})
                continue
            rep["evaluados"] += 1
            if res["estado"] == "ok":
                rep["ok"] += 1
                continue
            rep[res["estado"]].append({
                "id": propio.fid, "nombre": propio.nombre, "tipo": fj.tipo,
                "llave_mm": round(fj.s, 1),
                "bloquean": sorted({o.nombre for o in res["bloquean"]}),
            })
    rep["ms"] = round((time.perf_counter() - t_ini) * 1000.0)
    return rep
