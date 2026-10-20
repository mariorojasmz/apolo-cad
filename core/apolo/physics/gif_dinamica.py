"""GIF de la simulación dinámica (V8.2 D9/D10): la máquina en marcha, con el render de siempre.

Pinta con `kernel/render_vivo.EscenaViva` —el mismo aspecto que `render_view`, sacado de
`render_comun`— y una sola ventana off-screen para todo el GIF: cada pieza es un actor creado
una vez y por fotograma sólo cambian las poses (`mover`), sin re-teselar. El GIF corre a tiempo
REAL: cada fotograma dura lo que separa sus instantes simulados.

Dos fases, como la simulación (V6.2c):
- `extraer_gif_dinamica` (el caller sostiene `STATE_LOCK`): teselado OCCT y colores → datos
  puros. La API lo llama en la MISMA adquisición que `prepare_dynamics`: el dibujo es del mismo
  documento que la física.
- `render_dynamics_gif` (FUERA de `STATE_LOCK`): toma `RENDER_LOCK` y sólo usa VTK y Pillow.

Las piezas de un cuerpo de junta se mueven con T(t) = P(t)·P(0)⁻¹ (P = pose del cuerpo en la
salida de la dinámica); cada producto es su caja en la pose del fotograma, desde que entra.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import NamedTuple

MAX_FOTOGRAMAS_GIF = 90
_MS_MIN = 20   # ms por fotograma: debajo de esto los visores de GIF lo frenan a 100 ms

# vértices (signos) y triángulos de una caja unitaria centrada (normales hacia afuera)
_SIGNOS = [(sx, sy, sz) for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)]
_TRIS = [(0, 2, 1), (1, 2, 3), (4, 5, 6), (5, 7, 6), (0, 1, 4), (1, 5, 4),
         (2, 6, 3), (3, 6, 7), (0, 4, 2), (2, 4, 6), (1, 3, 5), (3, 7, 5)]


@dataclass
class EscenaGif:
    """Datos puros para el GIF: piezas teseladas (`PiezaViva`), su color y su cuerpo."""
    piezas: list
    colores: dict      # id → hex
    cuerpo_de: dict    # id de pieza → cuerpo de junta que la mueve
    apariencias: dict | None = None   # id → acabado (`services/apariencia`): color y brillo


def extraer_gif_dinamica(scene, piezas_cuerpo: list, colores: dict | None = None, *,
                         apariencias: dict | None = None) -> EscenaGif:
    """FASE OCCT (bajo `STATE_LOCK`). `piezas_cuerpo` es la salida `piezas` de la dinámica
    (`[{id, name}]`: pieza → cuerpo); `colores`, los del documento (ganan a la paleta, como en
    el viewport); `apariencias`, la tabla de acabados del visor ya aplicada (gana a `colores`).
    Lo oculto no se dibuja aunque la física lo cuente: ocultar es de la vista."""
    from apolo.kernel.render_vivo import colores_fijos, extraer_piezas

    return EscenaGif(piezas=extraer_piezas(scene, apariencias),
                     colores=colores_fijos(scene, colores),
                     cuerpo_de={p["id"]: p["name"] for p in piezas_cuerpo},
                     apariencias=apariencias)


def _fotogramas_gif(frames: list, maximo: int) -> list:
    """Submuestreo parejo a ≤ `maximo` fotogramas (más el último, si el paso lo saltó)."""
    paso = max(1, math.ceil(len(frames) / max(2, maximo)))
    sel = frames[::paso]
    if sel[-1] is not frames[-1]:
        sel.append(frames[-1])
    return sel


class _Punto(NamedTuple):
    """Vértice con la interfaz del teselado de build123d (`.X/.Y/.Z`), que lee `render_comun`."""
    X: float
    Y: float
    Z: float


def _duraciones(sel: list) -> list[int]:
    """ms de cada fotograma para que el GIF corra a tiempo REAL. El GIF guarda centésimas: se
    redondea el tiempo ACUMULADO (no cada paso), así el error no se suma a lo largo del GIF."""
    ts = [fr["t"] for fr in sel]
    medio = (ts[-1] - ts[0]) / max(1, len(ts) - 1)
    marcas = [round((t - ts[0]) * 100) * 10 for t in ts + [ts[-1] + medio]]
    return [max(_MS_MIN, b - a) for a, b in zip(marcas, marcas[1:])]


def _caja(nombre: str, dims, forma):
    """Malla de un producto centrada en su origen; `forma` es su identidad para `aplicar`."""
    from apolo.kernel.render_vivo import PiezaViva

    vertices = [_Punto(*(s * d / 2 for s, d in zip(signos, dims))) for signos in _SIGNOS]
    return PiezaViva(nombre, forma, vertices, _TRIS, 1.0)


def _bbox(esc: EscenaGif, relativas: list, tam: dict, sel: list):
    """Caja de encuadre FIJA de todo el recorrido (si no, la cámara «respira»)."""
    import numpy as np

    from apolo.kernel.render_comun import bounds_malla

    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for p in esc.piezas:
        mn, mx = bounds_malla(p.vertices)
        cuerpo = esc.cuerpo_de.get(p.id)
        if cuerpo is None:
            lo, hi = np.minimum(lo, mn), np.maximum(hi, mx)
            continue
        esquinas = np.array([[(mn, mx)[s][k] for k, s in enumerate(b)] for b in np.ndindex(2, 2, 2)])
        for rel in relativas:
            t = rel.get(cuerpo)
            pts = esquinas if t is None else esquinas @ t[:3, :3].T + t[:3, 3]
            lo, hi = np.minimum(lo, pts.min(axis=0)), np.maximum(hi, pts.max(axis=0))
    for fr in sel:
        for nombre, pose in fr["poses"].items():
            if nombre in tam:
                c = np.array([pose[0][3], pose[1][3], pose[2][3]])
                r = max(tam[nombre]) / 2 * math.sqrt(3)
                lo, hi = np.minimum(lo, c - r), np.maximum(hi, c + r)
    if not np.isfinite(lo).all():
        raise ValueError("Nada que animar: no hay piezas visibles ni productos")
    return lo, hi


def _rotulo(img, texto: str) -> None:
    from PIL import ImageDraw, ImageFont

    try:
        fuente = ImageFont.load_default(size=max(12, img.height // 24))
    except TypeError:   # Pillow < 10.1: la fuente de mapa de bits, sin tamaño
        fuente = ImageFont.load_default()
    ImageDraw.Draw(img).text((10, 8), texto, fill=(30, 35, 48), font=fuente)


def render_dynamics_gif(esc: EscenaGif, productos: list, frames: list, *, view: str = "iso",
                        size_px: int = 640, max_fotogramas: int = MAX_FOTOGRAMAS_GIF) -> bytes:
    """FASE VTK (fuera de `STATE_LOCK`, toma `RENDER_LOCK`): el GIF de la marcha. ValueError si
    no hay nada que animar; RuntimeError si falta Pillow; lo que lance VTK sin contexto OpenGL
    sube tal cual (la API lo vuelve 503, como `motion_gif`)."""
    import numpy as np

    from apolo.kernel.render_vivo import EscenaViva
    from apolo.kernel.render_vtk import RENDER_LOCK

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow no está instalado: `pip install pillow` para el GIF") from exc

    if not frames:
        raise ValueError("Nada que animar: la simulación no devolvió fotogramas")
    sel = _fotogramas_gif(frames, max_fotogramas)
    pose0 = frames[0]["poses"]
    inv0 = {c: np.linalg.inv(np.asarray(pose0[c], float)) for c in set(esc.cuerpo_de.values())
            if c in pose0}
    relativas = [{c: np.asarray(fr["poses"][c], float) @ inv for c, inv in inv0.items()}
                 for fr in sel]
    tam = {p["name"]: (p["w"], p["d"], p["h"]) for p in productos}
    cajas = {n: _caja(n, dims, object()) for n, dims in tam.items()}
    lo, hi = _bbox(esc, relativas, tam, sel)
    ancho = max(2, int(size_px) // 2 * 2)
    alto = max(2, int(size_px * 0.75) // 2 * 2)

    imagenes = []
    with RENDER_LOCK, EscenaViva((lo, hi), esc.colores, ancho=ancho, alto=alto, view=view,
                                 apariencias=esc.apariencias) as viva:
        for k, fr in enumerate(sel):
            activos = [n for n in fr["poses"] if n in cajas]
            viva.aplicar(esc.piezas + [cajas[n] for n in activos])
            for p in esc.piezas:
                cuerpo = esc.cuerpo_de.get(p.id)
                if cuerpo in relativas[k]:
                    viva.mover(p.id, relativas[k][cuerpo])
            for n in activos:
                viva.mover(n, fr["poses"][n])
            img = Image.fromarray(viva.fotograma())
            _rotulo(img, f"t = {fr['t']:.2f} s · {len(activos)} producto(s)")
            imagenes.append(img)
    out = io.BytesIO()
    imagenes[0].save(out, format="GIF", save_all=True, append_images=imagenes[1:],
                     duration=_duraciones(sel), loop=0, optimize=True)
    return out.getvalue()
