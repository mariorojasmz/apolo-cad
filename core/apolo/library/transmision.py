"""Matemática PURA de la transmisión por cadena de rodillos (ISO 606 serie B y ANSI B29.1).

Sin OCCT ni `Document`: la usan los builders del catálogo (`builders_transmision.py`), el
comando de cadena y la regla de ingeniería, que así no duplican cuentas (plan
`docs/plans/cadenas-pinones.md`, D5, D7, D9).

Unidades: mm, rpm, HP y kW; ángulos en RADIANES salvo donde el nombre dice `_deg`.

MARCO DEL LAZO (`camino_paso`, `rodillos_del_lazo`), en 2D: piñón A (el motriz) con su eje en el
origen, piñón B con su eje en (centros, 0); los dos giran alrededor de +Z. El lazo se recorre en
sentido ANTIHORARIO: A por su lado izquierdo de arriba hacia abajo, tramo INFERIOR de A a B, B
por su lado derecho de abajo hacia arriba y tramo SUPERIOR de B a A. La normal hacia AFUERA de
un tramo es la derecha del sentido de recorrido. La `fase` de un piñón es el ángulo, en ese
marco, del centro de UNO de sus asientos (el ancla `fase` del catálogo la da).

Fuentes (detalle en el plan, § «Lo que se revisó»): fórmulas de ISO 606 transcritas en
patentes, Tsubaki «Chain Drive Selection» y la tabla ACA 2001 (ASME B29.1, 15 000 h).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Holgura (mm) entre capas de la cadena que en la realidad se tocan (rodillo ↔ placa interior,
#: placa interior ↔ exterior): sin ella el modelo tendría caras tangentes (regla de builders).
HOLGURA_CAPA_MM = 0.1

#: rpm de las columnas de la tabla ACA.
RPM_TABLA_ACA: tuple[float, ...] = (10.0, 25.0, 50.0, 100.0, 300.0, 1000.0)

#: Potencia nominal de la cadena ASA 40-1 (HP) por dientes del piñón chico y rpm (tabla ACA,
#: adaptada de ASME B29.1 para 15 000 h). Para 08B no hay tabla numérica publicada.
POTENCIA_ASA40_1_HP: dict[int, tuple[float, ...]] = {
    14: (0.07, 0.17, 0.34, 0.66, 1.88, 5.98),
    15: (0.08, 0.19, 0.36, 0.70, 2.02, 6.41),
    16: (0.08, 0.20, 0.39, 0.75, 2.15, 6.84),
    17: (0.09, 0.21, 0.41, 0.80, 2.29, 7.27),
    18: (0.09, 0.22, 0.43, 0.84, 2.42, 7.69),
    19: (0.10, 0.24, 0.46, 0.89, 2.56, 8.12),
}

#: Factor de servicio con motor eléctrico (ACA / Tsubaki), por tipo de carga.
FACTOR_SERVICIO: dict[str, float] = {"suave": 1.0, "moderado": 1.3, "fuerte": 1.5}

#: Factor de capacidad por número de hileras (ACA): dos hileras = 1.7 veces una.
FACTOR_HILERAS: dict[int, float] = {1: 1.0, 2: 1.7}

HP_A_KW = 0.745699872


# ------------------------------------------------------------------ geometría del piñón
def diametro_primitivo(paso: float, z: int) -> float:
    """d0 = p / sin(180°/z) (ISO 606 y ANSI B29.1)."""
    _validar_z(z)
    return paso / math.sin(math.pi / z)


def diametro_fondo(paso: float, z: int, rodillo: float) -> float:
    """df = d0 − d1 (nominal ISO 606; el asiento de radio 0.505·d1 lo baja 0.01·d1)."""
    return diametro_primitivo(paso, z) - rodillo


def diametro_exterior_bs(paso: float, z: int, rodillo: float) -> float:
    """da máx = d0 + 1.25·p − d1 (ISO 606). Reproduce el Martin D08B14 (64.44)."""
    return diametro_primitivo(paso, z) + 1.25 * paso - rodillo


def diametro_exterior_ansi(paso: float, z: int) -> float:
    """de = p·(0.6 + cot(180°/z)) (ANSI B29.1). Reproduce los Tsubaki 40B12, 40B14 y 40B60."""
    _validar_z(z)
    return paso * (0.6 + 1.0 / math.tan(math.pi / z))


def forma_diente(z: int, rodillo: float) -> dict:
    """Forma de diente REPRESENTATIVA de ISO 606 que construye el builder `sprocket`:

    - `ri` = radio de asiento mínimo, 0.505·d1, centrado en el punto de paso;
    - `re` = radio de flanco, el MAYOR de los dos límites de la norma, 0.008·d1·(z² + 180);
    - `alfa` = ángulo de asiento máximo, 140° − 90°/z (rad).

    Es la forma de diente MÁXIMA (el hueco mínimo). El flanco es convexo y tangente al asiento
    en el extremo del arco de asiento (centro del flanco sobre la recta que une ese extremo con
    el centro del asiento, del lado del diente). Con α mínimo (120° − 90°/z) los dientes ASA
    de la ficha Tsubaki quedan en punta antes de llegar a su Ø exterior; con α máximo todos los
    del catálogo conservan cresta.
    """
    _validar_z(z)
    return {
        "ri": 0.505 * rodillo,
        "re": 0.008 * rodillo * (z * z + 180.0),
        "alfa": math.radians(140.0 - 90.0 / z),
    }


def _validar_z(z) -> None:
    if int(z) != z or z < 5:
        raise ValueError(f"Número de dientes inválido: {z} (entero ≥ 5)")


# ------------------------------------------------------------------ eslabones y centros
def eslabones_para_centros(paso: float, z1: int, z2: int, centros: float) -> float:
    """Largo de la cadena en eslabones (continuo, sin redondear) para una distancia entre
    centros: L = (z1+z2)/2 + 2C/p + p·((z2−z1)/2π)²/C."""
    if centros <= 0:
        raise ValueError(f"Distancia entre centros inválida: {centros}")
    k = ((z2 - z1) / (2.0 * math.pi)) ** 2
    return (z1 + z2) / 2.0 + 2.0 * centros / paso + paso * k / centros


def centros_para_eslabones(paso: float, z1: int, z2: int, eslabones: float) -> float:
    """Distancia entre centros para un largo de L eslabones (fórmula inversa de Tsubaki):
    C = p/8 · [2L − z1 − z2 + √((2L − z1 − z2)² − (8/π²)(z2 − z1)²)]. Es la inversa EXACTA de
    `eslabones_para_centros`."""
    a = 2.0 * eslabones - z1 - z2
    disc = a * a - (8.0 / math.pi ** 2) * (z2 - z1) ** 2
    if a <= 0 or disc < 0:
        raise ValueError(
            f"{eslabones} eslabones no alcanzan para abrazar piñones de {z1} y {z2} dientes"
        )
    return paso / 8.0 * (a + math.sqrt(disc))


def eslabones_pares(paso: float, z1: int, z2: int, centros: float) -> tuple[int, float]:
    """(L, C_exacto): el menor número PAR de eslabones cuyo centro exacto es ≥ `centros`.
    La diferencia C_exacto − centros es la holgura de redondeo (se publica, no se esconde).
    Impar exigiría eslabón acodado (Renold lo desaconseja; ACA lo desclasifica)."""
    tol = 1e-6
    n = math.ceil(eslabones_para_centros(paso, z1, z2, centros) - tol)
    n += n % 2
    while centros_para_eslabones(paso, z1, z2, n) < centros - tol:
        n += 2
    return n, centros_para_eslabones(paso, z1, z2, n)


def abrazamiento_deg(paso: float, z1: int, z2: int, centros: float) -> float:
    """Ángulo abrazado por la cadena en el piñón CHICO (grados): 180° − 2·asin(ΔR/C), con los
    radios primitivos."""
    r1, r2 = sorted((diametro_primitivo(paso, z1) / 2.0, diametro_primitivo(paso, z2) / 2.0))
    if centros <= r2 - r1:
        raise ValueError(f"Centros {centros:g} mm ≤ diferencia de radios primitivos {r2 - r1:.2f} mm")
    return 180.0 - 2.0 * math.degrees(math.asin((r2 - r1) / centros))


def velocidad_cadena(paso: float, z: int, rpm: float) -> float:
    """Velocidad media de la cadena (m/s) = z·p·n / 60 000."""
    return z * paso * rpm / 60000.0


# ------------------------------------------------------------------ capacidad (ACA)
def potencia_nominal_asa40_1_hp(z: int, rpm: float) -> float | None:
    """Potencia nominal (HP) de la ASA 40-1 por la tabla ACA, interpolando LINEAL en rpm (la
    curva real es apenas cóncava: lineal queda del lado seguro). Fuera de la tabla (z no
    tabulado o rpm fuera de 10–1000) → None: jamás se extrapola una capacidad."""
    fila = POTENCIA_ASA40_1_HP.get(int(z)) if int(z) == z else None
    if fila is None or not RPM_TABLA_ACA[0] <= rpm <= RPM_TABLA_ACA[-1]:
        return None
    for i in range(len(RPM_TABLA_ACA) - 1):
        n0, n1 = RPM_TABLA_ACA[i], RPM_TABLA_ACA[i + 1]
        if rpm <= n1:
            t = (rpm - n0) / (n1 - n0)
            return fila[i] + t * (fila[i + 1] - fila[i])
    return fila[-1]  # pragma: no cover (rpm == 1000 sale en el bucle)


def factor_servicio(servicio: str) -> float:
    """Factor de servicio con motor eléctrico: suave 1.0, moderado 1.3, fuerte 1.5."""
    try:
        return FACTOR_SERVICIO[servicio]
    except KeyError:
        raise ValueError(
            f"Servicio desconocido '{servicio}'; usa uno de {', '.join(FACTOR_SERVICIO)}"
        ) from None


def factor_hileras(hileras: int) -> float:
    """Factor de capacidad por hileras (1 → 1.0, 2 → 1.7)."""
    try:
        return FACTOR_HILERAS[int(hileras)]
    except KeyError:
        raise ValueError(f"Hileras no tabuladas: {hileras} (1 o 2)") from None


# ------------------------------------------------------------------ camino de paso del lazo
@dataclass(frozen=True)
class CaminoPaso:
    """Lazo abierto (tangentes exteriores) sobre los círculos primitivos de A y B."""

    radio_a: float
    radio_b: float
    centros: float
    phi: float              # ángulo de la normal en los puntos tangentes del tramo superior
    abrazamiento_a: float   # rad, arco abrazado en A = 2π − 2·phi
    abrazamiento_b: float   # rad, arco abrazado en B = 2·phi
    tangente_sup: tuple     # ((x, y) en A, (x, y) en B)
    tangente_inf: tuple
    largo_tramo: float      # mm, cada tramo recto entre puntos tangentes
    largo_mm: float         # mm, arcos + tramos sobre los círculos primitivos
    largo_pasos: float      # eslabones, con los arcos medidos en pasos (polígono de paso)


def camino_paso(paso: float, za: int, zb: int, centros: float) -> CaminoPaso:
    """Camino de paso del lazo A–B en el marco del módulo (A en el origen, B en (C, 0))."""
    ra = diametro_primitivo(paso, za) / 2.0
    rb = diametro_primitivo(paso, zb) / 2.0
    if centros <= abs(rb - ra):
        raise ValueError(
            f"Centros {centros:g} mm ≤ diferencia de radios primitivos {abs(rb - ra):.2f} mm: "
            "un piñón queda dentro del otro"
        )
    phi = math.acos((ra - rb) / centros)  # cos φ = (ra − rb)/C ⇒ φ = π/2 + β
    n_sup = (math.cos(phi), math.sin(phi))
    n_inf = (math.cos(phi), -math.sin(phi))
    tramo = math.sqrt(centros * centros - (rb - ra) ** 2)
    th_a, th_b = 2.0 * math.pi - 2.0 * phi, 2.0 * phi
    return CaminoPaso(
        radio_a=ra, radio_b=rb, centros=centros, phi=phi,
        abrazamiento_a=th_a, abrazamiento_b=th_b,
        tangente_sup=((ra * n_sup[0], ra * n_sup[1]), (centros + rb * n_sup[0], rb * n_sup[1])),
        tangente_inf=((ra * n_inf[0], ra * n_inf[1]), (centros + rb * n_inf[0], rb * n_inf[1])),
        largo_tramo=tramo,
        largo_mm=ra * th_a + rb * th_b + 2.0 * tramo,
        largo_pasos=(th_a * za + th_b * zb) / (2.0 * math.pi) + 2.0 * tramo / paso,
    )


# ------------------------------------------------------------------ rodillos del lazo
@dataclass(frozen=True)
class LazoRodillos:
    """Centros de los rodillos de un lazo cerrado, en orden antihorario (marco del módulo)."""

    puntos: tuple            # ((x, y), …), len == eslabones
    asentados_a: tuple       # índices de `puntos` sentados en asientos de A
    asentados_b: tuple       # índices sentados en asientos de B
    pasos_inferior: int      # pasos (eslabones) del tramo inferior, de A a B
    pasos_superior: int      # pasos del tramo superior, de B a A
    separacion_min: float    # mm entre rodillos consecutivos (cierre incluido)
    separacion_max: float


def asientos(radio: float, z: int, fase: float, centro=(0.0, 0.0)) -> list[tuple[float, float]]:
    """Centros de los z asientos de un piñón (vértices de su polígono de paso), antihorario
    desde el de ángulo `fase`."""
    return [(centro[0] + radio * math.cos(fase + 2.0 * math.pi * k / z),
             centro[1] + radio * math.sin(fase + 2.0 * math.pi * k / z)) for k in range(z)]


def _casco_convexo(puntos: list) -> list[int]:
    """Índices de los vértices del casco convexo, antihorario (cadena monótona de Andrew); los
    puntos colineales sobre un lado NO son vértices."""
    orden = sorted(range(len(puntos)), key=lambda i: puntos[i])

    def giro(o, a, b):
        return ((puntos[a][0] - puntos[o][0]) * (puntos[b][1] - puntos[o][1])
                - (puntos[a][1] - puntos[o][1]) * (puntos[b][0] - puntos[o][0]))

    def media_cadena(indices):
        out: list[int] = []
        for i in indices:
            while len(out) >= 2 and giro(out[-2], out[-1], i) <= 1e-9:
                out.pop()
            out.append(i)
        return out

    abajo, arriba = media_cadena(orden), media_cadena(reversed(orden))
    return abajo[:-1] + arriba[:-1]


def _gamma_flecha(n: int, razon: float) -> float:
    """γ ∈ (0, π/n) con sin(nγ)/sin(γ) = razon (cuerda/paso): n cuerdas de un paso sobre un
    arco de circunferencia cuya cuerda total es `razon`·paso. Bisección (f es decreciente)."""
    lo, hi = 1e-12, math.pi / n - 1e-12
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if math.sin(n * mid) / math.sin(mid) > razon:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _tramo(p0, p1, n: int, paso: float) -> list[tuple[float, float]]:
    """Los n−1 rodillos intermedios de un tramo de n pasos entre dos rodillos sentados.

    Si la cuerda es MENOR que n·p (flojo), los rodillos van sobre un arco hacia AFUERA del lazo
    (derecha del recorrido) con cuerdas de exactamente un paso: la flecha muestra la holgura
    sin acercarse a los dientes. Si es mayor (la cadena no alcanza con esas fases: en la
    realidad el piñón libre giraría hasta engranar), van en recta; el primero y el último quedan
    a exactamente un paso de su rodillo sentado —un eslabón que pivota sobre el asiento no toca
    el diente; uno más largo, sí— y el estiramiento se reparte entre los del medio (se publica
    en `separacion_max`). Con n = 1 no hay rodillos intermedios: el eslabón une los dos sentados
    midan lo que midan (sólo pasa con piñones casi tocándose)."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    d = math.hypot(dx, dy)
    if n <= 1:
        return []
    if d >= n * paso - 1e-9:
        if n == 2:
            return [(p0[0] + dx * paso / d, p0[1] + dy * paso / d)]
        s = [paso + (d - 2.0 * paso) * (i - 1) / (n - 2) for i in range(1, n)]
        return [(p0[0] + dx * si / d, p0[1] + dy * si / d) for si in s]
    g = _gamma_flecha(n, d / paso)
    rho = paso / (2.0 * math.sin(g))
    ox, oy = dy / d, -dx / d  # afuera = derecha del recorrido
    h = rho * math.cos(n * g)
    cx = (p0[0] + p1[0]) / 2.0 - ox * h
    cy = (p0[1] + p1[1]) / 2.0 - oy * h
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)

    def punto(signo: float, i: int) -> tuple[float, float]:
        a = a0 + signo * 2.0 * g * i
        return (cx + rho * math.cos(a), cy + rho * math.sin(a))

    def costo(s: float) -> tuple:
        # el sentido que lleva p0 a p1 en n cuerdas; con media vuelta exacta, el que va por afuera
        q = punto(s, max(1, n // 2))
        afuera = (q[0] - (p0[0] + p1[0]) / 2.0) * ox + (q[1] - (p0[1] + p1[1]) / 2.0) * oy
        return (round(math.dist(punto(s, n), p1), 6), -afuera)

    signo = min((1.0, -1.0), key=costo)
    return [punto(signo, i) for i in range(1, n)]


def rodillos_del_lazo(paso: float, za: int, zb: int, centros: float,
                      fase_a: float, fase_b: float, eslabones: int) -> LazoRodillos:
    """Centros de los `eslabones` rodillos de un lazo cerrado A–B (marco del módulo).

    Una cadena tensa sigue el CASCO CONVEXO de los asientos de los dos piñones (los vértices de
    sus polígonos de paso): cada asiento que es vértice del casco lleva un rodillo sentado, y los
    dos lados que unen A con B son los tramos. Así ningún rodillo entra al piñón, con cualquier
    fase (sentar hasta el punto tangente del círculo primitivo no sirve: la recta desde un
    asiento anterior a la tangente corta el piñón). Los pasos restantes se reparten entre los dos
    tramos para que ninguno quede estirado si se puede, y el superior lo más recto posible (la
    holgura va abajo): ver `_tramo`. Total de rodillos == eslabones (un lazo cerrado tiene tantos
    rodillos como pasos).
    """
    if int(eslabones) != eslabones or eslabones < 4:
        raise ValueError(f"Eslabones inválidos: {eslabones}")
    cam = camino_paso(paso, za, zb, centros)
    todos = asientos(cam.radio_a, za, fase_a) + asientos(cam.radio_b, zb, fase_b, (centros, 0.0))
    casco = _casco_convexo(todos)
    de_a = [i < za for i in casco]
    if sum(1 for j in range(len(casco)) if de_a[j] != de_a[j - 1]) != 2:
        raise ValueError("Un piñón queda dentro del otro: separa los centros")
    # rotar el casco para que empiece en el primer vértice de A después del puente B → A
    k = next(j for j in range(len(casco)) if de_a[j] and not de_a[j - 1])
    casco = casco[k:] + casco[:k]
    pa = [todos[i] for i in casco if i < za]
    pb = [todos[i] for i in casco if i >= za]
    libres = int(eslabones) - (len(pa) - 1) - (len(pb) - 1)
    if libres < 2:
        raise ValueError(f"{eslabones} eslabones no alcanzan para el lazo (faltan {2 - libres})")
    d_inf = math.dist(pa[-1], pb[0])
    d_sup = math.dist(pb[-1], pa[0])

    def costo(n_inf: int) -> tuple:
        n_sup = libres - n_inf
        estirado = max(0.0, d_inf / n_inf - paso, d_sup / n_sup - paso)
        return (round(estirado, 9), abs(d_sup / n_sup - paso))

    n_inf = min(range(1, libres), key=costo)
    n_sup = libres - n_inf
    puntos = (pa + _tramo(pa[-1], pb[0], n_inf, paso) + pb + _tramo(pb[-1], pa[0], n_sup, paso))
    i_b = len(pa) + n_inf - 1
    seps = [math.dist(puntos[i], puntos[(i + 1) % len(puntos)]) for i in range(len(puntos))]
    return LazoRodillos(
        puntos=tuple(puntos),
        asentados_a=tuple(range(len(pa))),
        asentados_b=tuple(range(i_b, i_b + len(pb))),
        pasos_inferior=n_inf, pasos_superior=n_sup,
        separacion_min=min(seps), separacion_max=max(seps),
    )


# ------------------------------------------------------------------ fase que engrana
#: Lo que el eslabón más largo de un lazo puede exceder el paso (mm) y contar como engranado.
TOL_ESTIRADO_MM = 0.05
_BARRIDO = 96      # pasos del barrido por diente (relaciones ≠ 1:1)
_REFINO = 40       # iteraciones de sección áurea alrededor del mejor del barrido


def estirado_lazo(paso: float, za: int, zb: int, centros: float, fase_a: float, fase_b: float,
                  eslabones: int) -> float:
    """mm que el eslabón más largo del lazo excede el paso: 0 = la cadena engrana sin
    estirarse. Con fases que no dejan cadena para un tramo (un lazo 1:1 a centros exactos con
    la fase relativa equivocada), `rodillos_del_lazo` estira los rodillos del medio."""
    lazo = rodillos_del_lazo(paso, za, zb, centros, fase_a, fase_b, eslabones)
    return max(0.0, lazo.separacion_max - paso)


def _envolver(angulo: float, diente: float) -> float:
    """El ángulo llevado a (−diente/2, diente/2]: girar un diente entero no cambia nada."""
    g = math.fmod(angulo, diente)
    if g > diente / 2.0:
        g -= diente
    elif g <= -diente / 2.0:
        g += diente
    return g


def giro_para_engranar(paso: float, za: int, zb: int, centros: float, fase_a: float,
                       fase_b: float, eslabones: int, gira: str) -> float:
    """Giro (rad, antihorario en el marco del lazo) que hay que dar al piñón `gira` ("a" o
    "b") para que la cadena engrane sin estirarse (`estirado_lazo` ≤ `TOL_ESTIRADO_MM`). 0.0 si
    ya engrana.

    En un lazo 1:1 a centros exactos la fase relativa que engrana es 0 o medio diente (L par
    con z impar ⇒ medio diente): se prueban esos dos primero, para que el giro sea el número
    redondo que pondría un taller. Si no alcanzan (otra relación, o centros que no son los
    exactos), se barre un diente del piñón que gira y se refina el mejor: gana el que menos
    estira (en centésimas de mm) y, a igual estirado, el giro más chico. Si ninguno engrana,
    devuelve el que menos estira: quien lo usa decide si eso basta."""
    if gira not in ("a", "b"):
        raise ValueError(f"gira es 'a' o 'b', no {gira!r}")
    diente = 2.0 * math.pi / (za if gira == "a" else zb)

    def estirado(g: float) -> float:
        fa, fb = (fase_a + g, fase_b) if gira == "a" else (fase_a, fase_b + g)
        return estirado_lazo(paso, za, zb, centros, fa, fb, eslabones)

    def costo(g: float) -> tuple:  # el estirado en centésimas de mm y, a igual, el giro chico
        return (round(estirado(g), 2), abs(g))

    if estirado(0.0) <= TOL_ESTIRADO_MM:
        return 0.0
    if za == zb:
        mia, otra = (fase_a, fase_b) if gira == "a" else (fase_b, fase_a)
        redondos = [_envolver(otra + rel - mia, diente) for rel in (0.0, diente / 2.0)]
        mejor = min(redondos, key=costo)
        if estirado(mejor) <= TOL_ESTIRADO_MM:
            return mejor
    barrido = [_envolver(k * diente / _BARRIDO, diente) for k in range(_BARRIDO)]
    mejor = min(barrido, key=costo)
    if costo(mejor)[0] == 0.0:
        return mejor
    lo, hi = mejor - diente / _BARRIDO, mejor + diente / _BARRIDO
    k = (math.sqrt(5.0) - 1.0) / 2.0
    for _ in range(_REFINO):  # sección áurea sobre el estirado (decrece hasta el que engrana)
        m1, m2 = hi - k * (hi - lo), lo + k * (hi - lo)
        if estirado(m1) <= estirado(m2):
            hi = m2
        else:
            lo = m1
    fino = round(_envolver(0.5 * (lo + hi), diente), 9)
    return min((mejor, fino), key=costo)


# ------------------------------------------------------------------ capas de la cadena
def capas_cadena(ancho_interior: float, espesor_placa: float, ancho_sobre_perno: float,
                 hileras: int = 1, pt: float = 0.0) -> dict:
    """Capas en Z de una cadena de rodillos cuyo plano medio de la hilera 1 es z = 0 y cuya
    hilera k (k = 1, 2) está en z = −(k−1)·pt: el mismo marco que las hileras del piñón.

    Devuelve tramos (z0, z1): `rodillos` (uno por hilera, ancho b1 − 2·holgura), `interiores`
    (placas interiores, dos por hilera), `exteriores` (las dos de afuera y, en dúplex, la placa
    MEDIA entre hileras —representativa: una sola placa de espesor t centrada—) y `perno`
    (ancho sobre perno, centrado en el plano medio de la cadena). Holgura `HOLGURA_CAPA_MM`
    entre capas que en la realidad se tocan (así no hay caras tangentes)."""
    h = HOLGURA_CAPA_MM
    b, t = ancho_interior / 2.0, espesor_placa
    if hileras not in (1, 2):
        raise ValueError(f"Hileras no soportadas: {hileras} (1 o 2)")
    if hileras == 2 and pt < ancho_interior + 3.0 * t + 2.0 * h:
        raise ValueError(f"Paso transversal {pt} no deja lugar a la placa media")
    filas = [-k * pt for k in range(hileras)]
    rodillos = [(zc - b + h, zc + b - h) for zc in filas]
    interiores = []
    for zc in filas:
        interiores += [(zc - b - t, zc - b), (zc + b, zc + b + t)]
    arriba, abajo = filas[0] + b + t + h, filas[-1] - b - t - h
    exteriores = [(abajo - t, abajo), (arriba, arriba + t)]
    if hileras == 2:
        zm = -pt / 2.0
        exteriores.insert(1, (zm - t / 2.0, zm + t / 2.0))
    zc = (filas[0] + filas[-1]) / 2.0
    perno = (zc - ancho_sobre_perno / 2.0, zc + ancho_sobre_perno / 2.0)
    if perno[1] <= arriba + t:
        raise ValueError(f"Ancho sobre perno {ancho_sobre_perno} no cubre las placas exteriores")
    return {"rodillos": rodillos, "interiores": interiores, "exteriores": exteriores, "perno": perno}
