"""Roles de pieza que el sistema LEE del NOMBRE (la excepción a «nombres por rol, no por
medida»: CLAUDE.md raíz § Paramétrico). Fuente única: el FEA de ensamblaje busca la cama
que recibe la carga y la lámina de instalación, la altura de trabajo y las piezas de
servicio, con los MISMOS patrones; la propuesta de estructura (`criterio_uniones.py`) decide el
tipo de cada unión por el rol de sus dos piezas (`rol_union`)."""

from __future__ import annotations

import re

# rol de superficie de carga (recibe el producto): la cama/mesa/deck del transportador
BED_RE = re.compile(r"\b(cama|mesa|bed|deck|tablero|placa\s*sup|superficie\s*de\s*carga)\b", re.I)
# piezas que se EXTRAEN para mantenimiento → su ancho es la holgura de servicio a dejar
# libre a un costado (V7.6 fase C, lámina de instalación)
SERVICE_RE = re.compile(r"\b(motorreductor|motor|tambor|rodillo\s+de\s+cola)\b", re.I)

# --- Roles de UNIÓN (plan mcp-sin-friccion, D6) -------------------------------------------
# Se leen del SUSTANTIVO que encabeza un tramo del nombre (anclados al inicio): «Eje del
# rodillo» es un eje, no un rodillo; «Separador de guarda» es estructura, no guarda. El tramo es
# lo que separa « · » (un super-comando nombra «{máquina} · {rol}» y una guarda partida, «Guarda
# de la transmisión · pared exterior»): manda el último tramo que encabece un rol.
_GIRA_PARTE = r"(tubo|buje|cubo|maza|brida|manto|camisa)\s+(del?|de\s+la)\s+"
_GIRA_CUERPO = r"(rodillo|tambor|polea|pi[ñn][oó]n|catarina|sprocket|engrane|engranaje|rueda|volante)"
_ROLES_NOMBRE = (
    ("tuerca", r"(contra)?tuercas?|nuts?"),
    ("perno", r"pernos?|tornillos?|torniller[ií]a|bul[oó]n|esp[aá]rragos?|prisioneros?|"
              r"varilla\s+roscada|bolts?|screws?|studs?"),
    ("chumacera", r"chumaceras?|soporte\s+de\s+rodamiento|pillow\s*block|uc[pft]l?\d*"),
    ("eje", r"ejes?|flechas?|[aá]rbol|shaft|axle"),
    ("flexible", r"cadenas?|correas?|bandas?|fajas?|cintas?|chain|belt"),
    ("equipo", r"moto-?reductor(es)?|motor(es)?|reductor(es)?|gear-?motor"),
    ("guarda", r"guardas?|cubiertas?|protecci[oó]n|cubre\w*|c[aá]rter|bandejas?|resguardo|guard"),
    ("gira", _GIRA_PARTE + _GIRA_CUERPO + "|" + _GIRA_CUERPO),
    ("estructura", r"patas?|largueros?|travesa[ñn]os?|placas?|bases?|columnas?|postes?|vigas?|"
                   r"perfil(es)?|bastidor|marco|soportes?|m[ée]nsulas?|separador(es)?|riostras?|"
                   r"refuerzos?|cartelas?|angular(es)?|chasis|apoyos?|frame|leg|beam"),
)
_ROL_RE = [(rol, re.compile(rf"^\s*({pat})\b", re.I)) for rol, pat in _ROLES_NOMBRE]
_FLEXIBLE_RE = dict(_ROL_RE)["flexible"]
_RODAMIENTO_RE = re.compile(r"\b(rodamientos?|bearings?|rodaje)\b", re.I)
# categorías del catálogo que deciden el rol antes que el nombre (la tornillería y lo que gira)
_ROL_CATEGORIA = {
    "tuercas": "tuerca", "pernos": "perno", "tornilleria": "perno", "tornilleria_madera": "perno",
    "rodamientos": "rodamiento", "chumaceras": "chumacera", "motorreductores": "equipo",
    "motorreductores_sinfin": "equipo", "rodillos": "gira", "tambores": "gira",
    "guardas": "guarda",
}
_ESTRUCTURA_CATEGORIA = {"perfiles_abiertos", "tubos_estructurales", "perfiles", "patas"}


def rol_union(nombre: str | None, categoria: str | None = None,
              nombre_catalogo: str | None = None, maquinas=()) -> tuple[str, str]:
    """(rol, cuerpo) de una pieza para decidir sus uniones. `rol`: tuerca, perno, chumacera,
    rodamiento, eje, flexible, equipo, guarda, gira, estructura o «» (sin rol: decide la
    geometría). `cuerpo`: el tramo del nombre que lo decidió, sin números ni paréntesis («Guarda
    de la transmisión · extremo (+X)» → «guarda de la transmisión»): dos partes de la MISMA
    guarda comparten cuerpo.

    Primero el catálogo de tornillería, rodamientos, equipos y lo que gira (`transmision` es
    flexible si el componente es una cadena o correa, si no gira); después el nombre (tramos de
    « · », del último al primero, sin los que nombran un grupo de `maquinas`: «Faja de banda ·
    Oreja» no es una banda; «… con rodamiento» es un asiento de rodamiento); por último los
    perfiles estructurales del catálogo."""
    if categoria in _ROL_CATEGORIA:
        return _ROL_CATEGORIA[categoria], ""
    if categoria == "transmision":
        return ("flexible" if _FLEXIBLE_RE.match(nombre_catalogo or "") else "gira"), ""
    tramos = [t for t in (nombre or "").split("·") if t.strip() and t.strip() not in maquinas]
    for tramo in reversed(tramos):
        cuerpo = re.sub(r"\([^)]*\)|\d+", "", tramo).strip().lower()
        for rol, regex in _ROL_RE:
            if regex.match(tramo):
                if rol in ("estructura", "gira") and _RODAMIENTO_RE.search(tramo):
                    return "rodamiento", cuerpo
                return rol, cuerpo
        if _RODAMIENTO_RE.search(tramo):
            return "rodamiento", cuerpo
    return ("estructura" if categoria in _ESTRUCTURA_CATEGORIA else ""), ""
