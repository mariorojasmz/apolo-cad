"""La API del núcleo que una extensión puede importar (`apolo/extensiones_api.py`, plan
nucleo-abierto-extensiones-privadas, F1c): cada nombre declarado existe, se re-exporta por
IDENTIDAD y sin cargar OCCT al importar el módulo; la extensión falsa de la suite importa sólo de
ahí. Si un nombre de `SUPERFICIE` o `MODULOS` deja de existir, este test falla: devolverlo, o
quitarlo de la lista y subir `CONTRATO_EXTENSIONES` (rompe a las extensiones que lo usan)."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from apolo import extensiones, extensiones_api

RAIZ = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("nombre", sorted(extensiones_api.SUPERFICIE))
def test_cada_nombre_de_la_superficie_existe_y_es_el_mismo_objeto(nombre):
    origen = extensiones_api.SUPERFICIE[nombre]
    modulo, _, atributo = origen.partition(":")
    assert hasattr(importlib.import_module(modulo), atributo), f"{nombre}: {origen} ya no existe"
    assert getattr(extensiones_api, nombre) is getattr(importlib.import_module(modulo), atributo)


@pytest.mark.parametrize("modulo", sorted(extensiones_api.MODULOS))
def test_cada_modulo_declarado_conserva_sus_nombres(modulo):
    m = importlib.import_module(modulo)
    faltan = [n for n in extensiones_api.MODULOS[modulo] if not hasattr(m, n)]
    assert not faltan, (f"{modulo} ya no tiene {', '.join(faltan)}: es API de extensiones "
                        "(extensiones_api.MODULOS); devuélvelo o sube CONTRATO_EXTENSIONES")


def test_lo_que_no_esta_declarado_no_se_re_exporta():
    with pytest.raises(AttributeError, match="no es API para extensiones"):
        extensiones_api.REGISTRY  # noqa: B018
    assert set(extensiones_api.SUPERFICIE) <= set(dir(extensiones_api))


def test_el_contrato_no_cambio_en_f1c():
    """F1c sólo DECLARA lo que ya se usaba (nada se quitó ni renombró): el contrato sigue en 1."""
    assert extensiones.CONTRATO_EXTENSIONES == extensiones_api.CONTRATO_EXTENSIONES == 1


def test_importar_la_superficie_no_carga_occt():
    """Como `extensiones.py`: el MCP lee la extensión (que importa de aquí) sin cargar OCCT."""
    codigo = ("import json, sys\nfrom apolo.extensiones_api import Extension, CONTRATO_EXTENSIONES\n"
              "print(json.dumps(sorted(m for m in sys.modules "
              "if m.split('.')[0] in ('OCP', 'build123d', 'apolo'))))")
    out = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True,
                         timeout=120, cwd=RAIZ)
    assert out.returncode == 0, out.stderr[-2000:]
    cargados = json.loads(out.stdout.strip().splitlines()[-1])
    assert not [m for m in cargados if not m.startswith("apolo")], cargados
    assert "apolo.commands" not in cargados and "apolo.kernel" not in cargados


def test_la_extension_falsa_importa_del_nucleo_solo_por_la_superficie():
    """La extensión de la suite es el ejemplo: todo `from apolo…` suyo pasa por `extensiones_api`
    o, para el trabajo de dominio (sus láminas, F1d), por un módulo de `MODULOS` y sólo con los
    nombres que declara."""
    import ast

    otros = []
    for ruta in sorted((RAIZ / "tests" / "ext_prueba").glob("*.py")):
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                otros += [f"{ruta.name}:{nodo.lineno}: import {a.name}" for a in nodo.names
                          if a.name.split(".")[0] == "apolo"]
            elif isinstance(nodo, ast.ImportFrom) and (nodo.module or "").split(".")[0] == "apolo":
                nombres = {a.name for a in nodo.names}
                declarados = set(extensiones_api.MODULOS.get(nodo.module, ()))
                if nodo.module != "apolo.extensiones_api" and not (
                        nodo.module in extensiones_api.MODULOS and nombres <= declarados):
                    otros.append(f"{ruta.name}:{nodo.lineno}: from {nodo.module} import "
                                 f"{', '.join(sorted(nombres - declarados))}")
    assert not otros, "\n".join(otros)


#: plan pedidos-de-extensiones, D1: lo que ya existía y una extensión leía por fuera, declarado con
#: los nombres de hoy (agregar no sube el contrato)
PEDIDOS_MODULOS = {
    "apolo.drawing.esquema": ("PILOTAJE", "pilotaje", "trazos_mm", "TRAZO_X_GROSOR",
                              "HUECO_X_GROSOR"),
    "apolo.library.electrico.redes": ("resolver",),
    "apolo.drawing.dwg": ("DwgError", "disponible", "sheet_to_dwg"),
    "apolo.services.escenarios": ("listar", "estado", "firma_documento", "SIN_CORRER", "VENCIDO"),
    "apolo.cosim.vivo_fotograma": ("FORMATO", "CABECERA", "leer_fotograma"),
}


@pytest.mark.parametrize("modulo,nombre", [(m, n) for m, ns in PEDIDOS_MODULOS.items() for n in ns])
def test_lo_de_pedidos_de_extensiones_esta_declarado(modulo, nombre):
    assert nombre in extensiones_api.MODULOS.get(modulo, ()), f"{modulo}.{nombre} no está en MODULOS"
    assert hasattr(importlib.import_module(modulo), nombre)


def test_pedir_entregable_esta_en_la_superficie_sin_subir_el_contrato():
    from apolo.tools import entregable

    assert extensiones_api.SUPERFICIE["pedir_entregable"] == "apolo.tools.entregable:pedir"
    assert extensiones_api.pedir_entregable is entregable.pedir
    assert extensiones.CONTRATO_EXTENSIONES == extensiones_api.CONTRATO_EXTENSIONES == 1


def test_la_extension_falsa_lee_por_el_contrato(monkeypatch):
    """D13 de lectura: la extensión resuelve bornes, dibuja el pilotaje, sabe si hay DWG, lee la
    FAT del núcleo y un fotograma del vivo, todo con los nombres de D1 (`ext_prueba/contrato.py`)."""
    import struct

    from ext_prueba import contrato
    from tablero_electrico import arranque_directo

    from apolo.doc import Document
    from apolo.drawing import dwg as D
    from apolo.drawing.esquema import PILOTAJE
    from apolo.drawing.sheet import SheetModel
    from apolo.services import escenarios as E

    d = Document("tablero")
    d.execute_many(arranque_directo())
    b = contrato.bornes(d, ["-Q3:A1", "-K9:A1", "-Q3:Z9"])
    assert b["-Q3:A1"] == ["-Q3", "A1"]
    assert "no existe" in b["-K9:A1"] and "no tiene el borne Z9" in b["-Q3:Z9"]

    m = SheetModel(297, 210)
    assert contrato.envolvente(m, 10, 10, 60, 40) == pytest.approx((4.2, 1.05))
    assert [ln.kind for ln in m.lines] == [PILOTAJE] * 4

    monkeypatch.setattr(D, "_discover", lambda *a, **k: False)
    assert contrato.dwg(m) == {"dwg": None, "aviso": D.SIN_ODA}

    assert contrato.fat(d) == {"firma": E.firma_documento(d), "escenarios": []}
    E.poner(d, "corto", {"duracion_s": 1})
    E.poner(d, "corrido", {"duracion_s": 1})
    ver = {"veredicto": "pasa", "aserciones": [], "n_fallidas": 0}
    comp = E.resultado_compacto(ver, {"resumen": {}}, firma=E.firma_documento(d),
                                hash_esc=E.hash_escenario(d.escenarios["corrido"]["escenario"]),
                                simulacion="s1")
    assert E.guardar_resultado(d, "corrido", comp)
    filas = {f["nombre"]: f for f in contrato.fat(d)["escenarios"]}
    assert filas["corto"] == {"nombre": "corto", "estado": E.SIN_CORRER, "vigente": False}
    assert filas["corrido"] == {"nombre": "corrido", "estado": "pasa", "vigente": True}

    plano = [1, 0.5, 1.0, 0, 0, 0, 0, 2, 3.0, float("nan")]
    f = contrato.fotograma(struct.pack("<10f", *plano), ["-M1.rpm", "-Q3.cerrado"])
    assert f == {"t": 0.5, "factor": 1.0, "valores": {"-M1.rpm": 3.0}}
    with pytest.raises(ValueError, match="formato 2"):
        contrato.fotograma(struct.pack("<8f", 2, 0, 1, 0, 0, 0, 0, 0), [])


def test_el_motor_de_laminas_esta_declarado_y_la_extension_falsa_lo_usa():
    """F1d: `drawing.sheet`, `tabla`, `titleblock` y `pdf` en `MODULOS`, y una extensión arma con
    ellos un PDF de varias hojas con su cajetín (`tests/ext_prueba/laminas.py`)."""
    from ext_prueba import laminas

    assert {"apolo.drawing.sheet", "apolo.drawing.tabla", "apolo.drawing.titleblock",
            "apolo.drawing.pdf"} <= set(extensiones_api.MODULOS)
    filas = [[i, f"Pieza de prueba número {i} con una descripción larga que se parte", i * 2]
             for i in range(1, 61)]
    hojas = laminas.laminas(filas)
    assert len(hojas) >= 2  # 60 filas partidas no entran en una A4: pagina por altura
    assert any(lb.text == "EXTENSIÓN DE PRUEBA" for lb in hojas[0].labels)
    laminas.cajetin_suelto(hojas[0])
    pdf = laminas.pdf(filas[:5])
    assert pdf.startswith(b"%PDF")
