"""La ficha de tienda (`ficha.yaml`) de una publicación: borrador, lectura y validación (plan
publicacion-tienda, F4 · D8, D9, D14 y D15)."""

from __future__ import annotations

import pytest
import yaml

from apolo.publicacion import ficha as F


def _ficha(**cambios) -> dict:
    f = yaml.safe_load(F.borrador("Transportador de rodillos", "transportador-de-rodillos", "1.0.0"))
    f["descripcion"] = "Transportador de rodillos por gravedad de 3 m."
    f.update(cambios)
    return f


def _errores(f, **kw) -> str:
    with pytest.raises(F.FichaError) as exc:
        F.validar(f, **kw)
    return str(exc.value)


def test_slug_sin_tildes_ni_simbolos():
    assert F.slug("Transportador de rodillos (3 m) — versión ñandú") == \
        "transportador-de-rodillos-3-m-version-nandu"
    assert F.slug("   ") == "maquina"


def test_el_borrador_es_yaml_con_los_defaults_del_plan(tmp_path):
    ruta = tmp_path / "ficha.yaml"
    ruta.write_text(F.borrador("Mesa «XL»: 2 m", "mesa-xl-2-m", "1.0.0"), encoding="utf-8")
    f = F.leer(ruta)
    assert f["titulo"] == "Mesa «XL»: 2 m" and f["version"] == "1.0.0"
    assert f["nivel"] == "gratis" and f["precio_usd"] == 0
    assert f["licencias"] == {"gratis": "CC BY-NC 4.0",
                              "completo": "Licencia personal de fabricación"}
    assert set(f["musica"]) == {"archivo", "titulo", "autor", "fuente", "licencia", "atribucion"}
    # tal cual sale, sólo le falta la descripción (la escribe una persona)
    assert "descripcion: no puede quedar vacío" in _errores(f)
    f["descripcion"] = "Una mesa."
    F.validar(f)


def test_valida_con_todos_los_problemas_juntos():
    f = _ficha(precio="10", nivel="pago", precio_usd=0, version="1.0", slug="Mal Slug",
               titulo="x" * 101, etiquetas=["ok", ""], url_tienda="tienda.com")
    msg = _errores(f)
    for esperado in ("clave desconocida «precio»", "nivel pago necesita un precio",
                     "version: debe ser X.Y.Z", "slug: sólo minúsculas", "titulo: tiene 101",
                     "etiquetas[1]: no puede quedar vacío", "url_tienda: debe empezar con https"):
        assert esperado in msg, msg
    assert msg.startswith("ficha.yaml tiene 7 problemas")


def test_precio_y_nivel_cuadran():
    F.validar(_ficha(nivel="pago", precio_usd=9.5))
    assert "el nivel gratis va con precio 0" in _errores(_ficha(precio_usd=5))
    assert "precio_usd: debe ser un número" in _errores(_ficha(precio_usd=True))


def test_youtube_rechaza_angulos():
    assert "YouTube rechaza" in _errores(_ficha(descripcion="Ver <aquí>"))


def test_la_musica_se_exige_completa_solo_si_el_video_la_lleva():
    f = _ficha()
    F.validar(f)  # sin música no hace falta nada
    msg = _errores(f, con_musica=True)
    assert "faltan titulo, autor, fuente, licencia" in msg
    f["musica"].update(titulo="Pista", autor="Autor", fuente="Biblioteca de audio de YouTube",
                       licencia="Licencia de la biblioteca de audio de YouTube")
    F.validar(f, con_musica=True)
    assert F.musica_publica(f)["titulo"] == "Pista" and "archivo" not in F.musica_publica(f)
    assert F.musica_publica(_ficha()) is None


def test_un_yaml_roto_dice_por_que(tmp_path):
    ruta = tmp_path / "ficha.yaml"
    ruta.write_text("titulo: [sin cerrar\n", encoding="utf-8")
    with pytest.raises(F.FichaError, match="no es YAML válido"):
        F.leer(ruta)
    with pytest.raises(F.FichaError, match="publicar guion"):
        F.leer(tmp_path / "no-existe.yaml")
