"""El video del guion grabado por el navegador (plan video-realista, F3 · D5 y D7).

- El guion gana la `marcha` (opcional): cuenta en la duración y en los capítulos, y el respaldo
  VTK la quita (`sin_marcha`).
- `services/plan_navegador.py` arma el plan cuadro por cuadro con las MISMAS funciones que el
  video de VTK: partes, piezas que entran, órbita, fundidos, rótulo y el reloj de la marcha.
- El rótulo del navegador se lee a ≥ 4.5:1 sobre cualquier cuadro (D4 de video-montaje-pulido).
- La API guarda guion y plan en la sesión, recibe la foto, dibuja tarjetas y rótulos y anota el
  fallo del navegador; `POST /api/video/guion` los arma para el botón «Grabar video».
- El lado del CLI (`publicar generar --render navegador`: buscar el navegador, lanzar la página
  `?grabar=<sesion>` y caer a VTK) es de la fábrica de publicaciones y se prueba con ella, fuera
  del núcleo. Lo que codifica se salta sin ffmpeg.
"""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api.routers import video as rv
from apolo.doc import Document
from apolo.media import grabacion as gr
from apolo.services import linea_tiempo as lt
from apolo.services.plan_navegador import PlanError, plan
from apolo.services.guion_video import (
    MODO_DISENO,
    MODO_MONTAJE,
    GuionError,
    capitulos,
    duracion_total,
    sin_marcha,
    validar_guion,
)

Image = pytest.importorskip("PIL.Image")
def _ffmpeg_disponible() -> bool:
    """¿Hay ffmpeg y ffprobe? (lo que codifica se salta sin ellos)."""
    from apolo.media.codificar import FfmpegNoEncontrado, buscar_ffmpeg, buscar_ffprobe

    try:
        buscar_ffmpeg()
        buscar_ffprobe()
    except FfmpegNoEncontrado:
        return False
    return True


con_ffmpeg = pytest.mark.skipif(not _ffmpeg_disponible(), reason="sin ffmpeg/ffprobe")
ANCHO, ALTO, FPS = 160, 90, 10


def _mesa() -> Document:
    """Cuatro patas ancladas y un tablero atornillado: una secuencia de montaje de verdad."""
    d = Document("Mesa de taller")
    patas = [d.execute("create_box", {"name": f"Pata ({i + 1})", "width": 40, "depth": 40,
                                      "height": 400, "position": {"x": x, "y": y, "z": 200}})
             for i, (x, y) in enumerate([(-250, -150), (250, -150), (-250, 150), (250, 150)])]
    tablero = d.execute("create_box", {"name": "Tablero", "width": 600, "depth": 340,
                                       "height": 20, "position": {"x": 0, "y": 0, "z": 410}})
    d.execute("create_group", {"name": "Bastidor", "members": patas})
    for i, p in enumerate(patas):
        d.execute("ground", {"name": f"g{i}", "feature": p})
        d.execute("fasten", {"name": f"f{i}", "a": tablero, "b": p, "kind": "perno"})
    return d


@pytest.fixture(scope="module")
def mesa():
    return _mesa()


def _guion(doc, *, marcha: bool = True, modo: str = MODO_MONTAJE) -> dict:
    from apolo.services.guion_video import guion
    from apolo.services.montaje_video import etapas_del_modo

    g = guion(doc, etapas_del_modo(doc, 30.0, modo), modo=modo,
              marcha={"duracion_s": 0.6, "escenario": {"duracion_s": 2.0}} if marcha else None)
    g["video"].update(ancho=ANCHO, alto=ALTO, fps=FPS)
    g["portada"]["duracion_s"] = 0.5
    for e in g["etapas"]:
        e["duracion_s"] = 1.0
    g["cifras"]["duracion_s"] = 0.4  # D10: se ignora (las cifras no salen en el video)
    g["orbita"]["duracion_s"], g["cierre"]["duracion_s"] = 1.0, 0.4
    return g


# ── El guion con la marcha ─────────────────────────────────────────────────────


def test_la_marcha_es_opcional_cuenta_en_la_duracion_y_vtk_la_quita(mesa):
    g = _guion(mesa)
    validar_guion(g, mesa)
    validar_guion(_guion(mesa, marcha=False), mesa)  # un guion de antes sigue valiendo
    assert duracion_total(g) == pytest.approx(duracion_total(sin_marcha(g)) + 0.6)
    assert "marcha" not in sin_marcha(g) and "marcha" in g
    partes = [t.parte for t in lt.tramos(g)]
    assert partes.index("marcha") == partes.index("orbita") - 1  # tras las etapas, antes de la vuelta
    assert "cifras" not in partes  # D10 de fabrica-de-publicaciones
    assert "marcha" not in [t.parte for t in lt.tramos(sin_marcha(g))]
    capitulos(g)  # la marcha cae dentro del último capítulo, sin romper la regla


@pytest.mark.parametrize("cambio, error", [
    (lambda m: m.update(duracion_s=-1), "marcha.duracion_s"),
    (lambda m: m.update(escenario=[1]), "marcha.escenario"),
    (lambda m: m.update(duracion=3), "clave desconocida «duracion»"),
])
def test_una_marcha_mal_escrita_se_rechaza(mesa, cambio, error):
    g = _guion(mesa)
    cambio(g["marcha"])
    with pytest.raises(GuionError, match=error):
        validar_guion(g)


# ── El plan cuadro por cuadro ─────────────────────────────────────────────────


def test_el_plan_reparte_el_guion_como_el_video_de_vtk(mesa):
    g = _guion(mesa)
    p = plan(mesa, g, proyecto=7)
    n = p["cuadros"]
    assert n == round(duracion_total(g) * FPS) == lt.total_fotogramas(lt.tramos(g))
    assert p["proyecto"] == 7 and p["video"] == {"ancho": ANCHO, "alto": ALTO, "fps": FPS}
    assert all(len(v) == n for v in p["cuadro"].values())
    tramos = {t["parte"]: t for t in p["tramos"] if t["parte"] != "etapa"}
    etapas = [t for t in p["tramos"] if t["parte"] == "etapa"]
    # cada pieza montada entra UNA vez, dentro de una etapa; la primera, al empezar
    montadas = [f for e in g["etapas"] for tanda in e["pasos"] for f in tanda]
    entran = [f for a in p["apariciones"] for f in a["ids"]]
    assert sorted(entran) == sorted(montadas) and len(set(entran)) == len(entran)
    assert p["apariciones"][0]["cuadro"] == etapas[0]["inicio"]
    for a in p["apariciones"]:
        assert any(e["inicio"] <= a["cuadro"] < e["fin"] for e in etapas)
    # el rótulo sólo en las etapas; la órbita sale de donde dejó la marcha
    for f, o in enumerate(p["cuadro"]["rotulo"]):
        assert (o > 0) <= any(e["inicio"] <= f < e["fin"] for e in etapas)
    az = p["cuadro"]["az"]
    m, o = tramos["marcha"], tramos["orbita"]
    assert az[o["inicio"]] == pytest.approx(az[m["fin"] - 1], abs=1e-3)
    assert "cifras" not in tramos  # D10: el cierre es la portada de la tienda, sin cifras
    assert all(az[f] is None for f in range(tramos["cierre"]["inicio"], tramos["cierre"]["fin"]))
    assert az[o["fin"] - 1] - az[o["inicio"]] > 300  # la vuelta final, casi completa
    assert az[etapas[0]["inicio"]] == pytest.approx(lt.AZIMUT_INICIAL)


def test_los_fundidos_y_el_reloj_de_la_marcha(mesa):
    p = plan(mesa, _guion(mesa))
    tramos = {t["parte"]: t for t in p["tramos"]}
    mezcla, mt = p["cuadro"]["mezcla"], p["cuadro"]["marcha_t"]
    assert tramos["marcha"]["cruza"] is False and mezcla[tramos["marcha"]["inicio"]] is None
    for parte in ("orbita", "cierre"):
        assert tramos[parte]["cruza"] and mezcla[tramos[parte]["inicio"]] is not None
    a = tramos["marcha"]["inicio"]
    assert mt[a - 1] is None and mt[a] == 0 and mt[a + 1] == pytest.approx(1 / FPS)
    assert all(mt[f] is None for f in range(tramos["cierre"]["inicio"], tramos["cierre"]["fin"]))
    o = tramos["orbita"]["inicio"]
    assert mt[o] == pytest.approx((o - a) / FPS)  # en la vuelta final la máquina sigue andando
    assert p["marcha"]["escenario"] == {"duracion_s": 2.0}
    assert p["cuadro"]["luz"][0] < 1 and p["cuadro"]["luz"][-1] < 1


def test_el_plan_es_solo_de_montaje(mesa):
    with pytest.raises(PlanError, match="MONTAJE"):
        plan(mesa, _guion(mesa, modo=MODO_DISENO, marcha=False))


# ── El rótulo legible ─────────────────────────────────────────────────────────


def test_el_rotulo_del_navegador_se_lee_sobre_cualquier_cuadro():
    from apolo.media import composicion as comp
    from apolo.media.contraste import BLANCO, NEGRO, contraste, peor_contraste

    e = comp.ESTILO
    a = comp.opacidad_rotulo_legible(e)
    assert e.opacidad_panel <= a <= 1
    for color in (e.color_texto, e.color_secundario):
        assert peor_contraste(color, e.color_panel, a) >= 4.5
    # con la opacidad del estilo, el texto secundario sobre un cuadro blanco no llegaba
    assert peor_contraste(e.color_secundario, e.color_panel, e.opacidad_panel) < 4.5
    assert contraste(BLANCO, NEGRO) == pytest.approx(21)
    capa = comp.capa_rotulo("Bastidor", "Cuatro patas ancladas al piso.", e)
    assert capa.mode == "RGBA" and capa.size == (e.ancho, e.alto)
    x0, y0, x1, y1 = comp.maquetar_rotulo("Bastidor", "Cuatro patas ancladas al piso.", e).caja
    assert capa.getpixel((5, 5))[3] == 0  # fuera del panel, transparente
    assert capa.getpixel((x1 - 4, y0 + 4))[3] == round(255 * a)


# ── La API ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    almacen = gr.Grabaciones(tmp_path / "grabaciones")
    monkeypatch.setattr(rv, "GRABACIONES", almacen)
    api.DOC = _mesa()
    return SimpleNamespace(c=TestClient(api.app), almacen=almacen, tmp=tmp_path)


def _imagen(formato: str = "JPEG", ancho: int = ANCHO, alto: int = ALTO, color=(90, 120, 150)):
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), color).save(buf, format=formato, quality=95)
    return buf.getvalue()


def _abrir(t, g: dict, **extra) -> dict:
    r = t.c.post("/api/video/grabacion", json={"guion": g, "plan": plan(api.DOC, g), **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_el_guion_del_boton_trae_guion_y_plan_con_la_ultima_marcha(cliente, monkeypatch):
    from apolo.api.routers import video_guion

    escenario = {"motores": [{"junta": "j", "modo": "velocidad"}]}
    monkeypatch.setattr(video_guion.MARCHAS, "ultimo_escenario", lambda proyecto: escenario)
    r = cliente.c.post("/api/video/guion", json={"duracion_s": 40})
    assert r.status_code == 200, r.text
    g, p = r.json()["guion"], r.json()["plan"]
    assert g["modo"] == MODO_MONTAJE and g["marcha"]["escenario"] == escenario
    assert p["cuadros"] == round(duracion_total(g) * g["video"]["fps"])
    assert duracion_total(g) == pytest.approx(40, abs=8)  # la marcha sale del presupuesto
    monkeypatch.setattr(video_guion.MARCHAS, "ultimo_escenario", lambda proyecto: None)
    assert "marcha" not in cliente.c.post("/api/video/guion").json()["guion"]
    api.DOC = Document("vacío")
    r = cliente.c.post("/api/video/guion")
    assert r.status_code == 400 and "no tiene piezas" in r.json()["detail"]


def test_la_sesion_guarda_guion_y_plan_y_dibuja_tarjetas_y_rotulos(cliente):
    g = _guion(api.DOC)
    s = _abrir(cliente, g)
    sid = s["sesion"]
    assert (s["ancho"], s["alto"], s["fps"], s["cuadros"]) == (ANCHO, ALTO, FPS,
                                                                  plan(api.DOC, g)["cuadros"])
    assert s["con_guion"] and not s["foto"] and Path(s["carpeta"]).is_dir()
    assert cliente.c.get(f"/api/video/grabacion/{sid}/plan").json() == plan(api.DOC, g)
    assert cliente.c.get(f"/api/video/grabacion/{sid}/foto").status_code == 404
    malo = cliente.c.post(f"/api/video/grabacion/{sid}/foto", content=_imagen(ancho=64))
    assert malo.status_code == 400 and "La foto mide 64" in malo.json()["detail"]
    assert cliente.c.post(f"/api/video/grabacion/{sid}/foto", content=_imagen("PNG")).status_code == 200
    assert cliente.c.get(f"/api/video/grabacion/{sid}/foto").content == _imagen("PNG")
    for parte in ("portada", "cierre"):
        r = cliente.c.get(f"/api/video/grabacion/{sid}/tarjeta/{parte}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        assert Image.open(io.BytesIO(r.content)).size == (ANCHO, ALTO)
    assert cliente.c.get(f"/api/video/grabacion/{sid}/tarjeta/otra").status_code == 404
    assert cliente.c.get(f"/api/video/grabacion/{sid}/tarjeta/cifras").status_code == 404  # D10
    capa = Image.open(io.BytesIO(cliente.c.get(f"/api/video/grabacion/{sid}/rotulo/0").content))
    assert capa.mode == "RGBA" and capa.size == (ANCHO, ALTO)
    assert cliente.c.get(f"/api/video/grabacion/{sid}/rotulo/99").status_code == 404
    assert cliente.c.delete(f"/api/video/grabacion/{sid}").status_code == 200
    assert not Path(s["carpeta"]).exists()  # la foto se borra con la sesión


def test_una_sesion_sin_guion_no_tiene_plan_y_un_plan_roto_se_rechaza(cliente):
    sid = cliente.c.post("/api/video/grabacion", json={"ancho": ANCHO, "alto": ALTO}).json()["sesion"]
    assert cliente.c.get(f"/api/video/grabacion/{sid}/plan").status_code == 409
    g = _guion(api.DOC)
    p = plan(api.DOC, g)
    p["cuadros"] += 1
    r = cliente.c.post("/api/video/grabacion", json={"guion": g, "plan": p})
    assert r.status_code == 400 and "plan completo" in r.json()["detail"]


def test_el_fallo_del_navegador_queda_en_la_sesion(cliente):
    sid = _abrir(cliente, _guion(api.DOC))["sesion"]
    r = cliente.c.post(f"/api/video/grabacion/{sid}/fallo",
                       json={"mensaje": "Este navegador dibuja sin GPU.", "motivo": "sin_gpu"})
    assert r.status_code == 200
    e = cliente.c.get(f"/api/video/grabacion/{sid}").json()
    assert (e["estado"], e["motivo"], e["error"]) == ("fallida", "sin_gpu",
                                                      "Este navegador dibuja sin GPU.")
    assert cliente.c.post(f"/api/video/grabacion/{sid}/cerrar").status_code == 409
    assert cliente.c.post(f"/api/video/grabacion/{sid}/cuadro/0", content=_imagen()).status_code == 409


@con_ffmpeg
def test_cerrar_sin_cuerpo_usa_lo_que_fijo_quien_abrio(cliente):
    salida = cliente.tmp / "fuera" / "video.mp4"
    salida.parent.mkdir()
    g = _guion(api.DOC, marcha=False)
    s = _abrir(cliente, g, salida=str(salida), conservar_cuadros=True)
    for n in range(s["cuadros"]):
        assert cliente.c.post(f"/api/video/grabacion/{s['sesion']}/cuadro/{n}",
                              content=_imagen()).status_code == 200
    inf = cliente.c.post(f"/api/video/grabacion/{s['sesion']}/cerrar").json()["informe"]
    assert inf["video"] == str(salida) and salida.is_file() and inf["cuadros_conservados"]
