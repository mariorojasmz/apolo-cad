"""La API del núcleo que una extensión puede importar (`apolo/extensiones_api.py`, plan
nucleo-abierto-extensiones-privadas, F1c): cada nombre declarado existe, se re-exporta por
IDENTIDAD y sin cargar OCCT al importar el módulo; la extensión falsa de la suite importa sólo de
ahí. Si un nombre de `SUPERFICIE` o `MODULOS` deja de existir, este test falla: devolverlo, o
quitarlo de la lista y subir `CONTRATO_EXTENSIONES` (rompe a las extensiones que lo usan)."""

from __future__ import annotations

import importlib
import json
import re
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
    """La extensión de la suite es el ejemplo: todo `from apolo…` suyo pasa por `extensiones_api`."""
    otros = []
    for ruta in sorted((RAIZ / "tests" / "ext_prueba").glob("*.py")):
        for n, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            m = re.match(r"\s*(?:from|import)\s+(apolo[\w.]*)", linea)
            if m and m.group(1) != "apolo.extensiones_api":
                otros.append(f"{ruta.name}:{n}: {linea.strip()}")
    assert not otros, "\n".join(otros)
