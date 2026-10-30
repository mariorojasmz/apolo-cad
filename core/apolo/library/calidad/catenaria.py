"""La carrera de una CATENARIA (plan lo-fijo-que-gira, D3a): el `tensor.carrera` de una banda
modular que se tensa con su peso, colgando tras la rueda motriz (el tensor de tipo `catenaria` lo
reconoce `services/calidad_catenaria.py`; la zona y la fuente, `library/catenaria_banda.py`).

Intralox (`catenaria_banda.FUENTE`, p. 15) pide la comba de 25,4 a 152 mm a la temperatura de
operación y, en el rodaje, la banda alarga del 0,5 % al 1 %: la comba lo toma creciendo y, si
alarga de más, se RETIRAN filas de módulos. La catenaria absorbe el rodaje si la banda puede
colgar LIBRE hasta el tope de 152 mm (lo que guarda hasta ahí, `absorbe_mm`; el resto, filas):

- algo dentro de la comba del tope (`choques`) → FALLA: la banda se apoya antes de llegar a la
  comba con que se retiran filas y deja de tensarse;
- con una temperatura de operación declarada fuera de `AMBIENTE_C` → SIN_EVALUAR justificable: la
  comba cambia con la dilatación térmica α·ΔT·L y falta la fuente del α del material (no se
  inventa); a temperatura ambiente, o sin temperatura declarada, la térmica no entra;
- si no, OK.
"""

from __future__ import annotations

from apolo.library.catenaria_banda import COMBA_MAX_MM, RODAJE

from .item import FALLA, OK, SIN_EVALUAR

#: Lo que se toma por temperatura AMBIENTE (°C): fuera de esto la comba de instalación cambia.
AMBIENTE_C = (10.0, 30.0)
CRITERIO = ("comba 25,4–152 mm tras el motriz y libre hasta 152 mm; el rodaje (1 %·L) se recoge "
            "creciendo la comba y retirando filas (Intralox 2024, p. 15)")


def carrera_catenaria(largo_mm, c: dict, nums: dict) -> tuple:
    """(estado, texto, números) de `tensor.carrera` para una catenaria `c` (el dict `catenaria`
    del tensor: comba_mm, vano_mm, absorbe_mm, largo_mm, choques, temperatura_c). El largo del
    rodaje es el de su línea media (`c["largo_mm"]`) y, sin él, el del lazo."""
    largo_mm = c.get("largo_mm") or largo_mm
    rodaje = None if largo_mm is None else RODAJE * float(largo_mm)
    n = {**nums, "comba_mm": c["comba_mm"], "vano_mm": c["vano_mm"], "tope_mm": COMBA_MAX_MM,
         "absorbe_mm": c["absorbe_mm"], "criterio": CRITERIO}
    if rodaje is not None:
        n["rodaje_mm"] = round(rodaje, 1)
        n["filas_mm"] = round(max(0.0, rodaje - c["absorbe_mm"]), 1)
    if c.get("choques"):
        x = c["choques"][0]
        n["choques"] = c["choques"]
        return (FALLA, f"colgando hasta el tope de {COMBA_MAX_MM:g} mm la banda entra {x['mm']:g} mm "
                       f"en «{x['nombre']}» ({x['pieza']}): se apoya antes de llegar a la comba con "
                       "que se retiran filas y deja de tensarse", n)
    toma = (f"la comba crece de {c['comba_mm']:g} a {COMBA_MAX_MM:g} mm libre y guarda "
            f"{c['absorbe_mm']:g} mm de lazo"
            + (f"; el resto del rodaje ({n['filas_mm']:g} de {n['rodaje_mm']:g} mm, 1 %·L) se "
               "retira por filas" if rodaje is not None else ""))
    temp = c.get("temperatura_c")
    if temp is not None and not AMBIENTE_C[0] <= float(temp) <= AMBIENTE_C[1]:
        n["temperatura_c"] = temp
        return (SIN_EVALUAR, f"{toma}; la dilatación térmica α·ΔT·L a {float(temp):g} °C queda sin "
                             "evaluar: falta la fuente del coeficiente α del material de la banda "
                             "(justifícala con el dato del fabricante)", n)
    return OK, toma, n
