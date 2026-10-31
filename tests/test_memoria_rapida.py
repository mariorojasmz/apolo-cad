"""La portada de la memoria de cálculo por el camino del manual (plan manual-rapido, F2).

- La memoria sale con las mismas secciones y textos que antes del cambio (congelados en un caso
  chico con el código de main, 2026-10-21): sólo cambian la foto de portada y dónde se dibuja.
- La portada tiene píxeles de la máquina (el color de sus piezas), no un recuadro vacío.
- Mientras se dibuja la foto, `STATE_LOCK` está libre: una mutación no espera.
- El teselado toma el candado pieza por pieza.
- Sin contexto OpenGL la foto sale con matplotlib sobre las mismas mallas y lo dice en el log.
"""

from __future__ import annotations

import io
import logging
import threading
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
import apolo.drawing as drawing
from apolo.doc import Document
from apolo.drawing import foto_escena


def _tb(hoja: str) -> list[str]:
    return ["Rev", "Fecha", "Descripción", "A", "<HOY>", "Memoria de cálculo", "mueble",
            "Plano —", "Dib. Apolo · agente IA  <HOY>", "Rev.    Apr. ", "Genix Apolo CAD",
            "Material", "—", "Acabado / Peso", "— · 100.48 kg", "Tol. gral / Unid.", "— · mm",
            "Escala / Hoja", f"— · {hoja} A4"]


#: Los textos y las imágenes de cada página con el código de main (matplotlib bajo STATE_LOCK).
#: Re-congelados en los cortes fijos fuera del cajetín (plan V8.9): comparados contra los de antes,
#: las hojas 2 y 3 dicen las MISMAS palabras (sólo cambia dónde se parte cada renglón: se mide en
#: la columna en vez de cortar a 46-58 caracteres) y la portada suma lo que se cortaba a 62 de las
#: normas («… cortant» → «… cortante del perno) · criterio de diseño: equilibrio estático …»).
PAGINAS_DE_MAIN = [
    (["MEMORIA DE CÁLCULO", "mueble", "BASES DE DISEÑO", "Carga por paquete:  50 kg",
      "Largo de paquete:  300 mm",
      "Normas aplicadas: EN 1993-1-8 · ISO 898-1 (capacidad a cortante del perno) · criterio de "
      "diseño: equilibrio", "estático (COG dentro de la huella de apoyo)",
      "ÍNDICE DE VERIFICACIONES", "1. Unión apernada u1", "OK", "2. Estabilidad al vuelco",
      "OK", "Resultado: 2 OK · 0 avisos · 0 errores", "VEREDICTO: APROBADO", *_tb("1/3")], 1),
    (["1. UNIÓN APERNADA U1", "OK", "DATOS DE ENTRADA",
      "masa colgante: 50.2 kg (grafo de conectividad)", "carga: 493 N", "pernos: 4× M8 8.8",
      "capacidad/ud: 14054 N (0.6·Rm·As/1.25, EN 1993-1-8)", "VERIFICACIÓN",
      "u1 (Base madera ↔ Tapa madera): 50.2 kg cuelgan de 4× M8 → utilización 1% a cortante.",
      "FÓRMULA", "u = F / (n · Fv)", "SUSTITUCIÓN",
      "u = 493 / (4·14054)", "RESULTADO", "u = 0.01 (1% de la capacidad a cortante)",
      "CRITERIO DE ACEPTACIÓN", "u ≤ 0.7 holgado · 0.7–1.0 justo · >1.0 sobrecargada",
      "NORMA DE REFERENCIA", "EN 1993-1-8 · ISO 898-1 (capacidad a cortante del perno)",
      "FACTOR DE SEGURIDAD", "FS = 114.07", *_tb("2/3")], 0),
    (["2. ESTABILIDAD AL VUELCO", "OK", "DATOS DE ENTRADA", "masa total: 100.48 kg (sin producto)",
      "COG: (0, 0, 255) mm", "base de apoyo: 4 vértices, dim. menor 400 mm", "VERIFICACIÓN",
      # D8 de puerta-fuera-de-catalogo: sin fuerzas de trabajo declaradas, el vuelco lo dice
      "COG a 200 mm del borde de la base de apoyo (mínimo requerido 40 mm; producto no incluido). "
      "Sin fuerzas de",
      "trabajo declaradas (requisitos fuerza_horizontal_n, carga_borde_n): no se verifica el "
      "vuelco al empujarla.",
      "FÓRMULA", "margen = dist(COG_xy, borde de la base de apoyo)", "SUSTITUCIÓN",
      "margen(0, 0) sobre el casco convexo de los apoyos", "RESULTADO", "margen = 200 mm",
      "CRITERIO DE ACEPTACIÓN", "≥ 10% de la base menor = 40 mm", "NORMA DE REFERENCIA",
      "criterio de diseño: equilibrio estático (COG dentro de la huella de apoyo)",
      "FACTOR DE SEGURIDAD", "FS = 5", *_tb("3/3")], 0),
]

ROJO, AZUL = "#e01010", "#1030e0"


def _mueble() -> tuple[Document, str, str]:
    doc = Document("mueble")
    base = doc.execute("create_box", {"name": "Base madera", "width": 800, "depth": 400,
                                      "height": 20, "position": {"z": 10}})
    tapa = doc.execute("create_box", {"name": "Tapa madera", "width": 800, "depth": 400,
                                      "height": 20, "position": {"z": 500}})
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "u1", "a": base, "b": tapa, "kind": "perno",
                           "size": "M8", "qty": 4})
    doc.requirements = {"carga_kg": 50.0, "largo_paquete_mm": 300.0}
    doc.colors[base], doc.colors[tapa] = AZUL, ROJO
    return doc, base, tapa


@pytest.fixture
def paginas(monkeypatch):
    """Pide la memoria por el endpoint y devuelve las láminas (`SheetModel`) que se imprimieron."""
    capt: dict = {}
    original = drawing.sheets_to_pdf

    def espia(pages):
        capt["pages"] = pages
        return original(pages)

    monkeypatch.setattr(drawing, "sheets_to_pdf", espia)

    def pedir(doc):
        api.DOC = doc
        r = TestClient(api.app).get("/api/calc-report.pdf")
        assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:300]
        return capt["pages"]

    return pedir


def _rgb(png: bytes):
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(float)


def _mascaras(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return {"rojo": (r > 90) & (r > 2.2 * g) & (r > 2.2 * b),
            "azul": (b > 90) & (b > 2.0 * r) & (b > 1.5 * g)}


def test_la_memoria_sale_con_las_mismas_secciones_y_textos(paginas):
    hoy = date.today().isoformat()
    pages = paginas(_mueble()[0])
    assert [([lb.text.replace(hoy, "<HOY>") for lb in p.labels], len(p.images))
            for p in pages] == PAGINAS_DE_MAIN


def test_la_portada_tiene_pixeles_de_la_maquina(paginas):
    portada = paginas(_mueble()[0])[0]
    (img,) = portada.images
    m = _mascaras(_rgb(img.png))
    assert m["rojo"].sum() > 300 and m["azul"].sum() > 300   # la tapa y la base, a color


def test_lo_oculto_no_sale_en_la_foto_y_sin_nada_visible_no_hay_foto(paginas):
    doc, base, tapa = _mueble()
    doc.set_visibility(tapa, False)
    m = _mascaras(_rgb(paginas(doc)[0].images[0].png))
    assert m["azul"].sum() > 300 and m["rojo"].sum() == 0
    doc.set_visibility(base, False)
    assert paginas(doc)[0].images == []          # como antes: la memoria sale sin foto


def test_la_foto_vtk_tiene_el_tamano_y_los_colores(monkeypatch):
    doc, base, tapa = _mueble()
    ex = foto_escena.teselar_foto(foto_escena.extraer_foto(doc.scene, colors=doc.colors,
                                                           size_px=400))
    try:
        png = foto_escena._foto_vtk(ex)
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL en este entorno
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    rgb = _rgb(png)
    assert rgb.shape[:2] == (312, 400)            # el aspecto de render_view
    m = _mascaras(rgb)
    assert m["rojo"].sum() > 300 and m["azul"].sum() > 300


# ── locks y respaldo ──────────────────────────────────────────────────────────

def _png_minimo() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_state_lock_queda_libre_mientras_se_dibuja_la_portada(monkeypatch):
    from apolo.state import STATE_LOCK

    doc = _mueble()[0]
    api.DOC = doc
    dibujando, seguir = threading.Event(), threading.Event()

    def foto_lenta(ex):
        dibujando.set()
        assert seguir.wait(30), "el test no soltó la foto"
        return _png_minimo()

    monkeypatch.setattr(foto_escena, "_foto_vtk", foto_lenta)
    resp = {}
    hilo = threading.Thread(target=lambda: resp.setdefault(
        "r", TestClient(api.app).get("/api/calc-report.pdf")))
    hilo.start()
    try:
        assert dibujando.wait(60), "la memoria nunca llegó a la foto"
        assert STATE_LOCK.acquire(timeout=2), "STATE_LOCK sigue tomado mientras se dibuja"
        try:  # una mutación en plena foto: no espera a la memoria
            doc.execute("create_box", {"name": "Intrusa", "width": 10, "depth": 10, "height": 10})
        finally:
            STATE_LOCK.release()
    finally:
        seguir.set()
        hilo.join(60)
    r = resp["r"]
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_el_teselado_de_la_portada_toma_el_candado_pieza_por_pieza(monkeypatch):
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
    doc, base, tapa = _mueble()
    ex = foto_escena.teselar_foto(foto_escena.extraer_foto(doc.scene), candado)
    assert candado.veces == 2 and not candado.tomado
    assert [p.id for p in ex.piezas] == [base, tapa]
    assert ex.bbox[0][2] == pytest.approx(0, abs=1) and ex.bbox[1][2] == pytest.approx(510, abs=1)


def test_sin_opengl_la_portada_sale_con_matplotlib_y_lo_dice(monkeypatch, caplog, paginas):
    import apolo.kernel.render_vivo as rv

    def sin_contexto(self, *a, **kw):
        raise RuntimeError("sin contexto OpenGL")

    monkeypatch.setattr(rv.EscenaViva, "__init__", sin_contexto)
    with caplog.at_level(logging.WARNING, logger="apolo.drawing.foto_escena"):
        portada = paginas(_mueble()[0])[0]
    assert any("matplotlib" in r.getMessage() for r in caplog.records)
    m = _mascaras(_rgb(portada.images[0].png))
    assert m["rojo"].sum() > 100 and m["azul"].sum() > 100
