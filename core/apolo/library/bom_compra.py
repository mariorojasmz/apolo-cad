"""Lo que la BOM lee de la pieza para COMPRAR y CORTAR sin leer su nombre (plan
bom-de-compra-fiel). Puro sobre la escena: `bom.bom_from_scene` lo llama por pieza.

- **D1. Chapa con ficha** (`Feature.chapa`): espesor, desarrollo y pliegues del MISMO
  `chapa_ficha.desarrollo` de la lista de corte (`cutlist_medida.fila_chapa`) y la norma del
  material (`norma_de_chapa`: la que nombra el material o la pieza, si no la del material
  genérico de la tabla `NORMA_CHAPA`).
- **D2. Perfil de catálogo cortable**: el largo exterior y el corte de cada extremo MEDIDOS
  (`cutlist_medida.medidas`, la medida de la lista de corte). Lo declarado (`cut_length`,
  `miter`) se contrasta: si coincide (± 1 mm, ± 0,5°) la fila conserva el largo declarado (la de
  siempre); si no, manda lo medido y la fila lo dice en `aviso`. Una copia de patrón (sin
  `miter`) agrupa con su original: la clave es la medida.
- **D3. La pieza que se fabrica**: dos piezas de la misma ref, largo y corte que difieren en su
  volumen (taladros u otra operación) no comparten fila (`VOL_REL`); las filas que quedan con la
  misma descripción llevan su `marca` (la pieza representante: `marcar`).

Y la norma de TODA pieza a medida de metal (D3 de hallazgos-del-revisor-en-la-puerta,
`norma_de_material`): lo declarado gana; si no, la del genérico según la FORMA del producto.
"""

from __future__ import annotations

import re

from .cutlist_medida import _TOL_L, es_perfil, fila_chapa, medidas, texto_angulos

#: volumen relativo bajo el cual dos piezas de la misma ref y corte son la MISMA (D3): el ruido de
#: OCCT entre copias es ~1e-9; un taladro Ø9 en un ángulo de 6 mm es ~6e-4 de su volumen
VOL_REL = 1e-4
_VOL_ABS = 1.0  # mm³

#: la norma de chapa del material GENÉRICO (D1): la de su límite elástico tabulado en
#: `materials.YIELD_MPA` (acero = A36, inoxidable = AISI 304, aluminio = 6061-T6)
NORMA_CHAPA = {
    "acero": "ASTM A36 (≈ EN 10025-2 S235JR)",
    "acero inoxidable": "ASTM A240 (AISI 304)",
    "aluminio": "ASTM B209 (6061-T6)",
}
#: D3 de hallazgos-del-revisor-en-la-puerta: la norma del producto según su FORMA, con el MISMO
#: grado que usa el cálculo (`YIELD_MPA`): el tubo inox es ASTM A554, la barra ASTM A276; el tubo
#: de acero al carbono ASTM A500 (Fy ≥ 250 MPa en todos sus grados, el cálculo usa 250); el
#: aluminio extruido ASTM B221. Lo que no está aquí (plancha, placa, pletina) es `NORMA_CHAPA`.
NORMA_FORMA = {
    ("acero", "tubo"): "ASTM A500",
    ("acero inoxidable", "tubo"): "ASTM A554",
    ("acero inoxidable", "barra"): "ASTM A276",
    ("aluminio", "tubo"): "ASTM B221",
    ("aluminio", "barra"): "ASTM B221",
}
#: el grado del material genérico, el de su `YIELD_MPA`
GRADO = {"acero inoxidable": "AISI 304", "aluminio": "6061-T6"}
#: la norma de la plancha (y de la barra de acero al carbono: A36 cubre planchas, barras y
#: perfiles) sin el grado; `NORMA_CHAPA` = ésta con el grado de `GRADO`
_BASE_PLANCHA = {"acero": NORMA_CHAPA["acero"], "acero inoxidable": "ASTM A240",
                 "aluminio": "ASTM B209"}
#: los materiales que son el genérico sin calificar: «acero zincado» o «acero galvanizado» no
#: dicen de qué acero base es (no se inventa)
_GENERICOS = {"acero", "acero al carbono", "acero estructural", "acero inoxidable", "acero inox",
              "inox", "aluminio"}
_NORMA_RE = re.compile(r"\b(ASTM\s*[AB]\d{2,4}(?:\s+Gr\.?\s*[A-Z0-9]+\b)?|EN\s*10\d{3}(?:-\d)?|"
                       r"JIS\s*G\s*\d{4})", re.I)
_GRADO_RE = re.compile(r"\b(AISI\s*\d{3}L?|SAE\s*\d{4})\b", re.I)
#: un grado de acero escrito pelado («A36», «A572 Gr.50», «S355J2»): su norma es implícita
_GRADO_ASTM_RE = re.compile(r"\b(A(?:36|283|500|529|572|588|1011)(?:\s+Gr\.?\s*[A-Z0-9]+\b)?)",
                            re.I)
_GRADO_EN_RE = re.compile(r"\b(S(?:235|275|355)(?:JR|J0|J2)?)\b", re.I)
#: la FORMA del producto por el ROL (anclada, o «tubo 40x40…» / «barra cuadrada…» descrita):
#: «Placa de cierre del tubo» es una placa
_TUBO_RE = re.compile(r"^(tubos?|tuber[ií]as?|ca[ñn]os?)\b|\btubos?\s+(\d|ø|cuadrad|redond|"
                      r"rectangular|inox|de\s+acero|estructural|hss)", re.I)
#: los metales de `materials.DENSITY_KG_MM3` (lo que pide norma o grado, D4)
_METALES = {"acero", "acero inoxidable", "aluminio", "laton", "cobre", "zinc"}
#: latón y cobre (D1 de puerta-fuera-de-catalogo): la norma del producto (EN 12164 barra de
#: mecanizado, EN 12163/12165/12168, EN 1652/13599 plancha, EN 13600 tubo, EN 13601 barra de
#: cobre, EN 13602 alambre de conductores, ASTM B…, IEC 60228 conductor) y la designación de la
#: aleación (CW614N / CuZn39Pb3, Cu-ETP / CW004A, UNS C36000 / C11000)
_NORMA_CU_RE = re.compile(r"\b(EN\s*(?:1652|1653|1654|12163|12164|12165|12167|12168|12449|"
                          r"13599|13600|13601|13602)|ASTM\s*B\d{1,4}|IEC\s*60228)\b", re.I)
_GRADO_CU_RE = re.compile(r"\b(CW\d{3}[A-Z]|CuZn\d+(?:Pb\d+)?(?:As)?|Cu-(?:ETP|OF|DHP|FRHC)|"
                          r"C[1-9]\d{4})\b")
#: el cobre sin calificar es el Cu-ETP del cálculo (`materials`: su ρ y su E), como el acero es el
#: A36; el latón NO: el del cálculo (CW614N) es de barra y una plancha es CuZn37 (se declara)
_COBRE_GENERICO = {"cobre", "cobre electrolitico", "cobre electrolítico", "cu"}
GRADO_COBRE = "Cu-ETP (CW004A)"
#: la norma de un producto de madera escrita en su material: «EN 338», «EN 636-2», «DIN 68150»
#: (en mayúsculas: «seca en 12 %» no es una norma)
_NORMA_MADERA_RE = re.compile(r"\b(EN|ISO|DIN|UNE|NTP|NCh|JAS)\s*-?\s*(\d{2,6}(?:[-.]\d+)*)")
#: la clase resistente de EN 338 (C14–C50, D18–D80) o EN 14080 (GL20–GL32): «D10» no es clase
_CLASE_MADERA_RE = re.compile(r"\b(C(?:14|16|18|20|22|24|27|30|35|40|45|50)|"
                              r"D(?:18|24|27|30|35|40|45|50|55|60|65|70|80)|"
                              r"GL\s?(?:20|22|24|26|28|30|32)[hc]?)\b")
_BARRA_RE = re.compile(r"^(barras?|varillas?|ejes?|pasador(es)?|redondos?|bul[oó]n(es)?|"
                       r"casquillos?|bujes?|espigas?|husillos?)\b|\bbarras?\s+(\d|ø|cuadrad|"
                       r"redond|maciz|lisa|hexagonal|calibrad)", re.I)


def _limpio(texto: str) -> str:
    t = re.sub(r"\s+", " ", texto.strip())
    t = re.sub(r"^(astm|en|jis)\b", lambda m: m.group(1).upper(), t, flags=re.I)
    t = re.sub(r"\b([ab])(\d)", lambda m: m.group(1).upper() + m.group(2), t)
    return re.sub(r"\bgr\.?\s*", "Gr.", t, flags=re.I)


def forma_de(nombre: str | None) -> str:
    """«tubo», «barra» o «plancha» (plancha, placa, pletina y el resto) por el ROL de la pieza."""
    from .materials import piece_role

    rol = piece_role(nombre or "")
    if _TUBO_RE.search(rol):
        return "tubo"
    return "barra" if _BARRA_RE.search(rol) else "plancha"


def norma_de_material(material: str | None, nombre: str | None, forma: str = "plancha") -> str:
    """La norma de la pieza de METAL hecha a medida (D1 de bom-de-compra-fiel para la chapa y D3
    de hallazgos-del-revisor para toda pieza), '' si no se sabe (nunca inventada):

    1. la norma que nombra su material o su pieza («ASTM A572 Gr.50», «… tubo ASTM A554»), con el
       grado declarado entre paréntesis si es otro dato («ASTM A554 (AISI 304)»);
    2. un grado pelado declarado («A36» → «ASTM A36», «S355J2» → «EN 10025-2 S355J2»);
    3. sin norma: la de la FORMA del producto (`NORMA_FORMA`, si no `NORMA_CHAPA`) para el material
       genérico o con su grado AISI declarado («acero inoxidable AISI 304»).

    La madera, la norma que escribe su material o su nombre (`norma_de_madera`); el latón y el
    cobre, `norma_de_cobre`."""
    from .materials import _norm

    if es_de_madera(material):
        return norma_de_madera(material, nombre)
    textos = [t for t in (material, nombre) if t]
    if _norm(_cabeza_material(material)) in ("laton", "cobre"):
        return norma_de_cobre(material, nombre)
    norma = next((_limpio(m.group(1)) for t in textos if (m := _NORMA_RE.search(t))), "")
    grado = next((re.sub(r"\s+", " ", m.group(1).upper()) for t in textos
                  if (m := _GRADO_RE.search(t))), "")
    if norma:
        return f"{norma} ({grado})" if grado else norma
    for t in textos:
        if m := _GRADO_ASTM_RE.search(t):
            return "ASTM " + _limpio(m.group(1))
        if m := _GRADO_EN_RE.search(t):
            return "EN 10025-2 " + m.group(1).upper()
    clave = _norm(material)
    if not grado and (material or "").strip().lower() not in _GENERICOS:
        return ""
    if grado and clave != "acero inoxidable":
        return grado  # «SAE 1045», un AISI de un acero al carbono: el grado es la designación
    base = NORMA_FORMA.get((clave, forma)) or _BASE_PLANCHA.get(clave)
    if base is None:
        return ""
    return f"{base} ({grado or GRADO[clave]})" if clave in GRADO else base


def _cabeza_material(material: str | None) -> str:
    """El material antes de su primer paréntesis: «lona poliéster (densidad asimilada a madera)»
    es lona, no madera."""
    return (material or "").split("(", 1)[0]


def es_de_madera(material: str | None) -> bool:
    """¿El material (por su cabeza) es una madera? La que pide norma o clase en la BOM (D4)."""
    from .materials import es_madera

    return es_madera(_cabeza_material(material))


def es_de_metal(material: str | None) -> bool:
    """¿El material (por su cabeza) es un metal? El que pide norma o grado en la BOM (D3, D4)."""
    from .materials import _norm

    return _norm(_cabeza_material(material)) in _METALES


def norma_de_cobre(material: str | None, nombre: str | None) -> str:
    """La norma del latón o del cobre a medida (D1 de puerta-fuera-de-catalogo), '' si no se sabe:
    la norma de producto y la designación de la aleación que nombran el material o la pieza
    («latón CW614N (EN 12164)» → «EN 12164 (CW614N)»); la designación sola alcanza («CW614N»,
    como el SAE 1045); el cobre sin calificar es Cu-ETP (CW004A), el del cálculo."""
    textos = [t for t in (material, nombre) if t]
    norma = next((re.sub(r"\s+", " ", m.group(1)).upper() for t in textos
                  if (m := _NORMA_CU_RE.search(t))), "")
    grado = next((m.group(1) for t in textos if (m := _GRADO_CU_RE.search(t))), "")
    if norma:
        return f"{norma} ({grado})" if grado else norma
    if grado:
        return grado
    return GRADO_COBRE if (material or "").strip().lower() in _COBRE_GENERICO else ""


def norma_de_madera(material: str | None, nombre: str | None = None) -> str:
    """La norma de la madera que ESCRIBE su material (D4 de hallazgos-del-revisor), '' si no la
    escribe: la norma del producto («EN 636-2», «EN 622-5», «DIN 68150») con su clase resistente
    («clase C16 (EN 338)» → «EN 338 C16»); una clase pelada es de EN 338 (C, D) o EN 14080 (GL);
    el grupo de la norma peruana, «Grupo C (E.010)» → «E.010 Grupo C» (D2 de
    puerta-fuera-de-catalogo). Si el material no la escribe, la del NOMBRE de la pieza, pero sólo
    una norma de producto de madera (`madera_clase.norma_madera_del_nombre`): el nombre de una
    pieza de madera también nombra la tornillería que la cruza («… con tornillos DIN 7997»)."""
    from .madera_clase import designacion_e010, grupo_e010, norma_madera_del_nombre

    texto = material or ""
    if g := grupo_e010(texto):
        return designacion_e010(g)
    norma = _norma_madera_del_material(texto)
    return norma or norma_madera_del_nombre(nombre)


def _norma_madera_del_material(texto: str) -> str:
    m = _NORMA_MADERA_RE.search(texto)
    norma = f"{m.group(1).upper()} {m.group(2)}" if m else ""
    c = _CLASE_MADERA_RE.search(texto)
    clase = re.sub(r"\s+", "", c.group(1)) if c else ""
    if not norma and clase:
        norma = "EN 14080" if clase.startswith("GL") else "EN 338"
    return f"{norma} {clase}".strip()


def norma_de_chapa(material: str | None, nombre: str | None) -> str:
    """La norma de la chapa con ficha (D1): `norma_de_material` con la forma «plancha»."""
    return norma_de_material(material, nombre, "plancha")


def campos_chapa(feat, material: str | None) -> dict | None:
    """{espesor_mm, desarrollo_mm, pliegues, norma, texto} de una pieza con ficha de chapa (D1),
    o None (sin ficha, varios sólidos o una ficha que no despliega: la fila de siempre)."""
    if not getattr(feat, "chapa", None):
        return None
    try:
        if len(list(feat.shape.solids())) > 1:
            return None
    except Exception:  # noqa: BLE001
        return None
    r = fila_chapa(feat, material)
    if r is None:
        return None
    (t, a, b), _firma, campos = r
    n = int(campos.get("pliegues") or 0)
    texto = f" — chapa e={t:g} mm, desarrollo {a:g}×{b:g} mm" + (
        f", {n} pliegue{'s' if n != 1 else ''}" if n else "")
    return {"espesor_mm": t, "desarrollo_mm": [a, b], "pliegues": n,
            "norma": norma_de_chapa(material, getattr(feat, "name", "")), "texto": texto}


def medida_perfil(feat, comp, memo: dict) -> dict | None:
    """{largo, clave, angulos (texto « ∠…» o ''), aviso} de un perfil de catálogo de UNA barra
    medida (D2), o None (no es perfil, varias barras o no se deja medir: la fila de siempre)."""
    if not es_perfil(comp):
        return None
    try:
        solidos = list(feat.shape.solids()) or [feat.shape]
    except Exception:  # noqa: BLE001
        return None
    if len(solidos) != 1:
        return None
    m = medidas(feat, comp, None, solidos, memo)[0]
    if m is None:
        return None
    (_t, _w, largo_medido), _firma, campos = m
    cut = getattr(feat, "cut_length", None)
    coincide = not cut or abs(float(cut) - largo_medido) <= _TOL_L
    largo = float(cut) if cut and coincide else largo_medido
    texto = texto_angulos(campos)
    # el aviso, sólo si la pieza DECLARÓ otra cosa (un inglete o un largo): la copia de un patrón
    # no hereda `miter` y no declaró «a escuadra»
    aviso = campos.get("aviso") if (getattr(feat, "miter", None) or not coincide) else None
    if campos.get("extremos"):  # despunte / especial: cada extremo por su forma
        clave = tuple((e["corte"], tuple(e["angulos"])) for e in campos["extremos"])
    elif campos.get("corte") == "inglete":  # el orden de los extremos no separa (copia girada)
        clave = tuple(sorted(float(a or 0.0) for a in (campos["angulo_1"], campos["angulo_2"])))
    else:
        clave = None
    return {"largo": largo, "clave": clave, "angulos": f" ∠{texto}" if texto else "",
            "aviso": aviso}


def volumen(feat) -> float | None:
    try:
        return float(feat.shape.volume)
    except Exception:  # noqa: BLE001
        return None


def variante(vistos: list[float], vol: float | None) -> int:
    """Índice de la variante geométrica (D3) de `vol` entre las ya vistas de su clave (agrega
    una nueva si ninguna coincide); 0 si no hay volumen."""
    if vol is None:
        return 0
    for i, v in enumerate(vistos):
        if abs(v - vol) <= max(_VOL_ABS, VOL_REL * max(abs(v), abs(vol))):
            return i
    vistos.append(vol)
    return len(vistos) - 1


def marcar(rows: list[dict], scene: dict) -> None:
    """D3: las filas que quedan con la misma ref, descripción, largo y material (piezas que
    difieren en taladros u otra operación) llevan su `marca` (la pieza representante, la de la
    lámina de plano) y la descripción la nombra. Muta las filas."""
    por: dict[tuple, list[dict]] = {}
    for r in rows:
        k = (r["ref"], r["descripcion"], r.get("longitud_mm"), r.get("material"), r.get("grupo"))
        por.setdefault(k, []).append(r)
    for filas in por.values():
        if len(filas) < 2:
            continue
        for r in filas:
            rep = r.get("_rep")
            nombre = getattr(scene.get(rep), "name", None) or rep
            r["marca"] = rep
            r["descripcion"] += f" · marca {rep} («{nombre}»)"
