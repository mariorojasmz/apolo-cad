"""Andamio TEMPORAL del plan `docs/plans/partir-api-main.md` (F1): por fuera, la API no
cambia mientras se parte `api/main.py`.

Compara el código ACTUAL contra lo congelado en `tests/data/partir_main/` desde el código
SIN tocar (`scripts/partir_main_snapshot.py`): rutas en orden, OpenAPI, textos de `main.py`
(que pueden mudarse a `api/` o `services/`, pero no perderse ni cambiar) y respuestas
doradas. **Si uno se pone rojo, la fase se detiene**: no se regenera el congelado para
hacerlo pasar (salvo un cambio deliberado de OTRO plan, que se anota en la bitácora).
Se borra en F7 junto con el script; lo permanente queda en `tests/test_rutas_api.py`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

import apolo.api.main as api

# Lo congelado sale de Windows (numérica de OCCT y texto de los PDF de ESTA máquina): en el
# CI de Linux difiere sin que la API haya cambiado. Se borra en F7 con el resto del andamio.
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="andamio temporal del plan partir-api-main; congelado en Windows; se borra en F7",
)

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "tests" / "data" / "partir_main"

_spec = importlib.util.spec_from_file_location(
    "partir_main_snapshot", RAIZ / "scripts" / "partir_main_snapshot.py")
snap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(snap)


def _congelado(nombre: str):
    return json.loads((DATOS / nombre).read_text(encoding="utf-8"))


def test_las_rutas_son_las_mismas_y_en_el_mismo_orden():
    """Starlette atiende la PRIMERA ruta que casa: el orden decide quién responde una
    URL solapada y qué `Allow` lleva un 405."""
    assert snap.capturar_rutas(api.app) == _congelado("rutas.json")


def test_el_openapi_no_cambia():
    """operationId (= nombre de función), modelos pydantic y parámetros, idénticos."""
    actual, congelado = snap.capturar_openapi(api.app), _congelado("openapi.json")
    distintos = sorted(set(actual["paths"]) ^ set(congelado["paths"]))
    assert not distintos, f"paths distintos: {distintos}"
    for path in congelado["paths"]:
        assert actual["paths"][path] == congelado["paths"][path], path
    assert actual == congelado


def test_ningun_texto_de_main_se_pierde_al_mudarse():
    """Cada constante de texto ≥ 12 caracteres que tenía `main.py` sigue existiendo, igual,
    en `api/` o en `services/` (un mensaje de error mudado no se reescribe)."""
    faltan = sorted(set(_congelado("textos.json")) - snap.textos_de(snap.fuentes_api()))
    assert not faltan, "Textos de main.py que ya no existen:\n" + "\n".join(faltan)


def test_respuestas_doradas():
    previo = {n: getattr(api, n) for n in snap._SESION}
    actual = snap.capturar_respuestas(api)
    # el andamio no deja la sesión de la API cambiada para el test siguiente
    assert {n: getattr(api, n) for n in snap._SESION} == previo
    congelado = _congelado("respuestas.json")
    assert [e["id"] for e in actual] == [e["id"] for e in congelado]
    distintas = [a["id"] for a, c in zip(actual, congelado) if a != c]
    if distintas:
        a = next(e for e in actual if e["id"] == distintas[0])
        c = next(e for e in congelado if e["id"] == distintas[0])
        pytest.fail(f"Respuestas distintas: {distintas}\n\n{distintas[0]} actual:\n"
                    f"{json.dumps(a, ensure_ascii=False, indent=1)[:4000]}\n\ncongelada:\n"
                    f"{json.dumps(c, ensure_ascii=False, indent=1)[:4000]}")
