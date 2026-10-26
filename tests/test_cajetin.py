"""El cajetín común de las láminas (`drawing/titleblock.py`; plan V8.9, pendiente 10): ningún texto
se corta a N caracteres ni se pisa con otro o con una línea; el diedro y «Genix Apolo CAD» no se
cruzan. Las cajas de texto se miden con la fuente del PDF (`tabla.ancho_mm`)."""

from __future__ import annotations

import pytest

from apolo.drawing.sheet import SheetModel
from apolo.drawing.tabla import MM_POR_PT, PT_POR_MM_ETIQUETA, ancho_mm, piso_tabla
from apolo.drawing.titleblock import (
    REV_ROW_H,
    TAM_MIN,
    TITLE_H,
    TITLE_W,
    alto_revisiones,
    draw_title_block,
)

NOTA = "V8.9 F7: desviador neumático de cajas con rampa de acumulación y presostato de corte"
CORTOS = {"project": "Mesa", "drawing_no": "P-1", "material": "A36", "date": "2026-10-25",
          "revisions": [{"rev": "A", "date": "2026-10-25", "note": "inicial"}]}
LARGOS = {
    "project": "Placa soporte del presostato (lado operador) (2/3) · 2× · Acero inoxidable AISI 304 2B",
    "drawing_no": "DV-077-PZ-012", "material": "Acero inoxidable AISI 304 2B laminado en frío",
    "finish": "Pintura electrostática epoxi-poliéster RAL 7035", "weight_kg": 1234.567,
    "tolerance": "ISO 2768-mK / ISO 13920-BF", "units": "mm", "scale": "1:2.5", "sheet": "A3",
    "sheet_no": 12, "n_sheets": 14, "drawn_by": "Apolo · agente IA", "checked_by": "M. Rojas Méndez",
    "approved_by": "Ingeniería de planta", "date": "2026-10-25",
    "revisions": [{"rev": "A", "date": "2026-10-24", "note": "Emisión inicial"},
                  {"rev": "B", "date": "2026-10-25 14:02:11", "note": NOTA}],
}
COTIZACION = {**LARGOS, "numero_rotulo": "Cotización", "titulo_dos_renglones": True,
              "project": "TRANSPORTADOR DE BANDA PARA PAQUETERÍA CON TABLERO Y VARIADOR DE FRECUENCIA"}


def _em(size: float) -> float:
    return size * PT_POR_MM_ETIQUETA * MM_POR_PT


def _caja(lab) -> tuple[float, float, float, float]:
    w = ancho_mm(lab.text, lab.size)
    x0 = {"middle": lab.x - w / 2, "end": lab.x - w}.get(lab.anchor, lab.x)
    return (x0, lab.y - 0.24 * _em(lab.size), x0 + w, lab.y + 0.76 * _em(lab.size))


def _se_tocan(a, b) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _cruza(seg, caja) -> bool:
    """¿El segmento entra en la caja? (Liang-Barsky)"""
    (x1, y1), (x2, y2) = seg
    x0, y0, xa, ya = caja
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - x0), (dx, xa - x1), (-dy, y1 - y0), (dy, ya - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def _cajetin(fields: dict, hoja=(297.0, 210.0)) -> SheetModel:
    m = SheetModel(*hoja)
    draw_title_block(m, fields)
    return m


def _diedro(m: SheetModel) -> tuple[float, float, float, float]:
    """La caja del diedro (`projection_symbol`: trapecio de s × s y círculo de Ø s a 1,9·s),
    sacada de su círculo exterior, el primero que dibuja."""
    (c, _) = m.circles
    s = 2 * c.r
    return (c.x - 1.9 * s, c.y - s / 2, c.x + c.r, c.y + s / 2)


@pytest.mark.parametrize("fields", [CORTOS, LARGOS, COTIZACION], ids=["cortos", "largos", "cotizacion"])
@pytest.mark.parametrize("hoja", [(297.0, 210.0), (420.0, 297.0)], ids=["A4", "A3"])
def test_nada_se_pisa_ni_se_sale_de_su_celda(fields, hoja):
    m = _cajetin(fields, hoja)
    cajas = [(lb, _caja(lb)) for lb in m.labels]
    # el diedro no toca ningún texto
    d = _diedro(m)
    for lb, c in cajas:
        assert not _se_tocan(d, c), f"el diedro pisa «{lb.text}»"
    # ningún texto cruza una línea del cajetín o de la tabla de revisiones (se saldría de su celda)
    lineas = [((ln.x1, ln.y1), (ln.x2, ln.y2)) for ln in m.lines]
    diedro = [s for s in lineas if d[0] - 1e-6 <= min(s[0][0], s[1][0]) and max(s[0][0], s[1][0]) <= d[2] + 1e-6
              and d[1] - 1e-6 <= min(s[0][1], s[1][1]) and max(s[0][1], s[1][1]) <= d[3] + 1e-6]
    assert len(diedro) == 4
    for lb, c in cajas:
        dentro = (c[0] + 0.1, c[1] + 0.1, c[2] - 0.1, c[3] - 0.1)
        assert not any(_cruza(s, dentro) for s in lineas), f"«{lb.text}» cruza una línea"
    # ni dos textos encimados
    for i, (la, ca) in enumerate(cajas):
        for lb, cb in cajas[i + 1:]:
            assert not _se_tocan(ca, cb), f"«{la.text}» pisa «{lb.text}»"
    # nada baja de la letra mínima ni termina en «…» (todo cabe medido)
    assert all(lb.size >= TAM_MIN for lb in m.labels)
    assert not any(lb.text.endswith("…") for lb in m.labels)


def test_genix_y_el_diedro_van_en_la_misma_fila_sin_cruzarse():
    m = _cajetin(CORTOS)
    x0 = m.width - 10.0 - TITLE_W
    genix = next(lb for lb in m.labels if lb.text == "Genix Apolo CAD")
    d = _diedro(m)
    fila = (10.0 + TITLE_H * 0.5, 10.0 + TITLE_H * 0.75)
    for caja in (_caja(genix), d):
        assert fila[0] < caja[1] and caja[3] < fila[1]  # dentro de su fila
    assert _caja(genix)[2] + 10.0 < d[0]  # con aire entre los dos
    assert d[2] <= x0 + TITLE_W - 2.0 + 1e-9


def test_una_nota_de_revision_larga_sale_entera_en_renglones():
    m = _cajetin(LARGOS)
    rx = m.width - 10.0 - 90.0
    desc = [lb for lb in m.labels if abs(lb.x - (rx + 35.0)) < 1e-9]
    renglones = [lb.text for lb in desc if lb.text not in ("Descripción", "Emisión inicial")]
    assert len(renglones) == 2 and " ".join(renglones) == NOTA  # nada recortado
    assert all(lb.size == 2.2 for lb in desc if lb.text in renglones)
    # la fila crece con sus renglones y la tabla lo dice a quien pone algo encima
    alto = alto_revisiones(LARGOS["revisions"])
    assert alto > 1.0 + 3 * REV_ROW_H
    assert piso_tabla(LARGOS) == pytest.approx(10.0 + TITLE_H + alto + 4.0)
    techo = max(max(ln.y1, ln.y2) for ln in m.lines)
    assert techo == pytest.approx(10.0 + TITLE_H + alto)
    # la fecha va sin la hora; el rótulo de la revisión, entero
    assert "2026-10-25" in [lb.text for lb in m.labels]


def test_una_tabla_de_revisiones_de_un_renglon_mide_lo_de_siempre():
    revs = [{"rev": i, "date": "2026-10-25", "note": "ajuste"} for i in range(8)]
    assert alto_revisiones(revs) == pytest.approx(1.0 + 7 * REV_ROW_H)  # las 6 últimas + cabecera
    assert alto_revisiones([]) == 0.0 and alto_revisiones(None) == 0.0


def test_un_material_largo_no_se_corta_a_18_si_cabe_medido():
    material = "Acero inoxidable AISI 304 2B"
    assert len(material) > 18
    textos = [lb.text for lb in _cajetin({**CORTOS, "material": material}).labels]
    assert material in textos
    # uno que no cabe en un renglón va en dos, entero, sin bajar de la letra mínima
    largo = LARGOS["material"]
    m = _cajetin({**CORTOS, "material": largo})
    x0 = m.width - 10.0 - TITLE_W
    celda = [lb for lb in m.labels if lb.x == x0 + 2 and lb.y < 10.0 + TITLE_H * 0.25]
    assert len(celda) == 2 and " ".join(lb.text for lb in celda) == largo
    assert all(TAM_MIN <= lb.size <= 3.0 for lb in celda)


@pytest.mark.parametrize("fields,renglones", [({**CORTOS, "project": COTIZACION["project"]}, 1),
                                              ({**LARGOS, "project": LARGOS["project"]
                                                + " · Tubo 40×40×2.5 ASTM A500 grado B galvanizado"},
                                               2)], ids=["mas_chico", "dos_renglones"])
def test_un_titulo_de_plano_largo_va_entero(fields, renglones):
    """Lo que no cabe a 4 en un renglón baja a 3 (y, si ni así, va en dos): nunca se corta a 34."""
    m = _cajetin(fields)
    x0 = m.width - 10.0 - TITLE_W
    fila = [lb for lb in m.labels if lb.x == x0 + 2 and lb.y > 10.0 + TITLE_H * 0.75]
    assert len(fila) == renglones and " ".join(lb.text for lb in fila) == fields["project"]
    assert all(TAM_MIN <= lb.size < 4.0 for lb in fila)
    assert f"Plano {fields['drawing_no']}" in [lb.text for lb in m.labels]


def test_el_ultimo_recurso_son_los_puntos_suspensivos():
    from apolo.drawing.titleblock import encajar

    s, lineas = encajar("x" * 400, 40.0, 3.0, max_renglones=2, alto=9.0)
    assert s == TAM_MIN and len(lineas) == 2 and lineas[-1].endswith("…")
    assert all(ancho_mm(ln, s) <= 40.0 for ln in lineas)
