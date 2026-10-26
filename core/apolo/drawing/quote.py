"""COTIZACIÓN del proyecto (Frente B): el entregable comercial.

PDF A4 multipágina: página de RESUMEN (totales por categoría, margen, impuesto,
PRECIO DE VENTA, ítem más costoso, notas comerciales) + páginas de DETALLE DE
PARTIDAS (el BOM costeado completo, paginado). Consume `library/costing.py`
(no calcula precios por su cuenta) y reusa `_table_sheet` (sheetset) +
`draw_title_block` + `sheets_to_pdf`.

Honestidad comercial: los precios de catálogo son REFERENCIALES y las piezas a
medida se estiman por peso×material×factor — las notas lo declaran siempre.

Identificada (plan cotizacion-identificada-y-ajustes-por-escenario, F1): el título y el bloque
«Cliente / Nº / Rev.» salen de `identificacion` (`services/identificacion.py`: el proyecto, una
extensión o, sin ninguna, el nombre del proyecto sin «(copia)» y sin bloque); su fuente va al pie.
Las notas del núcleo tienen id (`costeo_extension.NOTAS_NUCLEO`): una extensión acota sólo
`nucleo.alcance` y `nucleo.validez` (D3) y el alcance se calcula con lo que cubren las filas (D4).
"""

from __future__ import annotations

from datetime import date

from apolo.library.comercial import titulo_limpio

from . import notas_cotizacion as NC
from .assembly_manual import SHEETS, _wrap
from .sheet import Label, Line, SheetModel
from .tabla import hojas_tabla
from .titleblock import draw_title_block

#: Altura (mm) del rótulo «NOTAS» del resumen: la columna izquierda (desglose + ítem más
#: costoso) termina por encima, agrupando las categorías que no caben (V8.1 F4: en A4 apaisado,
#: con 15 categorías, «Ítem más costoso» caía encima de las notas).
_NOTAS_Y = 92.0
_PASO_CAT = 4.4


def _money(x: float | None, currency: str) -> str:
    return f"{x:,.2f} {currency}" if x is not None else "—"


def _categorias(por_categoria: dict, y0: float, *, con_top: bool) -> list[tuple[str, float]]:
    """Las filas del desglose que caben entre `y0` y las NOTAS (con el ítem más costoso debajo);
    las que no, juntas en «otras (N categorías)»: el total del desglose no cambia."""
    piso = _NOTAS_Y + 8.0 + (12.6 if con_top else 0.0)
    caben = max(1, int((y0 - piso) // _PASO_CAT) + 1)
    filas = list(por_categoria.items())
    if len(filas) <= caben:
        return filas
    resto = filas[caben - 1:]
    return filas[:caben - 1] + [(f"otras ({len(resto)} categorías)", round(sum(v for _, v in resto), 2))]


def precio_de_venta(directo: float, margin_pct: float, tax_pct: float) -> dict:
    """Costo directo → margen → impuesto → PRECIO DE VENTA, sin redondear (la hoja de resumen
    rotula estas cifras y la cotización las devuelve al agente: una sola cuenta)."""
    margen = directo * margin_pct / 100.0
    impuesto = (directo + margen) * tax_pct / 100.0
    return {"costo_directo": directo, "margen": margen, "impuesto": impuesto,
            "precio_venta": directo + margen + impuesto}


def _fx(fx) -> float:
    return float(fx) if fx and fx > 0 else 1.0


def resumen_precio(costeo: dict, *, margin_pct: float, tax_pct: float, currency: str = "USD",
                   fx: float = 1.0) -> dict:
    """Lo que dice el RESUMEN ECONÓMICO de la cotización, en la moneda presentada (con `fx` ≠ 1,
    el costo directo convertido como en la hoja): para la respuesta corta de la tool."""
    fx = _fx(fx)
    total = costeo["totales"]["total_usd"]
    p = precio_de_venta(round(total * fx, 2) if fx != 1.0 else total, margin_pct, tax_pct)
    out = {"moneda": currency, **({"tipo_cambio": fx} if fx != 1.0 else {}),
           "costo_directo": round(p["costo_directo"], 2), "margen_pct": margin_pct,
           "margen": round(p["margen"], 2)}
    if tax_pct:
        out.update(impuesto_pct=tax_pct, impuesto=round(p["impuesto"], 2))
    out["precio_venta"] = round(p["precio_venta"], 2)
    return out


def _titulo(m: SheetModel, H: float, titulo: str) -> None:
    """El título del resumen: hasta 54 caracteres a 4.6 mm (lo de siempre); uno más largo (un
    `comercial.titulo`, ≤ 80) baja a 3.4 mm en vez de recortarse."""
    texto = str(titulo)
    if len(texto) <= 54:
        m.labels.append(Label(16, H - 34, texto, 4.6, anchor="start"))
    else:
        m.labels.append(Label(16, H - 34, texto[:80], 3.4, anchor="start"))


def _bloque_cliente(m: SheetModel, y: float, ident: dict) -> float:
    """El bloque «Cliente / Nº / Rev.» (D1) desde `y`, sólo con lo que hay; devuelve la y libre."""
    y0 = y
    if ident.get("cliente"):
        for k, ln in enumerate(_wrap(f"Cliente: {ident['cliente']}", 62)):
            m.labels.append(Label(16 if k == 0 else 18, y, ln, 3.0, anchor="start"))
            y -= 4.6
    nro = " · ".join(t for t in (ident.get("numero") and f"Nº {ident['numero']}",
                                 ident.get("revision") and f"Rev. {ident['revision']}") if t)
    if nro:
        m.labels.append(Label(16, y, nro, 3.0, anchor="start"))
        y -= 4.6
    return y - 1.4 if y != y0 else y


def _summary_page(W: float, H: float, *, project_name: str, requirements: dict,
                  totals: dict, margin_pct: float, tax_pct: float, currency: str,
                  n_rows: int, base_meta: dict, fx_note: str | None = None,
                  avisos: list[dict] | None = None, riesgo: float | None = None,
                  mas_notas: list[str] = (), identificacion: dict | None = None,
                  acotadas: dict | None = None, incluye=()) -> SheetModel:
    ident = identificacion or {}
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    m.labels.append(Label(16, H - 24, "COTIZACIÓN", 8.0, anchor="start"))
    _titulo(m, H, project_name)
    m.labels.append(Label(W - 16, H - 24, f"N° {base_meta.get('drawing_no', '—')}", 4.0, anchor="end"))
    m.labels.append(Label(W - 16, H - 31, str(base_meta.get("date", "")), 3.0, anchor="end"))
    m.lines.append(Line(14, H - 39, W - 14, H - 39, "frame"))

    # columna izquierda: cliente (si hay) + alcance + desglose por categoría
    y = _bloque_cliente(m, H - 48, ident)
    producto = requirements.get("producto")
    if producto:
        m.labels.append(Label(16, y, f"Alcance: {str(producto)[:50]}", 3.0, anchor="start"))
        y -= 6
    m.labels.append(Label(16, y, "DESGLOSE POR CATEGORÍA", 3.4, anchor="start"))
    y -= 6
    top = totals.get("item_mas_costoso")
    for cat, val in _categorias(totals.get("por_categoria", {}), y, con_top=bool(top)):
        m.labels.append(Label(18, y, str(cat)[:34], 2.7, anchor="start"))
        m.labels.append(Label(120, y, _money(val, currency), 2.7, anchor="end"))
        y -= _PASO_CAT
    if top:
        y -= 3
        m.labels.append(Label(16, y, "Ítem más costoso:", 3.0, anchor="start"))
        y -= 4.6
        m.labels.append(Label(18, y, f"{top['descripcion'][:44]} — {_money(top['costo_total_usd'], currency)}",
                              2.7, anchor="start"))

    # columna derecha: totales → precio de venta
    rx = W * 0.55
    yy = H - 48
    m.labels.append(Label(rx, yy, "RESUMEN ECONÓMICO", 3.4, anchor="start"))
    yy -= 7
    p = precio_de_venta(totals.get("total_usd", 0.0), margin_pct, tax_pct)
    directo, margen, impuesto, venta = p["costo_directo"], p["margen"], p["impuesto"], p["precio_venta"]
    filas = [
        ("Componentes comprados", totals.get("catalogo_usd")),  # catálogo + comerciales a mano
        ("Fabricación a medida", totals.get("fabricacion_usd")),
        *([("Otros conceptos", totals["extensiones_usd"])] if "extensiones_usd" in totals else []),
        ("Costo directo", directo),
        (f"Margen ({margin_pct:g}%)", margen),
    ]
    if tax_pct:
        filas.append((f"Impuesto ({tax_pct:g}%)", impuesto))
    for label, val in filas:
        m.labels.append(Label(rx, yy, label, 3.0, anchor="start"))
        m.labels.append(Label(W - 18, yy, _money(val, currency), 3.0, anchor="end"))
        yy -= 5.2
    m.lines.append(Line(rx, yy + 2, W - 18, yy + 2, "frame"))
    yy -= 2
    m.labels.append(Label(rx, yy, "PRECIO DE VENTA", 4.2, anchor="start"))
    m.labels.append(Label(W - 18, yy, _money(venta, currency), 4.2, anchor="end"))
    if avisos:  # V8.1 F4c (D-c1): lo dudoso se dice donde se cobra, no sólo en delivery_check
        n_cab = sum(1 for a in avisos if a.get("tipo") == "cable 3D sin cobrar")
        yy -= 9
        m.labels.append(Label(rx, yy, "ATENCIÓN — AVISOS DE COBRO (hoja 2)", 3.2, anchor="start"))
        if riesgo:  # un aviso sin monto (fila de extensión descartada, cable) no es doble cobro
            yy -= 5.2
            m.labels.append(Label(rx, yy, "Posible doble cobro incluido", 3.0, anchor="start"))
            m.labels.append(Label(W - 18, yy, _money(riesgo, currency), 3.0, anchor="end"))
        if n_cab:
            yy -= 5.2
            m.labels.append(Label(rx, yy, f"Cables 3D que no se cobran: {n_cab}", 3.0, anchor="start"))

    # notas comerciales (honestidad + condiciones)
    ny = _NOTAS_Y
    m.labels.append(Label(16, ny, "NOTAS", 3.2, anchor="start"))
    ny -= 5
    for ln in _lineas_nucleo(n_rows, fx_note, avisos, acotadas, incluye):
        m.labels.append(Label(18, ny, ln, 2.5, anchor="start"))
        ny -= 3.8
    for ln in mas_notas:  # las de las extensiones, ya partidas (notas_cotizacion.repartir)
        m.labels.append(Label(18, ny, ln, 2.5, anchor="start"))
        ny -= 3.8
    if ident.get("fuente") not in (None, "nombre"):  # D2: de dónde salió la identificación
        rotulo = ident.get("fuente_rotulo") or ident["fuente"]  # legible; sin rótulo, el id
        m.labels.append(Label(16, 6.0, f"identificación: {rotulo}", 2.2, anchor="start"))
    draw_title_block(m, {**base_meta, "sheet_no": 1})
    return m


#: Lo que el alcance del núcleo excluye salvo que una fila lo cubra (D4), en su orden:
#: (clave de `costeo_extension.ALCANCES`, en «No incluye…», en «En las partidas…»).
_ALCANCE = (("transporte", "transporte", "el transporte"),
            ("instalacion", "instalación", "la instalación"),
            ("puesta_en_marcha", "puesta en marcha", "la puesta en marcha"))


def _y(cosas: list[str], conj: str) -> str:
    return cosas[0] if len(cosas) == 1 else f"{', '.join(cosas[:-1])} {conj} {cosas[-1]}"


def texto_alcance(incluye=()) -> str:
    """La nota `nucleo.alcance` (D4): sin nada incluido, la de siempre; lo que una fila cubre
    (`incluye`, de `costeo_extension.ALCANCES`) deja de excluirse y se dice que va en las
    partidas. Unas «pruebas» de marcha bastan para no decir «ni puesta en marcha»."""
    inc = set(incluye)
    fuera = [corto for k, corto, _ in _ALCANCE if k not in inc
             and not (k == "puesta_en_marcha" and "pruebas" in inc)]
    dentro = [largo for k, _, largo in _ALCANCE if k in inc]
    if "pruebas" in inc and "puesta_en_marcha" not in inc:
        dentro.append("las pruebas de marcha")
    if not dentro:
        return "No incluye transporte, instalación ni puesta en marcha, salvo pacto expreso."
    en = f"En las partidas: {_y(dentro, 'y')}."
    return f"No incluye {_y(fuera, 'ni')}, salvo pacto expreso. {en}" if fuera else en


def _notas_nucleo(n_rows: int, fx_note: str | None, avisos: list[dict] | None,
                  acotadas: dict | None = None, incluye=()) -> list[tuple[str, str]]:
    """Las notas comerciales del núcleo, `[(id, texto)]` en su orden (honestidad + condiciones).
    Una extensión no las quita: sólo `acota` (D3) `nucleo.alcance` o `nucleo.validez`
    (`acotadas`: id → texto, que va EN SU LUGAR); el alcance sin acotar se calcula (D4)."""
    acotadas = acotadas or {}
    notas = [
        ("nucleo.referenciales",
         "Precios de catálogo REFERENCIALES y fabricación estimada por peso×material×factor — "
         "confirmar con proveedores antes de comprometer."),
        ("nucleo.detalle",
         f"Detalle de las {n_rows} partidas en las hojas siguientes (con la fuente de cada precio)."),
        ("nucleo.alcance", acotadas.get("nucleo.alcance") or texto_alcance(incluye)),
        ("nucleo.validez",
         acotadas.get("nucleo.validez") or "Validez de la oferta: 15 días calendario."),
    ]
    if fx_note:
        notas.insert(1, ("nucleo.cambio", fx_note))
    if avisos:
        notas.insert(0, ("nucleo.avisos",
                         f"Hay {len(avisos)} aviso(s) de cobro en la hoja 2: el precio NO los "
                         "descuenta; liga o declara en el modelo lo que indica cada uno."))
    return notas


def _lineas_nucleo(n_rows: int, fx_note: str | None, avisos: list[dict] | None,
                   acotadas: dict | None = None, incluye=()) -> list[str]:
    """Las líneas de las notas del núcleo. Wrap a 60 chars: quedan a la izquierda de la tabla de
    revisiones del cajetín (x ≥ 107), sin solaparse aunque el proyecto tenga muchas revisiones."""
    notas = _notas_nucleo(n_rows, fx_note, avisos, acotadas, incluye)
    return [ln for idx, (_id, nota) in enumerate(notas, start=1)
            for ln in _wrap(f"{idx}. {nota}", 60)]


def _peso(scene: dict, meta: dict | None) -> float:
    """El peso del cajetín: el de `meta` o el de la máquina (como la memoria: con lo oculto)."""
    if (meta or {}).get("weight_kg") is not None:
        return meta["weight_kg"]
    from apolo.library.cutlist import scene_weight_kg

    return round(scene_weight_kg(scene, include_hidden=True), 1)


def quotation_pages(scene: dict, *, project_name: str = "Sin título",
                    requirements: dict | None = None, margin_pct: float = 25.0,
                    tax_pct: float = 0.0, currency: str = "USD", fx: float = 1.0,
                    meta: dict | None = None, sheet: str = "A4",
                    extra_rows: list[dict] | None = None,
                    costeo: dict | None = None,
                    identificacion: dict | None = None) -> list[SheetModel]:
    """Cotización multipágina: [resumen económico + avisos de cobro (si hay) + notas que no
    cupieron en el resumen (si hay) + N hojas de detalle de partidas]. `fx` = tipo de cambio sobre
    USD (solo PRESENTACIÓN: los costos se almacenan en USD; con fx≠1 la conversión se declara en
    las notas). `extra_rows` = partidas que la escena no tiene (el tablero eléctrico, V8.1 D10).
    `costeo` = el de `services/cobros.costeo` (filas, totales, `avisos` —V8.1 F4c— y `notas` de
    las extensiones —pedidos-de-extensiones D9—); sin él se costea aquí. `identificacion` = la de
    `services/identificacion.py` (título, cliente, número, revisión y su `fuente`); sin ella, el
    título es `project_name` sin «(copia)» y no hay bloque de cliente."""
    from apolo.library.costing import scene_costing

    W, H = SHEETS.get(sheet, SHEETS["A4"])
    data = costeo if costeo is not None else scene_costing(scene, extra=extra_rows)
    rows, totals, avisos = data["rows"], data["totales"], data.get("avisos")
    fx = _fx(fx)
    if fx != 1.0:
        rows = [
            {**r,
             "costo_ud_usd": None if r.get("costo_ud_usd") is None else round(r["costo_ud_usd"] * fx, 2),
             "costo_total_usd": None if r.get("costo_total_usd") is None else round(r["costo_total_usd"] * fx, 2)}
            for r in rows
        ]
        top = totals.get("item_mas_costoso")
        totals = {
            **totals,
            "catalogo_usd": round(totals["catalogo_usd"] * fx, 2),
            "fabricacion_usd": round(totals["fabricacion_usd"] * fx, 2),
            **({"extensiones_usd": round(totals["extensiones_usd"] * fx, 2)}
               if "extensiones_usd" in totals else {}),
            "total_usd": round(totals["total_usd"] * fx, 2),
            "por_categoria": {k: round(v * fx, 2) for k, v in totals.get("por_categoria", {}).items()},
            "item_mas_costoso": (
                {**top, "costo_total_usd": round(top["costo_total_usd"] * fx, 2)} if top else None
            ),
        }

    detail = [
        [r["ref"], str(r["descripcion"]),
         f"{r['cantidad']:g} {r['unidad']}" if r.get("unidad") else r["cantidad"],
         _money(r.get("costo_ud_usd"), ""), _money(r.get("costo_total_usd"), ""),
         str(r.get("costo_fuente", ""))]
        for r in rows
    ]
    headers = ["Ref", "Descripción", "Cant", f"{currency}/ud", f"{currency} total", "Fuente del precio"]
    avisos = list(avisos or [])
    tabla_avisos = [[a.get("tipo", ""), a.get("detalle", ""),
                     _money(None if a.get("monto_en_riesgo_usd") is None
                            else a["monto_en_riesgo_usd"] * fx, currency),
                     a.get("arreglo", "")] for a in avisos]
    cab_avisos = ["Aviso", "Qué pasa", "Monto en riesgo", "Cómo se arregla"]

    fx_note = (f"Montos convertidos de USD a {currency} a tipo de cambio {fx:g} "
               "(los costos base se mantienen en USD)." if fx != 1.0 else None)
    # notas de extensiones (pedidos-de-extensiones D9): tras las del núcleo; lo que no cabe a la
    # izquierda del cajetín sigue en «NOTAS (continuación)», tras los avisos y antes del detalle
    ident = dict(identificacion or {})
    titulo = ident.get("titulo") or titulo_limpio(project_name)
    # D3: una nota con `acota` va en lugar de la del núcleo (un solo dueño: lo valida la carga)
    acotadas = {n["acota"]: n["texto"] for n in data.get("notas") or () if n.get("acota")}
    incluye = tuple(data.get("incluye") or ())
    de_ext = [n["texto"] for n in data.get("notas") or () if not n.get("acota")]
    lineas = _lineas_nucleo(len(rows), fx_note, avisos, acotadas, incluye)
    n_nucleo = len(_notas_nucleo(len(rows), fx_note, avisos, acotadas, incluye))
    y_libre = _NOTAS_Y - 5 - 3.8 * len(lineas)
    mas_notas, resto = (NC.repartir(y_libre, W, de_ext, n_nucleo + 1, 2 + (1 if avisos else 0))
                        if de_ext else ([], []))

    def _tablas(meta_de) -> tuple[list[SheetModel], list[SheetModel], list[SheetModel]]:
        hojas_av = (hojas_tabla("AVISOS DE COBRO (no se descuentan solos)", cab_avisos, tabla_avisos,
                                W=W, H=H, flexibles={0, 1, 3}, derecha={2},
                                meta_hoja=lambda k, n: meta_de(1 + k))
                    if avisos else [])
        hojas_notas = NC.hojas_continuacion(resto, W=W, H=H,
                                            meta_hoja=lambda k, n: meta_de(1 + len(hojas_av) + k))
        antes = 1 + len(hojas_av) + len(hojas_notas)
        hojas_det = hojas_tabla("DETALLE DE PARTIDAS", headers, detail, W=W, H=H,
                                flexibles={0, 1, 5}, derecha={2, 3, 4},
                                meta_hoja=lambda k, n: meta_de(antes + k))
        return hojas_av, hojas_notas, hojas_det

    av0, notas0, det0 = _tablas(lambda k: {"revisions": (meta or {}).get("revisions", [])})
    n_pages = 1 + len(av0) + len(notas0) + len(det0)
    base_meta = {
        "project": titulo,
        "drawing_no": ident.get("numero") or (meta or {}).get("drawing_no", "COT-001"),
        "scale": "—", "sheet": sheet, "material": "—", "finish": "—",
        "weight_kg": _peso(scene, meta), "tolerance": "—", "units": "mm",
        "drawn_by": (meta or {}).get("drawn_by", "Apolo · agente IA"),
        "checked_by": "", "approved_by": "",
        "date": (meta or {}).get("date", date.today().isoformat()),
        "revisions": (meta or {}).get("revisions", []),
        "n_sheets": n_pages,
    }
    riesgo = None
    if avisos:
        riesgo = round(sum(a.get("monto_en_riesgo_usd") or 0.0 for a in avisos) * fx, 2)
    pages = [_summary_page(W, H, project_name=titulo,
                           requirements=requirements or {}, totals=totals,
                           margin_pct=margin_pct, tax_pct=tax_pct, currency=currency,
                           n_rows=len(rows), base_meta=base_meta, fx_note=fx_note,
                           avisos=avisos, riesgo=riesgo, mas_notas=mas_notas,
                           identificacion=ident, acotadas=acotadas, incluye=incluye)]
    av, notas, det = _tablas(lambda k: {**base_meta, "sheet_no": k})
    return pages + av + notas + det
