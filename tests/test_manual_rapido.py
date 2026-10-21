"""El manual de ensamblaje con UNA escena VTK y fuera de STATE_LOCK (plan manual-rapido, F1).

- Las láminas salen iguales en número y textos que antes del cambio (congelados en un caso chico
  con el código de main, 2026-10-21): sólo cambian las fotos y dónde se dibujan (D5).
- Cada foto muestra lo nuevo con su color, lo ya montado en gris y no lo que falta (D1).
- Mientras se dibujan las fotos, `STATE_LOCK` está libre: una mutación no espera (D2).
- Sin contexto OpenGL el manual sale igual, con matplotlib, y lo dice en el log (D4).
- Una pieza con zonas de acabado llega partida por zona, como en `render_view` (D3).
"""

from __future__ import annotations

import io
import logging
import threading

import numpy as np
import pytest

from apolo.doc import Document
from apolo.drawing import (
    assembly_manual,
    componer_manual,
    extraer_manual,
    fotos_manual,
    teselar_manual,
)
from apolo.drawing import manual_fotos

_FECHA = {"drawing_no": "7", "date": "2026-10-21"}


def _tb(hoja: str) -> list[str]:
    return ["Caja", "Plano 7", "Dib.   2026-10-21", "Rev.    Apr. ", "Genix Apolo CAD",
            "Material", "madera", "Acabado / Peso", "— · 8.233 kg", "Tol. gral / Unid.",
            "— · mm", "Escala / Hoja", f"— · {hoja} A3"]


#: Los textos de cada lámina con el código de main (matplotlib bajo STATE_LOCK).
TEXTOS_DE_MAIN = [
    ["MANUAL DE ENSAMBLAJE", "Caja", "SECUENCIA DE MONTAJE",
     "Paso 1.  Marco / bastidor  (1 pza)", "Paso 2.  Tornillería  (1 pza)",
     "Paso 3.  Tapa  (1 pza)", "Total: 3 piezas · 1 de herraje · 3 pasos", *_tb("1/4")],
    ["PASO 1 DE 3", "Marco / bastidor", "Presentar, escuadrar y soldar al conjunto",
     "(cordón de filete donde esté", "dimensionado). Se añaden 1 pieza(s);",
     "montadas 1 de 3.", "PIEZAS DE ESTE PASO", "1x  Marco base", *_tb("2/4")],
    ["PASO 2 DE 3", "Tornillería", "Atornillar a las piezas ya montadas y",
     "apretar en cruz al par indicado. Par de", "apriete (8.8, rosca seca): M6 → 11 N·m",
     "(llave 10 mm). Se añaden 1 pieza(s);", "montadas 2 de 3.", "PIEZAS DE ESTE PASO",
     "1x  Tornillo Allen DIN912-M6 · DIN 912", *_tb("3/4")],
    ["PASO 3 DE 3", "Tapa", "Monta y fija estas piezas sobre el",
     "conjunto, respetando las cotas del", "despiece. Se añaden 1 pieza(s); montadas 3",
     "de 3.", "PIEZAS DE ESTE PASO", "1x  Tapa sup", *_tb("4/4")],
]


def _caja() -> Document:
    d = Document("Caja")
    d.execute("create_box", {"name": "Marco base", "width": 400, "depth": 40, "height": 400})
    d.execute("create_box", {"name": "Tapa sup", "width": 400, "depth": 40, "height": 40,
                             "position": {"z": 220}})
    d.execute("insert_component", {"component": "DIN912-M6", "position": {"x": 0, "y": 0, "z": 0}})
    return d


def test_las_laminas_salen_iguales_en_numero_y_textos():
    d = _caja()
    paginas = assembly_manual(d.scene, commands=d.commands, project_name="Caja", size_px=200,
                              meta=_FECHA)
    assert [[lb.text for lb in p.labels] for p in paginas] == TEXTOS_DE_MAIN
    assert all(len(p.images) == 1 and p.images[0].png[:4] == b"\x89PNG" for p in paginas)


# ── las fotos ─────────────────────────────────────────────────────────────────

AZUL, ROJO, VERDE = "#1030e0", "#e01010", "#10c020"


def _torre():
    """Base (azul) → poste (rojo) → tapa (verde), un paso cada uno."""
    d = Document("Torre")
    caja = {"Base": ((400, 400, 20), (0, 0, 10)), "Poste": ((60, 60, 300), (0, 0, 170)),
            "Tapa": ((200, 200, 20), (0, 0, 330))}
    ids = {}
    for nombre, ((w, p, h), (x, y, z)) in caja.items():
        ids[nombre] = d.execute("create_box", {"name": nombre, "width": w, "depth": p, "height": h,
                                               "position": {"x": x, "y": y, "z": z}})
    etapas = [{"label": n, "ids": [ids[n]], "is_hw": False} for n in caja]
    colores = {ids["Base"]: AZUL, ids["Poste"]: ROJO, ids["Tapa"]: VERDE}
    return d, ids, etapas, colores


def _rgb(png: bytes):
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(float)


def _mascaras(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return {"rojo": (r > 90) & (r > 2.2 * g) & (r > 2.2 * b),
            "azul": (b > 90) & (b > 2.0 * r) & (b > 1.5 * g),
            "verde": (g > 90) & (g > 2.0 * r) & (g > 2.0 * b)}


@pytest.fixture(scope="module")
def fotos_torre():
    d, ids, etapas, colores = _torre()
    ex = teselar_manual(extraer_manual(d.scene, commands=d.commands, size_px=400, stages=etapas,
                                       colors=colores))
    try:
        fotos = manual_fotos._fotos_vtk(ex)
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL en este entorno
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    return d, ids, ex, fotos


def test_cada_foto_muestra_lo_nuevo_en_su_color_y_lo_montado_en_gris(fotos_torre):
    from apolo.kernel.render_vivo import EscenaViva

    d, ids, ex, fotos = fotos_torre
    assert len(fotos) == 4
    portada, paso1, paso2, paso3 = (_mascaras(_rgb(f)) for f in fotos)
    assert all(m.sum() > 200 for m in portada.values())          # la portada, todo a color
    assert paso1["azul"].sum() > 200 and not paso1["rojo"].any() and not paso1["verde"].any()
    # paso 2: el poste nuevo en rojo; la base, ya montada, gris (sin azul); la tapa aún no
    assert paso2["rojo"].sum() > 200 and paso2["azul"].sum() < 20 and not paso2["verde"].any()
    assert paso3["verde"].sum() > 200 and paso3["rojo"].sum() < 20
    # …y el rojo está DONDE va el poste: la misma cámara en todas las fotos
    with EscenaViva(ex.bbox, {}, ancho=400, alto=312) as esc:
        col, fila = esc.proyectar((0, 0, 170))
    alto, ancho = paso2["rojo"].shape
    assert (ancho, alto) == (400, 312)
    f, c = int(fila), int(col)
    assert paso2["rojo"][f - 4:f + 5, c - 4:c + 5].mean() > 0.6  # (la arista vertical cruza)


def test_la_pieza_con_zonas_llega_partida_como_en_render_view():
    from apolo.services.apariencia import apariencias_render

    d = Document("seta")
    d.execute("insert_component", {"component": "ESTOP-40-CAJA"})
    ex = teselar_manual(extraer_manual(d.scene, commands=d.commands,
                                       apariencias=apariencias_render(d)))
    (pieza,) = ex.piezas
    assert pieza.partes is not None and len(pieza.partes) > 1


def test_el_polydata_numpy_trae_los_mismos_puntos_y_celdas():
    """`render_comun.polydata` se arma con numpy (las cadenas de la piloto se llevaban ~1 min en
    bucles): mismos puntos (float32, el tipo de vtkPoints) y mismas celdas, en orden."""
    pytest.importorskip("vtk")
    from apolo.kernel.render_comun import _xyz, polydata, teselar

    d = Document("cil")
    fid = d.execute("create_cylinder", {"name": "Eje", "radius": 30, "height": 200})
    v, t = teselar(d.scene[fid].shape)
    pd = polydata(v, t)
    assert pd.GetNumberOfPoints() == len(v) and pd.GetNumberOfCells() == len(t)
    assert _xyz(v) is _xyz(v)                      # la conversión se cachea por lista
    for k in (0, len(t) // 2, len(t) - 1):
        ids = pd.GetCell(k).GetPointIds()
        assert [ids.GetId(i) for i in range(3)] == list(t[k])
    p = pd.GetPoint(len(v) - 1)
    assert p == pytest.approx(tuple(v[-1]), abs=1e-4)   # numpy desde teselado-rapido D2


# ── locks y respaldo ──────────────────────────────────────────────────────────

def _png_minimo() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_state_lock_queda_libre_mientras_se_dibujan_las_fotos(monkeypatch):
    from fastapi.testclient import TestClient

    import apolo.api.main as api
    from apolo.state import STATE_LOCK

    d, _ids, _etapas, _colores = _torre()
    api.DOC = d
    dibujando, seguir = threading.Event(), threading.Event()

    def fotos_lentas(ex):
        dibujando.set()
        assert seguir.wait(30), "el test no soltó las fotos"
        return [_png_minimo()] * (len(ex.stages) + 1)

    monkeypatch.setattr(manual_fotos, "_fotos_vtk", fotos_lentas)
    resp = {}
    hilo = threading.Thread(target=lambda: resp.setdefault(
        "r", TestClient(api.app).get("/api/assembly-manual.pdf")))
    hilo.start()
    try:
        assert dibujando.wait(60), "el manual nunca llegó a las fotos"
        assert STATE_LOCK.acquire(timeout=2), "STATE_LOCK sigue tomado mientras se dibuja"
        try:  # una mutación en plena foto: no espera al manual
            d.execute("create_box", {"name": "Intrusa", "width": 10, "depth": 10, "height": 10})
        finally:
            STATE_LOCK.release()
    finally:
        seguir.set()
        hilo.join(60)
    r = resp["r"]
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_el_teselado_toma_el_candado_pieza_por_pieza(monkeypatch):
    """F0: teselar la piloto en frío cuesta ~280 s; de un tirón congelaría la API. Cada pieza se
    tesela con el candado tomado y se suelta entre una y otra."""
    import apolo.kernel.render_vivo as rv

    class Candado:
        tomado, veces = False, 0

        def __enter__(self):
            assert not self.tomado
            self.tomado, self.veces = True, self.veces + 1

        def __exit__(self, *_exc):
            self.tomado = False

    candado = Candado()
    original = rv.extraer_piezas

    def espia(escena, *a, **kw):
        assert candado.tomado and len(escena) == 1, "una pieza por toma del candado"
        return original(escena, *a, **kw)

    monkeypatch.setattr(rv, "extraer_piezas", espia)
    d, ids, etapas, _colores = _torre()
    ex = teselar_manual(extraer_manual(d.scene, commands=d.commands, stages=etapas), candado)
    assert candado.veces == 3 and not candado.tomado
    assert [p.id for p in ex.piezas] == list(ids.values())
    assert ex.bbox[0][2] == pytest.approx(0, abs=1) and ex.bbox[1][2] == pytest.approx(340, abs=1)


def test_sin_opengl_el_manual_sale_con_matplotlib_y_lo_dice(monkeypatch, caplog):
    import apolo.kernel.render_vivo as rv

    def sin_contexto(self, *a, **kw):
        raise RuntimeError("sin contexto OpenGL")

    monkeypatch.setattr(rv.EscenaViva, "__init__", sin_contexto)
    d, ids, etapas, colores = _torre()
    ex = teselar_manual(extraer_manual(d.scene, commands=d.commands, size_px=300, stages=etapas,
                                       colors=colores))
    with caplog.at_level(logging.WARNING, logger="apolo.drawing.manual_fotos"):
        fotos = fotos_manual(ex)
    assert any("matplotlib" in r.getMessage() for r in caplog.records)
    assert len(fotos) == 4 and all(f[:4] == b"\x89PNG" for f in fotos)
    paso2 = _mascaras(_rgb(fotos[2]))
    assert paso2["rojo"].sum() > 100 and paso2["azul"].sum() < 20   # lo nuevo, a color
    paginas = componer_manual(ex, fotos)
    assert len(paginas) == 4 and paginas[2].images[0].png == fotos[2]
