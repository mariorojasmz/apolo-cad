"""Codificación del video con ffmpeg (`apolo.media.codificar`, plan publicacion-tienda F3,
D7 y D8).

ffmpeg es un binario externo: los tests que codifican se SALTAN si no está (en el CI de
Linux se instala con apt para que corran). Los que no lo necesitan —el error claro cuando
falta y el tamaño impar— corren siempre.

Clips sintéticos y chicos (320×180, 2 s): la suite entera tarda ~1 s.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from apolo.media import codificar as k


def _hay_ffmpeg() -> bool:
    try:
        k.buscar_ffmpeg()
        k.buscar_ffprobe()
    except k.FfmpegNoEncontrado:
        return False
    return True


con_ffmpeg = pytest.mark.skipif(not _hay_ffmpeg(), reason="ffmpeg no está instalado")


def _fotograma(i: int, ancho: int = 320, alto: int = 180):
    Image = pytest.importorskip("PIL.Image")
    return Image.new("RGB", (ancho, alto), (i * 4 % 256, 60, 200 - i % 200))


def _clip(ruta, segundos: float = 2.0, ancho: int = 320, alto: int = 180, fps: int = 30):
    with k.Codificador(ruta, ancho, alto, fps=fps) as cod:
        for i in range(round(segundos * fps)):
            cod.escribir(_fotograma(i, ancho, alto))
    return ruta


def _tono(ruta, segundos: float):
    """Una «pista» generada por el propio ffmpeg: un seno de 440 Hz, mono."""
    subprocess.run([k.buscar_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}", str(ruta)],
                   check=True)
    return ruta


def _volumen_medio(ruta, desde: float, durante: float) -> float:
    res = subprocess.run([k.buscar_ffmpeg(), "-hide_banner", "-nostats", "-ss", str(desde),
                          "-t", str(durante), "-i", str(ruta), "-map", "0:a",
                          "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True)
    return float(re.findall(r"mean_volume: (-?[\d.]+|-inf) dB", res.stderr)[-1])


# ── Sin ffmpeg ────────────────────────────────────────────────────────────────


def test_sin_ffmpeg_el_error_dice_como_instalarlo(monkeypatch):
    monkeypatch.delenv(k.ENV_FFMPEG, raising=False)
    monkeypatch.setattr(k.shutil, "which", lambda nombre: None)
    for buscar in (k.buscar_ffmpeg, k.buscar_ffprobe):
        with pytest.raises(k.FfmpegNoEncontrado) as err:
            buscar()
        texto = str(err.value)
        assert "Instala ffmpeg" in texto and k.ENV_FFMPEG in texto and "apt" in texto


def test_apolo_ffmpeg_que_no_existe_no_cae_al_path(monkeypatch, tmp_path):
    monkeypatch.setenv(k.ENV_FFMPEG, str(tmp_path / "no" / "ffmpeg.exe"))
    monkeypatch.setattr(k.shutil, "which", lambda nombre: "/usr/bin/" + nombre)
    with pytest.raises(k.FfmpegNoEncontrado, match="no apunta"):
        k.buscar_ffmpeg()


def test_apolo_ffmpeg_acepta_el_archivo_o_su_carpeta(monkeypatch, tmp_path):
    ext = ".exe" if k.os.name == "nt" else ""
    (tmp_path / f"ffmpeg{ext}").write_bytes(b"")
    (tmp_path / f"ffprobe{ext}").write_bytes(b"")
    for valor in (tmp_path / f"ffmpeg{ext}", tmp_path):
        monkeypatch.setenv(k.ENV_FFMPEG, str(valor))
        assert k.buscar_ffmpeg() == str(tmp_path / f"ffmpeg{ext}")
        assert k.buscar_ffprobe() == str(tmp_path / f"ffprobe{ext}")


@pytest.mark.parametrize("ancho, alto", [(321, 180), (320, 181), (0, 180)])
def test_un_tamano_impar_se_rechaza_antes_de_lanzar_ffmpeg(ancho, alto, tmp_path):
    with pytest.raises(ValueError, match="pares"):
        k.Codificador(tmp_path / "x.mp4", ancho, alto)
    assert not list(tmp_path.iterdir())


# ── Con ffmpeg ────────────────────────────────────────────────────────────────


@con_ffmpeg
def test_codifica_h264_high_yuv420p_mudo(tmp_path):
    ruta = _clip(tmp_path / "clip.mp4")
    info = k.sondear(ruta)
    assert info["codec"] == "h264" and info["perfil"] == "High"
    assert info["pix_fmt"] == "yuv420p" and info["color"] == "bt709"
    assert (info["ancho"], info["alto"]) == (320, 180)
    assert info["fps"] == pytest.approx(30)
    assert info["fotogramas"] == 60
    assert info["duracion"] == pytest.approx(60 / 30, abs=0.05)
    assert info["audio"] is False and info["codec_audio"] is None
    datos = ruta.read_bytes()
    assert datos.index(b"moov") < datos.index(b"mdat"), "sin +faststart"
    assert not list(tmp_path.glob("*.parcial*"))


@con_ffmpeg
def test_acepta_arreglos_numpy_del_render(tmp_path):
    np = pytest.importorskip("numpy")
    with k.Codificador(tmp_path / "np.mp4", 64, 36, fps=10) as cod:
        for i in range(10):
            cod.escribir(np.full((36, 64, 3), i * 20, dtype=np.uint8))
        with pytest.raises(ValueError, match="uint8"):
            cod.escribir(np.zeros((36, 64, 3), dtype=np.float32))
    assert k.sondear(tmp_path / "np.mp4")["fotogramas"] == 10


@con_ffmpeg
def test_un_fotograma_de_otro_tamano_aborta_sin_dejar_archivo(tmp_path):
    salida = tmp_path / "roto.mp4"
    with pytest.raises(ValueError, match="mide 640×360"):
        with k.Codificador(salida, 320, 180) as cod:
            cod.escribir(_fotograma(0))
            cod.escribir(_fotograma(1, 640, 360))
    assert not list(tmp_path.iterdir()), "quedó un MP4 a medias"


@con_ffmpeg
def test_un_error_no_pisa_el_video_bueno_anterior(tmp_path):
    salida = _clip(tmp_path / "video.mp4")
    antes = salida.read_bytes()
    with pytest.raises(RuntimeError, match="a mitad"):
        with k.Codificador(salida, 320, 180) as cod:
            cod.escribir(_fotograma(0))
            raise RuntimeError("falló el render a mitad")
    assert salida.read_bytes() == antes
    assert [p.name for p in tmp_path.iterdir()] == ["video.mp4"]


@con_ffmpeg
def test_sin_fotogramas_no_hay_video(tmp_path):
    with pytest.raises(ValueError, match="ningún fotograma"):
        with k.Codificador(tmp_path / "vacio.mp4", 320, 180):
            pass
    assert not list(tmp_path.iterdir())


@con_ffmpeg
def test_si_ffmpeg_falla_el_error_trae_su_stderr(tmp_path):
    with pytest.raises(k.ErrorCodificacion, match="nope"):
        with k.Codificador(tmp_path / "malo.mp4", 320, 180, preset="nope") as cod:
            for i in range(30):
                cod.escribir(_fotograma(i))
    assert not list(tmp_path.iterdir())


@con_ffmpeg
def test_la_musica_corta_entra_en_bucle_hasta_el_final(tmp_path):
    video = _clip(tmp_path / "mudo.mp4")
    tono = _tono(tmp_path / "tono.wav", 0.7)  # más corta que el video: tiene que repetirse
    final = k.mezclar_musica(video, tono, tmp_path / "final.mp4")
    info = k.sondear(final)
    assert info["audio"] and info["codec_audio"] == "aac"
    assert info["frecuencia_audio"] == 48000 and info["canales"] == 2
    assert info["duracion"] == pytest.approx(2.0, abs=0.1)
    assert info["duracion_audio"] == pytest.approx(2.0, abs=0.1), "el bucle no cubrió el video"
    assert info["codec"] == "h264" and info["fotogramas"] == 60  # el video se copió tal cual
    assert k.sondear(video)["audio"] is False  # el mudo queda como estaba


@con_ffmpeg
def test_la_musica_se_funde_al_final_y_queda_cerca_de_menos_14_lufs(tmp_path):
    video = _clip(tmp_path / "mudo.mp4", segundos=8, ancho=64, alto=36)
    final = k.mezclar_musica(video, _tono(tmp_path / "tono.wav", 1.5), tmp_path / "final.mp4")
    medio, cola = _volumen_medio(final, 4.0, 0.3), _volumen_medio(final, 7.8, 0.2)
    assert cola < medio - 15, f"sin fundido de salida: medio {medio} dB, cola {cola} dB"
    res = subprocess.run([k.buscar_ffmpeg(), "-hide_banner", "-nostats", "-i", str(final),
                          "-map", "0:a", "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True)
    integrada = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", res.stderr)[-1])
    assert -17 < integrada < -13, integrada  # −14 menos lo que restan los fundidos


@con_ffmpeg
def test_mezclar_rechaza_pisar_el_video_y_la_pista_que_falta(tmp_path):
    video = _clip(tmp_path / "mudo.mp4", segundos=0.5)
    with pytest.raises(FileNotFoundError, match="la música"):
        k.mezclar_musica(video, tmp_path / "no.mp3", tmp_path / "final.mp4")
    with pytest.raises(ValueError, match="otro archivo"):
        k.mezclar_musica(video, _tono(tmp_path / "t.wav", 0.3), video)


def test_los_fundidos_se_reparten_en_un_video_corto():
    assert k._fundidos(60, 1, 3) == (1, 3)
    entrada, salida = k._fundidos(2, 1, 3)
    assert entrada + salida == pytest.approx(2) and salida == pytest.approx(3 * entrada)
