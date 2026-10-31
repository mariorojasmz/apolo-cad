"""Con qué norma se calcula una pieza estructural que no es de catálogo (plan
puerta-fuera-de-catalogo, D7 y su ajuste de la F0). Puro: lee el TEXTO del material (y el nombre de
la pieza), nunca un `Document`.

Cuatro criterios que NUNCA se mezclan:
- **metal** (acero, inox, aluminio, latón, cobre, zinc): el de hoy de `viga_bastidor` (L/240 y
  0,6·fy) y `columna.py` (Euler/Johnson, FS ≥ 3), con E y fy de `materials`.
- **E.010** (madera latifoliada por GRUPO A/B/C/D, RNE E.010 2021): esfuerzos ADMISIBLES del grupo
  (Tabla 3) y el **E mínimo** por elemento (Art. 17: el promedio sólo en acción de conjunto). El
  grupo se lee del material o del nombre («Grupo C (E.010)») o, sin él, de la especie tabulada
  (`madera_clase.GRUPO_DE_ESPECIE`: copaiba = C, E.010 Anexo 1), y la regla lo dice.
- **EN 1995** (madera de clase EN 338 o un tablero de producto: contrachapado EN 636, fenólico EN
  314-2, OSB/3 EN 300, MDF EN 622-5): valores CARACTERÍSTICOS con kmod/γM (EN 1995-1-1 § 2.4.1,
  tablas 2.3, 3.1 y 3.2). E y fm,k del tablero: los de `materials` (EN 12369-2 o la ficha del
  fabricante, F1).
- **sin_clase**: madera sin grupo E.010 ni clase EN (ni especie con fuente): no se calcula — la
  regla sale SIN_EVALUAR justificable y dice cómo declararla. Lo que no es material estructural
  (vidrio, polímeros, caucho, cartón…) no es candidato.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..madera_clase import GRUPO_DE_ESPECIE, GRUPOS_E010, NORMA_E010, grupo_e010
from ..materials import _norm, _producto, es_madera, young_modulus, yield_strength

METALES = ("acero", "acero inoxidable", "aluminio", "laton", "cobre", "zinc")

#: EN 338:2016 tabla 1 (madera aserrada; C = conífera, D = frondosa): fm,k, fc,0,k, E0,mean y
#: E0,05 en N/mm². OJO: EN 338 no está entre las fuentes leídas en la F0 (`C:\\t\\f0-fuentes`): son
#: los valores publicados de la tabla 1 de 2016; las D sólo las de la haya (D35, D40, D45, D2 del
#: plan). La F6 los contrasta con la norma; una clase fuera de esta tabla sale SIN_EVALUAR.
EN338: dict[str, dict] = {
    "C14": {"fm_k": 14.0, "fc0_k": 16.0, "e0_mean": 7000.0, "e0_05": 4700.0},
    "C16": {"fm_k": 16.0, "fc0_k": 17.0, "e0_mean": 8000.0, "e0_05": 5400.0},
    "C18": {"fm_k": 18.0, "fc0_k": 18.0, "e0_mean": 9000.0, "e0_05": 6000.0},
    "C20": {"fm_k": 20.0, "fc0_k": 19.0, "e0_mean": 9500.0, "e0_05": 6400.0},
    "C22": {"fm_k": 22.0, "fc0_k": 20.0, "e0_mean": 10000.0, "e0_05": 6700.0},
    "C24": {"fm_k": 24.0, "fc0_k": 21.0, "e0_mean": 11000.0, "e0_05": 7400.0},
    "C27": {"fm_k": 27.0, "fc0_k": 22.0, "e0_mean": 11500.0, "e0_05": 7700.0},
    "C30": {"fm_k": 30.0, "fc0_k": 24.0, "e0_mean": 12000.0, "e0_05": 8000.0},
    "C35": {"fm_k": 35.0, "fc0_k": 25.0, "e0_mean": 13000.0, "e0_05": 8700.0},
    "C40": {"fm_k": 40.0, "fc0_k": 27.0, "e0_mean": 14000.0, "e0_05": 9400.0},
    "C45": {"fm_k": 45.0, "fc0_k": 29.0, "e0_mean": 15000.0, "e0_05": 10100.0},
    "C50": {"fm_k": 50.0, "fc0_k": 30.0, "e0_mean": 16000.0, "e0_05": 10700.0},
    "D35": {"fm_k": 35.0, "fc0_k": 25.0, "e0_mean": 12000.0, "e0_05": 10100.0},
    "D40": {"fm_k": 40.0, "fc0_k": 27.0, "e0_mean": 13000.0, "e0_05": 10900.0},
    "D45": {"fm_k": 45.0, "fc0_k": 29.0, "e0_mean": 13500.0, "e0_05": 11300.0},
}
NORMA_EN338 = "EN 338:2016 tabla 1"

#: EN 1995-1-1:2004+A1, clase de servicio 1 (interior, la de un mueble o una máquina bajo techo):
#: kmod permanente y de media duración (tabla 3.1), kdef (tabla 3.2) y γM (tabla 2.3) por producto.
_MACIZA = {"kmod_perm": 0.60, "kmod_media": 0.80, "kdef": 0.60, "gamma_m": 1.3,
           "producto": "madera maciza (EN 14081-1)"}
_TABLEROS = {
    "contrachapado": {"kmod_perm": 0.60, "kmod_media": 0.80, "kdef": 0.80, "gamma_m": 1.2,
                      "producto": "contrachapado (EN 636)"},
    "contrachapado fenolico": {"kmod_perm": 0.60, "kmod_media": 0.80, "kdef": 0.80,
                               "gamma_m": 1.2, "producto": "contrachapado fenólico (EN 636)"},
    "osb": {"kmod_perm": 0.40, "kmod_media": 0.70, "kdef": 1.50, "gamma_m": 1.2,
            "producto": "OSB/3 (EN 300)"},
    "mdf": {"kmod_perm": 0.20, "kmod_media": 0.60, "kdef": 2.25, "gamma_m": 1.3,
            "producto": "MDF.LA (EN 622-5)"},
}
NORMA_EC5 = "EN 1995-1-1:2004+A1:2008"
#: ψ2 de la acción variable (EN 1990 tabla A1.1): 0,8 = categoría E (almacenamiento), el
#: conservador; una mesa de trabajo cargada largo tiempo se parece más a un almacén que a una oficina.
PSI2 = 0.8
_CLASE_RE = re.compile(r"\b(C(?:14|16|18|20|22|24|27|30|35|40|45|50)|"
                       r"D(?:18|24|27|30|35|40|45|50|55|60|65|70|80)|"
                       r"GL\s?(?:20|22|24|26|28|30|32)[hc]?)\b")


@dataclass(frozen=True)
class Criterio:
    """Con qué se calcula la pieza. `tipo`: metal | e010 | en1995 | sin_clase | no_estructural."""

    tipo: str
    material: str
    etiqueta: str = ""          # para la memoria: «Grupo C (E.010)», «C24 (EN 338)», «acero»
    valores: dict = field(default_factory=dict)
    motivo: str = ""            # por qué no se calcula (sin_clase)
    hipotesis: tuple[str, ...] = ()

    @property
    def madera(self) -> bool:
        return self.tipo in ("e010", "en1995", "sin_clase")


def _clase_en(texto: str) -> str:
    m = _CLASE_RE.search(texto or "")
    return re.sub(r"\s+", "", m.group(1)) if m else ""


def criterio(material: str | None, nombre: str | None = None) -> Criterio:
    """El criterio de la pieza (ver el módulo). El material manda sobre el nombre; el producto
    (tablero) sobre la especie, como en `materials._norm`."""
    mat = material or ""
    clave = _norm(mat)
    if clave in METALES:
        return Criterio("metal", mat, clave, {"e": young_modulus(mat), "fy": yield_strength(mat)})
    if not es_madera(mat):
        return Criterio("no_estructural", mat, clave or mat)
    if clave not in _TABLEROS:  # el tablero escrito en el NOMBRE («Repisa - triplay fenólico»)
        clave = _producto((nombre or "").lower(), es_material=False) or clave
    if clave in _TABLEROS:
        t = _TABLEROS[clave]
        return Criterio("en1995", mat, t["producto"],
                        {**t, "fm_k": yield_strength(clave), "e0_mean": young_modulus(clave)},
                        hipotesis=(f"E y fm,k del tablero: los de la tabla de materiales ({clave}: "
                                   "EN 12369-2 o la ficha del fabricante, con su fuente).",))
    for texto in (mat, nombre or ""):
        if g := grupo_e010(texto):
            return _e010(mat, g, "declarado")
        if c := _clase_en(texto):
            if c not in EN338:
                return Criterio("sin_clase", mat, c, motivo=(
                    f"clase {c} sin valores tabulados (EN 338 de la casa: C14–C50, D35–D45)"))
            return Criterio("en1995", mat, f"{c} ({NORMA_EN338.split(' tabla')[0]})",
                            {**_MACIZA, **EN338[c], "clase": c})
    if g := GRUPO_DE_ESPECIE.get(clave):
        return _e010(mat, g, "especie")
    return Criterio("sin_clase", mat, clave or "madera", motivo=(
        "madera sin grupo E.010 ni clase EN 338 (declárala en el material: «… Grupo C (E.010)» o "
        "«… C24 (EN 338)») — sin clase no hay resistencia ni E de cálculo"))


def _e010(mat: str, grupo: str, origen: str) -> Criterio:
    hip = (f"Grupo {grupo} de la especie según {NORMA_E010} Anexo 1 (no declarado en el material: "
           "la copaiba del anexo es sólo Copaifera officinalis).",) if origen == "especie" else ()
    return Criterio("e010", mat, f"Grupo {grupo} ({NORMA_E010})",
                    {**GRUPOS_E010[grupo], "grupo": grupo}, hipotesis=hip)


__all__ = ["Criterio", "EN338", "METALES", "NORMA_EC5", "PSI2", "criterio"]
