"""Los textos de los entregables en papel salen ENTEROS y en su lugar (plan V8.9, «cortes fijos
fuera del cajetín»): la cotización, la lámina de instalación, el manual, las notas de las láminas,
la memoria de cálculo y las tablas del juego de planos ya no cortan a N caracteres ni a N renglones.
Cada texto se mide con la fuente del PDF (`tabla.ancho_mm`): se parte en renglones o baja de
tamaño (nunca de `TAM_MIN`) y no se sale de su celda ni de su columna, ni baja sobre el cajetín."""

from __future__ import annotations

from apolo.drawing.tabla import MM_POR_PT, PT_POR_MM_ETIQUETA, ancho_mm, piso_tabla
from apolo.drawing.texto_medido import TAM_MIN

META = {"date": "2026-10-25", "revisions": [{"rev": "A", "date": "2026-10-25", "note": "Emisión"}]}
LARGO = ("Transportador de rodillos · Guarda de la transmisión · pared interior del cárter con "
         "ventana de inspección")


def _caja(lb) -> tuple[float, float, float, float]:
    w = ancho_mm(lb.text, lb.size)
    em = lb.size * PT_POR_MM_ETIQUETA * MM_POR_PT
    x0 = {"middle": lb.x - w / 2, "end": lb.x - w}.get(lb.anchor, lb.x)
    return (x0, lb.y - 0.24 * em, x0 + w, lb.y + 0.76 * em)


def _dentro(lb, x0: float, x1: float, y0: float = -1e9, y1: float = 1e9) -> bool:
    c = _caja(lb)
    return x0 - 1e-6 <= c[0] and c[2] <= x1 + 1e-6 and y0 - 1e-6 <= c[1] and c[3] <= y1 + 1e-6


def _se_tocan(a, b) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) + 0.2 and min(a[3], b[3]) > max(a[1], b[1]) + 0.2


def _junto(labels) -> str:
    return " ".join(lb.text for lb in labels)


def png(w: int = 40, h: int = 30) -> bytes:
    """Un PNG gris mínimo (la foto no importa aquí: sólo su caja)."""
    import struct
    import zlib

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xc0\xc0\xc0" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ----------------------------------------------------------------------------- cotización
def test_la_categoria_y_el_item_mas_costoso_de_la_cotizacion_salen_enteros():
    """La categoría del desglose se cortaba a 34 y el ítem más costoso a 44."""
    from apolo.drawing.quote import quotation_pages

    cat = "accionamientos y transmisiones de potencia (motorreductores sinfín)"
    item = "Motorreductor sinfín-corona NMRV-090 i=30 con brida B14 y eje hueco Ø25 h7"
    costeo = {"rows": [], "totales": {
        "catalogo_usd": 10.0, "fabricacion_usd": 0.0, "total_usd": 10.0,
        "por_categoria": {cat: 10.0}, "item_mas_costoso": {"descripcion": item, "costo_total_usd": 10.0}}}
    m = quotation_pages({}, costeo=costeo, meta=META)[0]
    lb_cat = next(lb for lb in m.labels if lb.text.startswith("accionamientos"))
    assert lb_cat.text == cat and lb_cat.size >= TAM_MIN
    monto = next(lb for lb in m.labels if lb.anchor == "end" and abs(lb.y - lb_cat.y) < 1e-9)
    assert _caja(lb_cat)[2] < _caja(monto)[0]  # no pisa su monto
    lb_item = next(lb for lb in m.labels if lb.text.startswith("Motorreductor"))
    assert lb_item.text.startswith(item) and _dentro(lb_item, 18.0, m.width * 0.55)


# ----------------------------------------------------------------------------- instalación
def _instalacion(notas=(), suministro=()):
    from apolo.drawing.installation import installation_sheet

    datos = {"masa_kg": 120.0, "anclaje": {
        "n_apoyos": 4, "carga_max_kg": 40.0, "gobernante": "Pata", "apoyos": [],
        "hipotesis": "reparto elástico de grupo con el peso en el COG (excentricidad 82/90 mm); "
                     "apoyos de igual rigidez sobre piso rígido; con 4 apoyos el reparto es "
                     "hiperestático — el uniforme sería 115.5 kg/apoyo"},
        "suministro": list(suministro), "notas": list(notas)}
    return installation_sheet({}, datos, project_name="Faja", sheet="A3", meta=META)


def test_la_tabla_de_instalacion_no_corta_sus_celdas():
    """Cada celda se cortaba a 34: ahora va entera en su celda (uno o dos renglones)."""
    concepto = "Alimentación eléctrica del tablero principal de fuerza"
    valor = "380 V trifásico 60 Hz + neutro + tierra"
    nota = "desde el tablero general de planta, con interruptor diferencial"
    m = _instalacion(suministro=[{"concepto": concepto, "valor": valor, "nota": nota}])
    x0, top, row_h = m.width * 0.55, m.height - 40.0, 5.6
    xs = [x0, x0 + 58.0, x0 + 92.0, x0 + 138.0]
    for j, texto in enumerate((concepto, valor, nota)):
        col = [lb for lb in m.labels if abs(lb.x - (xs[j] + 1.4)) < 1e-9 and lb.y < top]
        filas = {}
        for lb in col:
            filas.setdefault(int((top - lb.y) // row_h), []).append(lb)
        fila = next(v for v in filas.values() if _junto(v).startswith(texto.split()[0]))
        assert _junto(fila) == texto
        k = int((top - fila[0].y) // row_h)
        for lb in fila:  # dentro de su columna y de su fila
            assert _dentro(lb, xs[j], xs[j + 1], top - (k + 1) * row_h, top - k * row_h), lb.text
            assert lb.size >= TAM_MIN


def test_los_datos_de_instalacion_llegan_enteros_al_papel():
    """`installation_rows` cortaba la pieza a 20 y el apoyo gobernante a 22 ANTES del papel
    («Holgura de servicio · Faja de banda · Tamb»): ahora la capa de datos da el nombre entero y
    la celda lo encaja (los nombres son los del testigo de rodillos)."""
    from apolo.drawing.installation import installation_sheet
    from apolo.library.engineering.installation import installation_rows

    gob = "Transportador de rodillos · Placa de piso (+Y, motriz)"
    pieza = "Transportador de rodillos · Base del motor"
    datos = {"masa_kg": 120.0, "anclaje": {"n_apoyos": 4, "carga_max_kg": 45.7, "gobernante": gob,
                                           "apoyos": [], "hipotesis": "reparto elástico"},
             "servicio": [{"pieza": pieza, "holgura_mm": 424.0}]}
    filas = installation_rows(datos)
    assert ["Carga máx. por apoyo", "45.7 kg", f"en «{gob}»"] in filas
    assert [f"Holgura de servicio · {pieza}", "424 mm", "extracción lateral"] in filas
    m = installation_sheet({}, datos, project_name="Rodillos", sheet="A3", meta=META)
    x0, top, row_h = m.width * 0.55, m.height - 40.0, 5.6
    tabla = [lb for lb in m.labels if lb.x >= x0 and top - len(filas) * row_h < lb.y < top]
    texto = _junto(tabla)
    assert f"en «{gob}»" in texto and f"Holgura de servicio · {pieza}" in texto
    assert "…" not in texto and all(lb.size >= TAM_MIN for lb in tabla)


def test_las_notas_de_instalacion_salen_enteras_sobre_el_cajetin():
    """La hipótesis del reparto (que va SIEMPRE) se cortaba a 60 caracteres."""
    larga = "Nivelar los apoyos antes de anclar; " * 3 + "el reparto supone piso rígido."
    m = _instalacion(notas=[larga])
    x0 = m.width * 0.55
    techo_cajetin = piso_tabla(META) - 4.0
    notas = [lb for lb in m.labels if lb.x >= x0 - 1e-9 and lb.size == 2.4 and lb.y > techo_cajetin]
    texto = _junto(notas)
    assert "hiperestático — el uniforme sería 115.5 kg/apoyo." in texto
    assert larga.replace("  ", " ").strip() in texto
    piso = piso_tabla(META)
    for lb in notas:
        assert _dentro(lb, x0, m.width - 16.0) and lb.y >= piso - 1e-6, lb.text


# ----------------------------------------------------------------------------- notas de lámina
def test_notes_block_parte_la_nota_bajo_su_texto_y_devuelve_el_borde():
    from apolo.drawing.dimensions import notes_block
    from apolo.drawing.sheet import SheetModel

    m = SheetModel(297.0, 210.0)
    nota = "Cota crítica: cadena «holgura del eje motriz a la guarda de la transmisión» (ver memoria)."
    y = notes_block(m, 16.0, 150.0, ["Romper aristas vivas", nota], ancho=70.0)
    renglones = [lb for lb in m.labels if lb.text != "NOTAS"]
    assert len(renglones) >= 3 and _junto(renglones[1:]) == f"2. {nota}"
    assert all(_dentro(lb, 16.0, 86.0) for lb in renglones)
    assert renglones[2].x > 16.0  # el renglón siguiente va bajo el texto, no bajo el número
    assert y < renglones[-1].y


# ----------------------------------------------------------------------------- manual
def test_el_paso_del_manual_dice_su_rotulo_y_sus_piezas_enteros():
    """El rótulo de la etapa se cortaba a 34 y la descripción de cada pieza a 30."""
    from apolo.drawing.assembly_manual import _cover_page, _step_page

    for W, H in ((420.0, 297.0), (297.0, 210.0)):
        rows = [f"{k}x  Cadena ASA 40-1 L=381 mm (30 eslabones) con candado · ANSI B29.1" for k in range(1, 30)]
        m = _step_page(W, H, step_no=1, n_steps=2, page_no=2, n_pages=3,
                       stage={"label": LARGO, "ids": ["a"]}, rows=rows,
                       instruction="Montar.", png=png(), base_meta=META)
        rx = 16 + (W - 20) * 0.58 + 10
        rotulo = [lb for lb in m.labels if lb.y > H - 43 and lb.y < H - 30 and lb.x == rx]
        assert _junto(rotulo) == LARGO and all(_dentro(lb, rx, W - 14) for lb in rotulo)
        filas = [lb for lb in m.labels if lb.size == 2.7 and lb.x >= rx]
        assert "Cadena ASA 40-1 L=381 mm (30 eslabones) con candado · ANSI B29.1" in _junto(filas)
        piso = piso_tabla(META)
        assert all(_dentro(lb, rx, W - 14) and lb.y >= piso for lb in filas)
        mas = [lb for lb in m.labels if lb.text.startswith("… y ")]
        assert len(mas) == 1 and mas[0].y >= piso  # lo que no entra lo dice, sobre el cajetín
        portada = _cover_page(W, H, project_name=LARGO + " " + LARGO, png=png(),
                              stages=[{"label": LARGO, "ids": ["a"]}] * 30,
                              totals={"piezas": 30, "herraje": 0}, base_meta=META, sheet="A3")
        titulo = next(lb for lb in portada.labels if abs(lb.y - (H - 38)) < 1e-9)
        assert titulo.text == LARGO + " " + LARGO and _dentro(titulo, 16, W - 16)
        cajas = [_caja(lb) for lb in portada.labels]
        for i, a in enumerate(cajas):  # la secuencia larga no baja sobre el cajetín
            assert not any(_se_tocan(a, b) for b in cajas[i + 1:]), portada.labels[i].text


# ----------------------------------------------------------------------------- memoria
RESULTADO = ("voladizo 0–367: δ = 0.84 mm (lím. 3.06); vano 367–4174: δ = 2.88 mm (lím. 15.86); "
             "voladizo 4174–4274: δ = 0.25 mm (lím. 0.84). Manda el voladizo 4174–4274 mm (L/815); "
             "|M| = 0.594 kN·m en x = 2377 mm; σ = 19.7 MPa")


def _regla(i: int = 0) -> dict:
    return {"regla": f"viga {i}", "estado": "ok",
            "detalle": "Flecha y tensión dentro de lo admisible en todos los tramos. " * 4,
            "recomendacion": "Ninguna: la viga tiene margen suficiente en flecha y en tensión. " * 2,
            "hipotesis": [f"Hipótesis {k}: carga útil repartida entre las vigas que tocan la cama; "
                          "envolvente sobre centros de tramo y puntas de voladizo." for k in range(6)],
            "calc": {"titulo": "Viga continua: Faja de banda · Brazo de la base del motor (1) y 1 "
                               "igual(es) del bastidor principal",
                     "entradas": {"perfil": "TUBO-2X2 — ASTM A500 · AISC 360-16 §B4.2 (t = 0.93·t_nom)"},
                     "formula": "Hermite con cargas consistentes", "resultado": RESULTADO,
                     "criterio": "δ ≤ L/240 en vanos y 2·Lv/240 en voladizos; σ ≤ 0.6·fy", "fs": 2.5}}


def test_la_memoria_no_corta_el_resultado_ni_el_titulo_ni_las_hipotesis():
    from apolo.drawing.calc_report import calc_report

    misc = [{"regla": f"unión apernada · c1_guarda_m_larg{k}", "estado": "ok",
             "detalle": "Unión redundante en el camino de carga: favorable estructuralmente; el "
                        "reparto no es determinable sin FEA, se asume compartido entre caminos."}
            for k in range(70)]
    pages = calc_report(None, rules=[_regla(), *misc], requirements={"carga_kg": 15.0},
                        meta={**META, "weight_kg": 10.0})
    hoja = pages[1]
    W, H = hoja.width, hoja.height
    textos = _junto(hoja.labels)
    assert RESULTADO in textos and "σ = 19.7 MPa" in textos
    assert "Ninguna: la viga tiene margen suficiente en flecha y en tensión." in textos
    assert "1. VIGA CONTINUA: FAJA DE BANDA · BRAZO DE LA BASE DEL MOTOR (1) Y 1 IGUAL(ES) DEL " \
           "BASTIDOR PRINCIPAL" == _junto([lb for lb in hoja.labels if lb.y > H - 30 and lb.x == 16])
    for k in range(6):
        assert f"Hipótesis {k}:" in textos
    piso = piso_tabla(META)
    rx = W * 0.55
    for lb in hoja.labels:
        if lb.y > H - 31 or lb.y < piso - 4.0:  # el título, el cajetín y sus revisiones
            continue
        assert lb.y >= piso - 1e-6 and lb.size >= TAM_MIN - 1e-9, lb.text
        assert _dentro(lb, 16, rx - 4) or _dentro(lb, rx, W - 16), lb.text
    # las cualitativas siguen en las hojas que pidan: ninguna se pierde
    cualitativas = [p for p in pages if any("VERIFICACIONES CUALITATIVAS" in lb.text for lb in p.labels)]
    assert len(cualitativas) > 1
    todas = " ".join(_junto(p.labels) for p in cualitativas)
    assert all(f"c1_guarda_m_larg{k}" in todas for k in range(70))
    for p in cualitativas:
        assert all(lb.y >= piso - 1e-6 for lb in p.labels if lb.x in (16, 20))  # sobre el cajetín
    assert pages[0].labels and any("últimas" in lb.text for lb in pages[0].labels)


# ----------------------------------------------------------------------------- juego de planos
def test_el_despiece_y_la_lista_de_corte_no_cortan_el_nombre():
    """El DESPIECE del conjunto cortaba el nombre a 16 y el material a 13; la lista de corte, a 40."""
    from apolo.doc import Document
    from apolo.drawing import sheet_set

    nombre = "Placa soporte del presostato (lado operador)"
    doc = Document("t")
    doc.execute("create_box", {"name": nombre, "width": 120, "depth": 80, "height": 6})
    pages = sheet_set(doc.scene, project_name="T", meta=META)
    ga = pages[0]
    x_pieza = 16.0 + (ga.width - 32.0) * 0.52 + 8.0 + 1.5  # la columna «Pieza» del DESPIECE
    celda = [lb for lb in ga.labels if abs(lb.x - x_pieza) < 1e-6 and lb.text != "Pieza"]
    assert _junto(celda) == nombre and all(lb.size >= TAM_MIN for lb in celda)
    assert all(_dentro(lb, x_pieza - 1.5, x_pieza - 1.5 + 36.0) for lb in celda)
    corte = next(p for p in pages if any(lb.text == "LISTA DE CORTE" for lb in p.labels))
    assert nombre in [lb.text for lb in corte.labels]
