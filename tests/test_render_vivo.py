"""Render VTK vivo para video (plan publicacion-tienda, F2 · D5): `kernel/render_vivo.py`.

Una ventana off-screen que dura todo el video, con actores incrementales, colores y cámara
fijados con la escena FINAL y un resaltado que se desvanece. Además, la extracción de lo común a
`render_comun.py`: el vivo y la foto de `render_vtk` dan los mismos píxeles.

VTK necesita un contexto OpenGL off-screen (en CI Linux: Xvfb + Mesa). Si el entorno no lo tiene,
los tests que rasterizan se SALTAN, como en `test_render_vtk.py`; la validación de tamaño no
rasteriza y corre igual.
"""

from __future__ import annotations

import gc
import io
import weakref
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("vtk")

from apolo.kernel import render_comun  # noqa: E402
from apolo.kernel.render import PALETTE  # noqa: E402
from apolo.kernel.render_vivo import (  # noqa: E402
    EscenaViva,
    bbox_final,
    colores_fijos,
    extraer_piezas,
)

CAJA = ((0.0, 0.0, 0.0), (100.0, 100.0, 100.0))


def _pieza(fid: str, x: float = 0.0, z: float = 0.0, lado: float = 100.0, **extra):
    from build123d import Box, Pos

    datos = {"id": fid, "name": fid, "material": None, "visible": True,
             "shape": Pos(x, 0, z) * Box(lado, lado, lado)}
    datos.update(extra)
    return SimpleNamespace(**datos)


def _escena(*piezas) -> dict:
    return {p.id: p for p in piezas}


def _centro(p):
    bb = p.shape.bounding_box()
    return ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)


def _pixel(viva, frame, punto):
    col, fila = viva.proyectar(punto)
    return frame[int(fila), int(col)].astype(int)


@pytest.fixture(scope="module")
def vtk_ok():
    try:
        with EscenaViva(CAJA, {}, ancho=64, alto=48) as viva:
            viva.fotograma()
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL en este entorno
        pytest.skip(f"VTK off-screen no disponible: {exc}")


@pytest.fixture
def abrir(vtk_ok):
    """Abre escenas vivas para el test y las cierra al terminar."""
    abiertas: list[EscenaViva] = []

    def _abrir(escena_final, colores=None, **kw):
        kw.setdefault("ancho", 320)
        kw.setdefault("alto", 240)
        viva = EscenaViva.para(escena_final, colores, **kw)
        abiertas.append(viva)
        return viva

    yield _abrir
    for viva in abiertas:
        viva.cerrar()


# ── tamaño ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ancho, alto", [(1919, 1080), (1920, 1081), (0, 1080), (-2, 1080),
                                         (1920.0, 1080), ("1920", 1080)])
def test_lados_impares_o_no_enteros_se_rechazan(ancho, alto):
    with pytest.raises(ValueError, match="par"):
        EscenaViva(CAJA, {}, ancho=ancho, alto=alto)


def test_bbox_invalido_se_rechaza():
    with pytest.raises(ValueError, match="bbox"):
        EscenaViva(((0, 0, 0), (np.inf, 1, 1)), {})


def test_fotograma_por_defecto_es_1080p_uint8_contiguo(vtk_ok):
    with EscenaViva.para(_escena(_pieza("a"))) as viva:
        viva.actualizar(_escena(_pieza("a")))
        frame = viva.fotograma()
    assert frame.shape == (1080, 1920, 3)
    assert frame.dtype == np.uint8 and frame.flags["C_CONTIGUOUS"]


def test_cualquier_tamano_par_vale(abrir):
    viva = abrir(_escena(_pieza("a")), ancho=640, alto=480)   # 4:3, no 16:9
    assert viva.fotograma().shape == (480, 640, 3)


def test_fotograma_va_de_arriba_hacia_abajo(vtk_ok):
    """VTK lee el buffer de abajo hacia arriba; el fotograma sale con la fila 0 ARRIBA. Sin
    piezas, la fila 0 es el color de arriba del degradado y la última el de abajo."""
    with EscenaViva(CAJA, {}, ancho=64, alto=48) as viva:
        frame = viva.fotograma().astype(int)
    arriba = np.array(render_comun.FONDO_ARRIBA) * 255
    abajo = np.array(render_comun.FONDO_ABAJO) * 255
    assert np.abs(frame[0, 32] - arriba).max() <= 4
    assert np.abs(frame[-1, 32] - abajo).max() <= 4


def test_proyectar_ubica_la_pieza_en_el_fotograma(abrir):
    alta, baja = _pieza("alta", z=400), _pieza("baja", z=-400)
    escena = _escena(alta, baja)
    viva = abrir(escena, view="frente")
    viva.actualizar(escena)
    frame = viva.fotograma()
    fila_alta = viva.proyectar(_centro(alta))[1]
    fila_baja = viva.proyectar(_centro(baja))[1]
    assert fila_alta < fila_baja   # la de arriba en el mundo sale arriba en el fotograma
    fondo = frame[2, 2].astype(int)
    for p in (alta, baja):
        assert np.abs(_pixel(viva, frame, _centro(p)) - fondo).max() > 20   # pieza, no fondo


# ── colores ───────────────────────────────────────────────────────────────────


def test_colores_fijos_regla_del_viewport():
    """Paleta por índice en la escena FINAL (invisibles incluidas, como `_feature_colors`) y el
    color asignado gana."""
    escena = _escena(_pieza("a"), _pieza("b", visible=False), _pieza("c"))
    assert colores_fijos(escena) == {"a": PALETTE[0], "b": PALETTE[1], "c": PALETTE[2]}
    assert colores_fijos(escena, {"c": "#123456"})["c"] == "#123456"


def test_misma_pieza_mismo_color_cuando_la_escena_crece(abrir):
    a, b, c = _pieza("a", x=-400), _pieza("b"), _pieza("c", x=400)
    final = _escena(a, b, c)
    viva = abrir(final)
    viva.actualizar(_escena(c))
    solo_c = _pixel(viva, viva.fotograma(), _centro(c))
    viva.actualizar(final)
    con_todas = _pixel(viva, viva.fotograma(), _centro(c))
    assert viva.color("c") == PALETTE[2]
    assert (solo_c == con_todas).all()
    # por índice de la escena PARCIAL, «c» sería la primera de la paleta: otro color
    parcial = abrir(_escena(c), bbox=bbox_final(final))
    parcial.actualizar(_escena(c))
    assert np.abs(_pixel(parcial, parcial.fotograma(), _centro(c)) - solo_c).max() > 20


def test_pieza_ajena_a_la_final_conserva_su_color(abrir):
    viva = abrir(_escena(_pieza("a")))
    tool = _pieza("herramienta", x=300)
    viva.actualizar(_escena(_pieza("a"), tool))
    primero = viva.color("herramienta")
    viva.actualizar(_escena(_pieza("a")))
    viva.actualizar(_escena(_pieza("a"), tool))
    assert viva.color("herramienta") == primero == PALETTE[1]


# ── cámara ────────────────────────────────────────────────────────────────────


def test_la_camara_no_se_mueve_al_crecer_la_escena(abrir):
    a, b = _pieza("a", x=-600), _pieza("b", x=600, z=300, lado=250)
    viva = abrir(_escena(a, b))
    antes = viva.camara()
    viva.actualizar(_escena(a))
    viva.fotograma()
    viva.actualizar(_escena(a, b))
    viva.fotograma()
    assert viva.camara() == antes


def _misma_camara(c1: dict, c2: dict) -> bool:
    return all(np.allclose(c1[k], c2[k]) for k in ("posicion", "foco", "arriba", "escala"))


def test_orbitar_pone_angulos_absolutos(abrir):
    viva = abrir(_escena(_pieza("a")))
    preset = viva.camara()
    viva.orbitar(azimut=30, elevacion=15, zoom=1.2)
    girada = viva.camara()
    viva.orbitar(azimut=-170, elevacion=60)
    viva.orbitar(azimut=30, elevacion=15, zoom=1.2)
    assert _misma_camara(viva.camara(), girada)
    assert not _misma_camara(girada, preset)
    viva.orbitar()
    assert _misma_camara(viva.camara(), preset)


def test_la_orbita_no_respira(abrir):
    """El encuadre usa la esfera del bbox final: la escala no cambia con el azimut."""
    viva = abrir(_escena(_pieza("a", x=-500), _pieza("b", x=500)))
    escalas = set()
    for az in range(0, 360, 45):
        viva.orbitar(azimut=az, elevacion=22)
        escalas.add(round(viva.camara()["escala"], 9))
    assert len(escalas) == 1


# ── actores incrementales ─────────────────────────────────────────────────────


def test_agregados_quitados_y_reemplazados(abrir):
    a, b, c = _pieza("a", x=-300), _pieza("b"), _pieza("c", x=300)
    viva = abrir(_escena(a, b, c))
    r = viva.actualizar(_escena(a, b))
    assert (r.agregados, r.quitados, r.reemplazados) == (["a", "b"], [], [])
    r = viva.actualizar(_escena(b, c))
    assert (r.agregados, r.quitados, r.reemplazados) == (["c"], ["a"], [])
    assert not viva.actualizar(_escena(b, c))      # nada cambió → Cambios vacío
    # «b» con OTRO objeto shape (misma geometría): se reemplaza su actor
    b2 = _pieza("b")
    r = viva.actualizar(_escena(b2, c))
    assert (r.agregados, r.quitados, r.reemplazados) == ([], [], ["b"])
    # una pieza oculta cuenta como ausente
    r = viva.actualizar(_escena(b2, _pieza("c", x=300, visible=False)))
    assert r.quitados == ["c"] and viva.ids() == ["b"]


def test_vidrio_cambia_de_opacidad_y_se_reemplaza(abrir):
    a = _pieza("a")
    viva = abrir(_escena(a))
    viva.actualizar(_escena(a))
    a_vidrio = SimpleNamespace(**{**vars(a), "material": "vidrio"})   # mismo shape
    assert viva.actualizar(_escena(a_vidrio)).reemplazados == ["a"]
    assert extraer_piezas(_escena(a_vidrio))[0].opacidad == render_comun.OPACIDAD_VIDRIO


def test_guarda_la_referencia_al_shape_para_que_su_id_no_se_recicle(abrir):
    """Un diff por `id(shape)` sin la referencia confundiría un shape NUEVO que reciba el id de
    uno recolectado con la pieza vieja: la escena viva guarda el shape y compara con `is`."""
    viva = abrir(_escena(_pieza("a")))
    a = _pieza("a")
    viva.actualizar(_escena(a))
    vivo = weakref.ref(a.shape)
    render_comun._RENDER_MESH_CACHE.clear()        # la caché de mallas también lo retiene
    del a
    gc.collect()
    assert vivo() is not None                      # lo retiene la escena viva → id no reciclable
    r = viva.actualizar(_escena(_pieza("a")))      # shape nuevo, mismo id de pieza
    assert r.reemplazados == ["a"]
    gc.collect()
    assert vivo() is None                          # al reemplazarlo, lo suelta


# ── resaltado ─────────────────────────────────────────────────────────────────


def test_resaltar_cambia_los_pixeles_y_cero_los_restaura(abrir):
    a, b = _pieza("a", x=-300), _pieza("b", x=300)
    escena = _escena(a, b)
    viva = abrir(escena)
    viva.actualizar(escena)
    base = viva.fotograma()
    viva.resaltar(["a"], 1.0)
    lleno = viva.fotograma()
    viva.resaltar(["a"], 0.5)
    medio = viva.fotograma()
    pa, pb = _centro(a), _centro(b)
    assert np.abs(_pixel(viva, lleno, pa) - _pixel(viva, base, pa)).max() > 30
    assert (_pixel(viva, lleno, pb) == _pixel(viva, base, pb)).all()   # «b» no se tocó
    d_medio = np.abs(_pixel(viva, medio, pa) - _pixel(viva, base, pa)).max()
    assert 0 < d_medio < np.abs(_pixel(viva, lleno, pa) - _pixel(viva, base, pa)).max()
    viva.resaltar(["a"], 0.0)
    assert (viva.fotograma() == base).all()        # intensidad 0 → exactamente lo de antes


def test_resaltar_un_id_antes_de_que_exista(abrir):
    a, b = _pieza("a", x=-300), _pieza("b", x=300)
    viva = abrir(_escena(a, b))
    viva.actualizar(_escena(a, b))
    base = viva.fotograma()
    viva.actualizar(_escena(a))
    viva.resaltar("b", 1.0)                        # aún sin actor: se guarda
    viva.actualizar(_escena(a, b))
    pb = _centro(b)
    assert np.abs(_pixel(viva, viva.fotograma(), pb) - _pixel(viva, base, pb)).max() > 30
    viva.resaltar(None, 0.0)                       # None = todas
    assert (viva.fotograma() == base).all()


# ── igual que la foto de render_vtk ──────────────────────────────────────────


@pytest.mark.parametrize("vidrio", [False, True])
def test_el_vivo_se_ve_como_render_vtk(vtk_ok, vidrio):
    """Misma escena, mismo tamaño (600×468 = el aspecto 0,78 de la foto): mismos píxeles. Comprueba
    la extracción a `render_comun` (material, aristas, fondo, luces, cámara, transparencia) y que
    `render_vtk` sigue rindiendo después de ella. Tolerancia por si un driver no es determinista."""
    from PIL import Image

    from apolo.doc import Document
    from apolo.kernel.render_vtk import render_scene_vtk

    d = Document()
    d.execute("create_box", {"width": 400, "depth": 120, "height": 120})
    d.execute("create_cylinder", {"radius": 60, "height": 300, "axis": "x",
                                  "position": {"x": 0, "y": 250, "z": 60}})
    if vidrio:
        v = d.execute("create_box", {"width": 300, "depth": 8, "height": 200,
                                     "position": {"x": 0, "y": -150, "z": 100}})
        d.set_material(v, "vidrio")
    png = render_scene_vtk(d.scene, "iso", size_px=600)
    assert png[:4] == b"\x89PNG"
    foto = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
    with EscenaViva.para(d.scene, d.colors, ancho=600, alto=468) as viva:
        viva.actualizar(d.scene)
        vivo = viva.fotograma().astype(int)
    assert foto.shape == vivo.shape
    distintos = (np.abs(foto - vivo).max(axis=2) > 2).mean()
    assert distintos < 0.001, f"{distintos:.2%} de los píxeles difieren"


def test_quitar_el_vidrio_vuelve_al_msaa(abrir):
    a = _pieza("a", x=-300)
    vidrio = _pieza("v", x=300, material="vidrio")
    viva = abrir(_escena(a, vidrio))
    viva.actualizar(_escena(a))
    sin_vidrio = viva.fotograma().astype(int)
    viva.actualizar(_escena(a, vidrio))
    con_vidrio = viva.fotograma().astype(int)
    assert np.abs(con_vidrio - sin_vidrio).max() > 20
    viva.actualizar(_escena(a))
    vuelta = viva.fotograma().astype(int)
    assert (np.abs(vuelta - sin_vidrio).max(axis=2) > 2).mean() < 0.001


# ── ciclo de vida ─────────────────────────────────────────────────────────────


def test_cerrar_suelta_la_ventana(vtk_ok):
    with EscenaViva(CAJA, {}, ancho=64, alto=48) as viva:
        viva.fotograma()
    with pytest.raises(RuntimeError, match="cerró"):
        viva.fotograma()
    viva.cerrar()   # idempotente
