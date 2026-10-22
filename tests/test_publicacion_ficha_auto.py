"""Ficha y textos automáticos (plan fabrica-de-publicaciones, F2): los límites de YouTube que
valida la tienda, la URL derivada, el aviso de responsabilidad (D8), la biblioteca de música
(D9), la miniatura con el título legible y el cierre del video. Sin API ni ffmpeg: lo de punta a
punta está en `test_publicacion_e2e.py`."""

from __future__ import annotations

import json

import pytest
import yaml
from PIL import Image

from apolo.media import composicion as comp
from apolo.media import tarjetas
from apolo.publicacion import ficha as F
from apolo.publicacion import musica, preparar, textos
from apolo.publicacion.paquete import PublicacionError

TIENDA = "https://apolocad.com"


def _ficha(**cambios) -> dict:
    f = yaml.safe_load(F.borrador("Transportador de rodillos", "transportador-de-rodillos", "1.0.0"))
    f["descripcion"] = "Transportador de rodillos por gravedad de 3 m."
    f.update(cambios)
    return f


# ------------------------------------------------------------------ límites de la tienda (T)
def test_caracteres_como_javascript_y_descripcion_en_bytes():
    assert textos.largo("ñandú") == 5 and textos.largo("🙂") == 2  # UTF-16, como `length`
    d = {"titulo": "x" * 100, "descripcion": "á" * 2500, "etiquetas": []}
    assert textos.problemas_youtube(d) == []  # 2500 caracteres = 5000 bytes: entra justo
    d["descripcion"] += "a"
    assert "pesa 5001 bytes UTF-8 (máximo 5000" in textos.problemas_youtube(d)[0]
    d = {"titulo": "🙂" * 51, "descripcion": "", "etiquetas": []}
    assert "título: tiene 102 caracteres" in textos.problemas_youtube(d)[0]
    assert "título: vacío" in textos.problemas_youtube({**d, "titulo": "  "})[0]


def test_etiquetas_con_espacios_suman_sus_comillas():
    assert textos.largo_etiquetas(["a", "bc"]) == 1 + 2 + 1  # una coma entre las dos
    assert textos.largo_etiquetas(["mesa de taller"]) == 14 + 2  # las comillas
    assert textos.largo_etiquetas([]) == 0
    justas = ["x" * 49] * 10  # 490 + 9 comas = 499
    assert textos.problemas_youtube({"titulo": "T", "descripcion": "", "etiquetas": justas}) == []
    con_espacio = ["x" * 48 + " y"] * 10  # 50 + 2 comillas cada una + 9 comas = 529
    msg = textos.problemas_youtube({"titulo": "T", "descripcion": "", "etiquetas": con_espacio})
    assert "etiquetas: suman 529" in msg[0]


def test_angulos_en_cualquier_campo():
    msg = textos.problemas_youtube({"titulo": "a<b", "descripcion": "c>d",
                                    "etiquetas": ["ok", "<x>"]})
    assert [m.split(":")[0] for m in msg] == ["título", "descripción", "etiqueta «<x>»"]


def test_la_ficha_cuenta_como_youtube():
    F.validar(_ficha(descripcion="á" * 1500))  # 3000 bytes: el tope
    with pytest.raises(F.FichaError, match=r"descripcion: tiene 3002 bytes UTF-8"):
        F.validar(_ficha(descripcion="á" * 1501))
    with pytest.raises(F.FichaError, match="etiquetas: suman 539"):
        F.validar(_ficha(etiquetas=["abcdefghijklmnopqrstuvwxy z"] * 18))  # (27+2) ×18 + 17
    # url_tienda ya no es obligatoria (se deriva), pero una de antes se acepta
    f = _ficha()
    assert "url_tienda" not in f
    F.validar(f)
    F.validar(_ficha(url_tienda="https://apolocad.com/maquinas/transportador-de-rodillos"))


# ------------------------------------------------------------------ texto de YouTube (D1, D8)
def test_la_descripcion_lleva_la_url_derivada_y_el_aviso():
    d = textos.datos_youtube(_ficha(etiquetas=["rodillos"]), [], tienda="https://tienda.example/")
    assert ("Descarga los planos y el modelo 3D: "
            "https://tienda.example/maquinas/transportador-de-rodillos") in d["descripcion"]
    assert ("Diseño generado y validado por software: no fue construido ni probado físicamente. "
            "Antes de fabricar, lee el aviso: https://tienda.example/terminos#responsabilidad"
            ) in d["descripcion"]
    assert d["etiquetas"] == ["rodillos"] and d["titulo"] == "Transportador de rodillos"


def test_datos_youtube_falla_con_todos_los_problemas():
    with pytest.raises(ValueError) as exc:
        textos.datos_youtube(_ficha(descripcion="ñ" * 2600, titulo="x" * 101), [])
    msg = str(exc.value)
    assert "título: tiene 101" in msg and "bytes UTF-8" in msg and "texto por defecto" in msg
    with pytest.raises(PublicacionError, match="publicar ficha --revisar"):
        preparar.bloque_youtube(_ficha(titulo="x" * 101), [], None, TIENDA)


def test_url_escrita_a_mano_que_no_coincide_se_avisa():
    avisos: list[str] = []
    f = preparar.con_url(_ficha(url_tienda="https://otra.example/x"), TIENDA, avisos.append)
    assert f["url_tienda"] == "https://apolocad.com/maquinas/transportador-de-rodillos"
    assert len(avisos) == 1 and "uso la derivada" in avisos[0]
    avisos.clear()
    preparar.con_url(_ficha(url_tienda=f["url_tienda"] + "/"), TIENDA, avisos.append)
    preparar.con_url(_ficha(), TIENDA, avisos.append)
    assert avisos == []


def test_el_video_usa_el_titulo_de_la_ficha_y_la_url_derivada():
    g = {"titulo": "transportador-de-rodillos", "documento": {"nombre": "transportador-de-rodillos"},
         "cierre": {"texto": "Descarga", "url": "", "duracion_s": 5.0}}
    f = preparar.con_url(_ficha(), TIENDA)
    v = preparar.guion_para_video(g, f)
    assert v["titulo"] == "Transportador de rodillos" and g["titulo"] == "transportador-de-rodillos"
    assert v["cierre"]["url"] == f["url_tienda"]
    # un título editado a mano en el guion se respeta
    g["titulo"] = "Mi transportador"
    assert preparar.guion_para_video(g, f)["titulo"] == "Mi transportador"


# ------------------------------------------------------------------ biblioteca de música (D9)
def _biblioteca(dir_, *nombres, usos=None):
    dir_.mkdir(exist_ok=True)
    for n in nombres:
        (dir_ / n).write_bytes(b"RIFF")
    (dir_ / musica.PISTAS).write_text(json.dumps([
        {"archivo": n, "titulo": n.upper(), "autor": "A", "fuente": "Pixabay Music",
         "licencia": "Pixabay Content License"} for n in nombres]), encoding="utf-8-sig")
    if usos is not None:
        (dir_ / musica.USOS).write_text(json.dumps(usos), encoding="utf-8")
    return dir_


def test_elige_la_menos_usada_y_anota_el_uso(tmp_path):
    dir_ = _biblioteca(tmp_path / "m", "a.mp3", "b.mp3", "c.mp3", usos={"a.mp3": 1, "b.mp3": 1})
    assert musica.elegir(dir_)["archivo"] == "c.mp3"
    musica.anotar_uso(dir_, "c.mp3")
    musica.anotar_uso(dir_, "c.mp3")
    assert musica.elegir(dir_)["archivo"] == "a.mp3"  # a igualdad, la primera de la lista
    assert musica.usos(dir_) == {"a.mp3": 1, "b.mp3": 1, "c.mp3": 2}
    assert json.loads((dir_ / musica.PISTAS).read_text(encoding="utf-8-sig"))[0]["archivo"] == \
        "a.mp3"  # pistas.json no se reescribe


def test_una_biblioteca_rota_dice_todo_lo_que_falta(tmp_path):
    dir_ = tmp_path / "m"
    dir_.mkdir()
    (dir_ / "x.mp3").write_bytes(b"ID3")
    (dir_ / musica.PISTAS).write_text(json.dumps([
        {"archivo": "no.mp3", "titulo": "T", "autor": "A", "fuente": "F", "licencia": "L"},
        {"archivo": "x.mp3", "titulo": "T", "autor": "A"},
        {"archivo": "x.mp3", "titulo": "T", "autor": "A", "fuente": "F", "licencia": "L",
         "precio": 1}]), encoding="utf-8")
    with pytest.raises(musica.MusicaError) as exc:
        musica.pistas(dir_)
    msg = str(exc.value)
    assert "3 problemas" in msg and "no encuentro" in msg and "faltan fuente, licencia" in msg
    assert "clave desconocida «precio»" in msg
    assert musica.elegir(tmp_path / "vacia") is None  # sin pistas.json: no hay pistas


def test_que_musica_suena(tmp_path):
    dir_ = _biblioteca(tmp_path / "m", "a.mp3")
    avisos: list[str] = []
    f, pista, de_bib = preparar.elegir_musica(_ficha(), eco=avisos.append, dir_musica=dir_)
    assert pista == (dir_ / "a.mp3").resolve() and de_bib["archivo"] == "a.mp3"
    assert f["musica"]["titulo"] == "A.MP3" and F.musica_publica(f)["licencia"]
    F.validar(f, con_musica=True)  # la biblioteca la deja completa
    assert "la menos usada de la biblioteca (0 usos)" in avisos[0]
    # --musica gana; la de ficha.yaml también; --sin-musica fuerza silencio
    assert preparar.elegir_musica(_ficha(), "x.wav", dir_musica=dir_)[1].name == "x.wav"
    propia = _ficha()
    propia["musica"]["archivo"] = "propia.wav"
    assert preparar.elegir_musica(propia, dir_musica=dir_)[1].name == "propia.wav"
    assert preparar.elegir_musica(_ficha(), sin_musica=True, dir_musica=dir_)[1:] == (None, None)
    with pytest.raises(PublicacionError, match="no van juntos"):
        preparar.elegir_musica(_ficha(), "x.wav", sin_musica=True)
    # sin pistas: sin música, y lo dice
    avisos.clear()
    assert preparar.elegir_musica(_ficha(), eco=avisos.append,
                                  dir_musica=tmp_path / "nada")[1] is None
    assert "sale SIN música" in avisos[0]


def test_la_carpeta_de_la_biblioteca(tmp_path, monkeypatch):
    assert musica.carpeta({"APOLO_MUSICA_DIR": str(tmp_path)}) == tmp_path
    monkeypatch.setenv("APOLO_HOME", str(tmp_path / "home"))
    assert musica.carpeta({}) == tmp_path / "home" / "musica"


# ------------------------------------------------------------------ miniatura y cierre (D8)
@pytest.mark.parametrize("titulo", [
    "Mesa",
    "Transportador de rodillos motorizado por cadena de 2 m",
    "Clasificadora manual de paquetería con doce puestos, cuarenta bandejas y banda central "
    "de 6 m",
])
def test_la_miniatura_lleva_el_titulo_entero(titulo):
    assert len(titulo) <= 100
    escala, lineas = comp.maquetar_miniatura(titulo)
    assert " ".join(lineas).split() == titulo.split() and comp.ELIPSIS not in "".join(lineas)
    assert len(lineas) <= (2 if escala > 1.0 else 3)
    im = comp.miniatura(Image.new("RGB", (800, 600), (90, 90, 90)), titulo)
    assert im.size == comp.TAM_MINIATURA


def test_la_miniatura_corta_usa_letra_grande():
    assert comp.maquetar_miniatura("Mesa")[0] == comp.ESCALAS_MINIATURA[0]


def test_el_cierre_lleva_el_aviso_en_los_dos_renders():
    sin = comp.cierre("Descarga", "https://apolocad.com/maquinas/x", aviso="")
    con = comp.cierre("Descarga", "https://apolocad.com/maquinas/x")
    assert sin.tobytes() != con.tobytes()
    assert "no fue construido ni probado" in comp.AVISO_CIERRE
    # el navegador pide la misma tarjeta a `tarjetas` (la dibuja `cierre` con su aviso)
    g = {"cierre": {"texto": "Descarga", "url": "https://apolocad.com/maquinas/x"}}
    png = tarjetas.tarjeta(g, "cierre", 1920, 1080)
    assert png == tarjetas._png(con)
