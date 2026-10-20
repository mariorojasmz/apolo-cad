"""Grabación del video desde el visor (plan video-realista, F2/D4): `POST /api/video/grabacion`
abre una sesión, `…/{sesion}/cuadro/{n}` sube cada cuadro y `…/{sesion}/cerrar` codifica con
`media/codificar.py`.

Los tests que codifican usan el ffmpeg real (PATH o `APOLO_FFMPEG`) y se SALTAN si no está, como
los de `test_media_codificar.py`. Cuadros sintéticos y chicos (64×36): cada cuadro lleva un color
propio para comprobar, al decodificar el MP4, que salieron en orden.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api.routers import video as rv
from apolo.media import codificar as k
from apolo.media import grabacion as g

Image = pytest.importorskip("PIL.Image")

ANCHO, ALTO = 64, 36


def _hay_ffmpeg() -> bool:
    try:
        k.buscar_ffmpeg()
        k.buscar_ffprobe()
    except k.FfmpegNoEncontrado:
        return False
    return True


con_ffmpeg = pytest.mark.skipif(not _hay_ffmpeg(), reason="ffmpeg no está instalado")


def _color(n: int) -> tuple[int, int, int]:
    """Colores bien separados (el H.264 los mueve unos pocos niveles)."""
    return (40 + 50 * (n % 4), 40 + 60 * (n // 4 % 3), 200 - 30 * (n % 5))


def _cuadro(n: int, formato: str = "jpeg", ancho: int = ANCHO, alto: int = ALTO) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), _color(n)).save(buf, format=formato.upper(), quality=95)
    return buf.getvalue()


@pytest.fixture
def grab(tmp_path, monkeypatch):
    """Un almacén de grabaciones en una carpeta temporal y un cliente de la API."""
    almacen = g.Grabaciones(tmp_path / "grabaciones")
    monkeypatch.setattr(rv, "GRABACIONES", almacen)
    return TestClient(api.app), almacen


def _abrir(c, **kw) -> str:
    r = c.post("/api/video/grabacion", json={"ancho": ANCHO, "alto": ALTO, **kw})
    assert r.status_code == 200, r.text
    return r.json()["sesion"]


def _subir(c, sesion: str, n: int, datos: bytes | None = None, formato: str = "jpeg"):
    return c.post(f"/api/video/grabacion/{sesion}/cuadro/{n}",
                  content=datos if datos is not None else _cuadro(n, formato),
                  headers={"Content-Type": f"image/{formato}"})


def _colores_del_video(ruta: Path) -> list[tuple[float, float, float]]:
    """El color medio de cada fotograma del MP4, en orden."""
    crudo = subprocess.run([k.buscar_ffmpeg(), "-hide_banner", "-loglevel", "error", "-i",
                            str(ruta), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           capture_output=True, check=True).stdout
    tam = ANCHO * ALTO * 3
    out = []
    for i in range(len(crudo) // tam):
        trozo = crudo[i * tam:(i + 1) * tam]
        out.append(tuple(sum(trozo[c::3]) / (ANCHO * ALTO) for c in range(3)))
    return out


# ── Abrir ─────────────────────────────────────────────────────────────────────


def test_abrir_da_la_sesion_el_disco_estimado_y_el_libre(grab):
    c, almacen = grab
    r = c.post("/api/video/grabacion", json={"ancho": ANCHO, "alto": ALTO, "fps": 30,
                                              "cuadros": 90})
    d = r.json()
    assert r.status_code == 200 and d["estado"] == "abierta" and d["recibidos"] == 0
    assert d["estimado_bytes"] == g.estimar_bytes(ANCHO, ALTO, "jpeg", 90)
    assert d["espacio_libre_bytes"] > 0 and "aviso" not in d
    assert (almacen.raiz / d["sesion"] / "cuadros").is_dir()


def test_los_defaults_son_1080p_a_30_fps_en_jpeg(grab):
    c, _ = grab
    d = c.post("/api/video/grabacion").json()
    assert (d["ancho"], d["alto"], d["fps"], d["formato"]) == (1920, 1080, 30, "jpeg")
    # sin cuadros declarados se estima un minuto
    assert d["estimado_bytes"] == g.estimar_bytes(1920, 1080, "jpeg", 30 * 60)


@pytest.mark.parametrize("cuerpo, texto", [
    ({"ancho": 63, "alto": 36}, "pares"),
    ({"ancho": 7680, "alto": 4320}, "3840×2160"),
    ({"fps": 0}, "cuadros por segundo"),
    ({"cuadros": 0}, "de 1 a"),
])
def test_abrir_rechaza_parametros_que_no_sirven(grab, cuerpo, texto):
    c, _ = grab
    r = c.post("/api/video/grabacion", json=cuerpo)
    assert r.status_code == 400 and texto in r.json()["detail"]


def test_sin_disco_se_niega_y_con_poco_avisa(grab, monkeypatch):
    c, _ = grab
    necesita = g.estimar_bytes(1920, 1080, "png", 1800)
    monkeypatch.setattr(g, "_libre", lambda carpeta: necesita // 2)
    r = c.post("/api/video/grabacion", json={"formato": "png", "cuadros": 1800})
    assert r.status_code == 507 and "Libera espacio" in r.json()["detail"]
    monkeypatch.setattr(g, "_libre", lambda carpeta: int(necesita * 1.5))
    d = c.post("/api/video/grabacion", json={"formato": "png", "cuadros": 1800}).json()
    assert "se borran al terminar" in d["aviso"]


# ── Cuadros ───────────────────────────────────────────────────────────────────


def test_los_cuadros_llegan_desordenados_y_se_cuentan(grab):
    c, almacen = grab
    s = _abrir(c, cuadros=3)
    for n in (2, 0, 1):
        r = _subir(c, s, n)
        assert r.status_code == 200 and r.json()["cuadro"] == n
    assert c.get(f"/api/video/grabacion/{s}").json()["recibidos"] == 3
    archivos = sorted(p.name for p in (almacen.raiz / s / "cuadros").iterdir())
    assert archivos == ["000000.jpg", "000001.jpg", "000002.jpg"]  # sin .parcial


def test_un_cuadro_repetido_es_un_error_del_reloj(grab):
    c, _ = grab
    s = _abrir(c)
    assert _subir(c, s, 0).status_code == 200
    r = _subir(c, s, 0)
    assert r.status_code == 409 and "repitió" in r.json()["detail"]


@pytest.mark.parametrize("n, datos, texto", [
    (5, None, "fuera de la grabación"),
    (-1, None, "fuera de la grabación"),
    (0, b"no soy una imagen", "no es una imagen"),
    (0, "png", "espera JPEG"),
    (0, "grande", "mide 128×72"),
])
def test_un_cuadro_malo_dice_que_le_pasa(grab, n, datos, texto):
    c, almacen = grab
    s = _abrir(c, cuadros=5)
    if datos == "png":
        datos = _cuadro(0, "png")
    elif datos == "grande":
        datos = _cuadro(0, "jpeg", ANCHO * 2, ALTO * 2)
    r = _subir(c, s, n, datos)
    assert r.status_code == 400 and texto in r.json()["detail"]
    assert c.get(f"/api/video/grabacion/{s}").json()["recibidos"] == 0
    assert not list((almacen.raiz / s / "cuadros").iterdir())  # nada a medias


def test_una_sesion_que_no_existe_da_404(grab):
    c, _ = grab
    assert _subir(c, "nohay", 0).status_code == 404
    assert c.get("/api/video/grabacion/nohay").status_code == 404
    r = c.post("/api/video/grabacion/nohay/cerrar")
    assert r.status_code == 404 and "Abre una nueva" in r.json()["detail"]


# ── Cerrar ────────────────────────────────────────────────────────────────────


def test_cerrar_con_un_cuadro_faltante_dice_cual(grab):
    c, _ = grab
    s = _abrir(c, cuadros=5)
    for n in (0, 1, 3):
        _subir(c, s, n)
    r = c.post(f"/api/video/grabacion/{s}/cerrar")
    assert r.status_code == 400
    assert "Faltan 2 de 5 cuadros (2, 4)" in r.json()["detail"]
    assert c.get(f"/api/video/grabacion/{s}").json()["estado"] == "abierta"  # se puede seguir


def test_sin_cuadros_declarados_el_hueco_tambien_se_ve(grab):
    c, _ = grab
    s = _abrir(c)
    for n in (0, 2):
        _subir(c, s, n)
    r = c.post(f"/api/video/grabacion/{s}/cerrar")
    assert r.status_code == 400 and "Faltan 1 de 3 cuadros (1)" in r.json()["detail"]


def test_cerrar_sin_cuadros_no_arma_nada(grab):
    c, _ = grab
    r = c.post(f"/api/video/grabacion/{_abrir(c)}/cerrar")
    assert r.status_code == 400 and "ningún cuadro" in r.json()["detail"]


def test_cerrar_rechaza_una_salida_que_no_es_mp4_y_una_musica_que_no_existe(grab, tmp_path):
    c, _ = grab
    s = _abrir(c, cuadros=1)
    _subir(c, s, 0)
    r = c.post(f"/api/video/grabacion/{s}/cerrar", json={"salida": str(tmp_path / "v.avi")})
    assert r.status_code == 400 and ".mp4" in r.json()["detail"]
    r = c.post(f"/api/video/grabacion/{s}/cerrar", json={"musica": str(tmp_path / "no.mp3")})
    assert r.status_code == 400 and "música" in r.json()["detail"]


def test_sin_ffmpeg_el_cierre_dice_como_instalarlo(grab, monkeypatch):
    c, _ = grab
    monkeypatch.delenv(k.ENV_FFMPEG, raising=False)
    monkeypatch.setattr(k.shutil, "which", lambda nombre: None)
    s = _abrir(c, cuadros=1)
    _subir(c, s, 0)
    r = c.post(f"/api/video/grabacion/{s}/cerrar")
    assert r.status_code == 503 and "winget install" in r.json()["detail"]
    estado = c.get(f"/api/video/grabacion/{s}").json()
    assert estado["estado"] == "error" and estado["recibidos"] == 1  # los cuadros siguen ahí


@con_ffmpeg
def test_cerrar_codifica_en_orden_y_borra_los_cuadros(grab):
    c, almacen = grab
    total = 12
    s = _abrir(c, fps=24, cuadros=total)
    for n in reversed(range(total)):  # al revés: el orden lo da el número, no la llegada
        assert _subir(c, s, n).status_code == 200
    r = c.post(f"/api/video/grabacion/{s}/cerrar")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["estado"] == "lista"
    inf = d["informe"]
    video = Path(inf["video"])
    assert video == almacen.raiz / s / "video.mp4" and video.is_file()
    assert inf["cuadros"] == total and inf["duracion_s"] == pytest.approx(0.5)
    assert inf["bytes_video"] == video.stat().st_size and inf["con_musica"] is False
    meta = k.sondear(video)
    assert (meta["codec"], meta["ancho"], meta["alto"]) == ("h264", ANCHO, ALTO)
    assert meta["fotogramas"] == total and meta["fps"] == pytest.approx(24)
    assert meta["color"] == "bt709" and meta["audio"] is False
    colores = _colores_del_video(video)
    assert len(colores) == total
    for n, medio in enumerate(colores):
        assert all(abs(a - b) < 12 for a, b in zip(medio, _color(n))), (n, medio, _color(n))
    assert not (almacen.raiz / s / "cuadros").exists(), "los cuadros no se borraron"
    assert c.get(f"/api/video/grabacion/{s}").json()["informe"]["video"] == str(video)
    # cerrada: ni más cuadros ni otro cierre
    assert _subir(c, s, 0).status_code == 409
    assert c.post(f"/api/video/grabacion/{s}/cerrar").status_code == 409


@con_ffmpeg
def test_los_png_y_la_salida_elegida_y_conservar_los_cuadros(grab, tmp_path):
    c, almacen = grab
    s = _abrir(c, formato="png", cuadros=3)
    for n in range(3):
        assert _subir(c, s, n, formato="png").status_code == 200
    salida = tmp_path / "otra" / "maquina.mp4"
    r = c.post(f"/api/video/grabacion/{s}/cerrar",
               json={"salida": str(salida), "conservar_cuadros": True})
    inf = r.json()["informe"]
    assert inf["video"] == str(salida) and k.sondear(salida)["fotogramas"] == 3
    assert len(list((almacen.raiz / s / "cuadros").glob("*.png"))) == 3
    assert inf["cuadros_conservados"] == str(almacen.raiz / s / "cuadros")


@con_ffmpeg
def test_cerrar_con_musica_la_mezcla_y_no_deja_el_mudo(grab, tmp_path):
    c, almacen = grab
    tono = tmp_path / "tono.wav"
    subprocess.run([k.buscar_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=0.4", str(tono)], check=True)
    s = _abrir(c, fps=30, cuadros=30)
    for n in range(30):
        _subir(c, s, n)
    inf = c.post(f"/api/video/grabacion/{s}/cerrar", json={"musica": str(tono)}).json()["informe"]
    assert inf["con_musica"] is True
    meta = k.sondear(inf["video"])
    assert meta["audio"] and meta["codec_audio"] == "aac" and meta["frecuencia_audio"] == 48000
    assert meta["duracion_audio"] == pytest.approx(1.0, abs=0.1)  # la pista corta, en bucle
    assert not (almacen.raiz / s / "video.mudo.mp4").exists()


# ── Descartar ─────────────────────────────────────────────────────────────────


def test_descartar_borra_los_cuadros_y_olvida_la_sesion(grab):
    c, almacen = grab
    s = _abrir(c, cuadros=2)
    _subir(c, s, 0)
    r = c.delete(f"/api/video/grabacion/{s}")
    assert r.status_code == 200 and r.json()["descartada"] is True
    assert not (almacen.raiz / s).exists()
    assert c.get(f"/api/video/grabacion/{s}").status_code == 404


@con_ffmpeg
def test_descartar_una_sesion_lista_deja_el_video(grab):
    c, almacen = grab
    s = _abrir(c, cuadros=2)
    for n in range(2):
        _subir(c, s, n)
    video = Path(c.post(f"/api/video/grabacion/{s}/cerrar").json()["informe"]["video"])
    assert c.delete(f"/api/video/grabacion/{s}").status_code == 200
    assert video.is_file()


def test_durante_la_codificacion_no_se_descarta_ni_se_sube(grab):
    _, almacen = grab
    d = almacen.abrir(ancho=ANCHO, alto=ALTO, cuadros=1)
    almacen._sesiones[d["sesion"]].estado = "codificando"
    with pytest.raises(g.Conflicto, match="codificando"):
        almacen.descartar(d["sesion"])
    with pytest.raises(g.Conflicto, match="ya no recibe"):
        almacen.guardar_cuadro(d["sesion"], 0, _cuadro(0))


# ── Frontera ──────────────────────────────────────────────────────────────────


def test_la_grabacion_es_e_s_pura_sin_el_documento():
    """D4: ni `STATE_LOCK` ni el documento; el router sólo habla con `media/grabacion.py` (y las
    tarjetas del guion, F3). Lo que lee la escena vive aparte, en `video_guion.py`."""
    raiz = Path(__file__).resolve().parents[1] / "core" / "apolo"
    for archivo in (raiz / "api" / "routers" / "video.py", raiz / "media" / "grabacion.py",
                    raiz / "media" / "tarjetas.py", raiz / "media" / "contraste.py"):
        codigo = archivo.read_text(encoding="utf-8")
        for prohibido in ("import STATE_LOCK", "apolo.state", "S.doc", "..session"):
            assert prohibido not in codigo, f"{archivo.name} usa {prohibido}"


def test_faltantes():
    assert g.faltantes({0, 1, 2}, None) == (3, [])
    assert g.faltantes({0, 2}, None) == (3, [1])
    assert g.faltantes({0, 1}, 4) == (4, [2, 3])
    assert g.faltantes(set(), None) == (0, [])
