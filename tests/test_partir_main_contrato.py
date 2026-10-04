"""Andamio TEMPORAL del plan `docs/plans/partir-api-main.md` (F1): por fuera, la API no
cambia mientras se parte `api/main.py`.

Compara el código ACTUAL contra lo congelado en `tests/data/partir_main/` desde el código
SIN tocar (`scripts/partir_main_snapshot.py`): rutas (y el orden de las que pueden casar la
misma URL), OpenAPI, textos de `main.py`
(que pueden mudarse a `api/` o `services/`, pero no perderse ni cambiar) y respuestas
doradas. **Si uno se pone rojo, la fase se detiene**: no se regenera el congelado para
hacerlo pasar (salvo un cambio deliberado de OTRO plan, que se anota en la bitácora).
Se borra en F7 junto con el script; lo permanente queda en `tests/test_rutas_api.py`.
"""

from __future__ import annotations

import importlib.util
import json
import re
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


def _segmento_casa(a: str, b: str) -> bool:
    """¿Hay un segmento de URL que casen los dos patrones? `{x}` = texto sin «/» (el
    convertidor `str` de Starlette, el único que usa la API)."""
    pa, pb = "{" in a, "{" in b
    if not pa and not pb:
        return a == b
    if pa and pb:
        return True  # dos segmentos con parámetro: se asume que pueden casar
    patron, literal = (a, b) if pa else (b, a)
    rx = "".join("[^/]+" if p.startswith("{") else re.escape(p)
                 for p in re.split(r"(\{[^}]+\})", patron))
    return re.fullmatch(rx, literal) is not None


def solapan(p: str, q: str) -> bool:
    """¿Pueden los paths `p` y `q` casar la MISMA URL? (un path consigo mismo, también)."""
    a, b = p.split("/"), q.split("/")
    return len(a) == len(b) and all(map(_segmento_casa, a, b))


def _clave(r: dict) -> tuple:
    return (r["tipo"], tuple(r["metodos"]), r["path"], r["nombre"])


def test_las_rutas_son_las_mismas_y_las_que_se_solapan_conservan_su_orden():
    """Mismas rutas (tipo, métodos, path, nombre) que las congeladas. Starlette atiende la
    PRIMERA ruta que casa: el orden decide quién responde una URL solapada y qué `Allow` lleva
    un 405. Ese orden es el de las rutas que pueden casar la MISMA URL —los 11 pares solapados
    y los 9 paths con varios métodos— y se compara par por par contra lo congelado; el orden
    GLOBAL cambia por diseño al repartir las rutas en routers (D5: cada par vive dentro de un
    router). Hasta F6a este test comparaba la lista entera en orden (bitácora de F6b)."""
    actual, congelado = snap.capturar_rutas(api.app), _congelado("rutas.json")
    assert sorted(map(_clave, actual)) == sorted(map(_clave, congelado))
    pos = {_clave(r): i for i, r in enumerate(actual)}
    invertidos = [
        f"{a['nombre']} ({a['path']}) debe ir antes que {b['nombre']} ({b['path']})"
        for i, a in enumerate(congelado) for b in congelado[i + 1:]
        if solapan(a["path"], b["path"]) and pos[_clave(a)] > pos[_clave(b)]
    ]
    assert not invertidos, "\n".join(invertidos)


def test_el_detector_de_solapes_ve_los_pares_del_plan():
    """Sin esto, un `solapan` roto (siempre False) dejaría verde el test de arriba sin
    comparar nada: sobre lo congelado ve los 11 pares de paths DISTINTOS y los 9 paths con
    varios métodos que midió el plan."""
    r = _congelado("rutas.json")
    pares = [(a["path"], b["path"]) for i, a in enumerate(r) for b in r[i + 1:]
             if solapan(a["path"], b["path"])]
    assert sum(p != q for p, q in pares) == 11
    assert len({p for p, q in pares if p == q}) == 9
    assert ("/api/fea/group/{name}", "/api/fea/{feature_id}/fringe.png") in pares
    assert not solapan("/api/export/step", "/api/export/urdf")


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
