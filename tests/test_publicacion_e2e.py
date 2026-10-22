"""`publicar guion` → `publicar generar` de punta a punta contra la API de tests (plan
publicacion-tienda, F4).

Dos proyectos chicos en una base temporal: una mesa con su estructura declarada (puerta en
VERDE) y seis cajas sin anclar (ROJO). El guion se achica a 320×180 y a pocos segundos para que
el video tarde ~1 s. Lo que necesita ffmpeg se salta sin él (en el CI de Linux se instala).
El juego de planos en DWG necesita ODA: si falta, la publicación lo registra y sigue.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo import paths
from apolo.doc import Document
from apolo.projects import ProjectStore
from apolo.publicacion import flujo
from apolo.publicacion.paquete import PublicacionError, PuertaRoja
from apolo.publicacion.video import ffmpeg_disponible
from apolo.services.guion_video import duracion_total

SECRETO = "precio interno al cliente: 1234 USD"
RAIZ_REPO = Path(__file__).resolve().parents[1]
con_ffmpeg = pytest.mark.skipif(not ffmpeg_disponible(), reason="sin ffmpeg/ffprobe")


def _mesa() -> Document:
    """~16 comandos: variable, 4 patas y tablero en dos grupos, anclajes y uniones."""
    d = Document("Mesa de taller")
    d.execute("set_variable", {"name": "L", "expression": "600"})
    patas = [d.execute("create_box", {"name": f"Pata ({i + 1})", "width": 40, "depth": 40,
                                      "height": 400, "position": {"x": x, "y": y, "z": 200}})
             for i, (x, y) in enumerate([(-250, -150), (250, -150), (-250, 150), (250, 150)])]
    tablero = d.execute("create_box", {"name": "Tablero", "width": "=L", "depth": 340,
                                       "height": 20, "position": {"x": 0, "y": 0, "z": 410}})
    d.execute("create_group", {"name": "Bastidor", "members": patas})
    d.execute("create_group", {"name": "Cubierta", "members": [tablero]})
    for i, p in enumerate(patas):
        d.execute("ground", {"name": f"g{i}", "feature": p})
        d.execute("fasten", {"name": f"f{i}", "a": tablero, "b": p, "kind": "perno"})
    d.agent_notes.append(SECRETO)
    d.set_requirements({"carga_kg": 20, "tipo_cambio": 3.7})
    return d


def _cajas() -> Document:
    d = Document("Cajas sueltas")
    for i in range(6):
        d.execute("create_box", {"name": f"Caja {i}", "width": 100, "depth": 100, "height": 100,
                                 "position": {"x": i * 200}})
    return d


@pytest.fixture()
def tienda(tmp_path):
    api.DOC = Document("vacío")
    api.STORE = ProjectStore(tmp_path / "proyectos.db")
    mesa, cajas = _mesa(), _cajas()
    ids = SimpleNamespace(verde=api.STORE.create(mesa), rojo=api.STORE.create(cajas))
    try:
        yield SimpleNamespace(c=TestClient(api.app), raiz=tmp_path / "publicaciones",
                              mesa=mesa, **vars(ids))
    finally:
        api._autosave_sched.cancel()
        api.STORE = None
        api.PROJECT_ID = None


def _preparar(t, proyecto: int, version: str | None = None) -> dict:
    """`guion` y lo que haría una persona: video chico y corto, ficha con descripción."""
    r = flujo.guion(t.c, proyecto, raiz=t.raiz, version=version, eco=None)
    g = json.loads(r["guion"].read_text(encoding="utf-8"))
    g["video"].update(ancho=320, alto=180)
    g["portada"]["duracion_s"] = 1.0
    for e in g["etapas"]:
        e["duracion_s"] = 1.5
    g["cifras"]["duracion_s"], g["orbita"]["duracion_s"], g["cierre"]["duracion_s"] = 1.0, 1.5, 1.0
    r["guion"].write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    texto = r["ficha"].read_text(encoding="utf-8")
    r["ficha"].write_text(texto.replace('descripcion: ""', 'descripcion: "Mesa de taller."'),
                          encoding="utf-8")
    return {**r, "g": g}


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


@con_ffmpeg
def test_guion_y_generar_dejan_un_paquete_publicable(tienda):
    from PIL import Image

    from apolo.media.codificar import sondear

    prep = _preparar(tienda, tienda.verde)
    carpeta = prep["carpeta"]
    assert carpeta == tienda.raiz / "mesa-de-taller" / "1.0.0"
    # el guion trae la URL derivada (con la tienda por defecto) y la ficha ya no la pide
    assert prep["g"]["cierre"]["url"] == "https://apolocad.com/maquinas/mesa-de-taller"
    assert "url_tienda" not in prep["ficha"].read_text(encoding="utf-8").split("musica:")[0]
    avisos: list[str] = []
    res = flujo.generar(tienda.c, tienda.verde, raiz=tienda.raiz, eco=avisos.append,
                        tienda="https://tienda.example")
    # otra tienda al generar: el cierre muestra la de ahora y lo avisa; sin pistas, sin música
    assert any("el video muestra la segunda" in a for a in avisos)
    assert any("sale SIN música" in a for a in avisos)

    nombres = {p.name for p in carpeta.iterdir()}
    assert {"guion.json", "ficha.yaml", "ficha.json", "generacion.json", "video.mp4",
            "youtube.txt", "gratis", "completo", "mesa-de-taller-1.0.0-gratis.zip",
            "mesa-de-taller-1.0.0-completo.zip"} <= nombres
    assert ".generando" not in nombres
    # la vista 3D (plan vista-3d-tienda, F1): metros, apoyada en Y = 0, bajo el tope
    assert "vista-3d.glb" in nombres and "vista-3d.crudo.glb" not in nombres
    v3 = json.loads((carpeta / "generacion.json").read_text(encoding="utf-8"))["vista_3d"]
    assert v3["archivo"] == "vista-3d.glb" and v3["piezas"] == 5
    assert v3["caja_m"][0][1] == 0.0 and v3["caja_m"][1][1] == pytest.approx(0.42, abs=1e-3)
    assert v3["triangulos"] <= v3["tope_triangulos"]
    assert v3["bytes"] == (carpeta / "vista-3d.glb").stat().st_size
    # su trozo de HTML (F2): una etiqueta por grupo, el póster es la miniatura del video
    assert "vista-3d.html" in nombres and v3["html"]["archivo"] == "vista-3d.html"
    assert [e["grupo"] for e in v3["html"]["etiquetas"]] == ["Bastidor", "Cubierta"]
    html_ = (carpeta / "vista-3d.html").read_text(encoding="utf-8")
    assert f'poster="{v3["html"]["poster"]}"' in html_ and (carpeta / v3["html"]["poster"]).is_file()
    assert 'data-src="vista-3d.glb"' in html_ and "Pata" not in html_  # D5
    ficha = json.loads((carpeta / "ficha.json").read_text(encoding="utf-8"))
    assert ficha["estado"] == "verificado" and ficha["url_video"] == ""
    assert ficha["validacion"]["veredicto"] == "VERDE"

    # niveles (D10) y nada prohibido (D11, D12)
    zips = {}
    for nivel in ("gratis", "completo"):
        with zipfile.ZipFile(carpeta / f"mesa-de-taller-1.0.0-{nivel}.zip") as zf:
            zips[nivel] = {n.split("/", 1)[1]: zf.read(n) for n in zf.namelist()}
    vista = {"vista-3d.glb", "vista-3d.html", ficha["miniatura"]}  # F3: en los dos niveles
    assert set(zips["gratis"]) == {"LEEME.md", "LICENCIA.txt", "AVISO.txt", "bom.csv",
                                   "modelo.step", "planos/conjunto_GA.pdf", "render/iso.png",
                                   "render/lateral.png", "render/planta.png"} | vista
    assert {"mesa-de-taller.apolo", "memoria.pdf", "manual.pdf", "planos/juego.pdf",
            "planos/cutlist.csv", "bom.json"} | vista <= set(zips["completo"])
    for nivel in zips:
        assert zips[nivel]["vista-3d.glb"] == (carpeta / "vista-3d.glb").read_bytes()
        assert "`vista-3d.html` | Vista 3D para la web" in zips[nivel]["LEEME.md"].decode()
    # ficha.json nombra la vista 3D, con su sha256 en `archivos`
    assert ficha["vista_3d"] == {
        "modelo": "vista-3d.glb", "html": "vista-3d.html", "poster": ficha["miniatura"],
        "bytes": v3["bytes"], "triangulos": v3["triangulos"],
        "etiquetas": [{"grupo": e["grupo"], "cifra": e["cifra"]} for e in v3["html"]["etiquetas"]]}
    assert {"vista-3d.glb", "vista-3d.html"} <= {a["nombre"] for a in ficha["archivos"]}
    for nivel, contenido in zips.items():
        assert not [n for n in contenido if any(x in n for x in ("costeo", "cotiz", "validacion"))]
        for n, blob in contenido.items():
            assert SECRETO.encode() not in blob, f"{nivel}/{n} filtra la nota del agente"
    if "planos/juego_dwg.zip" not in zips["completo"]:  # sin ODA: se registra, no se falla
        assert any("DWG" in x for x in res["faltantes"])

    # el .apolo saneado abre y regenera la misma máquina
    apolo = zips["completo"]["mesa-de-taller.apolo"]
    with zipfile.ZipFile(io.BytesIO(apolo)) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert "agent_notes" not in manifest and "tipo_cambio" not in manifest["requirements"]
    abierto = Document.from_apolo_bytes(apolo)
    assert set(abierto.scene) == set(tienda.mesa.scene) and abierto.name == "Mesa de taller"

    # cada sha256 de ficha.json cuadra con su archivo, también adentro de los zips (D9)
    for archivo in ficha["archivos"]:
        assert _sha((carpeta / archivo["nombre"]).read_bytes()) == archivo["sha256"]
        nivel = archivo.get("contenido") and archivo["nivel"]
        for interno in archivo.get("contenido", []):
            assert _sha(zips[nivel][interno["nombre"]]) == interno["sha256"]

    # el video dura lo que dice el guion, y la miniatura es la de YouTube
    sonda = sondear(carpeta / "video.mp4")
    assert (sonda["ancho"], sonda["alto"], sonda["codec"]) == (320, 180, "h264")
    assert sonda["duracion"] == pytest.approx(duracion_total(prep["g"]), abs=1 / 30 + 0.02)
    assert res["video"]["fotogramas"] == round(duracion_total(prep["g"]) * 30)
    mini = carpeta / ficha["miniatura"]
    assert Image.open(mini).size == (1280, 720)
    youtube = (carpeta / "youtube.txt").read_text(encoding="utf-8")
    url = "https://tienda.example/maquinas/mesa-de-taller"
    assert "Mesa de taller" in youtube and url in youtube and ficha["url_tienda"] == url
    # F2: el bloque youtube de ficha.json es el texto de youtube.txt, con el aviso (D8)
    yt = ficha["youtube"]
    assert yt["titulo"] == "Mesa de taller" and yt["descripcion"] in youtube
    assert "no fue construido ni probado físicamente" in yt["descripcion"]
    assert "https://tienda.example/terminos#responsabilidad" in yt["descripcion"]
    assert len(yt["descripcion"].encode("utf-8")) <= 5000
    leeme = zips["gratis"]["LEEME.md"].decode()
    assert "con observaciones" not in leeme and "Sin interferencias" in leeme

    # una versión publicada no se pisa (D14)
    with pytest.raises(PublicacionError, match="ya está publicada"):
        flujo.generar(tienda.c, tienda.verde, raiz=tienda.raiz, version="1.0.0", eco=None)
    with pytest.raises(PublicacionError, match="ya está publicada"):
        flujo.guion(tienda.c, tienda.verde, raiz=tienda.raiz, version="1.0.0", eco=None)
    with pytest.raises(PublicacionError, match="--version"):
        flujo.guion(tienda.c, tienda.verde, raiz=tienda.raiz, eco=None)


def test_la_puerta_roja_se_niega_sin_tocar_la_carpeta(tienda):
    prep = _preparar(tienda, tienda.rojo)
    antes = sorted(p.name for p in prep["carpeta"].iterdir())
    with pytest.raises(PuertaRoja, match="sujeción · sin anclajes"):
        flujo.generar(tienda.c, tienda.rojo, raiz=tienda.raiz, con_gravedad=False, eco=None)
    assert sorted(p.name for p in prep["carpeta"].iterdir()) == antes


def _pista(ruta: Path, segundos: float = 2.0) -> Path:
    """Una pista WAV (seno de 440 Hz) hecha con la stdlib."""
    import math
    import struct
    import wave

    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 22050)))
                               for i in range(int(22050 * segundos))))
    return ruta


@con_ffmpeg
def test_forzada_queda_con_observaciones_y_con_su_musica(tienda, tmp_path):
    from apolo.media.codificar import sondear
    from apolo.publicacion import ficha as fichas

    prep = _preparar(tienda, tienda.rojo)
    pista = _pista(tmp_path / "pista.wav")
    with pytest.raises(fichas.FichaError, match="faltan titulo, autor, fuente, licencia"):
        flujo.generar(tienda.c, tienda.rojo, raiz=tienda.raiz, forzar=True, musica=pista,
                      con_gravedad=False, eco=None)
    texto = prep["ficha"].read_text(encoding="utf-8")
    for clave, valor in (("titulo", "Seno"), ("autor", "Prueba"), ("fuente", "La suite"),
                         ("licencia", "CC0 1.0")):
        texto = texto.replace(f'  {clave}: ""', f'  {clave}: "{valor}"', 1)
    prep["ficha"].write_text(texto, encoding="utf-8")
    flujo.generar(tienda.c, tienda.rojo, raiz=tienda.raiz, forzar=True, musica=pista,
                  con_gravedad=False, eco=None)
    carpeta = prep["carpeta"]
    ficha = json.loads((carpeta / "ficha.json").read_text(encoding="utf-8"))
    assert ficha["estado"] == "con observaciones"
    assert any("sin anclajes" in o for o in ficha["validacion"]["observaciones"])
    for nivel in ("gratis", "completo"):
        leeme = (carpeta / nivel / "LEEME.md").read_text(encoding="utf-8")
        assert "Publicado con observaciones" in leeme and "sin anclajes" in leeme
    # la música (D8): mezclada, acreditada y sin la ruta local
    assert sondear(carpeta / "video.mp4")["audio"] and not (carpeta / "video.mudo.mp4").exists()
    assert ficha["video"]["musica"]["titulo"] == "Seno" and "archivo" not in ficha["video"]["musica"]
    assert "Música: «Seno» de Prueba (La suite) · Licencia: CC0 1.0" in \
        (carpeta / "youtube.txt").read_text(encoding="utf-8")


def test_un_texto_de_youtube_que_la_tienda_rechazaria_corta_antes_de_trabajar(tienda,
                                                                               monkeypatch):
    """Bitácora T: si el bloque youtube no cumple, la tienda lo guarda null EN SILENCIO y usa su
    texto por defecto. `generar` falla antes de la puerta y del video, sin tocar la carpeta."""
    from apolo.publicacion import textos

    prep = _preparar(tienda, tienda.verde)
    antes = sorted(p.name for p in prep["carpeta"].iterdir())
    monkeypatch.setattr(textos, "MAX_DESCRIPCION_BYTES", 100)  # el aviso solo ya no entra
    with pytest.raises(PublicacionError, match=r"bytes UTF-8 \(máximo 100") as exc:
        flujo.generar(tienda.c, tienda.verde, raiz=tienda.raiz, con_gravedad=False, eco=None)
    assert "publicar ficha --revisar" in str(exc.value)
    assert sorted(p.name for p in prep["carpeta"].iterdir()) == antes


@con_ffmpeg
def test_sin_musica_explicita_usa_la_menos_usada_de_la_biblioteca(tienda, tmp_path, monkeypatch):
    from apolo.media.codificar import sondear

    biblioteca = tmp_path / "musica"
    biblioteca.mkdir()
    _pista(biblioteca / "a.wav")
    _pista(biblioteca / "b.wav")
    (biblioteca / "pistas.json").write_text(json.dumps([
        {"archivo": n, "titulo": t, "autor": "Prueba", "fuente": "Pixabay Music",
         "licencia": "Pixabay Content License"} for n, t in (("a.wav", "Seno A"), ("b.wav", "Seno B"))
    ]), encoding="utf-8")
    (biblioteca / "usos.json").write_text('{"a.wav": 2}', encoding="utf-8")
    monkeypatch.setenv("APOLO_MUSICA_DIR", str(biblioteca))
    prep = _preparar(tienda, tienda.rojo)
    flujo.generar(tienda.c, tienda.rojo, raiz=tienda.raiz, forzar=True, con_gravedad=False,
                  eco=None)
    carpeta = prep["carpeta"]
    ficha = json.loads((carpeta / "ficha.json").read_text(encoding="utf-8"))
    assert ficha["video"]["musica"]["titulo"] == "Seno B" and sondear(carpeta / "video.mp4")["audio"]
    assert "Música: «Seno B» de Prueba (Pixabay Music)" in ficha["youtube"]["descripcion"]
    assert "b.wav" not in json.dumps(ficha)  # la ruta local no se publica
    assert json.loads((biblioteca / "usos.json").read_text(encoding="utf-8")) == \
        {"a.wav": 2, "b.wav": 1}
    # --sin-musica fuerza silencio aunque haya pistas
    r = _preparar(tienda, tienda.rojo, version="1.0.1")
    flujo.generar(tienda.c, tienda.rojo, raiz=tienda.raiz, version="1.0.1", forzar=True,
                  con_gravedad=False, sin_musica=True, eco=None)
    assert json.loads((r["carpeta"] / "ficha.json").read_text(encoding="utf-8"))["video"][
        "musica"] is None
    assert json.loads((biblioteca / "usos.json").read_text(encoding="utf-8"))["b.wav"] == 1


def test_el_guion_es_de_montaje_salvo_que_pidas_diseno(tienda):
    """D8 de video-tienda-pulido: por defecto el video sigue cómo se ARMA (las patas ancladas y
    después el tablero atornillado); `modo="diseño"` deja el guion de siempre (pasos = k)."""
    r = flujo.guion(tienda.c, tienda.verde, raiz=tienda.raiz, eco=None)
    g = json.loads(r["guion"].read_text(encoding="utf-8"))
    assert g["modo"] == "montaje"
    tandas = [f for e in g["etapas"] for t in e["pasos"] for f in t]
    nombres = [tienda.mesa.scene[f].name for f in tandas]
    assert sorted(nombres[:4]) == [f"Pata ({i})" for i in range(1, 5)] and nombres[4:] == ["Tablero"]
    r = flujo.guion(tienda.c, tienda.verde, raiz=tienda.raiz, version="1.0.1", modo="diseño",
                    eco=None)
    g = json.loads(r["guion"].read_text(encoding="utf-8"))
    assert "modo" not in g and all(isinstance(k, int) for e in g["etapas"] for k in e["pasos"])
    with pytest.raises(PublicacionError, match="Modo de video desconocido"):
        flujo.guion(tienda.c, tienda.verde, raiz=tienda.raiz, version="1.0.2", modo="armado",
                    eco=None)


def test_un_log_que_cambio_desde_el_guion_se_niega(tienda):
    prep = _preparar(tienda, tienda.verde)
    r = tienda.c.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Estante", "width": 500, "depth": 300, "height": 15,
        "position": {"x": 0, "y": 0, "z": 150}}})
    assert r.status_code == 200, r.text
    with pytest.raises(PublicacionError, match="firma del log no coincide"):
        flujo.generar(tienda.c, tienda.verde, raiz=tienda.raiz, eco=None)
    assert not (prep["carpeta"] / "ficha.json").exists()


def _cli():
    spec = importlib.util.spec_from_file_location("publicar_cli", RAIZ_REPO / "scripts" / "publicar.py")
    mod = importlib.util.module_from_spec(spec)
    import sys

    previo = sys.dont_write_bytecode
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = previo
    return mod


def test_el_cli_escribe_el_guion_y_explica_lo_que_falta(tienda, monkeypatch, capsys):
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: tienda.raiz)
    cli = _cli()
    assert cli.main(["guion", "--project", str(tienda.verde)], cliente=tienda.c) == 0
    salida = capsys.readouterr().out
    assert "la UI que tengas abierta cambia" in salida and "ficha.yaml" in salida
    assert (tienda.raiz / "mesa-de-taller" / "1.0.0" / "guion.json").is_file()
    # la ficha sigue en borrador: generar se niega y dice qué falta
    assert cli.main(["generar", "--project", str(tienda.verde)], cliente=tienda.c) == 2
    assert "descripcion: no puede quedar vacío" in capsys.readouterr().err
    # `ficha --revisar` (F2) dice lo mismo sin abrir el proyecto, y en verde imprime el texto
    assert cli.main(["ficha", "--slug", "mesa-de-taller", "--revisar"]) == 2
    assert "descripcion: no puede quedar vacío" in capsys.readouterr().err
    ruta = tienda.raiz / "mesa-de-taller" / "1.0.0" / "ficha.yaml"
    ruta.write_text(ruta.read_text(encoding="utf-8").replace(
        'descripcion: ""', 'descripcion: "Mesa de taller soldada."'), encoding="utf-8")
    assert cli.main(["ficha", "--slug", "mesa-de-taller", "--revisar"]) == 2
    assert "etiquetas: vacía" in capsys.readouterr().err
    ruta.write_text(ruta.read_text(encoding="utf-8").replace(
        "etiquetas: []", 'etiquetas: ["mesa", "taller", "mesa de trabajo"]'), encoding="utf-8")
    assert cli.main(["ficha", "--slug", "mesa-de-taller", "--revisar"]) == 0
    salida = capsys.readouterr().out
    assert "https://apolocad.com/maquinas/mesa-de-taller" in salida
    assert "Diseño generado y validado por software" in salida
    assert "ficha.yaml lista para `publicar generar`" in salida
