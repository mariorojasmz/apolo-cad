"""`kernel/glb.py`: el GLB de la vista 3D de la tienda (plan vista-3d-tienda, F1 · D1, D2).

Una máquina sintética en mm y Z arriba, que NO apoya en z = 0 (las patas bajan a −260), con
grupos anidados, una pieza girada, una pieza suelta, piezas repetidas (mismo TShape, una con
otro color) y nombres con tilde. Se exige del GLB: metros, Y arriba (x, y, z) → (x, z, −y),
apoyado en Y = 0, cada pieza en su lugar (< 1 mm), nombres intactos, una malla por prototipo y
los triángulos dibujados bajo el tope bajando primero lo que más pesa.
"""

from __future__ import annotations

import numpy as np
import pytest
from build123d import Box, Cylinder, Location, Pos, Rot, Sphere

from apolo.kernel import glb
from apolo.kernel.glb_resumen import leer, resumen

PISO_MM = -260.0


def _caja_mundo(shape):
    """Caja exacta (mm, Z arriba) del shape ubicado, sin malla: la verdad de referencia."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    caja = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, caja, False, False)
    x0, y0, z0, x1, y1, z1 = caja.Get()
    return np.array([x0, y0, z0]), np.array([x1, y1, z1])


def _caja_esperada(shape):
    """Caja (mm, Z arriba) que el GLB tiene que dar a la pieza: la caja exacta del shape SIN
    ubicación, con sus 8 esquinas llevadas por la ubicación de la pieza. Es lo que el visor ve
    de un nodo (su malla en su marco, más la matriz del nodo): igual a la caja del mundo para
    una caja girada, más holgada para un cilindro girado sobre su eje."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.gp import gp_Pnt
    from OCP.TopLoc import TopLoc_Location

    caja = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped.Located(TopLoc_Location()), caja, False, False)
    x0, y0, z0, x1, y1, z1 = caja.Get()
    trsf = shape.wrapped.Location().Transformation()
    pts = []
    for x in (x0, x1):
        for y in (y0, y1):
            for z in (z0, z1):
                p = gp_Pnt(x, y, z).Transformed(trsf)
                pts.append((p.X(), p.Y(), p.Z()))
    pts = np.array(pts)
    return pts.min(0), pts.max(0)


def _a_gltf(lo, hi, piso=PISO_MM):
    """Caja del documento (mm, Z arriba) → caja esperada en el GLB (m, Y arriba, piso en 0)."""
    return (np.array([lo[0], lo[2] - piso, -hi[1]]) / 1000,
            np.array([hi[0], hi[2] - piso, -lo[1]]) / 1000)


def _maquina() -> list[glb.PiezaGlb]:
    pata = Box(60, 60, 300)  # un solo TShape para las cuatro patas
    piezas = [glb.PiezaGlb(f"Pata ({i + 1})", pata.moved(Location((x, y, -110))), "#5b8def",
                           ("Bastidor",))
              for i, (x, y) in enumerate([(0, 0), (1200, 0), (0, 500), (1200, 500)])]
    piezas[3] = glb.PiezaGlb("Pata (4)", piezas[3].shape, "#c75f7c", ("Bastidor",))
    piezas += [
        glb.PiezaGlb("Cubierta", Pos(600, 250, 60) * Box(1300, 560, 40), "#46b58a",
                     ("Bastidor",)),
        glb.PiezaGlb("Piñón", Pos(150, -80, 200) * Rot(0, 0, 30) * Cylinder(60, 25), "#c77d4f",
                     ("Transmisión", "Motor")),
        glb.PiezaGlb("Motorreductor (eje hueco)", Pos(150, -200, 200) * Rot(0, 0, 25)
                     * Box(220, 140, 160), "#8e6fd8", ("Transmisión", "Motor")),
        glb.PiezaGlb("Guarda de la transmisión", Pos(150, -150, 330) * Box(300, 220, 4),
                     "#d8a03a", ("Transmisión",)),
        glb.PiezaGlb("Placa suelta", Pos(1500, 250, 5) * Box(100, 100, 10), "#5fa8c9"),
    ]
    return piezas


@pytest.fixture(scope="module")
def exportada(tmp_path_factory):
    piezas = _maquina()
    ruta = tmp_path_factory.mktemp("glb") / "maquina.glb"
    informe = glb.escribir_glb(piezas, ruta, titulo="Máquina de prueba")
    return piezas, informe, resumen(ruta)


def _instancias(res) -> dict[str, dict]:
    return {n["nombre"]: n for n in res["nodos"] if n["caja"] is not None}


def test_metros_y_arriba_y_apoyada_en_el_piso(exportada):
    piezas, informe, res = exportada
    lo = np.min([_caja_esperada(p.shape)[0] for p in piezas], axis=0)
    hi = np.max([_caja_esperada(p.shape)[1] for p in piezas], axis=0)
    assert lo[2] == pytest.approx(PISO_MM)  # la sintética NO apoya en z = 0
    esperado = _a_gltf(lo, hi)
    lo_g, hi_g = res["caja"]
    assert np.allclose(lo_g, esperado[0], atol=1e-3) and np.allclose(hi_g, esperado[1], atol=1e-3)
    assert lo_g[1] == pytest.approx(0.0, abs=1e-6)          # apoya en Y = 0
    assert hi_g[1] == pytest.approx((hi[2] - lo[2]) / 1000, abs=1e-4)  # el alto va en Y, en m
    assert hi_g[0] - lo_g[0] == pytest.approx((hi[0] - lo[0]) / 1000, abs=1e-3)  # ≈ 1.6 m, no 1600
    assert informe.piso_mm == pytest.approx(PISO_MM, abs=1e-6)
    # el informe mide la malla misma: coincide con la caja exacta del mundo
    lo_w = np.min([_caja_mundo(p.shape)[0] for p in piezas], axis=0)
    hi_w = np.max([_caja_mundo(p.shape)[1] for p in piezas], axis=0)
    assert np.allclose(informe.bbox_m, _a_gltf(lo_w, hi_w), atol=1e-3)


def test_cada_pieza_en_su_lugar(exportada):
    piezas, _informe, res = exportada
    nodos = _instancias(res)
    for p in piezas:
        lo, hi = _a_gltf(*_caja_esperada(p.shape))
        lo_g, hi_g = nodos[p.nombre]["caja"]
        error = max(np.abs(lo_g - lo).max(), np.abs(hi_g - hi).max())
        # la malla de un cilindro queda dentro de su caja exacta, a menos de la deflexión
        assert error < 1e-3, f"{p.nombre} se movió {error * 1000:.2f} mm"


def test_nombres_con_tilde_y_grupos_anidados(exportada):
    _piezas, _informe, res = exportada
    por_nombre = {n["nombre"]: n for n in res["nodos"]}
    for nombre in ("Máquina de prueba", "Transmisión", "Piñón", "Motorreductor (eje hueco)",
                   "Guarda de la transmisión"):
        assert nombre in por_nombre, f"falta «{nombre}»: {sorted(por_nombre)}"
    assert not [n for n in por_nombre if "Ã" in n or n.startswith("=>")]
    padre = {n["indice"]: n for n in res["nodos"]}
    motor = por_nombre["Motor"]
    assert padre[motor["padre"]]["nombre"] == "Transmisión"
    assert padre[por_nombre["Transmisión"]["padre"]]["nombre"] == "Máquina de prueba"
    assert padre[por_nombre["Piñón"]["padre"]]["nombre"] == "Motor"
    assert padre[por_nombre["Placa suelta"]["padre"]]["nombre"] == "Máquina de prueba"


def test_las_piezas_repetidas_comparten_malla(exportada):
    piezas, informe, res = exportada
    nodos = _instancias(res)
    js = leer(informe.ruta)
    posiciones = {js["meshes"][nodos[f"Pata ({i})"]["malla"]]["primitives"][0]["attributes"]
                  ["POSITION"] for i in (1, 2, 3)}
    assert len(posiciones) == 1  # tres instancias del mismo color, una sola malla guardada
    # la de otro color: OCCT guarda su malla aparte (otro estilo = otros datos); son 12 tri
    assert res["triangulos"] - res["triangulos_archivo"] == 2 * 12
    assert informe.triangulos == res["triangulos"]
    assert informe.prototipos == len(piezas) - 3 and informe.piezas == len(piezas)
    # la pata de otro color lleva su material: los dos colores están en el GLB
    def lineal(c):
        c = c / 255.0
        return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    colores = [np.array(m["pbrMetallicRoughness"]["baseColorFactor"][:3])
               for m in res["materiales"]]
    for hexa in ("#5b8def", "#c75f7c"):
        rgb = lineal(np.array([int(hexa[k:k + 2], 16) for k in (1, 3, 5)], dtype=float))
        assert any(np.allclose(c, rgb, atol=2e-3) for c in colores), hexa
    # PBR explícito: sin metallicFactor, glTF asume metal = 1 (metal crudo oscuro)
    for m in res["materiales"]:
        pbr = m["pbrMetallicRoughness"]
        assert pbr.get("metallicFactor", 1.0) == pytest.approx(glb.METAL)
        assert pbr.get("roughnessFactor", 1.0) == pytest.approx(glb.RUGOSIDAD)


def test_no_tesela_los_shapes_del_llamador(tmp_path):
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location

    caja = Pos(10, 0, 0) * Box(10, 20, 30)
    glb.escribir_glb([glb.PiezaGlb("Caja", caja, "#808080")], tmp_path / "c.glb", titulo="c")
    for cara in caja.faces():
        assert BRep_Tool.Triangulation_s(cara.wrapped, TopLoc_Location()) is None


def test_el_tope_baja_primero_lo_que_mas_dibuja(tmp_path):
    esfera = Sphere(40)  # 30 instancias de un prototipo denso
    piezas = [glb.PiezaGlb(f"Bola ({i})", esfera.moved(Location((i * 100, 0, 0))), "#cccccc",
                           ("Bolas",)) for i in range(30)]
    piezas.append(glb.PiezaGlb("Cilindro", Cylinder(30, 200), "#888888"))
    libre = glb.escribir_glb(piezas, tmp_path / "libre.glb", titulo="t", tope=10**9)
    assert not libre.rebajados and not libre.sobre_tope
    tope = libre.triangulos // 3
    ajustado = glb.escribir_glb(piezas, tmp_path / "tope.glb", titulo="t", tope=tope)
    assert ajustado.triangulos <= tope and not ajustado.sobre_tope
    assert [r["pieza"] for r in ajustado.rebajados] == ["Bola (0)"]  # sólo lo repetido y denso
    assert ajustado.rebajados[0]["instancias"] == 30
    res = resumen(tmp_path / "tope.glb")
    assert res["triangulos"] == ajustado.triangulos  # lo que cuenta el kernel es lo que se dibuja
    assert res["triangulos_archivo"] == ajustado.triangulos_archivo


def test_un_tope_imposible_se_declara(tmp_path):
    piezas = [glb.PiezaGlb("Bola", Sphere(40), "#cccccc")]
    inf = glb.escribir_glb(piezas, tmp_path / "x.glb", titulo="t", tope=10)
    assert inf.sobre_tope and inf.triangulos > 10
    assert inf.rebajados[0]["nivel"] == len(glb.NIVELES) - 1


def test_sin_piezas_no_hay_glb(tmp_path):
    with pytest.raises(ValueError, match="No hay piezas"):
        glb.escribir_glb([], tmp_path / "x.glb", titulo="t")
