"""Amortiguador hidráulico EXTERNO al fin de carrera de un cilindro (plan amortiguador-externo D1–D7).

Puro (biblioteca estándar), como el resto de `neumatica/`:
  - `parse_ficha(specs, ref)`: la ficha de capacidad de una ref de la familia
    `amortiguador_hidraulico` (las `specs` del YAML). La COMPLETITUD se valida al cargar (el
    loader la llama): sin un dato, la ref no carga. `fuente` obligatoria; lo derivado o leído sin
    su dibujo va en `a_confirmar`.
  - `choque`: la energía que absorbe en UN extremo con la fórmula de su ficha (SMC RB, «Model
    Selection», carrera de cilindro con carga horizontal): E = E1 + E2, E1 = ½·m·v² (cinética),
    E2 = F·S (el trabajo de la fuerza del cilindro durante la carrera S del amortiguador), contra
    la energía máxima por ciclo, la fuerza máxima admisible y el rango de velocidad de choque.
  - `frecuencia`: la cadencia contra la frecuencia máxima de la ficha (n ≤ n máx, tal cual);
  - `por_hora`: E·ciclos/h contra la energía máxima por hora (la ficha da la frecuencia máxima a
    energía máxima: E_h,máx = E_máx · n_máx · 60);
  - `entran`: las refs de un catálogo de fichas que pasan las tres para el mismo choque.

Estados como en el ERC: «ok», «aviso», «error»; `por_hora` sin ciclos da «sin_evaluar» (quien lo
llama decide cómo lo dice: D5).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Familia (builder) del catálogo cuyas refs llevan esta ficha.
FAMILIA = "amortiguador_hidraulico"
#: Extremos de la carrera del cilindro donde puede ir un amortiguador (campo del servicio).
EXTREMOS = ("avance", "retroceso")
#: Bajo esta fracción de la energía máxima la ficha pide un tamaño menor (SMC RB, «Caution on
#: Selection»: «If the impact energy is smaller than 5% of the maximum energy absorption, select a
#: model that is one class smaller»).
FRACCION_MINIMA = 0.05
#: Tolerancia relativa de las comparaciones con la ficha (el redondeo binario de E·n·60).
_REL = 1e-9
NORMA = "criterio de selección de la ficha del fabricante (SMC RB «Model Selection»: E = E1 + E2)"

#: Claves numéricas obligatorias de la ficha: clave → para qué sirve.
REQUERIDOS = {
    "carrera_mm": "carrera de absorción S (el trabajo F·S de la fuerza del cilindro)",
    "E_max_J": "energía máxima absorbida por ciclo",
    "E_max_hora_J": "energía máxima absorbida por hora (E máx × frecuencia máx × 60)",
    "n_max_ciclos_min": "frecuencia máxima de trabajo a energía máxima",
    "F_max_N": "fuerza (empuje) máxima admisible",
    "v_min_m_s": "velocidad de choque mínima",
    "v_max_m_s": "velocidad de choque máxima",
}


@dataclass(frozen=True)
class FichaAmortiguador:
    ref: str
    carrera_mm: float
    E_max_J: float
    E_max_hora_J: float
    n_max_ciclos_min: float
    F_max_N: float
    v_min_m_s: float
    v_max_m_s: float
    rosca: str
    fuente: str
    a_confirmar: tuple[str, ...] = ()


def parse_ficha(specs: dict, ref: str) -> FichaAmortiguador:
    """La ficha de una ref de amortiguador, o `ValueError` con lo que falta y para qué sirve."""
    faltan = [f"{k} ({para})" for k, para in REQUERIDOS.items()
              if not isinstance(specs.get(k), (int, float)) or specs[k] <= 0]
    for k in ("rosca", "fuente"):
        if not specs.get(k):
            faltan.append(f"{k} ({'rosca de montaje del cuerpo' if k == 'rosca' else 'la ficha oficial de las cifras'})")
    if faltan:
        raise ValueError(f"Amortiguador '{ref}': ficha incompleta, falta {', '.join(faltan)}")
    if specs["v_min_m_s"] >= specs["v_max_m_s"]:
        raise ValueError(f"Amortiguador '{ref}': v_min_m_s ≥ v_max_m_s")
    ac = specs.get("a_confirmar") or ()
    return FichaAmortiguador(ref=ref, rosca=str(specs["rosca"]), fuente=str(specs["fuente"]),
                             a_confirmar=tuple([ac] if isinstance(ac, str) else ac),
                             **{k: float(specs[k]) for k in REQUERIDOS})


def _res(titulo: str, valor: dict, estado: str, hipotesis: list[str], **calc) -> dict:
    return {"titulo": titulo, "valor": valor, "estado": estado, "hipotesis": hipotesis,
            "calc": {"titulo": titulo, **calc}}


def choque(m_kg: float, v_m_s: float, F_N: float, ficha: FichaAmortiguador, *, extremo: str) -> dict:
    """Energía por ciclo en un extremo: E1 = ½·m·v², E2 = F·S, E = E1 + E2 ≤ E máx; además F ≤ F
    máx y v dentro del rango de la ficha. Informa la masa equivalente Me = 2·E/v² (la ficha da su
    máximo en un gráfico, «Data D»: no se juzga) y la fuerza sobre el soporte 2·E/S (fórmula de la
    ficha, «Precautions»: el operador se leyó del texto extraído, a confirmar)."""
    S = ficha.carrera_mm / 1000.0
    E1 = 0.5 * m_kg * v_m_s ** 2
    E2 = F_N * S
    E = E1 + E2
    Me = 2.0 * E / v_m_s ** 2 if v_m_s > 0 else float("inf")
    F_soporte = 2.0 * E / S
    fallas, avisos = [], []
    if E > ficha.E_max_J * (1 + _REL):
        fallas.append(f"E = {E:.1f} J > {ficha.E_max_J:g} J por ciclo")
    if F_N > ficha.F_max_N * (1 + _REL):
        fallas.append(f"F = {F_N:.0f} N > {ficha.F_max_N:g} N admisibles")
    if v_m_s > ficha.v_max_m_s:
        fallas.append(f"v = {v_m_s:.2f} m/s > {ficha.v_max_m_s:g} m/s de la ficha")
    elif v_m_s < ficha.v_min_m_s:
        avisos.append(f"v = {v_m_s:.2f} m/s < {ficha.v_min_m_s:g} m/s de la ficha")
    if not fallas and E < FRACCION_MINIMA * ficha.E_max_J:
        avisos.append(f"E = {E:.2f} J < {100 * FRACCION_MINIMA:g} % de la máxima: la ficha pide un tamaño menor")
    estado = "error" if fallas else ("aviso" if avisos else "ok")
    hip = ["choque horizontal (la ficha: F·S; vertical sumaría ±m·g·S, no evaluado)",
           f"masa equivalente Me = 2·E/v² = {Me:.0f} kg: su máximo está en el gráfico de la ficha (a confirmar con él)",
           f"fuerza sobre el soporte ≈ 2·E/S = {F_soporte:.0f} N (fórmula de la ficha; operador a confirmar)",
           "el amortiguador no se simula: se verifica (plan amortiguador-externo D6)"]
    hip += [f"{k} de la ficha a confirmar" for k in ficha.a_confirmar]
    return _res(
        f"Amortiguador {ficha.ref} al {extremo}",
        {"E_J": E, "E1_J": E1, "E2_J": E2, "E_max_J": ficha.E_max_J, "F_N": F_N, "F_max_N": ficha.F_max_N,
         "v_m_s": v_m_s, "m_kg": m_kg, "Me_kg": Me, "F_soporte_N": F_soporte, "extremo": extremo,
         "ref": ficha.ref, "motivos": fallas + avisos},
        estado, hip,
        entradas={"masa móvil + carga": f"{m_kg:g} kg", "velocidad de choque": f"{v_m_s:g} m/s",
                  "fuerza del cilindro": f"{F_N:.0f} N", "carrera del amortiguador": f"{ficha.carrera_mm:g} mm",
                  "ficha": f"{ficha.E_max_J:g} J/ciclo, {ficha.F_max_N:g} N, {ficha.v_min_m_s:g}–{ficha.v_max_m_s:g} m/s"},
        formula="E = E1 + E2 · E1 = ½·m·v² · E2 = F·S",
        sustitucion=(f"E = ½·{m_kg:g}·{v_m_s:g}² + {F_N:.0f}·{S:g} = {E1:.2f} + {E2:.2f} = {E:.2f} J"),
        resultado=f"{E:.2f} J contra {ficha.E_max_J:g} J por ciclo · F = {F_N:.0f} N (máx {ficha.F_max_N:g} N)",
        criterio=(f"E ≤ E máx por ciclo, F ≤ F máx, v en {ficha.v_min_m_s:g}–{ficha.v_max_m_s:g} m/s "
                  f"(E ≥ {100 * FRACCION_MINIMA:g} % de la máxima)"),
        fs=round(ficha.E_max_J / E, 2) if E > 0 else None, norma=NORMA)


def frecuencia(ciclos_min: float | None, ficha: FichaAmortiguador, *, extremo: str, origen: str = "") -> dict:
    """La cadencia contra la frecuencia máxima de la ficha, tal cual (n ≤ n máx): así la compara
    el ejemplo de selección de SMC RB («n = 20 < 25»), aunque la energía sea mucho menor que la
    máxima. Sin ciclos: «sin_evaluar»."""
    titulo = f"Amortiguador {ficha.ref} al {extremo}: frecuencia"
    nmax = ficha.n_max_ciclos_min
    if not ciclos_min:
        return _res(titulo, {"n_max_ciclos_min": nmax, "extremo": extremo, "ref": ficha.ref}, "sin_evaluar",
                    ["sin cadencia del cilindro ni capacidad nominal: no se evalúa"], entradas={}, formula="n ≤ n máx",
                    sustitucion="", resultado="sin evaluar", criterio="n ≤ frecuencia máxima de la ficha", fs=None,
                    norma=NORMA)
    estado = "ok" if ciclos_min <= nmax * (1 + _REL) else "error"
    hip = [f"ciclos de {origen}" if origen else "un choque por ciclo del cilindro",
           "la frecuencia máxima de la ficha se compara tal cual, como en su ejemplo de selección (la nota de la "
           "serie RBL que la deja crecer al bajar la energía no se aplica)"]
    return _res(
        titulo, {"ciclos_min": ciclos_min, "n_max_ciclos_min": nmax, "extremo": extremo, "ref": ficha.ref},
        estado, hip, entradas={"ciclos": f"{ciclos_min:g}/min", "ficha": f"{nmax:g} ciclos/min máx"},
        formula="n ≤ n máx", sustitucion=f"n = {ciclos_min:g} contra {nmax:g} ciclos/min",
        resultado=f"{ciclos_min:g} de {nmax:g} ciclos/min", criterio="n ≤ frecuencia máxima de la ficha",
        fs=round(nmax / ciclos_min, 2), norma=NORMA)


def por_hora(E_J: float, ciclos_min: float | None, ficha: FichaAmortiguador, *, extremo: str,
             origen: str = "") -> dict:
    """Energía por hora en un extremo: un choque por ciclo, E_h = E·ciclos/min·60 ≤ E máx por hora.
    Sin ciclos: estado «sin_evaluar» (no se inventa una cadencia)."""
    titulo = f"Amortiguador {ficha.ref} al {extremo}: energía por hora"
    if not ciclos_min:
        return _res(titulo, {"E_max_hora_J": ficha.E_max_hora_J, "extremo": extremo, "ref": ficha.ref},
                    "sin_evaluar", ["sin cadencia del cilindro ni capacidad nominal: no se evalúa"],
                    entradas={}, formula="E_h = E·n·60", sustitucion="", resultado="sin evaluar",
                    criterio="E_h ≤ E máx por hora", fs=None, norma=NORMA)
    n_h = ciclos_min * 60.0
    Eh = E_J * n_h
    estado = "ok" if Eh <= ficha.E_max_hora_J * (1 + _REL) else "error"
    hip = [f"un choque en el {extremo} por ciclo del cilindro; ciclos de {origen}" if origen else
           f"un choque en el {extremo} por ciclo del cilindro",
           f"E máx por hora = E máx · n máx · 60 = {ficha.E_max_J:g}·{ficha.n_max_ciclos_min:g}·60 "
           "(la ficha da la frecuencia máxima a energía máxima)"]
    return _res(
        titulo, {"E_h_J": Eh, "E_max_hora_J": ficha.E_max_hora_J, "ciclos_min": ciclos_min, "E_J": E_J,
                 "extremo": extremo, "ref": ficha.ref}, estado, hip,
        entradas={"energía por choque": f"{E_J:.2f} J", "ciclos": f"{ciclos_min:g}/min ({n_h:g}/h)",
                  "admisible": f"{ficha.E_max_hora_J:g} J/h"},
        formula="E_h = E · n · 60", sustitucion=f"E_h = {E_J:.2f}·{ciclos_min:g}·60 = {Eh:.0f} J/h",
        resultado=f"{Eh:.0f} J/h contra {ficha.E_max_hora_J:g} J/h",
        criterio="E_h ≤ E máx por hora", fs=round(ficha.E_max_hora_J / Eh, 2) if Eh > 0 else None, norma=NORMA)


def entran(m_kg: float, v_m_s: float, F_N: float, ciclos_min: float | None, fichas: dict, *,
           extremo: str) -> list[FichaAmortiguador]:
    """Las fichas que pasan el choque, la frecuencia y la energía por hora (sin error) para ese
    choque, de menor a mayor energía; una por capacidad (la ref sin tope antes que la «-T»). Sin
    ciclos, sólo el choque."""
    out, vistas = [], set()
    for f in sorted(fichas.values(), key=lambda f: (f.E_max_J, f.ref)):
        clave = (f.carrera_mm, f.E_max_J, f.n_max_ciclos_min, f.F_max_N)
        r = choque(m_kg, v_m_s, F_N, f, extremo=extremo)
        if clave in vistas or r["estado"] == "error":
            continue
        if ciclos_min and "error" in (frecuencia(ciclos_min, f, extremo=extremo)["estado"],
                                      por_hora(r["valor"]["E_J"], ciclos_min, f, extremo=extremo)["estado"]):
            continue
        vistas.add(clave)
        out.append(f)
    return out
