"""La forma REAL de la faja para el visor (visor-realista D6): matemática PURA, sin OCCT.

La banda del CAD es un sólido rígido (el lazo tenso del super-comando o uno hecho a mano). En la
máquina andando la banda abraza sus tambores y, en el ramal de RETORNO, cuelga entre apoyos.
Esto calcula esa ruta en el PLANO de la faja (u = marcha, w = normal hacia arriba, ambos ⟂ al
eje de los tambores), en mm:

- **Envolvente**: la línea media de la banda sigue el casco convexo de los tambores y rodillos
  que quedan DENTRO del lazo (radio + espesor/2): arcos sobre cada uno y tramos tangentes. Los
  círculos se muestrean y el casco es el de esos puntos (monótona de Andrew), así un lazo de
  cualquier número de tambores sale igual.
- **Apoyos por afuera**: un rodillo de retorno (o un travesaño) bajo el ramal de retorno que toca
  su cara exterior (holgura ≤ `TOQUE_MM`) parte el tramo; si lo empuja hacia adentro, la banda
  pasa por él.
- **Comba**: entre apoyos del ramal de retorno la banda cuelga con la parábola de la catenaria,
  f = w·l²/(8·T) (w = peso por largo, T = tensión), con dos topes: el de CEMA para una banda bien
  tensada (2 % del vano: la tensión del tensor no se modela, el tensor la debe dar) y la holgura
  con lo que hay debajo (la banda no atraviesa un travesaño).

Desde el ajuste D13 de fabrica-de-publicaciones la ruta sale de la SECCIÓN del sólido de la
banda (`ruta_faja_modelo.py`): el casco convexo de aquí es sólo el RESPALDO cuando esa sección no
da un lazo cerrado (un drive central en Ω no es convexo). La comba (`_vano`) es de las dos.

El recorrido es ANTIHORARIO en (u, w): con w hacia arriba, el ramal superior va hacia −u. La
normal hacia AFUERA de un tramo es la derecha del sentido de recorrido.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Comba máxima de un vano como fracción de su largo: CEMA recomienda tensar la banda para no
#: pasar del 2 % entre apoyos (con 3 % ya se derrama el material y patina).
COMBA_CEMA = 0.02
#: Holgura (mm) entre la cara exterior de la banda y una pieza de afuera para contarla APOYO.
TOQUE_MM = 1.0
#: Separación (mm) de los puntos de un vano que cuelga.
PASO_COMBA_MM = 25.0
#: Un vano más corto que esto no cuelga (mm).
VANO_MIN_MM = 80.0
#: Tolerancia de redondez del encuadre de una pieza (fracción): Δu ≈ Δw.
TOL_REDONDA = 0.03
#: Fracción del ancho de la banda que una pieza tiene que cubrir a lo largo del eje para contar.
CUBRE_MIN = 0.5
#: Espesor de banda si no sale de la geometría (mm).
ESPESOR_DEFECTO_MM = 3.0


@dataclass(frozen=True)
class PiezaPlano:
    """Encuadre de una pieza en el marco de la faja (mm): u a lo largo de la marcha, w normal, v a
    lo largo del eje. `redonda`: su sección ⟂ al eje es un círculo (tambor, rodillo, eje)."""

    pieza: str
    u0: float
    u1: float
    w0: float
    w1: float
    v0: float
    v1: float
    redonda: bool = False

    @property
    def centro(self) -> tuple[float, float]:
        return ((self.u0 + self.u1) / 2.0, (self.w0 + self.w1) / 2.0)

    @property
    def radio(self) -> float:
        return (self.u1 - self.u0 + self.w1 - self.w0) / 4.0


@dataclass
class RutaFaja:
    puntos: list                  # [(u, w)] línea media, antihoraria, sin repetir el primero
    espesor: float
    largo_mm: float
    envueltos: list               # [{pieza, u, w, r, abrazamiento_deg}] dentro del lazo, en orden
    apoyos_fuera: list            # [{pieza, u, w, r}] rodillos redondos que apoyan por afuera
    tramos: list = field(default_factory=list)   # vanos que cuelgan: {largo_mm, comba_mm, limita}
    # ajuste D13: la línea media del MODELO (sección del sólido) de la que sale la ruta, los
    # tramos rectos que cuelgan [(i, j)] en sus índices (j = n es el cierre) y de dónde salió
    modelo: list | None = None
    combables: list = field(default_factory=list)
    origen: str = "casco"


def encuadre_cuadrado(du: float, dw: float) -> bool:
    """Δu ≈ Δw: condición NECESARIA de una sección circular (la suficiente la mide quien tiene la
    geometría: el encuadre girado 45° tampoco crece)."""
    return du > 0 and dw > 0 and abs(du - dw) <= TOL_REDONDA * max(du, dw)


def _casco(puntos: list) -> list[int]:
    """Índices del casco convexo antihorario (monótona de Andrew); colineales fuera."""
    orden = sorted(range(len(puntos)), key=lambda i: (puntos[i][0], puntos[i][1]))

    def giro(o, a, b):
        return ((puntos[a][0] - puntos[o][0]) * (puntos[b][1] - puntos[o][1])
                - (puntos[a][1] - puntos[o][1]) * (puntos[b][0] - puntos[o][0]))

    def media(indices):
        out: list[int] = []
        for i in indices:
            while len(out) >= 2 and giro(out[-2], out[-1], i) <= 1e-9:
                out.pop()
            out.append(i)
        return out

    abajo, arriba = media(orden), media(list(reversed(orden)))
    return abajo[:-1] + arriba[:-1]


def _muestras(r: float) -> int:
    return int(min(360, max(48, math.ceil(2.0 * math.pi * r / 4.0))))


def envolvente(circulos: list[tuple[float, float, float]]) -> list[tuple[float, float, int]]:
    """Casco convexo de círculos (u, w, r): [(u, w, índice del círculo)] antihorario, empezando
    en el primer punto de un círculo después de un tramo (así ningún arco queda partido)."""
    pts, dueno = [], []
    for k, (cu, cw, r) in enumerate(circulos):
        n = _muestras(r)
        for i in range(n):
            a = 2.0 * math.pi * i / n
            pts.append((cu + r * math.cos(a), cw + r * math.sin(a)))
            dueno.append(k)
    idx = _casco(pts)
    if len({dueno[i] for i in idx}) > 1:
        k0 = next(j for j in range(len(idx)) if dueno[idx[j]] != dueno[idx[j - 1]])
        idx = idx[k0:] + idx[:k0]
    return [(pts[i][0], pts[i][1], dueno[i]) for i in idx]


def _espesor(banda: PiezaPlano, dentro: list[PiezaPlano], volumen_mm3: float | None) -> float:
    """Banda menos tambores: del tope (o del fondo) de la banda al de cada tambor, el MENOR que
    tenga sentido (un tambor más chico deja más; uno que se mete en la banda —el engomado del
    super-comando— da negativo y no cuenta). Si ninguno sirve, volumen / (ancho · largo)."""
    cands = []
    for p in dentro:
        cands += [banda.w1 - (p.centro[1] + p.radio), (p.centro[1] - p.radio) - banda.w0]
    validos = [t for t in cands if 0.3 <= t <= 30.0]
    if validos:
        return min(validos)
    ancho = banda.v1 - banda.v0
    if volumen_mm3 and ancho > 0:
        t = ESPESOR_DEFECTO_MM
        for _ in range(2):
            casco = envolvente([(*p.centro, p.radio + t / 2.0) for p in dentro])
            largo = sum(math.dist(casco[i][:2], casco[(i + 1) % len(casco)][:2]) for i in range(len(casco)))
            t = volumen_mm3 / (ancho * largo)
        if 0.3 <= t <= 30.0:
            return t
    return ESPESOR_DEFECTO_MM


def clasificar(banda: PiezaPlano, piezas: list[PiezaPlano]) -> tuple[list, list]:
    """(dentro, afuera): las piezas redondas cuyo centro cae dentro del encuadre de la banda son
    los tambores que abraza; el resto que cubre su ancho, obstáculos de afuera (o del interior,
    que la comba ignora sola). Una pieza que no cubre `CUBRE_MIN` del ancho no cuenta."""
    ancho = banda.v1 - banda.v0
    dentro, afuera = [], []
    for p in piezas:
        if p.pieza == banda.pieza:
            continue
        cubre = min(p.v1, banda.v1) - max(p.v0, banda.v0)
        if ancho <= 0 or cubre < CUBRE_MIN * ancho:
            continue
        cu, cw = p.centro
        if p.redonda and banda.u0 < cu < banda.u1 and banda.w0 < cw < banda.w1:
            dentro.append(p)
        else:
            afuera.append(p)
    return dentro, afuera


def _perfil(p: PiezaPlano) -> list[tuple[float, float]]:
    """Puntos del contorno de un obstáculo en el plano: círculo o bordes de su caja c/20 mm."""
    if p.redonda:
        (cu, cw), r = p.centro, p.radio
        return [(cu + r * math.cos(2 * math.pi * i / 72), cw + r * math.sin(2 * math.pi * i / 72))
                for i in range(72)]
    out = []
    for (a, b) in (((p.u0, p.w0), (p.u1, p.w0)), ((p.u1, p.w0), (p.u1, p.w1)),
                   ((p.u1, p.w1), (p.u0, p.w1)), ((p.u0, p.w1), (p.u0, p.w0))):
        n = max(1, int(math.ceil(math.dist(a, b) / 20.0)))
        out += [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n)]
    return out


def _vano(p0, p1, espesor, afuera, peso_n_mm, tension_n, puntos_obst):
    """Puntos interiores de un tramo de retorno que cuelga + sus vanos (entre apoyos)."""
    largo = math.dist(p0, p1)
    tx, tw = (p1[0] - p0[0]) / largo, (p1[1] - p0[1]) / largo
    nx, nw = tw, -tx   # afuera = derecha del recorrido
    # cada obstáculo, en (x a lo largo del tramo, y hacia afuera DESDE la cara exterior)
    perfiles = []
    for p, pts in zip(afuera, puntos_obst):
        loc = [((q[0] - p0[0]) * tx + (q[1] - p0[1]) * tw,
                (q[0] - p0[0]) * nx + (q[1] - p0[1]) * nw - espesor / 2.0) for q in pts]
        loc = [(x, y) for x, y in loc if 0.0 < x < largo]
        if not loc:
            continue
        cerca = min(loc, key=lambda q: q[1])
        if cerca[1] < -(espesor + 5.0):   # del interior del lazo o que la atraviesa
            continue
        perfiles.append((p, loc, cerca))
    apoyos = sorted(((c[0], min(c[1], TOQUE_MM), p) for p, _l, c in perfiles if c[1] <= TOQUE_MM),
                    key=lambda a: a[0])
    fusion: list = []
    for a in apoyos:                      # dos apoyos pegados (las dos caras de un rodillo) = uno
        if fusion and a[0] - fusion[-1][0] < 30.0:
            if a[1] < fusion[-1][1]:
                fusion[-1] = a
            continue
        fusion.append(a)
    nodos = [(0.0, 0.0, None)] + [a for a in fusion if 20.0 < a[0] < largo - 20.0] + [(largo, 0.0, None)]
    libres = [(x, y) for p, loc, c in perfiles if c[1] > TOQUE_MM for x, y in loc]
    interior, vanos = [], []
    for (xa, ya, pa), (xb, yb, _pb) in zip(nodos, nodos[1:]):
        lv = xb - xa
        comba, limita = 0.0, "corto"
        if lv >= VANO_MIN_MM:
            comba, limita = COMBA_CEMA * lv, "cema"
            if tension_n and peso_n_mm:
                f_t = peso_n_mm * lv * lv / (8.0 * tension_n)
                if f_t < comba:
                    comba, limita = f_t, "tension"
            for x, y in libres:
                if xa < x < xb:
                    s = (x - xa) / lv
                    forma = 4.0 * s * (1.0 - s)
                    techo = (y - (ya + (yb - ya) * s)) / forma if forma > 1e-6 else math.inf
                    if techo < comba:
                        comba, limita = max(0.0, techo), "holgura"
        vanos.append({"largo_mm": round(lv, 1), "comba_mm": round(comba, 2), "limita": limita})
        if pa is not None:
            interior.append((p0[0] + xa * tx + ya * nx, p0[1] + xa * tw + ya * nw))
        n = max(1, int(math.ceil(lv / PASO_COMBA_MM))) if comba > 0.05 else 1
        for i in range(1, n):
            s = i / n
            x = xa + lv * s
            y = ya + (yb - ya) * s + comba * 4.0 * s * (1.0 - s)
            interior.append((p0[0] + x * tx + y * nx, p0[1] + x * tw + y * nw))
    usados = [a[2] for a in nodos[1:-1]]
    return interior, vanos, usados


def ruta_faja(banda: PiezaPlano, piezas: list[PiezaPlano], *, peso_n_mm: float | None = None,
              tension_n: float | None = None, volumen_mm3: float | None = None) -> RutaFaja:
    """La ruta de la línea media de la banda (ver el docstring del módulo).

    Sin dos tambores redondos dentro del lazo se asume un lazo de pista (racetrack) inscrito en
    el encuadre de la banda, con el espesor que da su volumen."""
    dentro, afuera = clasificar(banda, piezas)
    if len(dentro) >= 2:
        t = _espesor(banda, dentro, volumen_mm3)
        circ = [(*p.centro, p.radio + t / 2.0) for p in dentro]
    else:
        alto, largo = banda.w1 - banda.w0, banda.u1 - banda.u0
        r_ext = alto / 2.0
        ancho = banda.v1 - banda.v0
        perim = 2.0 * (largo - alto) + math.pi * alto
        t = (volumen_mm3 / (ancho * perim)) if volumen_mm3 and ancho > 0 and perim > 0 else ESPESOR_DEFECTO_MM
        t = min(max(t, 0.3), r_ext * 0.8)
        wc = (banda.w0 + banda.w1) / 2.0
        circ = [(banda.u0 + r_ext, wc, r_ext - t / 2.0), (banda.u1 - r_ext, wc, r_ext - t / 2.0)]
        dentro = []
    casco = envolvente(circ)
    obst = [_perfil(p) for p in afuera]
    puntos, tramos, apoyos = [], [], []
    n = len(casco)
    for i in range(n):
        u, w, k = casco[i]
        puntos.append((u, w))
        u2, w2, k2 = casco[(i + 1) % n]
        if k2 == k:
            continue
        largo = math.hypot(u2 - u, w2 - w)
        if largo < 1e-6:   # pragma: no cover (degenerado)
            continue
        normal_w = -(u2 - u) / largo   # w de la normal afuera (derecha de (du, dw) = (dw, −du))
        if normal_w < -0.5:   # ramal de retorno: cuelga
            interior, vanos, usados = _vano((u, w), (u2, w2), t, afuera, peso_n_mm, tension_n, obst)
            puntos += interior
            tramos += vanos
            apoyos += usados
    largo_total = sum(math.dist(puntos[i], puntos[(i + 1) % len(puntos)]) for i in range(len(puntos)))
    envueltos = []
    for k, p in enumerate(dentro):
        idx = [j for j, c in enumerate(casco) if c[2] == k]
        if not idx:
            continue
        # abrazamiento = lo que gira la banda entre el tramo que llega y el que sale (no depende
        # de dónde cayeron las muestras del círculo)
        a, b = casco[idx[0] - 1], casco[idx[0]]
        c, d = casco[idx[-1]], casco[(idx[-1] + 1) % n]
        giro = math.atan2(d[1] - c[1], d[0] - c[0]) - math.atan2(b[1] - a[1], b[0] - a[0])
        (cu, cw), r = p.centro, p.radio
        envueltos.append({"pieza": p.pieza, "u": cu, "w": cw, "r": r,
                          "abrazamiento_deg": round(math.degrees(giro % (2 * math.pi)), 1)})
    fuera = []
    for p in apoyos:
        if p.redonda and p.pieza not in {f["pieza"] for f in fuera}:
            fuera.append({"pieza": p.pieza, "u": p.centro[0], "w": p.centro[1], "r": p.radio})
    return RutaFaja(puntos=puntos, espesor=t, largo_mm=largo_total, envueltos=envueltos,
                    apoyos_fuera=fuera, tramos=tramos)
