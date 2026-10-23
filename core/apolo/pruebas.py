"""Plugin de pytest con el aislamiento que necesita una suite que use Apolo (plan
nucleo-abierto-extensiones-privadas, A6): viaja en la wheel, así una extensión lo usa igual que
la suite del núcleo, sin copiar `tests/conftest.py`.

    # conftest.py de la suite
    pytest_plugins = ["apolo.pruebas"]

Trae, autouse:
  - `_errorlog_aislado` (sesión): `logs/errors.log` en tmp; sin él, los tests que provocan 4xx o
    inyectan fallos escribían errores FALSOS en el log REAL que se lee al «revisa»;
  - `_sandbox_perezoso` (sesión): `APOLO_SANDBOX_PREWARM=0`, el worker del sandbox arranca con el
    primer script y no con la API;
  - `_sesion_api_aislada` (cada test): deja `apolo.api.session.S` como estaba y cancela el Timer
    del autosave (un test no hereda el documento de otro).
Y a pedido, `extensiones_aisladas`: `apolo.extensiones.cargar()` puede volver a correr dentro
del test (con `APOLO_EXTENSIONES_EXTRA`) y al salir los registros del núcleo quedan como estaban.

Lo que una suite apaga ANTES de importar `apolo` (p. ej. `APOLO_EXTENSIONES=0` en la del núcleo,
que cuenta 59 comandos y 90 tools) va en su conftest, no aquí: este plugin no decide qué se carga.
"""

from __future__ import annotations

import dataclasses
import sys

import pytest


@pytest.fixture(autouse=True, scope="session")
def _errorlog_aislado(tmp_path_factory):
    """Redirige `logs/errors.log` a un directorio temporal. `errorlog` resuelve la ruta al
    IMPORTAR (constantes LOG_DIR/LOG_FILE) y la lee en cada entrada (sin handler abierto:
    varias-maquinas D7), así que basta con parchear las rutas. Alcance de SESIÓN (no por test):
    el autosave debounced corre en un Timer que puede disparar ENTRE tests — con un parche por
    test, ese rezagado escribiría en el log real."""
    from apolo.api import errorlog

    log_dir = tmp_path_factory.mktemp("errorlog")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(errorlog, "LOG_DIR", log_dir)
        mp.setattr(errorlog, "LOG_FILE", log_dir / "errors.log")
        yield log_dir


@pytest.fixture(autouse=True, scope="session")
def _sandbox_perezoso():
    """`APOLO_SANDBOX_PREWARM=0` en toda la suite (plan sandbox-caliente, D7): ningún test corre
    el arranque de la API (un TestClient se presta SIN entrar: entrar abriría la SQLite real),
    pero uno que lo hiciera levantaría un proceso de ~370 MB en paralelo con la suite. Quien
    prueba el precalentado lo enciende con `monkeypatch.setenv`."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("APOLO_SANDBOX_PREWARM", "0")
        yield


@pytest.fixture(autouse=True)
def _sesion_api_aislada():
    """Cada test deja la sesión de la API como la encontró (D11 del plan partir-api-main): al
    terminar cancela el Timer del autosave y devuelve `apolo.api.session.S` (documento activo,
    almacén, proyecto y salud) a sus valores de antes. Sólo actúa si la API ya está importada
    (no la carga en los tests que no la usan) y no crea documentos: restaura los objetos que
    había. Corre su teardown DESPUÉS del de las fixtures del test (las autouse se instancian
    primero), así que una fixture que restaura lo suyo sigue funcionando igual."""
    sesion = sys.modules.get("apolo.api.session")
    previo = None if sesion is None else {
        f.name: getattr(sesion.S, f.name) for f in dataclasses.fields(sesion.S)}
    yield
    autosave = sys.modules.get("apolo.api.autosave")
    if autosave is not None:
        autosave._autosave_sched.cancel()  # sin Timers huérfanos que disparen en otro test
    if previo is not None:
        for campo, valor in previo.items():
            setattr(sesion.S, campo, valor)


@pytest.fixture
def extensiones_aisladas(monkeypatch):
    """`apolo.extensiones` desde cero dentro del test: `cargar()` vuelve a buscar (entry points y
    `APOLO_EXTENSIONES_EXTRA`, que el test fija con `monkeypatch.setenv`) y al salir `REGISTRY`,
    catálogo, modelos de la co-sim, pistas y catálogo del chat quedan como estaban."""
    from apolo import extensiones

    monkeypatch.delenv("APOLO_EXTENSIONES", raising=False)
    with extensiones.aislado():
        yield extensiones
