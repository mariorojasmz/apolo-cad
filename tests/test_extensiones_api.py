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
