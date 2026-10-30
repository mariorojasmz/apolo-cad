"""La clase resistente de la madera y de los tableros (plan puerta-fuera-de-catalogo, D1 y D2 con
sus ajustes de la F0). Puro: lee TEXTO (el material o el nombre de una pieza), nunca un `Document`.

- **Grupos de la norma peruana** (RNE E.010 «Madera», 2021): la madera estructural latifoliada se
  compra y se calcula por GRUPO A/B/C/D con los esfuerzos ADMISIBLES de la norma (Tablas 3 y 5),
  no con kmod/γM de EN 1995-1-1: los datos de cada grupo se guardan aquí (`GRUPOS_E010`) para el
  cálculo de flecha de la madera fuera de catálogo (F4); nunca se mezclan con los de clase EN.
  E.010 no fija el formato de la designación; su Art. 11.5 pide en los planos el grupo y el
  contenido de humedad. Forma propuesta: «copaiba, Grupo C (E.010), CH ≤ 22 %».
- **La clase de cada especie tabulada**, sólo con fuente (`GRUPO_DE_ESPECIE`). No se pone sola en
  la BOM: la escribe quien modela (la FALLA de `bom.comprable` la sugiere, `sugerencia`).
- **La norma de un tablero o una madera escrita en el NOMBRE** de la pieza (`norma_madera_del_nombre`):
  sólo las normas de producto de madera (`NORMAS_MADERA`), nunca la de la tornillería que la cruza
  («Tablero (con tornillos DIN 7997)» no es un tablero DIN 7997).
"""

from __future__ import annotations

import re

#: RNE E.010 (2021), Tabla 3 (esfuerzos admisibles para latifoliadas, MPa, CH ≤ 22 %) y Tabla 5
#: (módulo de elasticidad, MPa): fm flexión, ft tracción ∥, fc_par compresión ∥, fc_perp
#: compresión ⊥, fv corte ∥; `e_min` = el menor de los E promedio de las especies del grupo, el
#: que se usa POR ELEMENTO; `e_prom` sólo en acción de conjunto (Art. 17: entablados, viguetas a
#: ≤ 60 cm). Tabla 2: densidad básica (g/cm³). El grupo D es nuevo en 2021: su fm 6,8 y su Emín
#: 4 414 se verificaron en la F0; el resto de su fila se leyó del texto del PDF (columnas
#: desalineadas; las de A, B y C coinciden con la E.010 de 2006 en kg/cm²).
GRUPOS_E010: dict[str, dict] = {
    "A": {"fm": 20.6, "ft": 14.2, "fc_par": 14.2, "fc_perp": 3.9, "fv": 1.5,
          "e_min": 9316.0, "e_prom": 12748.0, "densidad_basica": (0.71, None)},
    "B": {"fm": 14.7, "ft": 10.3, "fc_par": 10.8, "fc_perp": 2.7, "fv": 1.2,
          "e_min": 7355.0, "e_prom": 9806.0, "densidad_basica": (0.56, 0.70)},
    "C": {"fm": 9.8, "ft": 7.3, "fc_par": 7.8, "fc_perp": 1.5, "fv": 0.8,
          "e_min": 5394.0, "e_prom": 8826.0, "densidad_basica": (0.40, 0.55)},
    "D": {"fm": 6.8, "ft": 5.8, "fc_par": 6.2, "fc_perp": 1.3, "fv": 0.6,
          "e_min": 4414.0, "e_prom": 6400.0, "densidad_basica": (0.36, 0.39)},
}
NORMA_E010 = "RNE E.010 (2021)"

#: El grupo E.010 de cada especie tabulada en `materials`, sólo con fuente:
#: - copaiba: Grupo C, E.010 Anexo 1 (fila 15). OJO: el anexo nombra sólo *Copaifera officinalis*;
#:   *C. paupera* y *C. reticulata*, las otras copaibas del mercado, no figuran;
#: - pino radiata y haya: no están en E.010; su clase EN 338 depende del GRADO visual (radiata:
#:   UNE 56544 ME-1 → C24, ME-2 → C18, CTE DB SE-M tabla C.1 y CEN AGR-VISUAL 2024; haya: H1 → D40,
#:   H2 → D35 en Francia, LS1 → D45 en Italia, AGR-VISUAL 2024): la escribe quien modela;
#: - eucalipto (*E. globulus*): sin fuente primaria (el D40 por UNE 56546 sólo sale en
#:   secundarias). No se inventa: la FALLA queda hasta que quien modela la declare.
GRUPO_DE_ESPECIE = {"copaiba": "C"}

#: «Grupo C (E.010)», «grupo C RNE E.010», «E.010 Grupo C»: el grupo cuenta sólo si el texto nombra
#: la norma (un «grupo B» suelto puede ser otra cosa)
_GRUPO_RE = re.compile(r"\bgrupo\s+([ABCD])\b", re.I)
_E010_RE = re.compile(r"\bE\s?[.\-]?\s?010\b")

#: las normas de PRODUCTO de madera y tableros que valen escritas en el NOMBRE de la pieza: EN 300
#: (OSB), 312 (aglomerado), 314 (encolado del contrachapado), 338 (clases), 622 (tableros de
#: fibras), 636 (contrachapado), 1912 (asignación de clases), 12369 (valores de cálculo), 13353
#: (tablero macizo), 13986 (tableros en construcción), 14080 (laminada), 14081 (marcado CE),
#: 14279 (LVL), 15497 (empalmada), 16351 (CLT); ISO 12465 y 13609 (contrachapado); DIN 4074
#: (clasificación visual), DIN 68705 (contrachapado); UNE 56544 y 56546 (clasificación visual);
#: NTP 251.xxx (las de madera del INACAL)
_NORMAS_EN = ("300", "312", "314", "338", "622", "636", "1912", "12369", "13353", "13986",
              "14080", "14081", "14279", "15497", "16351")
NORMAS_MADERA = re.compile(
    r"\b(?:(EN|ISO|DIN|UNE|NTP)\s*-?\s*(" + "|".join(_NORMAS_EN) + r"|12465|13609|4074|68705|"
    r"56544|56546|251\.\d{3})((?:-\d+)*))(?![\d.])")
#: la clase EN 338 / EN 14080 (la misma lista que `bom_compra`)
_CLASE_RE = re.compile(r"\b(C(?:14|16|18|20|22|24|27|30|35|40|45|50)|"
                       r"D(?:18|24|27|30|35|40|45|50|55|60|65|70|80)|"
                       r"GL\s?(?:20|22|24|26|28|30|32)[hc]?)\b")

#: la designación que se sugiere cuando falta, por clave de `materials`
_SUGERENCIA = {
    "copaiba": "«copaiba, Grupo C (E.010), CH ≤ 22 %»",
    "radiata": "«pino radiata C24 (EN 338)» (grado visual UNE 56544 ME-1)",
    "haya": "«haya D40 (EN 338)» (grado visual H1)",
    "contrachapado": "«contrachapado EN 636-2» (o «triplay fenólico EN 314-2»)",
    "contrachapado fenolico": "«triplay fenólico EN 314-2»",
    "mdf": "«MDF EN 622-5»",
    "osb": "«OSB/3 EN 300»",
}
_SUGERENCIA_GENERICA = "«pino radiata C16 (EN 338)», «triplay EN 636-2», «… Grupo C (E.010)»"


def grupo_e010(texto: str | None) -> str:
    """El grupo E.010 que DECLARA el texto («A»…«D»), o '' si no lo declara con su norma."""
    t = texto or ""
    m = _GRUPO_RE.search(t)
    return m.group(1).upper() if m and _E010_RE.search(t) else ""


def designacion_e010(grupo: str) -> str:
    return f"E.010 Grupo {grupo}"


def norma_madera_del_nombre(nombre: str | None) -> str:
    """La norma de madera que escribe el NOMBRE de la pieza («Repisa (triplay fenólico 18 mm EN
    314-2)» → «EN 314-2»; «Peldaño (copaiba, Grupo C (E.010))» → «E.010 Grupo C»), con su clase
    EN 338 si la escribe junto a la norma; '' si no nombra una norma de producto de madera."""
    texto = nombre or ""
    if g := grupo_e010(texto):
        return designacion_e010(g)
    m = NORMAS_MADERA.search(texto)
    if not m:
        return ""
    norma = f"{m.group(1).upper()} {m.group(2)}{m.group(3)}"
    c = _CLASE_RE.search(texto)
    return f"{norma} {_sin_espacios(c.group(1))}" if c else norma


def _sin_espacios(texto: str) -> str:
    return re.sub(r"\s+", "", texto)


def grupo_contradice(clave: str, grupo: str) -> str | None:
    """Por qué el grupo declarado no vale para la especie (uno MEJOR que el de su fuente: «copaiba
    Grupo A»), o None. Uno peor (más conservador) vale."""
    tabla = GRUPO_DE_ESPECIE.get(clave)
    if not tabla or not grupo or grupo >= tabla:  # A < B < C < D: «mayor» = más débil
        return None
    return (f"«{clave}» es Grupo {tabla} según E.010 Anexo 1 (sólo Copaifera officinalis), no "
            f"Grupo {grupo}")


def sugerencia(clave: str) -> str:
    """Cómo se declara la madera de esa clave (`materials._norm`) para comprarla."""
    return _SUGERENCIA.get(clave, _SUGERENCIA_GENERICA)
