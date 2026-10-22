"""Sondas con el brazo DOBLADO (ISO 13857, alcance a través de aberturas) para la puerta de
publicación — el complemento de las sondas rectas de `calidad_sondas.py` (F6 de
puerta-de-publicacion).

Una sonda recta sólo ve el peligro si una LÍNEA desde fuera de la máquina llega a él. El brazo
entra por una abertura > 20 mm hasta el hombro y se dobla: la cuña retorno ↔ desvío de la faja de
motor central quedaba a 60 mm de la ranura de 36 mm entre el borde de la banda y el larguero,
encima de la guarda del drive, y ninguna recta llegaba (se sube entre las patas y se baja junto
a la banda). Aquí:

1. `campo_alcance`: el campo del brazo (`library/seguridad/alcance.py`) sobre el teselado de todos
   los sólidos;
2. `sondas_con_codo`: desde cada objetivo del peligro, la MANO sale recta en cada dirección de la
   esfera hasta el primer sólido ajeno al peligro; el primer punto de ese tramo al que el brazo
   llega (el codo) es el origen de una sonda hacia el objetivo, y `sondas.veredicto` la juzga con
   sus haces: profundidad = la del codo + el tramo recto.

Lee shapes (teselado): el llamador sostiene `STATE_LOCK`. Sin `Document`.
"""

from __future__ import annotations

import time

from apolo.library.seguridad.iso13857 import ALCANCE_DESDE_MUNECA_MM
from apolo.library.seguridad.sondas import desplazamientos, direcciones, veredicto

PASO_TRAMO_MM = 5.0      # cada cuánto se busca el codo sobre el tramo de la mano
MAX_SONDAS_CODO = 4096   # por peligro (como las rectas)
#: En una cuña, la mano tiene que llegar a la CUÑA: tocar el tambor a más de esto del punto (su
#: canto o su cara más allá del borde de la banda) no es la cuña. Las rectas, como siempre, cuentan
#: todo contacto con el peligro; el extremo de eje y lo que gira tienen sus propios objetivos.
TOQUE_CUNA_MM = 20.0


def campo_alcance(solidos: dict, caja, z_piso: float):
    """El `CampoAlcance` de la máquina: muestras del teselado de render de cada sólido."""
    import numpy as np

    from apolo.kernel.malla_render import triangular
    from apolo.library.seguridad.alcance import CampoAlcance, muestrear_triangulos

    nubes = []
    for lista in solidos.values():
        for s in lista:
            try:
                xyz, tri, _ = triangular(s)
            except Exception:  # noqa: BLE001 — un sólido que no tesela no aporta paredes
                continue
            nubes.append(muestrear_triangulos(xyz, tri))
    pts = np.concatenate(nubes) if nubes else np.zeros((0, 3))
    return CampoAlcance(pts, caja, z_piso)


def _tramo_libre(tr, p, u, propias: set) -> float:
    """Cuánto sale la mano desde `p` en la dirección `u` sin cruzar un sólido ajeno al peligro
    (lo del peligro se atraviesa: tocarlo ya es llegar)."""
    t_min = 0.0
    while True:
        h = tr.primero(p, u, ALCANCE_DESDE_MUNECA_MM, t_min)
        if h is None:
            return ALCANCE_DESDE_MUNECA_MM
        if h[1] not in propias:
            return h[0]
        t_min = h[0] + 1e-3


def sondas_con_codo(tr, campo, peligro: dict, n_direcciones: int = 64) -> tuple[list[dict], float]:
    """Las sondas con el brazo doblado de un peligro → ([sonda], ms), con el formato de
    `calidad_sondas.evaluar_peligro` (las que alcanzan llevan además `codo` y su profundidad)."""
    t0 = time.perf_counter()
    objetivos = peligro.get("objetivos") or []
    n = n_direcciones
    if objetivos and len(objetivos) * n > MAX_SONDAS_CODO:
        n = max(16, MAX_SONDAS_CODO // len(objetivos))
    propias = set(peligro["piezas"])
    forman = propias | set(peligro.get("forman", ()))
    cuna = bool(peligro.get("cuna"))
    sondas = []
    for p in objetivos:
        for u in direcciones(n):
            libre = _tramo_libre(tr, p, u, propias)
            codo, prof = None, None
            s = 0.0
            while s <= libre and s <= ALCANCE_DESDE_MUNECA_MM:
                q = tuple(p[i] + s * u[i] for i in range(3))
                prof = campo.profundidad(q)
                if prof is not None:
                    codo = q
                    break
                s += PASO_TRAMO_MM
            if codo is None:
                sondas.append({"alcanza": False, "bloquea": [], "motivo": "el brazo no llega"})
                continue
            d = tuple(-c for c in u)  # del codo hacia el objetivo
            hit = tr.primero(codo, d, s + 0.5)
            t_llega = hit[0] if hit is not None else s
            if cuna and s - t_llega > TOQUE_CUNA_MM:
                sondas.append({"alcanza": False, "bloquea": [],
                               "motivo": "toca el tambor lejos de la cuña"})
                continue

            def haces(ancho, o=codo, d=d, t_llega=t_llega):
                out = []
                for off in desplazamientos(ancho, d):
                    oo = tuple(o[i] + off[i] for i in range(3))
                    h = tr.primero(oo, d, t_llega)
                    out.append(h[0] if h is not None and h[1] not in forman else None)
                return out

            v = veredicto(t_llega, 0.0, prof, haces)
            if not v["alcanza"]:
                sondas.append({"alcanza": False, "bloquea": [], "motivo": v["motivo"]})
                continue
            sondas.append({
                "alcanza": True, "via": "brazo doblado", "objetivo": [round(c, 1) for c in p],
                "direccion": [round(c, 3) for c in d],
                "codo": [round(c, 1) for c in codo], "profundidad_codo_mm": round(prof, 1),
                "toca": [round(codo[i] + t_llega * d[i], 1) for i in range(3)],
                "pieza_tocada": hit[1] if hit is not None else None,
                "distancia_mm": v.get("profundidad_mm"), "abertura_mm": v.get("abertura_mm"),
                "sr_mm": v.get("sr_mm"), "sr_requerida_mm": v.get("sr_requerida_mm"),
            })
    return sondas, (time.perf_counter() - t0) * 1000.0
