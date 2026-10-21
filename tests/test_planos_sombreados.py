"""Las isométricas SOMBREADAS de los planos fuera de `STATE_LOCK` (plan manual-rapido, F2b).

- El juego de planos y la hoja GA salen con las mismas láminas, textos (en su orden) e imágenes
  que antes del cambio (congelados en `tests/data/planos_sombreados_main.json` con el código de
  main, 2026-10-21): sólo cambian las fotos y dónde se dibujan.
- Cada foto tiene píxeles de la máquina: el GA, todas sus piezas; la lámina de una pieza, sólo la
  suya, con su color.
- Mientras se dibujan, `STATE_LOCK` está libre (una mutación no espera); el teselado lo toma pieza
  por pieza; todas las fotos salen de UNA ventana VTK.
- Sin contexto OpenGL salen con matplotlib y lo dice el log.
- Por job (`?async=true`): el mismo archivo, el mismo 400 que en directo y 409 si cambia el
  proyecto mientras espera.
"""

from __future__ import annotations

import io
import json
import logging
import pathlib
import threading
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
import apolo.drawing as drawing
from apolo.doc import Document
from apolo.drawing import fotos_planos
from apolo.state import STATE_LOCK

ROJO, AZUL = "#e01010", "#1030e0"
GA = {"sheet": "A3", "cutlist": True, "hardware": True, "shaded": True, "assembly_notes": [],
      "format": "pdf"}
MAIN = json.loads((pathlib.Path(__file__).parent / "data" / "planos_sombreados_main.json")
                  .read_text(encoding="utf-8"))


def _mueble() -> tuple[Document, str, str]:
    doc = Document("mueble")
    base = doc.execute("create_box", {"name": "Base madera", "width": 800, "depth": 400,
                                      "height": 20, "position": {"z": 10}})
    tapa = doc.execute("create_box", {"name": "Tapa madera", "width": 700, "depth": 400,
                                      "height": 20, "position": {"z": 500}})
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "u1", "a": base, "b": tapa, "kind": "perno",
                           "size": "M8", "qty": 4})
    doc.colors[base], doc.colors[tapa] = AZUL, ROJO
    return doc, base, tapa


@pytest.fixture
def laminas(monkeypatch):
    """Pide el juego (`"juego"`) o el GA (`"ga"`) por el endpoint y devuelve las láminas."""
    capt: dict = {}
    muchas, una = drawing.sheets_to_pdf, drawing.sheet_to_pdf
    monkeypatch.setattr(drawing, "sheets_to_pdf",
                        lambda pages: (capt.__setitem__("p", pages), muchas(pages))[1])
    monkeypatch.setattr(drawing, "sheet_to_pdf",
                        lambda m: (capt.__setitem__("p", [m]), una(m))[1])

    def pedir(doc, cual: str):
        api.DOC = doc
        c = TestClient(api.app)
        r = (c.get("/api/drawingset.pdf", params={"shaded": "true"}) if cual == "juego"
             else c.post("/api/drawing/spec", json=GA))
        assert r.status_code == 200 and r.content[:4] == b"%PDF", r.text[:300]
        return capt["p"]

    return pedir


def _rgb(png: bytes):
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(float)


def _colores(png: bytes) -> dict:
    rgb = _rgb(png)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return {"rojo": int(((r > 90) & (r > 2.2 * g) & (r > 2.2 * b)).sum()),
            "azul": int(((b > 90) & (b > 2.0 * r) & (b > 1.5 * g)).sum())}


@pytest.mark.parametrize("cual", ["juego", "ga"])
def test_mismas_laminas_textos_e_imagenes_que_main(laminas, cual):
    hoy = date.today().isoformat()
    pages = laminas(_mueble()[0], cual)
    assert [[[lb.text.replace(hoy, "<HOY>") for lb in p.labels], len(p.images)]
            for p in pages] == MAIN[cual]
    assert all(p.hueco_iso is None for p in pages)


def test_cada_foto_tiene_pixeles_de_su_maquina(laminas):
    conjunto, base, tapa = laminas(_mueble()[0], "juego")[:3]
    ga = _colores(conjunto.images[0].png)
    assert ga["rojo"] > 300 and ga["azul"] > 300          # las dos piezas, a color
    b, t = _colores(base.images[0].png), _colores(tapa.images[0].png)
    assert b["azul"] > 300 and b["rojo"] == 0             # cada lámina, sólo su pieza
    assert t["rojo"] > 300 and t["azul"] == 0


def test_la_foto_cabe_en_su_cuadrante_con_el_rotulo_encima(laminas):
    (ga,) = laminas(_mueble()[0], "ga")
    (img,) = ga.images
    rot = next(lb for lb in ga.labels if lb.text == fotos_planos.ROTULO)
    assert img.w > 50 and img.h > 50 and img.x > 200          # cuadrante derecho del A3
    assert rot.y == pytest.approx(img.y + img.h + 3)


def test_lo_oculto_no_sale_y_sin_nada_visible_no_hay_foto_ni_rotulo(laminas):
    doc, base, tapa = _mueble()
    doc.set_visibility(tapa, False)
    (ga,) = laminas(doc, "ga")
    c = _colores(ga.images[0].png)
    assert c["azul"] > 300 and c["rojo"] == 0
    m = drawing.compose_sheet(doc.scene, cutlist=True, shaded=True, foto_diferida=True)
    textos = [lb.text for lb in m.labels]
    m.hueco_iso.escena = {tapa: doc.scene[tapa]}      # sólo lo oculto: nada que fotografiar
    fotos_planos.revelar(fotos_planos.extraer([m]))
    assert m.images == [] and [lb.text for lb in m.labels] == textos and m.hueco_iso is None


# ── locks, una ventana y respaldo ─────────────────────────────────────────────

def _png_minimo() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize("cual", ["juego", "ga"])
def test_state_lock_queda_libre_mientras_se_dibujan(monkeypatch, cual):
    doc = _mueble()[0]
    api.DOC = doc
    dibujando, seguir = threading.Event(), threading.Event()

    def fotos_lentas(validas):
        dibujando.set()
        assert seguir.wait(30), "el test no soltó las fotos"
        return [(i, _png_minimo()) for i, _ex in validas]

    monkeypatch.setattr(fotos_planos, "_fotos_vtk", fotos_lentas)
    c, resp = TestClient(api.app), {}
    pedir = ((lambda: c.get("/api/drawingset.pdf", params={"shaded": "true"})) if cual == "juego"
             else (lambda: c.post("/api/drawing/spec", json=GA)))
    hilo = threading.Thread(target=lambda: resp.setdefault("r", pedir()))
    hilo.start()
    try:
        assert dibujando.wait(60), "el plano nunca llegó a las fotos"
        assert STATE_LOCK.acquire(timeout=2), "STATE_LOCK sigue tomado mientras se dibuja"
        try:  # una mutación en plena foto: no espera al plano
            doc.execute("create_box", {"name": "Intrusa", "width": 10, "depth": 10, "height": 10})
        finally:
            STATE_LOCK.release()
    finally:
        seguir.set()
        hilo.join(60)
    assert resp["r"].status_code == 200 and resp["r"].content[:4] == b"%PDF"


def test_el_teselado_toma_el_candado_pieza_por_pieza_y_hay_una_sola_ventana(monkeypatch):
    import apolo.kernel.render_vivo as rv

    class Candado:
        tomado, veces = False, 0

        def __enter__(self):
            assert not self.tomado
            self.tomado, self.veces = True, self.veces + 1

        def __exit__(self, *_exc):
            self.tomado = False

    candado, ventanas = Candado(), []
    original_extraer, original_init = rv.extraer_piezas, rv.EscenaViva.__init__

    def espia(escena, *a, **kw):
        assert candado.tomado and len(escena) == 1, "una pieza por toma del candado"
        return original_extraer(escena, *a, **kw)

    def contar(self, *a, **kw):
        ventanas.append(kw.get("fondo"))
        original_init(self, *a, **kw)

    monkeypatch.setattr(rv, "extraer_piezas", espia)
    monkeypatch.setattr(rv.EscenaViva, "__init__", contar)
    doc = _mueble()[0]
    pages = drawing.sheet_set(doc.scene, shaded=True, foto_diferida=True, colors=doc.colors)
    assert sum(p.hueco_iso is not None for p in pages) == 3 and not any(p.images for p in pages)
    fotos_planos.revelar(fotos_planos.extraer(pages), candado)
    assert candado.veces == 4 and not candado.tomado     # 2 piezas del GA + 1 por lámina
    assert [len(p.images) for p in pages] == [1, 1, 1, 0]   # sin la de instalación
    assert ventanas == [fotos_planos.BLANCO]              # UNA ventana para las 3 fotos


def test_sin_opengl_salen_con_matplotlib_y_lo_dice(monkeypatch, caplog, laminas):
    import apolo.kernel.render_vivo as rv

    def sin_contexto(self, *a, **kw):
        raise RuntimeError("sin contexto OpenGL")

    monkeypatch.setattr(rv.EscenaViva, "__init__", sin_contexto)
    with caplog.at_level(logging.WARNING, logger="apolo.drawing.fotos_planos"):
        conjunto, base, tapa = laminas(_mueble()[0], "juego")[:3]
    assert any("matplotlib" in r.getMessage() for r in caplog.records)
    c = _colores(conjunto.images[0].png)
    assert c["rojo"] > 100 and c["azul"] > 100
    assert _colores(tapa.images[0].png)["rojo"] > 100


def test_compose_sheet_sin_diferir_sigue_dibujando_la_foto():
    doc, base, tapa = _mueble()
    model = drawing.compose_sheet(doc.scene, cutlist=True, shaded=True, colors=doc.colors)
    assert model.hueco_iso is None and len(model.images) == 1
    c = _colores(model.images[0].png)
    assert c["rojo"] > 300 and c["azul"] > 300


# ── por job ───────────────────────────────────────────────────────────────────

def _esperar(c: TestClient, job_id: str) -> dict:
    for _ in range(10):
        job = c.get(f"/api/jobs/{job_id}", params={"wait_s": 30}).json()
        if job["estado"] in ("ok", "error"):
            return job
    raise AssertionError(f"el job {job_id} no terminó")


def test_el_juego_y_el_ga_por_job_dejan_su_archivo_para_bajar():
    api.DOC = _mueble()[0]
    c = TestClient(api.app)
    for tipo, r, nombre in (
        ("drawing_set", c.get("/api/drawingset.pdf", params={"shaded": "true", "async": "true"}),
         "mueble-planos.pdf"),
        ("drawing", c.post("/api/drawing/spec", params={"async": "true"}, json=GA),
         "mueble.pdf"),
    ):
        assert r.status_code == 202, r.text
        job = _esperar(c, r.json()["job_id"])
        assert job["estado"] == "ok" and job["tipo"] == tipo
        res = job["resultado"]
        assert res["tipo"] == "application/pdf" and res["nombre"] == nombre
        pdf = c.get(res["archivo"])
        assert pdf.content[:4] == b"%PDF" and len(pdf.content) == res["bytes"]


def test_el_plano_svg_por_job_trae_el_svg():
    api.DOC = _mueble()[0]
    c = TestClient(api.app)
    r = c.post("/api/drawing/spec", params={"async": "true"}, json={**GA, "format": "svg"})
    res = _esperar(c, r.json()["job_id"])["resultado"]
    assert res["tipo"] == "image/svg+xml"
    assert "<image" in c.get(res["archivo"]).text


@pytest.mark.parametrize("pedir", [
    lambda c, extra: c.get("/api/drawingset.pdf", params={"sheet": "A5", **extra}),
    lambda c, extra: c.post("/api/drawing/spec", params=extra,
                            json={**GA, "isolate": ["no-existe"]}),
], ids=["juego", "ga"])
def test_un_job_fallido_da_el_mismo_error_que_en_directo(pedir):
    api.DOC = _mueble()[0]
    c = TestClient(api.app)
    directo = pedir(c, {})
    job = _esperar(c, pedir(c, {"async": "true"}).json()["job_id"])
    assert directo.status_code == 400
    assert job["estado"] == "error" and job["http_status"] == 400
    assert job["error"] == directo.json()["detail"]


def test_si_cambia_el_proyecto_mientras_espera_no_se_genera():
    api.DOC = _mueble()[0]
    api.PROJECT_ID = 7
    c = TestClient(api.app)
    with STATE_LOCK:   # los jobs no pueden empezar: se encolan con el proyecto 7…
        ids = [c.get("/api/drawingset.pdf", params={"async": "true"}).json()["job_id"],
               c.post("/api/drawing/spec", params={"async": "true"}, json=GA).json()["job_id"]]
        api.PROJECT_ID = 8   # …y antes de correr se abrió otro
    for job_id in ids:
        job = _esperar(c, job_id)
        assert job["estado"] == "error" and job["http_status"] == 409
        assert "era 7, ahora 8" in job["error"]
