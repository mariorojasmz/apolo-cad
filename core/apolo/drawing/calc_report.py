"""MEMORIA DE CÁLCULO — el entregable que justifica el diseño (Frente A, Fase 6).

PDF multipágina estilo memoria de ingeniería: portada (proyecto + render + BASES
DE DISEÑO + índice de verificaciones + veredicto) y UNA página por verificación
CON cálculo (`calc` de la regla: entradas → fórmula → sustitución → resultado →
criterio → factor de seguridad → estado). Las reglas sin `calc` van juntas en una
tabla final de verificaciones cualitativas.

Espejo estructural de `assembly_manual.py` (reusa `_embed`/`_wrap`/`SHEETS`,
`draw_title_block` y `sheets_to_pdf`). Consume el resultado de
`conveyor_engineering_check` + `structure_engineering_check` — no calcula nada
por su cuenta: la memoria REPORTA lo que el motor de reglas verificó.
"""

from __future__ import annotations

from datetime import date

from .assembly_manual import SHEETS, _embed, _wrap
from .sheet import Label, Line, SheetModel
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
    "producto": "Producto",
    "entorno": "Entorno",
    "normativa": "Normativa",
    "notas": "Notas",
}
_REQ_UNITS = {
    "carga_kg": "kg", "largo_paquete_mm": "mm", "ancho_paquete_mm": "mm",
    "alto_paquete_mm": "mm", "velocidad_m_s": "m/s", "inclinacion_deg": "°",
    "temperatura_c": "°C",
}
_ESTADO = {"ok": "OK", "aviso": "AVISO", "error": "ERROR"}


def _verdict(rules: list[dict]) -> str:
    estados = {r.get("estado") for r in rules}
    if "error" in estados:
        return "NO CONFORME"
    if "aviso" in estados:
        return "APROBADO CON AVISOS"
    return "APROBADO"


def _req_rows(requirements: dict) -> list[str]:
    rows = []
    for key, value in requirements.items():
        label = _REQ_LABELS.get(key, key)
        unit = _REQ_UNITS.get(key, "")
        val = f"{value:g} {unit}".strip() if isinstance(value, (int, float)) else str(value)
        rows.append(f"{label}:  {val}")
    return rows


def _cover(W: float, H: float, *, project_name: str, png: bytes | None,
           requirements: dict, sections: list[dict], misc: list[dict],
           rules: list[dict], base_meta: dict) -> SheetModel:
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    m.labels.append(Label(16, H - 24, "MEMORIA DE CÁLCULO", 8.0, anchor="start"))
    m.labels.append(Label(16, H - 34, str(project_name)[:54], 4.6, anchor="start"))
    m.lines.append(Line(14, H - 39, W - 14, H - 39, "frame"))

    # columna izquierda: bases de diseño + render
    y = H - 48
    m.labels.append(Label(16, y, "BASES DE DISEÑO", 3.6, anchor="start"))
    y -= 6
    reqs = _req_rows(requirements) or ["(sin requisitos declarados — parámetros de la llamada)"]
    for row in reqs[:10]:
        m.labels.append(Label(18, y, row[:60], 2.7, anchor="start"))
        y -= 4.4
    # normas aplicadas por las verificaciones (V5.10) — memoria NORMATIVA
    normas = sorted({str(r.get("calc", {}).get("norma", "")).split(" — ")[0].split(",")[0]
                     for r in rules if r.get("calc", {}).get("norma")})
    if normas:
        m.labels.append(Label(18, y, ("Normas aplicadas: " + " · ".join(normas))[:62],
                              2.7, anchor="start"))
        y -= 4.4
    if png:
        _embed(m, png, (16, 58, 118, max(y - 62, 40)))

    # columna derecha: índice de verificaciones con estado
    rx = W * 0.52
    m.labels.append(Label(rx, H - 48, "ÍNDICE DE VERIFICACIONES", 3.6, anchor="start"))
    yy = H - 54
    for i, sec in enumerate(sections, start=1):
        estado = _ESTADO.get(sec.get("estado"), "?")
        titulo = sec.get("calc", {}).get("titulo") or sec.get("regla", "")
        m.labels.append(Label(rx, yy, f"{i}. {str(titulo)[:38]}", 2.7, anchor="start"))
        m.labels.append(Label(W - 18, yy, estado, 2.7, anchor="end"))
        yy -= 4.2
        if yy < 70:
            m.labels.append(Label(rx, yy, f"… y {len(sections) - i} más", 2.6, anchor="start"))
            break
    if misc:
        m.labels.append(Label(rx, yy - 2, f"+ {len(misc)} verificación(es) cualitativas (última hoja)",
                              2.6, anchor="start"))
        yy -= 6.5

    # resumen + veredicto
    n_ok = sum(1 for r in rules if r.get("estado") == "ok")
    n_av = sum(1 for r in rules if r.get("estado") == "aviso")
    n_er = sum(1 for r in rules if r.get("estado") == "error")
    m.labels.append(Label(rx, 66, f"Resultado: {n_ok} OK · {n_av} avisos · {n_er} errores",
                          3.0, anchor="start"))
    m.labels.append(Label(rx, 58, f"VEREDICTO: {_verdict(rules)}", 4.4, anchor="start"))
    draw_title_block(m, {**base_meta, "sheet_no": 1})
    return m


def _section_page(W: float, H: float, *, idx: int, n_sections: int, page_no: int,
                  rule: dict, base_meta: dict) -> SheetModel:
    calc = rule.get("calc", {})
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    titulo = calc.get("titulo") or rule.get("regla", "")
    m.labels.append(Label(16, H - 24, f"{idx}. {str(titulo)[:48].upper()}", 5.6, anchor="start"))
    m.labels.append(Label(W - 16, H - 24, _ESTADO.get(rule.get("estado"), "?"), 5.6, anchor="end"))
    m.lines.append(Line(14, H - 30, W - 14, H - 30, "frame"))

    # columna izquierda: datos de entrada
    y = H - 40
    m.labels.append(Label(16, y, "DATOS DE ENTRADA", 3.2, anchor="start"))
    y -= 5.5
    for k, v in (calc.get("entradas") or {}).items():
        for ln in _wrap(f"{k}: {v}", 52):
            m.labels.append(Label(18, y, ln, 2.7, anchor="start"))
            y -= 4.2
    # detalle (veredicto en prosa)
    y -= 3
    m.labels.append(Label(16, y, "VERIFICACIÓN", 3.2, anchor="start"))
    y -= 5.5
    for ln in _wrap(str(rule.get("detalle", "")), 58)[:6]:
        m.labels.append(Label(18, y, ln, 2.7, anchor="start"))
        y -= 4.2
    if rule.get("recomendacion"):
        y -= 2
        for ln in _wrap("Recomendación: " + str(rule["recomendacion"]), 58)[:4]:
            m.labels.append(Label(18, y, ln, 2.7, anchor="start"))
            y -= 4.2
    # tabla por pieza (FEA de ensamblaje: σ_vm / FS por pieza) — bajo la verificación
    if rule.get("tabla"):
        y -= 3
        m.labels.append(Label(16, y, "RESULTADO POR PIEZA", 3.2, anchor="start"))
        y -= 5.5
        for row in rule["tabla"][:12]:
            m.labels.append(Label(18, y, str(row)[:64], 2.6, anchor="start"))
            y -= 4.0

    # columna derecha: el cálculo (fórmula → sustitución → resultado → criterio → FS)
    rx = W * 0.55
    yy = H - 40
    for header, key in (("FÓRMULA", "formula"), ("SUSTITUCIÓN", "sustitucion"),
                        ("RESULTADO", "resultado"), ("CRITERIO DE ACEPTACIÓN", "criterio"),
                        ("NORMA DE REFERENCIA", "norma")):
        if not calc.get(key):
            continue
        m.labels.append(Label(rx, yy, header, 3.2, anchor="start"))
        yy -= 5.5
        for ln in _wrap(str(calc[key]), 46)[:3]:
            m.labels.append(Label(rx + 2, yy, ln, 3.0, anchor="start"))
            yy -= 4.6
        yy -= 2.5
    fs = calc.get("fs")
    if fs is not None:
        m.labels.append(Label(rx, yy, "FACTOR DE SEGURIDAD", 3.2, anchor="start"))
        yy -= 6
        m.labels.append(Label(rx + 2, yy, f"FS = {fs:g}", 4.6, anchor="start"))
    draw_title_block(m, {**base_meta, "sheet_no": page_no})
    return m


def _misc_page(W: float, H: float, *, misc: list[dict], page_no: int,
               base_meta: dict) -> SheetModel:
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    m.labels.append(Label(16, H - 24, "VERIFICACIONES CUALITATIVAS", 5.6, anchor="start"))
    m.lines.append(Line(14, H - 30, W - 14, H - 30, "frame"))
    y = H - 40
    for r in misc:
        if y < 62:
            m.labels.append(Label(16, y, f"… y {len(misc)} verificaciones en total", 2.6, anchor="start"))
            break
        m.labels.append(Label(16, y, f"· {str(r.get('regla', ''))[:40]}", 3.0, anchor="start"))
        m.labels.append(Label(W - 16, y, _ESTADO.get(r.get("estado"), "?"), 3.0, anchor="end"))
        y -= 4.8
        for ln in _wrap(str(r.get("detalle", "")), 92)[:3]:
            m.labels.append(Label(20, y, ln, 2.6, anchor="start"))
            y -= 4.0
        y -= 2.5
    draw_title_block(m, {**base_meta, "sheet_no": page_no})
    return m


def calc_report(scene: dict, *, rules: list[dict], requirements: dict,
                project_name: str = "Sin título", png: bytes | None = None,
                meta: dict | None = None, sheet: str = "A4") -> list[SheetModel]:
    """Memoria de cálculo multipágina: [portada + 1 página por regla con `calc` +
    tabla de reglas cualitativas]. `rules` = ingenieria + estructura del chequeo."""
    from apolo.library.cutlist import scene_weight_kg

    W, H = SHEETS.get(sheet, SHEETS["A4"])
    sections = [r for r in rules if r.get("calc")]
    misc = [r for r in rules if not r.get("calc")]
    n_pages = 1 + len(sections) + (1 if misc else 0)
    peso = (meta or {}).get("weight_kg")
    if peso is None:
        try:
            peso = scene_weight_kg(scene)
        except Exception:
            peso = 0.0
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
                    sections=sections, misc=misc, rules=rules, base_meta=base_meta)]
    for i, rule in enumerate(sections, start=1):
        pages.append(_section_page(W, H, idx=i, n_sections=len(sections),
                                   page_no=i + 1, rule=rule, base_meta=base_meta))
    if misc:
        pages.append(_misc_page(W, H, misc=misc, page_no=n_pages, base_meta=base_meta))
    return pages
