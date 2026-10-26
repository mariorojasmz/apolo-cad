"""El calentamiento de un TABLERO armado (plan V8.5 D6, F3): pérdidas, temperatura a la altura de
cada aparato contra su máxima y lo que se sugiere si se pasa.

PURO (sin OCCT, catálogo ni `Document`): el método de la norma está en `iec60890.py`; lo que sale
del documento (la envolvente con sus caras cubiertas, cada aparato con su altura y su `T_max_C`,
las pérdidas declaradas y cada conductor con su largo ruteado) lo arma
`services/tablero_calor.py`.

Reglas (decisiones de F3, vetables; cada una sale como supuesto en el resultado):
1. **Pérdidas** = Σ `perdidas_W` de los aparatos (× cantidad; la de la ficha, a plena carga: lado
   seguro) + Σ I²·R de cada conductor DENTRO del tablero (su largo ruteado).
2. **R del conductor**: IEC 60228 clase 5, cobre sin recubrir, máxima a 20 °C (`R20_OHM_KM`, con su
   cita), sin corregir por temperatura.
3. **Corriente de un conductor** (hipótesis declarada, `corriente_de_borne` + `corriente_conductor`):
   una COTA SUPERIOR de lo que circula en servicio, por lo que dice cada borne que une. Si llega al
   lado CARGA de una protección (In del ITM, Ir del guardamotor o del relé térmico, el cartucho del
   fusible) o a la salida de una fuente o de un variador, no pasa más que el menor de esos
   límites; si alimenta el lado LÍNEA de protecciones, la suma de sus corrientes; si no, la mayor
   corriente asignada de los otros aparatos en ese borne (Ie AC-3 del contactor, Ith del
   seccionador, la entrada del variador, una salida del PLC, un relé, un piloto). Un conductor de
   tierra (un borne de rol `tierra`) no lleva corriente en servicio: 0. Uno del que ningún borne
   dice nada (de un pulsador a una entrada del PLC: señal) cuenta 0 W y se lista.
4. **Temperatura de un aparato** = ambiente + el calentamiento a la altura de su BORDE SUPERIOR
   (`Calentamiento.delta_a`), contra el `T_max_C` de su ficha; los conductores (su `T_max_C`, el
   del aire alrededor del aislamiento) contra la de arriba (pasan por la canaleta de arriba).
5. **Si se pasa** (ventilación sugerida, `Sugerencia`):
   - ventilación FORZADA (ventilador con filtro abajo y rejilla con filtro arriba): el caudal que
     se lleva TODA la pérdida con el aire subiendo de ambiente a la máxima admisible más baja,
     Q = P / (ρ·cp·ΔT), sin contar lo que disipan las paredes (lado seguro), con el aire seco como
     gas ideal a 101,325 kPa (nivel del mar: `P_ATM_PA`, `R_AIRE`, `CP_AIRE`, criterio de diseño
     con las constantes del aire). Es el caudal EFECTIVO, con los filtros puestos: el de soplado
     libre de la ficha del ventilador es mayor;
   - aberturas naturales: sólo en la rama Ae > 1,25 m² (la chica no tiene rama con aberturas):
     la menor entrada de la T9 que alcanza (`iec60890.entrada_minima`);
   - con el ambiente ya sobre la máxima admisible, ninguna ventilación alcanza: equipo de
     refrigeración (fuera del método).
   El gabinete siguiente lo prueba `services/tablero_calor.py` (tiene que entrar el layout).
6. **Con ventilación forzada DECLARADA** (`layout_tablero.ventilacion_m3h`, el caudal efectivo):
   IEC 60890 no aplica (es de convección natural); el aire de todo el tablero se toma a la
   temperatura con que sale, ambiente + P / (ρ·cp·Q) (`forzada`, lado seguro), y así el ERC queda
   verde cuando el ventilador alcanza.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import iec60890

#: IEC 60228:2004, tabla de la clase 5 (conductores flexibles de cobre), cobre SIN recubrir,
#: resistencia máxima a 20 °C en Ω/km, tal como la reproduce Cembre, «General Catalogue», pág. 205
#: «IEC 60228:2004 — conductor tables», https://storage.electrika.com/flips/8940-cembre-16/files/
#: assets/basic-html/page-212.html (consultada 2026-10-26); las de 0,75 a 4 mm² coinciden con las de
#: la F0 del plan V8.5 (§ 5).
R20_OHM_KM = {0.5: 39.0, 0.75: 26.0, 1.0: 19.5, 1.5: 13.3, 2.5: 7.98, 4.0: 4.95, 6.0: 3.30, 10.0: 1.91,
              16.0: 1.21}
FUENTE_R20 = ("IEC 60228:2004, clase 5, cobre sin recubrir, R máx. a 20 °C (Cembre, General Catalogue, "
              "pág. 205)")
#: el aire de la ventilación forzada (criterio de diseño: aire seco como gas ideal a nivel del mar)
P_ATM_PA = 101325.0
R_AIRE = 287.05     # J/(kg·K), constante del aire seco
CP_AIRE = 1005.0    # J/(kg·K), calor específico del aire seco a presión constante

#: Las protecciones: un conductor en su lado CARGA no lleva más que su corriente asignada; uno en
#: su lado LÍNEA las alimenta (regla 3)
PROTECCIONES = {"itm": ("In_A",), "diferencial": ("In_A",), "guardamotor": ("Ir_A",),
                "rele_termico": ("Ir_A",), "fusible": ("cartucho_In_A", "In_max_A")}
#: (`modelo.tipo`, rol del borne, lado) → claves de la corriente que limita o asigna ese borne
#: (None = cualquier lado); en orden, la primera que la ficha o el ajuste dan
OTRAS = {
    ("fuente", "mando", "carga"): ("I_salida_A",),       # la salida de la fuente: la limita
    ("variador", "potencia", "linea"): ("I_entrada_A",),
    ("variador", "potencia", "carga"): ("I_salida_A",),
    ("contactor", "potencia", None): ("Ie_AC3_A",),
    ("seccionador", "potencia", None): ("Ith_A",),
    ("plc", "señal", None): ("DO_A",),                    # una salida del PLC (lado seguro para una entrada)
    ("rele", "contacto", None): ("contacto_A",),
    ("piloto", "mando", None): ("I_mA",),
    ("sensor", None, None): ("I_salida_mA",),
}


def _valor(modelo: dict, ajustes: dict, claves) -> float | None:
    for k in claves:
        v = ajustes.get(k, modelo.get(k))
        if isinstance(v, (list, tuple)) and v:
            v = max(float(x) for x in v)  # un rango [mín, máx]: el máximo (lado seguro)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            return float(v) / (1000.0 if k.endswith("_mA") else 1.0)
    return None


def corriente_de_borne(tipo: str | None, modelo: dict, ajustes: dict | None, rol: str | None,
                       lado: str | None) -> tuple[str, float] | None:
    """(clase, A) de lo que dice un borne de la corriente del conductor que llega (regla 3): «tierra»
    (0 en servicio), «limite» (el lado carga de una protección o la salida de una fuente o un
    variador: no pasa más), «alimenta» (el lado línea de una protección: la suma) u «otra» (la
    corriente asignada del aparato en ese borne). El AJUSTE manda sobre la ficha. None: el borne
    no dice nada (una entrada, un pulsador, un borne de paso)."""
    ajustes, modelo = ajustes or {}, modelo or {}
    if rol == "tierra":
        return ("tierra", 0.0)
    if tipo in PROTECCIONES and rol == "potencia":
        a = _valor(modelo, ajustes, PROTECCIONES[tipo])
        if a is not None:
            return ("limite" if lado == "carga" else "alimenta", a)
        return None
    for (t, r, ld), claves in OTRAS.items():
        if t == tipo and r in (None, rol) and ld in (None, lado):
            a = _valor(modelo, ajustes, claves)
            if a is not None:
                limita = (tipo == "fuente") or (tipo == "variador" and lado == "carga")
                return ("limite" if limita else "otra", a)
    return None


def corriente_conductor(bornes: list[tuple[str, float] | None]) -> float | None:
    """La corriente (A) de un conductor por lo que dicen sus bornes (regla 3): con un borne de
    tierra, 0; con un límite, el menor; si alimenta protecciones, la suma de sus corrientes; si no,
    la mayor de las otras; None si ninguno dice nada."""
    dichos = [b for b in bornes if b is not None]
    if any(c == "tierra" for c, _ in dichos):
        return 0.0
    for clase, junta in (("limite", min), ("alimenta", sum), ("otra", max)):
        xs = [a for c, a in dichos if c == clase]
        if xs:
            return junta(xs)
    return None


@dataclass(frozen=True)
class Conductor:
    id: str
    seccion_mm2: float | None
    largo_mm: float
    corriente_A: float | None    # None: sin corriente asignada (regla 3); 0: tierra


def perdidas_conductor(c: Conductor) -> tuple[float, str | None]:
    """(W, motivo si no se cuenta): I²·R20·largo."""
    if c.corriente_A is None:
        return 0.0, "sin corriente asignada"
    if c.corriente_A == 0:
        return 0.0, None
    r = R20_OHM_KM.get(float(c.seccion_mm2)) if c.seccion_mm2 else None
    if r is None:
        return 0.0, f"sección {c.seccion_mm2} mm² sin resistencia tabulada"
    return c.corriente_A ** 2 * r * c.largo_mm / 1e6, None


@dataclass(frozen=True)
class AparatoTermico:
    designacion: str
    h: float                    # altura relativa de su borde superior (0 = piso, 1 = techo)
    T_max_C: float | None
    nombre: str = ""


@dataclass(frozen=True)
class Lectura:
    designacion: str
    h: float
    T_C: float
    T_max_C: float | None

    @property
    def pasa(self) -> bool:
        return self.T_max_C is not None and self.T_C > self.T_max_C + 1e-9


@dataclass(frozen=True)
class Sugerencia:
    caudal_m3h: float | None = None       # ventilación forzada (efectivo, con filtros)
    entrada_cm2: float | None = None      # aberturas naturales (rama grande)
    refrigeracion: bool = False           # el ambiente ya pasa la máxima: ventilar no alcanza
    dt_admisible_K: float | None = None


@dataclass(frozen=True)
class Evaluacion:
    calor: iec60890.Calentamiento
    ambiente_C: float
    lecturas: tuple[Lectura, ...]
    sin_tmax: tuple[str, ...] = ()
    sugerencia: Sugerencia | None = None
    supuestos: tuple[str, ...] = field(default=())

    @property
    def T_media_C(self) -> float:
        return self.ambiente_C + self.calor.dt_media_K

    @property
    def T_arriba_C(self) -> float:
        return self.ambiente_C + self.calor.dt_arriba_K

    @property
    def pasan(self) -> tuple[Lectura, ...]:
        return tuple(x for x in self.lecturas if x.pasa)

    @property
    def peor(self) -> Lectura | None:
        """La lectura con menos margen (la que más se pasa, o la más justa)."""
        con = [x for x in self.lecturas if x.T_max_C is not None]
        return min(con, key=lambda x: x.T_max_C - x.T_C) if con else None


def densidad_aire(T_C: float) -> float:
    return P_ATM_PA / (R_AIRE * (T_C + 273.15))


def caudal_m3h(P_W: float, dt_K: float, T_C: float) -> float:
    """Q = P / (ρ·cp·ΔT), en m³/h, con ρ a la temperatura de entrada (regla 5)."""
    return P_W / (densidad_aire(T_C) * CP_AIRE * dt_K) * 3600.0


def forzada(env: iec60890.Envolvente, P_W: float, caudal: float, ambiente_C: float) -> iec60890.Calentamiento:
    """Regla 6: con ventilación FORZADA declarada el método de IEC 60890 no aplica (es de convección
    natural): balance de energía, todo el calor se va con el aire, que sale a ambiente + ΔT; el
    aire de TODO el tablero se toma a esa temperatura (lado seguro: sin lo que disipan las paredes
    ni el perfil de altura)."""
    dt = P_W / (densidad_aire(ambiente_C) * CP_AIRE * caudal / 3600.0)
    return iec60890.Calentamiento(
        P_W, iec60890.superficie_efectiva(env), f"ventilación forzada de {caudal:g} m³/h (balance de energía, "
        "fuera de IEC 60890)", 0.0, 1.0, 1.0, 1.0, dt, dt, 0.5, caras=iec60890.caras(env),
        tablas=("Q = P / (ρ·cp·ΔT)",), citas=("balance de energía del aire seco (criterio de diseño)",))


def evaluar(env: iec60890.Envolvente, P_W: float, aparatos: list[AparatoTermico], ambiente_C: float,
            ventilacion_m3h: float = 0.0) -> Evaluacion:
    """La regla 4 y, si algo se pasa, la 5 (con `ventilacion_m3h` > 0, la 6). `FueraDeDominio` del
    método sube tal cual."""
    calor = (forzada(env, P_W, ventilacion_m3h, ambiente_C) if ventilacion_m3h > 0
             else iec60890.calentamiento(env, P_W))
    lecturas = tuple(Lectura(a.designacion, round(a.h, 3), ambiente_C + calor.delta_a(a.h), a.T_max_C)
                     for a in aparatos)
    sin = tuple(a.designacion for a in aparatos if a.T_max_C is None)
    sug = None
    if any(x.pasa for x in lecturas):
        tmin = min(x.T_max_C for x in lecturas if x.T_max_C is not None)
        adm = tmin - ambiente_C
        if adm <= 0:
            sug = Sugerencia(refrigeracion=True, dt_admisible_K=round(adm, 1))
        else:
            sug = Sugerencia(caudal_m3h=round(caudal_m3h(P_W, adm, ambiente_C), 1),
                             entrada_cm2=iec60890.entrada_minima(env, P_W, adm), dt_admisible_K=round(adm, 1))
    return Evaluacion(calor, ambiente_C, lecturas, sin, sug)
