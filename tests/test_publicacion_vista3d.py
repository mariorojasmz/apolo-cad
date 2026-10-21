"""`publicacion/vista3d.py`: del documento al `vista-3d.glb` (plan vista-3d-tienda, F1).

Qué piezas entran (visibles, sin guías ni superficies) con qué color y ruta de grupos, y qué
pasa con la compresión: sin gltfpack, con uno que falla y con uno que anda (falso) el GLB sale
igual y el informe lo dice. La compresión real con `gltfpack` corre sólo si está instalado
(`APOLO_GLTFPACK` o el PATH): ningún otro test depende de él.
"""

from __future__ import annotations

import shutil

import numpy as np
import pytest

from apolo.doc import Document
from apolo.kernel.glb_resumen import leer, resumen
from apolo.kernel.render_comun import hex_de_paleta
from apolo.publicacion import vista3d


@pytest.fixture(scope="module")
def doc() -> Document:
    d = Document("Faja de prueba")
    bastidor = d.execute("create_box", {"name": "Larguero", "width": 1000, "depth": 40,
                                        "height": 60, "position": {"x": 500, "y": 0, "z": 30}})
    motor = d.execute("create_box", {"name": "Motorreductor", "width": 150, "depth": 120,
                                     "height": 120, "position": {"x": 100, "y": -150, "z": 60}})
    pinon = d.execute("create_cylinder", {"name": "Piñón", "radius": 40, "height": 20,
                                          "axis": "y", "position": {"x": 100, "y": -230,
                                                                    "z": 60}})
    oculta = d.execute("create_box", {"name": "Oculta", "width": 10, "depth": 10, "height": 10,
                                      "position": {"x": 0, "y": 0, "z": 500}})
    d.execute("create_box", {"name": "Suelta", "width": 50, "depth": 50, "height": 10,
                             "position": {"x": 1200, "y": 0, "z": 5}})
    d.execute("create_group", {"name": "Bastidor", "members": [bastidor]})
    d.execute("create_group", {"name": "Transmisión", "members": [motor]})
    d.execute("create_group", {"name": "Piñonería", "members": [pinon], "parent": "Transmisión"})
    d.set_color(motor, "#c77d4f")
    d.set_visibility(oculta, False)
    return d


def test_piezas_visibles_con_color_y_grupos(doc):
    # D5 (F2): cada instancia se llama como su grupo, nunca como la pieza
    piezas = {p.nombre: p for p in vista3d.piezas(doc)}
    assert set(piezas) == {"Bastidor", "Transmisión", "Piñonería", vista3d.SIN_GRUPO}
    assert piezas["Piñonería"].grupos == ("Transmisión", "Piñonería")
    assert piezas["Bastidor"].grupos == ("Bastidor",) and piezas[vista3d.SIN_GRUPO].grupos == ()
    assert piezas["Transmisión"].color == "#c77d4f"  # el asignado gana
    indice = list(doc.scene).index(next(f.id for f in doc.scene.values() if f.name == "Larguero"))
    assert piezas["Bastidor"].color == hex_de_paleta(indice)  # si no, la paleta del viewport
    # acabado D5 del viewport: el larguero de una máquina de acero es acero pintado
    assert (piezas["Bastidor"].metal, piezas["Bastidor"].rugosidad) == (0.15, 0.55)
    assert len(vista3d.ids_glb(doc)) == 4  # sin la oculta


def test_sin_gltfpack_sale_sin_comprimir_y_lo_dice(doc, tmp_path, monkeypatch):
    monkeypatch.setattr(vista3d, "buscar_gltfpack", lambda: None)
    inf = vista3d.generar(doc, tmp_path / vista3d.ARCHIVO, titulo="Faja")
    assert [p.name for p in tmp_path.iterdir()] == [vista3d.ARCHIVO]  # sin el .crudo
    assert inf["comprimido_con"] is None and "gltfpack" in inf["aviso"]
    assert inf["bytes"] == inf["bytes_crudo"] == (tmp_path / vista3d.ARCHIVO).stat().st_size
    assert inf["piezas"] == 4 and not inf["sobre_tope"]
    assert inf["caja_m"][0][1] == 0.0  # apoyada en Y = 0
    res = resumen(tmp_path / vista3d.ARCHIVO)
    nombres = {n["nombre"] for n in res["nodos"]}
    assert {"Faja", "Bastidor", "Transmisión", "Piñonería", vista3d.SIN_GRUPO} <= nombres
    assert not nombres & {"Larguero", "Motorreductor", "Piñón", "Suelta"}  # D5
    assert not any(m.get("name") in {"Larguero", "Piñón", "Suelta"}
                   for m in leer(tmp_path / vista3d.ARCHIVO).get("meshes", []))
    assert inf["triangulos"] == res["triangulos"] <= inf["tope_triangulos"]



def test_el_glb_lleva_el_acabado_de_cada_pieza(tmp_path, monkeypatch):
    """Material por (color, acabado), con los factores PBR de la tabla D5 (la del viewport):
    sin ellos glTF asume metal = rugosidad = 1 y un visor externo ve la máquina apagada."""
    from apolo.library.apariencia import ACABADOS

    d = Document("Acabados")
    larguero = d.execute("create_box", {"name": "Larguero", "width": 400, "depth": 40,
                                        "height": 60, "position": {"x": 0, "y": 0, "z": 30}})
    rodillo = d.execute("create_cylinder", {"name": "Rodillo de carga", "radius": 25,
                                            "height": 300, "axis": "y",
                                            "position": {"x": 0, "y": 0, "z": 100}})
    for fid in (larguero, rodillo):
        d.set_color(fid, "#2255aa")  # mismo color asignado: el acabado igual los separa
    monkeypatch.setattr(vista3d, "buscar_gltfpack", lambda: None)
    vista3d.generar(d, tmp_path / vista3d.ARCHIVO)
    pbr = [m["pbrMetallicRoughness"] for m in leer(tmp_path / vista3d.ARCHIVO)["materials"]]
    pares = sorted((round(m["metallicFactor"], 3), round(m["roughnessFactor"], 3)) for m in pbr)
    assert pares == [(0.15, 0.55), (0.9, 0.48)]  # acero pintado y galvanizado
    galv = ACABADOS["galvanizado"]
    assert (galv.metalness, galv.roughness) == (0.9, 0.48)  # la tabla, no una copia a mano
    colores = {(round(m["metallicFactor"], 3)): m["baseColorFactor"][:3] for m in pbr}
    assert colores[0.15] != colores[0.9]  # el galvanizado lleva su albedo, no el asignado


def test_una_variable_rota_no_tumba_la_publicacion(doc, tmp_path, monkeypatch):
    monkeypatch.setenv(vista3d.ENV_GLTFPACK, str(tmp_path / "no-existe"))
    inf = vista3d.generar(doc, tmp_path / "v.glb")
    assert inf["comprimido_con"] is None and vista3d.ENV_GLTFPACK in inf["aviso"]
    assert (tmp_path / "v.glb").is_file()


def test_gltfpack_que_falla_deja_el_crudo(doc, tmp_path, monkeypatch):
    def falla(crudo, destino, exe):
        raise RuntimeError("gltfpack salió con 1: boom")

    monkeypatch.setattr(vista3d, "buscar_gltfpack", lambda: "gltfpack")
    monkeypatch.setattr(vista3d, "comprimir", falla)
    inf = vista3d.generar(doc, tmp_path / "v.glb")
    assert inf["comprimido_con"] is None and "boom" in inf["aviso"]
    assert [p.name for p in tmp_path.iterdir()] == ["v.glb"]


def test_gltfpack_que_anda_reemplaza_al_crudo(doc, tmp_path, monkeypatch):
    llamadas = []

    def copia(crudo, destino, exe):
        llamadas.append(exe)
        shutil.copyfile(crudo, destino)

    monkeypatch.setattr(vista3d, "buscar_gltfpack", lambda: "C:/x/gltfpack.exe")
    monkeypatch.setattr(vista3d, "comprimir", copia)
    inf = vista3d.generar(doc, tmp_path / "v.glb")
    assert llamadas == ["C:/x/gltfpack.exe"] and inf["aviso"] is None
    assert inf["comprimido_con"] == "gltfpack -cc -kn"
    assert [p.name for p in tmp_path.iterdir()] == ["v.glb"]


def test_buscar_gltfpack_en_una_carpeta(tmp_path, monkeypatch):
    exe = tmp_path / "gltfpack.exe"
    exe.write_bytes(b"")
    monkeypatch.setenv(vista3d.ENV_GLTFPACK, str(tmp_path))
    assert vista3d.buscar_gltfpack() == str(exe)


def _gltfpack_real() -> bool:
    try:
        return vista3d.buscar_gltfpack() is not None
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not _gltfpack_real(), reason="sin gltfpack (APOLO_GLTFPACK o el PATH)")
def test_compresion_real_conserva_grupos_y_lugares(doc, tmp_path):
    crudo = vista3d.generar(doc, tmp_path / "crudo.glb", comprimir_=False)
    inf = vista3d.generar(doc, tmp_path / "v.glb")
    assert inf["comprimido_con"] == "gltfpack -cc -kn", inf["aviso"]
    assert inf["bytes"] < crudo["bytes"]
    assert "EXT_meshopt_compression" in resumen(tmp_path / "v.glb")["extensiones"]
    antes = {n["nombre"]: n["caja"] for n in resumen(tmp_path / "crudo.glb")["nodos"]
             if n["caja"] is not None}
    despues = {n["nombre"]: n["caja"] for n in resumen(tmp_path / "v.glb")["nodos"]
               if n["caja"] is not None and n["nombre"]}
    for nombre in ("Bastidor", "Transmisión", "Piñonería", vista3d.SIN_GRUPO):
        assert nombre in despues, f"gltfpack borró «{nombre}» (¿falta -kn?)"
        error = max(np.abs(despues[nombre][0] - antes[nombre][0]).max(),
                    np.abs(despues[nombre][1] - antes[nombre][1]).max())
        assert error < 1e-3, f"{nombre} se movió {error * 1000:.2f} mm al comprimir"
    assert inf["triangulos"] == crudo["triangulos"]
