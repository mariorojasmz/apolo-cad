"""MEMORIA DE CÁLCULO — el entregable que justifica el diseño (Frente A, Fase 6).

PDF multipágina estilo memoria de ingeniería: portada (proyecto + render + BASES
DE DISEÑO + índice de verificaciones + veredicto) y UNA página por verificación
CON cálculo (`calc` de la regla: entradas → fórmula → sustitución → resultado →
criterio → factor de seguridad → estado). Las reglas sin `calc` van juntas en una
tabla final de verificaciones cualitativas.

Espejo estructural de `assembly_manual.py` (reusa `_embed`/`SHEETS`,
`draw_title_block` y `sheets_to_pdf`). Consume el resultado de
`conveyor_engineering_check` + `structure_engineering_check` — no calcula nada
por su cuenta: la memoria REPORTA lo que el motor de reglas verificó.

Ningún texto se corta a N caracteres ni a N renglones (plan V8.9, cortes fijos fuera del cajetín):
cada columna se MIDE (`texto_medido.columna`) hasta el cajetín y las verificaciones cualitativas
siguen en tantas hojas como pidan.
"""

from __future__ import annotations

from datetime import date

from .assembly_manual import SHEETS, _embed
from .sheet import Label, Line, SheetModel
from .tabla import alto_linea_mm, ancho_mm, partir, piso_tabla
from .texto_medido import Parrafo, celda, columna, encajar
from .titleblock import draw_title_block

# etiquetas amistosas de las claves de requisitos en la tabla BASES DE DISEÑO
_REQ_LABELS = {
    "carga_kg": "Carga por paquete",
    "largo_paquete_mm": "Largo de paquete",
    "ancho_paquete_mm": "Ancho de paquete",
    "alto_paquete_mm": "Alto de paquete",
    "velocidad_m_s": "Velocidad objetivo",
    "inclinacion_deg": "Inclinación",
    "temperatura_c": "Temperatura ambiente",
    "ancho_producto_mm": "Ancho máximo de producto",
    "desarmable": "Desarmable",
    "instalacion": "Instalación",
    "producto": "Producto",
    "entorno": "Entorno",
    "normativa": "Normativa",
    "notas": "Notas",
}
_REQ_UNITS = {
    "carga_kg": "kg", "largo_paquete_mm": "mm", "ancho_paquete_mm": "mm",
    "alto_paquete_mm": "mm", "velocidad_m_s": "m/s", "inclinacion_deg": "°",
    "temperatura_c": "°C", "ancho_producto_mm": "mm",
}
_ESTADO = {"ok": "OK", "aviso": "AVISO", "error": "ERROR"}


def _verdict(rules: list[dict]) -> str:
    """Veredicto global de la memoria. «Aprobado» EXIGE que algo se haya verificado: un
    documento con cero verificaciones OK no aprueba nada — aprueba el vacío. Hallazgo del
    SEGUNDO testigo (2026-07-24): un proyecto sin uniones ni requisitos declarados salía
    «APROBADO CON AVISOS» con 0 OK, que es exactamente la clase de falso positivo que la
    doctrina prohíbe."""
    estados = [r.get("estado") for r in rules]
    if "error" in estados:
        return "NO CONFORME"
    if not any(e == "ok" for e in estados):
        return "NO CONCLUYENTE"
    if "aviso" in estados:
        return "APROBADO CON AVISOS"
    return "APROBADO"


#: El veredicto de la portada, sin componer el PDF: lo lee la puerta de publicación
#: (`services/memoria_reglas.veredicto_memoria`; «NO CONFORME» bloquea, plan puerta-de-publicacion D2).
veredicto = _verdict


def _req_rows(requirements: dict) -> list[str]:
    """Una fila por requisito; lo que el ingeniero ASUMIÓ (lista `asumidos`, ficha del
    encargo) lleva «(asumido)»: la memoria no presenta un supuesto como dato del cliente."""
    asumidos = requirements.get("asumidos")
    asumidos = set(asumidos) if isinstance(asumidos, list) else set()
    rows = []
    for key, value in requirements.items():
        if key == "asumidos":
            continue
        label = _REQ_LABELS.get(key, key)
        unit = _REQ_UNITS.get(key, "")
        if isinstance(value, bool):
            val = "sí" if value else "no"
        elif isinstance(value, (int, float)):
            val = f"{value:g} {unit}".strip()
        else:
            val = str(value)
        rows.append(f"{label}:  {val}" + ("  (asumido)" if key in asumidos else ""))
    return rows


#: lo más chico que queda la foto de la portada (mm de alto, desde y = 58): las bases de diseño y
#: las normas bajan hasta ahí y, si no entran, bajan de escala (V8.9, cortes fijos)
_FOTO_MIN = 40.0


def _cover(W: float, H: float, *, project_name: str, png: bytes | None,
           requirements: dict, sections: list[dict], misc: list[dict],
           rules: list[dict], base_meta: dict, hojas_misc: int = 1) -> SheetModel:
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    m.labels.append(Label(16, H - 24, "MEMORIA DE CÁLCULO", 8.0, anchor="start"))
    size, (nombre,) = encajar(str(project_name), W - 32.0, 4.6)  # medido (antes, cortado a 54)
    m.labels.append(Label(16, H - 34, nombre, size, anchor="start"))
    m.lines.append(Line(14, H - 39, W - 14, H - 39, "frame"))

    # columna izquierda: bases de diseño + render
    y = H - 48
    m.labels.append(Label(16, y, "BASES DE DISEÑO", 3.6, anchor="start"))
    y -= 6
    reqs = _req_rows(requirements) or ["(sin requisitos declarados — parámetros de la llamada)"]
    # normas aplicadas por las verificaciones (V5.10) — memoria NORMATIVA
    normas = sorted({str(r.get("calc", {}).get("norma", "")).split(" — ")[0].split(",")[0]
                     for r in rules if r.get("calc", {}).get("norma")})
    # todos los requisitos y todas las normas, ENTEROS (antes: 10 requisitos cortados a 60 y las
    # normas a 62): partidos en la columna, sobre la foto
    parrafos = [Parrafo(row, 2.7, 4.4) for row in reqs]
    if normas:
        parrafos.append(Parrafo("Normas aplicadas: " + " · ".join(normas), 2.7, 4.4))
    y = columna(m, 18, y, parrafos, W * 0.52 - 4 - 18, piso=58 + _FOTO_MIN + 4)
    if png:
        _embed(m, png, (16, 58, 118, max(y - 62, _FOTO_MIN)))

    # columna derecha: índice de verificaciones con estado
    rx = W * 0.52
    m.labels.append(Label(rx, H - 48, "ÍNDICE DE VERIFICACIONES", 3.6, anchor="start"))
    yy = H - 54
    # veredicto y resultado SOBRE la tabla de revisiones (antes, fijos en y = 58 y 66: la tabla
    # de revisiones de la memoria los pisaba); el índice baja hasta donde el «… y N más» y la
    # línea de las cualitativas no pisan el «Resultado» (antes el corte en y < 70 los encimaba)
    y_veredicto = max(58.0, piso_tabla(base_meta) + 1.2)
    y_resultado = y_veredicto + 8.0
    limite = y_resultado + 8.0 + (6.5 if misc else 0.0)
    for i, sec in enumerate(sections, start=1):
        if yy < limite and i < len(sections):
            m.labels.append(Label(rx, yy, f"… y {len(sections) - i + 1} más", 2.6, anchor="start"))
            yy -= 4.2
            break
        estado = _ESTADO.get(sec.get("estado"), "?")
        titulo = sec.get("calc", {}).get("titulo") or sec.get("regla", "")
        # medido hasta el estado (antes, cortado a 38)
        celda(m, rx, yy, W - 18 - ancho_mm(estado, 2.7) - 3.0 - rx, 2.7, f"{i}. {titulo}")
        m.labels.append(Label(W - 18, yy, estado, 2.7, anchor="end"))
        yy -= 4.2
    if misc:
        donde = "última hoja" if hojas_misc == 1 else f"últimas {hojas_misc} hojas"
        m.labels.append(Label(rx, yy - 2, f"+ {len(misc)} verificación(es) cualitativas ({donde})",
                              2.6, anchor="start"))
        yy -= 6.5

    # resumen + veredicto
    n_ok = sum(1 for r in rules if r.get("estado") == "ok")
    n_av = sum(1 for r in rules if r.get("estado") == "aviso")
    n_er = sum(1 for r in rules if r.get("estado") == "error")
    m.labels.append(Label(rx, y_resultado, f"Resultado: {n_ok} OK · {n_av} avisos · {n_er} errores",
                          3.0, anchor="start"))
    m.labels.append(Label(rx, y_veredicto, f"VEREDICTO: {_verdict(rules)}", 4.4, anchor="start"))
    draw_title_block(m, {**base_meta, "sheet_no": 1})
    return m


def _izquierda(rule: dict, calc: dict) -> list[Parrafo]:
    """La columna izquierda de una verificación: datos de entrada, verificación, recomendación,
    resultado por pieza e hipótesis, como párrafos ENTEROS (antes: 6 renglones de 58 caracteres de
    verificación, 4 de recomendación, 12 filas de 64, 2 renglones por hipótesis y 18 en total)."""
    out = [Parrafo("DATOS DE ENTRADA", 3.2, 5.5)]
    out += [Parrafo(f"{k}: {v}", 2.7, 4.2, sangria=2) for k, v in (calc.get("entradas") or {}).items()]
    out.append(Parrafo("VERIFICACIÓN", 3.2, 5.5, antes=3))
    if str(rule.get("detalle", "")).strip():
        out.append(Parrafo(str(rule["detalle"]), 2.7, 4.2, sangria=2))
    if rule.get("recomendacion"):
        out.append(Parrafo("Recomendación: " + str(rule["recomendacion"]), 2.7, 4.2, sangria=2, antes=2))
    # tabla por pieza (FEA de ensamblaje: σ_vm / FS por pieza) — bajo la verificación
    if rule.get("tabla"):
        out.append(Parrafo("RESULTADO POR PIEZA", 3.2, 5.5, antes=3))
        out += [Parrafo(str(row), 2.6, 4.0, sangria=2) for row in rule["tabla"]]
    # hipótesis y alcance (FEA: lo que un ingeniero lee ANTES de firmar — bonded/lineal,
    # exclusiones con su peso, alcance acotado, nota del analista; el alcance y la nota van al
    # final: si la hoja no alcanza, la columna baja de escala antes que cortarlos)
    if rule.get("hipotesis"):
        out.append(Parrafo("HIPÓTESIS Y ALCANCE", 3.2, 5.5, antes=3))
        out += [Parrafo("· " + str(h), 2.4, 3.8, sangria=2, sangria_sig=4) for h in rule["hipotesis"]]
    return out


def _derecha(calc: dict) -> list[Parrafo]:
    """El cálculo: fórmula → sustitución → resultado → criterio → norma → FS, cada uno ENTERO
    (antes, 3 renglones de 46 caracteres: el resultado de una viga perdía su σ)."""
    out: list[Parrafo] = []
    for header, key in (("FÓRMULA", "formula"), ("SUSTITUCIÓN", "sustitucion"),
                        ("RESULTADO", "resultado"), ("CRITERIO DE ACEPTACIÓN", "criterio"),
                        ("NORMA DE REFERENCIA", "norma")):
        if not calc.get(key):
            continue
        out.append(Parrafo(header, 3.2, 5.5, antes=2.5 if out else 0.0))
        out.append(Parrafo(str(calc[key]), 3.0, 4.6, sangria=2))
    if calc.get("fs") is not None:
        out.append(Parrafo("FACTOR DE SEGURIDAD", 3.2, 6.0, antes=2.5 if out else 0.0))
        out.append(Parrafo(f"FS = {calc['fs']:g}", 4.6, 4.6, sangria=2))
    return out


def _section_page(W: float, H: float, *, idx: int, n_sections: int, page_no: int,
                  rule: dict, base_meta: dict) -> SheetModel:
    calc = rule.get("calc", {})
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    titulo = calc.get("titulo") or rule.get("regla", "")
    estado = _ESTADO.get(rule.get("estado"), "?")
    # el título ENTERO (antes, cortado a 48): un renglón a 5,6 si cabe; si no, dos sobre la raya
    size, lineas = encajar(f"{idx}. {titulo}".upper(), W - 32 - ancho_mm(estado, 5.6) - 4.0, 5.6, 2)
    for k, ln in enumerate(lineas):
        m.labels.append(Label(16, H - 24 + (len(lineas) - 1 - k) * alto_linea_mm(size), ln, size,
                              anchor="start"))
    m.labels.append(Label(W - 16, H - 24, estado, 5.6, anchor="end"))
    m.lines.append(Line(14, H - 30, W - 14, H - 30, "frame"))
    piso = piso_tabla(base_meta)
    rx = W * 0.55
    # columna izquierda: datos de entrada, verificación, tabla e hipótesis; derecha: el cálculo
    columna(m, 16, H - 40, _izquierda(rule, calc), rx - 4 - 16, piso)
    columna(m, rx, H - 40, _derecha(calc), W - 16 - rx, piso)
    draw_title_block(m, {**base_meta, "sheet_no": page_no})
    return m


def _bloque_misc(r: dict, W: float) -> tuple[str, list[str]]:
    """(estado, renglones del detalle) de una verificación cualitativa, medidos en la hoja."""
    detalle = str(r.get("detalle", ""))
    return (_ESTADO.get(r.get("estado"), "?"),
            partir(detalle, W - 16 - 20, 2.6) if detalle.strip() else [])


def _hojas_misc(misc: list[dict], W: float, H: float, piso: float) -> list[list[int]]:
    """Las verificaciones cualitativas repartidas en hojas por ALTURA (antes: una sola hoja con 3
    renglones de 92 caracteres por regla y, lo que no entraba, «… y N verificaciones en total»)."""
    hojas: list[list[int]] = [[]]
    y = H - 40
    for i, r in enumerate(misc):
        n = len(_bloque_misc(r, W)[1])
        if hojas[-1] and y - 4.8 - max(n - 1, 0) * 4.0 < piso:
            hojas.append([])
            y = H - 40
        hojas[-1].append(i)
        y -= 4.8 + n * 4.0 + 2.5
    return hojas


def _misc_page(W: float, H: float, *, misc: list[dict], page_no: int,
               base_meta: dict, hoja: int = 1, n_hojas: int = 1) -> SheetModel:
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    titulo = "VERIFICACIONES CUALITATIVAS" + (f" ({hoja}/{n_hojas})" if n_hojas > 1 else "")
    m.labels.append(Label(16, H - 24, titulo, 5.6, anchor="start"))
    m.lines.append(Line(14, H - 30, W - 14, H - 30, "frame"))
    y = H - 40
    for r in misc:
        estado, lineas = _bloque_misc(r, W)
        celda(m, 16, y, W - 32 - ancho_mm(estado, 3.0) - 4.0, 3.0, f"· {r.get('regla', '')}")
        m.labels.append(Label(W - 16, y, estado, 3.0, anchor="end"))
        y -= 4.8
        for ln in lineas:
            m.labels.append(Label(20, y, ln, 2.6, anchor="start"))
            y -= 4.0
        y -= 2.5
    draw_title_block(m, {**base_meta, "sheet_no": page_no})
    return m


def peso_memoria(scene: dict | None, default_material: str | None = None) -> float:
    """El peso del cajetín: el de la MÁQUINA, como el del vuelco (lo oculto en la vista también
    pesa), con la MISMA fuente que `GET /api/mass-properties` (`scene_mass_properties` con el
    material del vertical, `doc.default_material()`): con `scene_weight_kg` sin el vertical, un
    «Larguero» de acero pesaba como madera y la memoria de una faja decía 252,4 kg contra los
    260,6 de mass-properties (F6 de puerta-de-publicacion). Lee OCCT: en la API va bajo
    `STATE_LOCK` y llega a `calc_report` en `meta`."""
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.mass import scene_mass_properties

    try:
        return scene_mass_properties(scene or {}, CATALOG, default_material=default_material,
                                     include_hidden=True)["total"]["masa_kg"]
    except Exception:
        return 0.0


def calc_report(scene: dict | None, *, rules: list[dict], requirements: dict,
                project_name: str = "Sin título", png: bytes | None = None,
                meta: dict | None = None, sheet: str = "A4") -> list[SheetModel]:
    """Memoria de cálculo multipágina: [portada + 1 página por regla con `calc` +
    tabla de reglas cualitativas]. `rules` = ingenieria + estructura del chequeo. `scene` sólo
    se lee para el peso cuando `meta` no trae `weight_kg` (`peso_memoria`): con él, la
    composición es pura y corre fuera de `STATE_LOCK` (plan manual-rapido, F2)."""
    W, H = SHEETS.get(sheet, SHEETS["A4"])
    sections = [r for r in rules if r.get("calc")]
    misc = [r for r in rules if not r.get("calc")]
    piso = piso_tabla({"revisions": (meta or {}).get("revisions", [])})
    hojas_misc = _hojas_misc(misc, W, H, piso) if misc else []
    n_pages = 1 + len(sections) + len(hojas_misc)
    peso = (meta or {}).get("weight_kg")
    if peso is None:
        peso = peso_memoria(scene)
    base_meta = {
        "project": project_name,
        "drawing_no": (meta or {}).get("drawing_no", "MC-001"),
        "scale": "—", "sheet": sheet, "material": "—", "finish": "—",
        "weight_kg": peso, "tolerance": "—", "units": "mm",
        "drawn_by": (meta or {}).get("drawn_by", "Apolo · agente IA"),
        "checked_by": "", "approved_by": "",
        "date": (meta or {}).get("date", date.today().isoformat()),
        "revisions": (meta or {}).get("revisions", []),
        "n_sheets": n_pages,
    }
    pages = [_cover(W, H, project_name=project_name, png=png, requirements=requirements,
                    sections=sections, misc=misc, rules=rules, base_meta=base_meta,
                    hojas_misc=max(1, len(hojas_misc)))]
    for i, rule in enumerate(sections, start=1):
        pages.append(_section_page(W, H, idx=i, n_sections=len(sections),
                                   page_no=i + 1, rule=rule, base_meta=base_meta))
    for k, idx in enumerate(hojas_misc, start=1):
        pages.append(_misc_page(W, H, misc=[misc[i] for i in idx], page_no=1 + len(sections) + k,
                                base_meta=base_meta, hoja=k, n_hojas=len(hojas_misc)))
    return pages
