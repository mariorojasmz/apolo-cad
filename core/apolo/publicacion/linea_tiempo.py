"""La línea de tiempo del video: en qué fotograma empieza cada parte y cuánto pesa cada efecto
en cada fotograma (plan publicacion-tienda, F4). Puro: sin VTK ni Pillow, se prueba solo.

Partes, en orden (las de 0 s se saltan): portada → una por etapa → marcha (si el guion la trae:
la máquina andando, sólo en el navegador, D5 de video-realista) → cifras → órbita → cierre.
Los bordes salen de los segundos ACUMULADOS redondeados a fotogramas, así la suma no deriva:
el video dura exactamente `round(duracion_total × fps)` fotogramas, lo que `sondear` mide.

Efectos (constantes en segundos):
  - fundido desde negro al empezar y a negro al terminar;
  - fundido cruzado al entrar a cada parte que no sea otra etapa (portada → construcción,
    construcción → cifras → órbita → cierre): entre etapas la escena 3D sigue sin corte;
  - rótulo de cada etapa con fundido de entrada y de salida;
  - resaltado de lo que aparece, que se desvanece;
  - órbita lenta y continua durante la construcción y una vuelta completa, suavizada, al final.
"""

from __future__ import annotations

from dataclasses import dataclass

NEGRO_INICIO_S = 0.6
NEGRO_FIN_S = 1.0
TRANSICION_S = 0.6
FUNDIDO_ROTULO_S = 0.5
RESALTE_S = 1.2
#: Órbita de la construcción: lenta, una vuelta cada 90 s.
GRADOS_POR_S = 4.0
#: Cámara: la del preset iso de `render_view` (`kernel/render.VIEW_ANGLES`).
AZIMUT_INICIAL = -55.0
ELEVACION = 22.0


@dataclass(frozen=True)
class Tramo:
    """Una parte del video: fotogramas [inicio, fin)."""

    parte: str  # portada | etapa | marcha | cifras | orbita | cierre
    inicio: int
    fin: int
    etapa: int | None = None  # índice en guion["etapas"]

    @property
    def n(self) -> int:
        return self.fin - self.inicio


def tramos(g: dict) -> list[Tramo]:
    """Las partes del guion en fotogramas, con redondeo acumulado."""
    fps = g["video"]["fps"]
    partes = [("portada", None, g["portada"]["duracion_s"])]
    partes += [("etapa", i, e["duracion_s"]) for i, e in enumerate(g["etapas"])]
    if g.get("marcha"):
        partes.append(("marcha", None, g["marcha"]["duracion_s"]))
    partes += [(p, None, g[p]["duracion_s"]) for p in ("cifras", "orbita", "cierre")]
    out, t = [], 0.0
    for parte, i, dur in partes:
        a = round(t * fps)
        t += dur
        b = round(t * fps)
        if b > a:
            out.append(Tramo(parte, a, b, i))
    return out


def total_fotogramas(plan: list[Tramo]) -> int:
    return plan[-1].fin if plan else 0


def reparto(a: int, b: int, pesos: list[float]) -> list[tuple[int, int]]:
    """[a, b) repartido por peso con redondeo acumulado (un tramo puede quedar vacío)."""
    total = sum(pesos)
    if not pesos:
        return []
    if total <= 0:
        pesos, total = [1.0] * len(pesos), float(len(pesos))
    out, acumulado, inicio = [], 0.0, a
    for w in pesos:
        acumulado += w
        fin = a + round((b - a) * acumulado / total)
        out.append((inicio, fin))
        inicio = fin
    return out


def apariciones(a: int, b: int, m: int) -> list[int]:
    """El fotograma en que aparece cada una de las `m` sub-listas de un paso en [a, b): la
    primera al empezar y las demás escalonadas parejas."""
    return [a + (i * (b - a)) // m for i in range(m)]


def _rampa(x: float) -> float:
    return min(max(x, 0.0), 1.0)


def opacidad_rotulo(f: int, a: int, b: int, fps: int) -> float:
    """Rótulo de la etapa [a, b): entra y sale con un fundido (más corto si la etapa lo es)."""
    n = max(1.0, min(FUNDIDO_ROTULO_S * fps, (b - a) / 3))
    return _rampa(min((f - a + 1) / n, (b - f) / n))


def entrada(f: int, a: int, fps: int) -> float | None:
    """Mezcla del fundido cruzado al entrar a una parte en `a`: de 0 (la imagen anterior) a 1
    (la nueva); None fuera de la transición."""
    n = round(TRANSICION_S * fps)
    if n <= 0 or not a <= f < a + n:
        return None
    return (f - a + 1) / (n + 1)


def luz(f: int, total: int, fps: int) -> float:
    """1 salvo en el fundido desde negro del principio y a negro del final."""
    n0, n1 = max(1, round(NEGRO_INICIO_S * fps)), max(1, round(NEGRO_FIN_S * fps))
    return _rampa(min((f + 1) / n0, (total - f) / n1, 1.0))


def resalte(f: int, f0: int, fps: int) -> float:
    """Intensidad del resaltado de lo que apareció en `f0`: 1 → 0 en RESALTE_S."""
    return _rampa(1.0 - (f - f0) / max(1.0, RESALTE_S * fps))


def azimut_construccion(f: int, inicio: int, fps: int) -> float:
    return AZIMUT_INICIAL + GRADOS_POR_S * (f - inicio) / fps


def azimut_orbita(f: int, a: int, b: int, desde: float) -> float:
    """Una vuelta completa en [a, b), suavizada (arranca y frena sin saltos)."""
    x = (f - a) / max(1, b - a)
    return desde + 360.0 * x * x * (3 - 2 * x)
