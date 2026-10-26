"""Calentamiento del aire dentro de una envolvente por el método de IEC/TR 60890 (plan V8.5 D6, F3).

PURO (sólo la biblioteca estándar): las curvas del método, tabuladas, y la cuenta. Lo que lee un
documento (pérdidas, caras cubiertas, alturas de los aparatos) está en `services/tablero_calor.py`.

**Fuente de cada cifra** (`FUENTE`): ABB SACE, «Electrical installation handbook – Vol. 1 –
Protection and control devices», 2.ª ed. (febrero 2004, doc. 1SDC008001D0202), Annex B
«Temperature rise evaluation according to IEC 60890», págs. 292–305 (impresas). Las tablas 4–12 son
idénticas en la 4.ª ed. (marzo 2006, 1SDC010002D0204). ABB declara reproducir **IEC 60890:1987**:
el método NO se verificó contra la edición vigente (IEC TR 60890:2022, que agrega ecuaciones por
curva que sólo están en el texto pago). Cada tabla lleva su número y página; nada sale de memoria.

**El método** (diagrama de flujo, pág. 296):
- Ae = Σ A₀·b (T4: techo libre 1,4, techo cubierto 0,7, cara lateral libre 0,9, cubierta 0,5, piso 0).
- Ae > 1,25 m²: f = h^1,35 / A_b (h alto en m, A_b área de la base en m²).
  - SIN aberturas: d (T5), k (T7), c (T8, por tipo de instalación), x = 0,804.
  - CON aberturas: d (T6), k (T9, por la sección de ENTRADA de aire), c (T10), x = 0,715.
  - Δt₀,₅ = d·k·Pˣ (a media altura) y Δt₁,₀ = c·Δt₀,₅ (arriba).
- Ae ≤ 1,25 m² (sólo SIN aberturas): g = h/w (alto/ancho), k (T11), c (T12), x = 0,804, sin d;
  Δt₀,₅ = k·Pˣ y Δt₀,₇₅ = Δt₁,₀ = c·Δt₀,₅. **La rama chica CON aberturas no existe en el método**:
  se rechaza (`FueraDeDominio`), nunca se extrapola.
- Condiciones (pág. 292): pérdidas repartidas de forma aproximadamente uniforme; Σ de corrientes de
  alimentación ≤ 3150 A; salida de aire ≥ 1,1 × la entrada; a lo sumo 3 tabiques horizontales.
  Ambiente de referencia: 35 °C («as prescribed by the Standard», ejemplo, pág. 305).

**Interpolación** (decisión de F3): LINEAL entre filas y columnas de cada tabla (bilineal en T9 y
T10), como «value interpolated» del ejemplo; fuera del rango tabulado es `FueraDeDominio` con el
rango, nunca una extrapolación (Ae > 11,5 m² sin aberturas: la guía pide partir la envolvente en
secciones ficticias, pág. 296).

**Dos valores dudosos de la guía, conservados tal cual** (decisión de F3, vetable): T8, f = 11,
columna 3 → 1,549 (los pasos de la columna son +0,014 y +0,001 alrededor; con 1,54 o 1,545 la
curva sería pareja: es una lectura de la curva al tabular, pero no se sabe cuál); T9, 300 cm² y
Ae = 6 → 0,115 (los vecinos en fila y en columna interpolan los dos 0,112). Los dos yerran hacia
MÁS calor (c y k mayores), por eso se dejan: corregirlos bajaría la temperatura sin certeza.

**Columnas de la T8** (leídas del texto de la pág. 298 y confirmadas por el ejemplo, que usa la 3
para «separate enclosure for wall-mounting»): 1 aislada, separada por todos lados; 2 primera o
última de una fila exenta; 3 aislada adosada a la pared, o central de una fila exenta; 4 primera o
última de una fila adosada a la pared, o central adosada a la pared con el techo cubierto; 5 central
adosada a la pared (techo libre).
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field

FUENTE = ("ABB SACE, «Electrical installation handbook – Vol. 1 – Protection and control devices», "
          "2.ª ed. 2004 (1SDC008001D0202), Annex B «Temperature rise evaluation according to IEC "
          "60890», págs. 292–305; tablas idénticas en la 4.ª ed. 2006 (1SDC010002D0204)")
METODO = ("IEC 60890:1987 tabulado por ABB SACE (no se verificó contra la edición vigente, IEC TR "
          "60890:2022)")
#: Ambiente de referencia del método (ejemplo de la guía, pág. 305: «as prescribed by the Standard»)
AMBIENTE_C = 35.0
#: Frontera de las dos ramas del método (diagrama, pág. 296; la guía imprime «mm2»: errata, es m²)
AE_RAMA_M2 = 1.25
#: Exponentes x (diagrama, pág. 296)
X_SIN_ABERTURAS = 0.804
X_CON_ABERTURAS = 0.715
#: A lo sumo 3 tabiques horizontales (condiciones, pág. 292)
TABIQUES_MAX = 3

#: T4 (pág. 297): factor de superficie b por tipo de cara
B_TECHO_LIBRE = 1.4
B_TECHO_CUBIERTO = 0.7
B_CARA_LIBRE = 0.9
B_CARA_CUBIERTA = 0.5   # cubierta (el fondo de una envolvente de pared) o lateral de una central
B_PISO = 0.0

#: T5 / T6 (pág. 297): d por número de tabiques horizontales n
D_SIN_ABERTURAS = (1.0, 1.05, 1.15, 1.3)
D_CON_ABERTURAS = (1.0, 1.05, 1.1, 1.15)

#: T7 (pág. 297): k sin aberturas, Ae > 1,25 m² — (Ae m², k)
T7_K = ((1.25, 0.524), (1.5, 0.45), (2, 0.35), (2.5, 0.275), (3, 0.225), (3.5, 0.2), (4, 0.185),
        (4.5, 0.17), (5, 0.16), (5.5, 0.15), (6, 0.14), (6.5, 0.135), (7, 0.13), (7.5, 0.125),
        (8, 0.12), (8.5, 0.115), (9, 0.11), (9.5, 0.105), (10, 0.1), (10.5, 0.095), (11, 0.09),
        (11.5, 0.085))

#: T8 (pág. 298): c sin aberturas, Ae > 1,25 m² — f → (c de las columnas 1…5 del tipo de instalación)
T8_F = (0.6, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10, 10.5, 11, 11.5,
        12, 12.5)
T8_C = (
    (1.225, 1.21, 1.19, 1.17, 1.113), (1.24, 1.225, 1.21, 1.185, 1.14), (1.265, 1.245, 1.23, 1.21, 1.17),
    (1.285, 1.27, 1.25, 1.23, 1.19), (1.31, 1.29, 1.275, 1.25, 1.21), (1.325, 1.31, 1.295, 1.27, 1.23),
    (1.35, 1.33, 1.315, 1.29, 1.255), (1.37, 1.355, 1.34, 1.32, 1.275), (1.395, 1.375, 1.36, 1.34, 1.295),
    (1.415, 1.395, 1.38, 1.36, 1.32), (1.435, 1.415, 1.4, 1.38, 1.34), (1.45, 1.435, 1.42, 1.395, 1.355),
    (1.47, 1.45, 1.435, 1.41, 1.37), (1.48, 1.47, 1.45, 1.43, 1.39), (1.495, 1.48, 1.465, 1.44, 1.4),
    (1.51, 1.49, 1.475, 1.455, 1.415), (1.52, 1.505, 1.49, 1.47, 1.43), (1.535, 1.52, 1.5, 1.48, 1.44),
    (1.55, 1.53, 1.515, 1.49, 1.455), (1.56, 1.54, 1.52, 1.5, 1.47), (1.57, 1.55, 1.535, 1.51, 1.475),
    (1.575, 1.565, 1.549, 1.52, 1.485),  # 1,549: dudoso (docstring), se conserva
    (1.585, 1.57, 1.55, 1.525, 1.49), (1.59, 1.58, 1.56, 1.535, 1.5), (1.6, 1.585, 1.57, 1.54, 1.51))
#: Los tipos de instalación de la T8 (nota de la tabla, pág. 298)
TIPOS = {
    1: "envolvente aislada, separada de todo por todos sus lados",
    2: "primera o última envolvente de una fila exenta",
    3: "envolvente aislada adosada a la pared, o central de una fila exenta",
    4: "primera o última de una fila adosada a la pared, o central adosada a la pared con el techo cubierto",
    5: "envolvente central adosada a la pared (techo libre)",
}

#: T9 (pág. 299): k con aberturas, Ae > 1,25 m² — filas: entrada de aire (cm²); columnas: Ae (m²)
T9_ENTRADA = (50, 100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700)
T9_AE = (1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10, 12, 14)
T9_K = (
    (0.36, 0.33, 0.3, 0.28, 0.26, 0.24, 0.22, 0.208, 0.194, 0.18, 0.165, 0.145, 0.135),
    (0.293, 0.27, 0.25, 0.233, 0.22, 0.203, 0.187, 0.175, 0.165, 0.153, 0.14, 0.128, 0.119),
    (0.247, 0.227, 0.21, 0.198, 0.187, 0.173, 0.16, 0.15, 0.143, 0.135, 0.123, 0.114, 0.107),
    (0.213, 0.196, 0.184, 0.174, 0.164, 0.152, 0.143, 0.135, 0.127, 0.12, 0.11, 0.103, 0.097),
    (0.19, 0.175, 0.165, 0.155, 0.147, 0.138, 0.13, 0.121, 0.116, 0.11, 0.1, 0.095, 0.09),
    (0.17, 0.157, 0.148, 0.14, 0.133, 0.125, 0.118, 0.115, 0.106, 0.1, 0.093, 0.088, 0.084),  # Ae 6: dudoso
    (0.152, 0.141, 0.135, 0.128, 0.121, 0.115, 0.109, 0.103, 0.098, 0.093, 0.087, 0.082, 0.079),
    (0.138, 0.129, 0.121, 0.117, 0.11, 0.106, 0.1, 0.096, 0.091, 0.088, 0.081, 0.078, 0.075),
    (0.126, 0.119, 0.111, 0.108, 0.103, 0.099, 0.094, 0.09, 0.086, 0.083, 0.078, 0.074, 0.07),
    (0.116, 0.11, 0.104, 0.1, 0.096, 0.092, 0.088, 0.085, 0.082, 0.078, 0.073, 0.07, 0.067),
    (0.107, 0.102, 0.097, 0.093, 0.09, 0.087, 0.083, 0.08, 0.078, 0.075, 0.07, 0.068, 0.065),
    (0.1, 0.095, 0.09, 0.088, 0.085, 0.082, 0.079, 0.076, 0.073, 0.07, 0.067, 0.065, 0.063),
    (0.094, 0.09, 0.086, 0.083, 0.08, 0.077, 0.075, 0.072, 0.07, 0.068, 0.065, 0.063, 0.061),
    (0.089, 0.085, 0.08, 0.078, 0.076, 0.074, 0.072, 0.07, 0.068, 0.066, 0.064, 0.062, 0.06))

#: T10 (pág. 299): c con aberturas, Ae > 1,25 m² — filas: entrada (cm², las de T9); columnas: f
T10_F = (1.5, 2, 3, 4, 5, 6, 7, 8, 9, 10)
T10_C = (
    (1.3, 1.35, 1.43, 1.5, 1.57, 1.63, 1.68, 1.74, 1.78, 1.83),
    (1.41, 1.46, 1.55, 1.62, 1.68, 1.74, 1.79, 1.84, 1.88, 1.92),
    (1.5, 1.55, 1.63, 1.69, 1.75, 1.8, 1.85, 1.9, 1.94, 1.97),
    (1.56, 1.61, 1.67, 1.75, 1.8, 1.85, 1.9, 1.94, 1.97, 2.01),
    (1.61, 1.65, 1.73, 1.78, 1.84, 1.88, 1.93, 1.97, 2.01, 2.04),
    (1.65, 1.69, 1.75, 1.82, 1.86, 1.92, 1.96, 2, 2.03, 2.06),
    (1.68, 1.72, 1.78, 1.85, 1.9, 1.94, 1.97, 2.02, 2.05, 2.08),
    (1.71, 1.75, 1.81, 1.87, 1.92, 1.96, 2, 2.04, 2.07, 2.1),
    (1.74, 1.77, 1.83, 1.88, 1.94, 1.97, 2.02, 2.05, 2.08, 2.12),
    (1.76, 1.79, 1.85, 1.9, 1.95, 1.99, 2.04, 2.06, 2.1, 2.13),
    (1.77, 1.82, 1.88, 1.93, 1.97, 2.01, 2.05, 2.08, 2.11, 2.14),
    (1.8, 1.83, 1.88, 1.94, 1.98, 2.02, 2.06, 2.09, 2.12, 2.15),
    (1.81, 1.85, 1.9, 1.95, 1.99, 2.04, 2.07, 2.1, 2.14, 2.17),
    (1.83, 1.87, 1.92, 1.96, 2, 2.05, 2.08, 2.12, 2.15, 2.18))

#: T11 (pág. 300): k sin aberturas, Ae ≤ 1,25 m² — (Ae m², k)
T11_K = ((0.08, 3.973), (0.09, 3.643), (0.1, 3.371), (0.15, 2.5), (0.2, 2.022), (0.25, 1.716),
         (0.3, 1.5), (0.35, 1.339), (0.4, 1.213), (0.45, 1.113), (0.5, 1.029), (0.55, 0.960),
         (0.6, 0.9), (0.65, 0.848), (0.7, 0.803), (0.75, 0.764), (0.8, 0.728), (0.85, 0.696),
         (0.9, 0.668), (0.95, 0.641), (1, 0.618), (1.05, 0.596), (1.1, 0.576), (1.15, 0.557),
         (1.2, 0.540), (1.25, 0.524))

#: T12 (pág. 300): c sin aberturas, Ae ≤ 1,25 m² — (g = alto/ancho, c)
T12_C = ((0, 1), (0.1, 1.02), (0.2, 1.04), (0.3, 1.06), (0.4, 1.078), (0.5, 1.097), (0.6, 1.118),
         (0.7, 1.137), (0.8, 1.156), (0.9, 1.174), (1, 1.188), (1.1, 1.2), (1.2, 1.21), (1.3, 1.22),
         (1.4, 1.226), (1.5, 1.231), (1.6, 1.237), (1.7, 1.24), (1.8, 1.244), (1.9, 1.246), (2, 1.249),
         (2.1, 1.251), (2.2, 1.253), (2.3, 1.254), (2.4, 1.255), (2.5, 1.256), (2.6, 1.257),
         (2.7, 1.258), (2.8, 1.259))


class FueraDeDominio(ValueError):
    """El caso no está en el método (o fuera de sus tablas): el mensaje dice el rango y cómo seguir."""


def _lineal(xs, ys, x: float, que: str, tabla: str) -> float:
    if not xs[0] - 1e-9 <= x <= xs[-1] + 1e-9:
        raise FueraDeDominio(f"{que} = {x:.3g} fuera de la {tabla} ({xs[0]:g}…{xs[-1]:g}): el método "
                             "tabulado no lo cubre y no se extrapola")
    x = min(max(x, xs[0]), xs[-1])
    i = min(max(bisect_right(xs, x) - 1, 0), len(xs) - 2)
    t = (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[i] + t * (ys[i + 1] - ys[i])


def _bilineal(filas, cols, z, a: float, b: float, que_a: str, que_b: str, tabla: str) -> float:
    fila = [_lineal(cols, z[i], b, que_b, tabla) for i in range(len(filas))]
    return _lineal(filas, fila, a, que_a, tabla)


def k_t7(ae: float) -> float:
    return _lineal([p[0] for p in T7_K], [p[1] for p in T7_K], ae, "Ae (m²)", "T7")


def k_t11(ae: float) -> float:
    return _lineal([p[0] for p in T11_K], [p[1] for p in T11_K], ae, "Ae (m²)", "T11")


def c_t8(f: float, columna: int) -> float:
    return _lineal(T8_F, [r[columna - 1] for r in T8_C], f, "f = h^1,35/A_b", f"T8 (columna {columna})")


def c_t12(g: float) -> float:
    return _lineal([p[0] for p in T12_C], [p[1] for p in T12_C], g, "g = alto/ancho", "T12")


def k_t9(entrada_cm2: float, ae: float) -> float:
    return _bilineal(T9_ENTRADA, T9_AE, T9_K, entrada_cm2, ae, "entrada de aire (cm²)", "Ae (m²)", "T9")


def c_t10(entrada_cm2: float, f: float) -> float:
    return _bilineal(T9_ENTRADA, T10_F, T10_C, entrada_cm2, f, "entrada de aire (cm²)", "f = h^1,35/A_b", "T10")


# ── la envolvente ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Envolvente:
    """Una envolvente de UN compartimento. Medidas en mm (alto = vertical). `laterales_cubiertos`
    = 0, 1 o 2 caras laterales tapadas (otra envolvente o una pared al lado); el frente y el fondo
    se dicen aparte (una envolvente de pared tiene el fondo cubierto)."""
    alto_mm: float
    ancho_mm: float
    fondo_mm: float
    techo_cubierto: bool = False
    fondo_cubierto: bool = True
    frente_cubierto: bool = False
    laterales_cubiertos: int = 0
    tabiques: int = 0
    entrada_aire_cm2: float = 0.0   # 0 = sin aberturas de ventilación


@dataclass(frozen=True)
class Cara:
    nombre: str
    A0_m2: float
    b: float

    @property
    def Ae_m2(self) -> float:
        return self.A0_m2 * self.b


def caras(env: Envolvente) -> tuple[Cara, ...]:
    """Las caras con su b (T4); el piso no cuenta (b = 0)."""
    h, w, d = env.alto_mm / 1000.0, env.ancho_mm / 1000.0, env.fondo_mm / 1000.0
    lat = [B_CARA_CUBIERTA if i < env.laterales_cubiertos else B_CARA_LIBRE for i in range(2)]
    return (Cara("techo", w * d, B_TECHO_CUBIERTO if env.techo_cubierto else B_TECHO_LIBRE),
            Cara("frente", w * h, B_CARA_CUBIERTA if env.frente_cubierto else B_CARA_LIBRE),
            Cara("fondo", w * h, B_CARA_CUBIERTA if env.fondo_cubierto else B_CARA_LIBRE),
            Cara("lateral 1", d * h, lat[0]), Cara("lateral 2", d * h, lat[1]))


def superficie_efectiva(env: Envolvente) -> float:
    """Ae = Σ A₀·b (m²)."""
    return sum(c.Ae_m2 for c in caras(env))


def tipo_instalacion(env: Envolvente) -> int:
    """La columna de la T8 por las caras cubiertas (decisión de F3, vetable): sin el fondo cubierto,
    1 (aislada, separada de todo) con los laterales libres o 2 (extremo de fila exenta) con uno
    tapado o 3 (central de fila exenta) con los dos; con el fondo cubierto (de pared), 3 con los
    laterales libres, 4 con uno tapado, y con los dos, 4 si el techo está cubierto y 5 si no."""
    n = env.laterales_cubiertos
    if not env.fondo_cubierto:
        return (1, 2, 3)[n]
    if n == 0:
        return 3
    if n == 1:
        return 4
    return 4 if env.techo_cubierto else 5


@dataclass(frozen=True)
class Calentamiento:
    """El resultado del método: el calentamiento del aire (K) a media altura y arriba (`h_arriba`
    es la fracción del alto desde donde vale el de arriba: 1,0, o 0,75 en la rama chica)."""
    P_W: float
    Ae_m2: float
    rama: str                 # «Ae > 1,25 m², sin aberturas» …
    k: float
    c: float
    d: float
    x: float
    dt_media_K: float
    dt_arriba_K: float
    h_arriba: float
    f: float | None = None
    g: float | None = None
    tipo: int | None = None   # columna de la T8 (rama grande sin aberturas)
    caras: tuple = ()
    tablas: tuple = ()        # las tablas usadas («T7 (pág. 297)» …)
    citas: tuple = field(default=(FUENTE,))

    def delta_a(self, h: float) -> float:
        """El calentamiento a la altura relativa `h` (0 = piso, 1 = techo), decisión de F3: debajo de
        la mitad, el de media altura (el método no da otro; el aire de abajo está más frío: lado
        seguro); entre la mitad y `h_arriba`, lineal; de ahí arriba, el de arriba."""
        if h <= 0.5:
            return self.dt_media_K
        if h >= self.h_arriba:
            return self.dt_arriba_K
        t = (h - 0.5) / (self.h_arriba - 0.5)
        return self.dt_media_K + t * (self.dt_arriba_K - self.dt_media_K)


def calentamiento(env: Envolvente, P_W: float) -> Calentamiento:
    """El método completo (diagrama, pág. 296). `FueraDeDominio` si el caso no está en el método."""
    if P_W < 0:
        raise ValueError(f"pérdidas negativas ({P_W} W)")
    if not 0 <= env.tabiques <= TABIQUES_MAX:
        raise FueraDeDominio(f"{env.tabiques} tabiques horizontales: el método admite hasta {TABIQUES_MAX} "
                             "(condiciones, pág. 292)")
    ae = superficie_efectiva(env)
    hh, w, dd = env.alto_mm / 1000.0, env.ancho_mm / 1000.0, env.fondo_mm / 1000.0
    cs = caras(env)
    abre = env.entrada_aire_cm2 > 0
    if ae <= AE_RAMA_M2:
        if abre:
            raise FueraDeDominio(
                f"Ae = {ae:.2f} m² ≤ {AE_RAMA_M2:g} m² con aberturas de ventilación: el método no tiene esa "
                "rama (diagrama, pág. 296: la rama chica es sólo sin aberturas). Evalúa sin aberturas o "
                "con ventilación forzada")
        g = hh / w
        k, c = k_t11(ae), c_t12(g)
        dt = k * P_W ** X_SIN_ABERTURAS
        return Calentamiento(P_W, ae, f"Ae ≤ {AE_RAMA_M2:g} m², sin aberturas", k, c, 1.0, X_SIN_ABERTURAS,
                             dt, c * dt, 0.75, g=g, caras=cs, tablas=("T4 (pág. 297)", "T11 (pág. 300)",
                                                                      "T12 (pág. 300)"))
    f = hh ** 1.35 / (w * dd)
    if abre:
        d = D_CON_ABERTURAS[env.tabiques]
        k, c = k_t9(env.entrada_aire_cm2, ae), c_t10(env.entrada_aire_cm2, f)
        dt = d * k * P_W ** X_CON_ABERTURAS
        return Calentamiento(P_W, ae, f"Ae > {AE_RAMA_M2:g} m², con aberturas ({env.entrada_aire_cm2:g} cm² de "
                             "entrada)", k, c, d, X_CON_ABERTURAS, dt, c * dt, 1.0, f=f, caras=cs,
                             tablas=("T4", "T6 (pág. 297)", "T9", "T10 (pág. 299)"))
    tipo = tipo_instalacion(env)
    d = D_SIN_ABERTURAS[env.tabiques]
    k, c = k_t7(ae), c_t8(f, tipo)
    dt = d * k * P_W ** X_SIN_ABERTURAS
    return Calentamiento(P_W, ae, f"Ae > {AE_RAMA_M2:g} m², sin aberturas", k, c, d, X_SIN_ABERTURAS, dt, c * dt,
                         1.0, f=f, tipo=tipo, caras=cs,
                         tablas=("T4", "T5", "T7 (pág. 297)", f"T8 columna {tipo} (pág. 298)"))


def entrada_minima(env: Envolvente, P_W: float, dt_max_K: float) -> float | None:
    """La menor sección de ENTRADA de aire de la T9 (cm²) con la que el calentamiento de ARRIBA no
    pasa `dt_max_K` (la salida, ≥ 1,1 veces: condición del método). None si ninguna fila alcanza o si
    la envolvente es de la rama chica (no hay rama con aberturas)."""
    from dataclasses import replace

    if superficie_efectiva(env) <= AE_RAMA_M2:
        return None
    for entrada in T9_ENTRADA:
        try:
            r = calentamiento(replace(env, entrada_aire_cm2=float(entrada)), P_W)
        except FueraDeDominio:
            return None
        if r.dt_arriba_K <= dt_max_K:
            return float(entrada)
    return None
