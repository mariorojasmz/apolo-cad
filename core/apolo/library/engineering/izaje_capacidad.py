"""Regla «capacidad de la cadena de izaje» (plan `docs/plans/cadena-de-izaje.md`, F2a): PURA, recibe
lo que cuelga de cada extremo de UNA cadena de `create_hoist_chain` (lo mide
`services/izaje_rules.py`) y devuelve la regla con su bloque `calc`, en el formato de `rules.py`.

Tensión de la cadena (la del extremo más cargado):

    T = (m_cuerpo + m_útil)·g·Ku(n) + m_cadena·g

- `m_cuerpo`: la masa del cuerpo móvil al que se amarra el extremo (lo que mueve su junta, con
  sus hijos `fija`); `m_útil`: la carga útil de los requisitos (`carga_kg`), si la hay.
- `Ku(n)`: el coeficiente de carga DESIGUAL entre las n cadenas que cuelgan el mismo cuerpo
  (`KU_TSUBAKI`). Con un n que la tabla no trae se toma el de la n tabulada inmediata inferior,
  que es mayor (conservador), y se declara.
- `m_cadena·g`: el peso propio de la cadena ENTERA (conservador: sólo cuelga un ramal).

Criterio: FS = F_rotura / T ≥ `FS_MIN` (la rotura mínima de la ficha del catálogo).

**De dónde sale cada cifra** (`FUENTES`, leídas el 2026-10-27; ninguna norma de máquina con
la cifra es de lectura pública —EN 1570-1, ANSI MH29.1 y ASME B20.1 son de pago— y la guía de
la MHIA para elevadores de material, que acompaña a la B20.1, no da factor para la cadena):

- FS ≥ 7 sobre la rotura: iwis, regla práctica del fabricante para dimensionar una transmisión
  por cadena, donde manda la fatiga. Coincide con el mínimo de 7 sobre la rotura que el Código de
  California (Title 8 § 3093.53) pide al medio de suspensión de un elevador de acceso especial.
- Ku: Tsubaki, «The Complete Guide to Chain», tabla 4.3 (2 cadenas 0,6; 4 cadenas 0,36).

El impacto de arranque y frenado (el factor K de Tsubaki, que pide la inercia del motor) NO se
calcula: se declara en las hipótesis. Ninguna cifra se inventa.
"""

from __future__ import annotations

from ..rules import _check
from .report_comun import G

#: Factor de seguridad mínimo sobre la rotura de la cadena (fuente en `FUENTES["fs"]`).
FS_MIN = 7.0
#: Coeficiente de carga desigual por número de cadenas que cuelgan el mismo cuerpo (Tsubaki).
KU_TSUBAKI: dict[int, float] = {1: 1.0, 2: 0.6, 4: 0.36}

REGLA = "capacidad de la cadena de izaje"

FUENTES: dict[str, dict] = {
    "fs": {
        "fuente": "iwis, «Tensile Testing» (ensayo de rotura de cadenas)",
        "url": "https://www.iwis.com/en-en/expertise-technology/testing-analysis/"
               "drive-systems-testing/tensile-strength",
        "frase": "as a rule of thumb, it is recommended to calculate with a safety factor of 7 "
                 "based on the breaking force",
        "cifra": 7.0,
    },
    "fs_coincide": {
        "fuente": "California Code of Regulations, Title 8, § 3093.53 (Special Access Lifts)",
        "url": "https://dir.ca.gov/Title8/3093_53.html",
        "frase": "The factor of safety of the suspension means shall be not less than 7 based on "
                 "the manufacturer's rated breaking strength.",
        "cifra": 7.0,
    },
    "ku": {
        "fuente": "U.S. Tsubaki, «The Complete Guide to Chain», cap. 4, pág. 36, tabla 4.3 "
                  "(Unbalanced Load Factor Ku)",
        "url": "https://www.ustsubaki.com/pdf/the-complete-guide.pdf",
        "frase": "When you use two or four chains in a hanging application or shuttle traction "
                 "setup, the tension of each chain is not equal.",
        "cifra": "2 cadenas: 0,6 · 4 cadenas: 0,36",
    },
}

NORMA = ("criterio de diseño: FS ≥ 7 sobre la rotura (iwis; el mismo mínimo de CCR Title 8 "
         "§ 3093.53 para el medio de suspensión) · Ku de Tsubaki «The Complete Guide to Chain» "
         "tabla 4.3 · rotura mínima ISO 606 / ANSI B29.1 de la ficha")


def coeficiente_desigual(n: int) -> tuple[float, str | None]:
    """(Ku, nota): el de la tabla, o el de la n tabulada inmediata inferior (mayor: conservador)."""
    if n in KU_TSUBAKI:
        return KU_TSUBAKI[n], None
    base = max(k for k in KU_TSUBAKI if k <= n)
    return KU_TSUBAKI[base], (f"Ku de {n} cadenas no está tabulado: se toma el de {base} "
                              f"({KU_TSUBAKI[base]:g}), mayor que el de más cadenas (conservador)")


def regla_capacidad_izaje(nombre: str, *, cadena: str, rotura_kn: float, kg_m: float,
                          largo_mm: float, extremos: list[dict], piezas: list[str]) -> dict:
    """La regla de UNA cadena. `extremos`: por cada cuerpo al que se amarra, {cuerpo (nombre),
    masa_kg, util_kg, cadenas (n que lo cuelgan)}; vacío = la carga no se pudo determinar
    (AVISO, sin cifra inventada). Devuelve la regla con `verificada` (True si calculó el FS)."""
    titulo = f"{REGLA} · {nombre}"
    hip_fuentes = [f"{f['fuente']}: «{f['frase']}» ({f['url']})" for f in FUENTES.values()]
    if not extremos:
        r = _check(titulo, "aviso",
                   f"{nombre}: no se pudo determinar la carga que cuelga de la cadena {cadena} "
                   "(el cuerpo amarrado también se apoya en otra cosa que no es una junta): la "
                   "capacidad no se verifica.",
                   "Cuelga la pieza de una junta (prismática o de giro) cuyo cuerpo móvil la "
                   "lleve, o declara la estructura para que la cadena sea su único sostén.")
        return {**r, "piezas": piezas, "verificada": False, "hipotesis": hip_fuentes}
    m_cadena = kg_m * largo_mm / 1000.0
    lados, notas = [], []
    for e in extremos:
        ku, nota = coeficiente_desigual(int(e["cadenas"]))
        if nota:
            notas.append(nota)
        t = (e["masa_kg"] + e["util_kg"]) * G * ku + m_cadena * G
        lados.append((t, ku, e))
    t, ku, e = max(lados, key=lambda x: x[0])
    rotura_n = rotura_kn * 1000.0
    fs = rotura_n / t if t > 0 else float("inf")
    cuerpo = e["masa_kg"] + e["util_kg"]
    entradas = {
        "cadena": f"{cadena} · rotura mínima {rotura_kn:g} kN (ficha) · {kg_m:g} kg/m",
        "cuerpo colgado": f"{e['cuerpo']}: {e['masa_kg']:.1f} kg (su cuerpo móvil)",
        "carga útil": (f"{e['util_kg']:g} kg (requisito carga_kg)" if e["util_kg"]
                       else "sin carga_kg en los requisitos"),
        "cadenas que lo cuelgan": f"{e['cadenas']} → Ku = {ku:g} (Tsubaki, tabla 4.3)",
        "peso propio de la cadena": f"{m_cadena:.2f} kg ({largo_mm:.0f} mm, entero: conservador)",
    }
    calc = {
        "titulo": f"Capacidad de la cadena de izaje {nombre}",
        "entradas": entradas,
        "formula": "T = (m_cuerpo + m_útil)·g·Ku + m_cadena·g ; FS = F_rotura / T",
        "sustitucion": (f"T = ({e['masa_kg']:.1f} + {e['util_kg']:g})·{G:g}·{ku:g} + "
                        f"{m_cadena:.2f}·{G:g} = {t:.0f} N ; FS = {rotura_n:.0f} / {t:.0f}"),
        "resultado": f"T = {t:.0f} N, FS = {fs:.1f}",
        "criterio": f"FS ≥ {FS_MIN:g} sobre la rotura mínima",
        "fs": round(fs, 2),
        "norma": NORMA,
    }
    det = (f"{nombre}: {cuerpo:.1f} kg colgados de {e['cadenas']} cadena(s) {cadena} → T = "
           f"{t / 1000.0:.2f} kN contra {rotura_kn:g} kN de rotura: FS = {fs:.1f} "
           f"(mínimo {FS_MIN:g}).")
    hip = [*notas,
           "El impacto de arranque y frenado (factor K de Tsubaki, que pide la inercia del motor y "
           "los tiempos de aceleración) no se calcula: el FS 7 de iwis es el margen para la "
           "fatiga de una transmisión por cadena.",
           "El pasador de cada amarre es el perno del eslabón de unión de la cadena (ISO 606): su "
           "capacidad es la rotura de la cadena y queda verificado por esta regla.",
           *hip_fuentes]
    if fs < FS_MIN:
        r = _check(titulo, "error", det,
                   f"Sube la cadena (paso mayor o doble) o reparte la carga en más cadenas: hace "
                   f"falta una rotura ≥ {FS_MIN * t / 1000.0:.1f} kN.", calc=calc)
    else:
        r = _check(titulo, "ok", det, calc=calc)
    return {**r, "piezas": piezas, "verificada": True, "hipotesis": hip,
            "fuentes": list(FUENTES.values())}
