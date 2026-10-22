"""Fixtures globales de la suite.

Mínimo a propósito: aísla el registro de errores (sesión) y la SESIÓN de la API (cada test),
y apaga el precalentado del sandbox. El resto del estado global (cachés de proceso, `WS`,
jobs) sigue a cargo de cada test.
"""

from __future__ import annotations

import dataclasses
import sys

import pytest


@pytest.fixture(autouse=True, scope="session")
def _errorlog_aislado(tmp_path_factory):
    """Redirige `logs/errors.log` a un directorio temporal: sin esto, los tests que
    provocan 4xx o inyectan fallos (tortura: autosave «disco lleno (inyectado)», stores
    falsos) escribían cientos de errores FALSOS en el log REAL que el usuario lee al
    «revisa».

    `errorlog` resuelve la ruta al IMPORTAR (constantes LOG_DIR/LOG_FILE) y la lee en cada
    entrada (sin handler abierto: varias-maquinas D7), así que basta con parchear las rutas.
    Alcance de SESIÓN (no por test): el autosave debounced corre en un Timer que puede
    disparar ENTRE tests — con un parche por test, ese rezagado escribiría en el log real."""
    from apolo.api import errorlog

    log_dir = tmp_path_factory.mktemp("errorlog")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(errorlog, "LOG_DIR", log_dir)
        mp.setattr(errorlog, "LOG_FILE", log_dir / "errors.log")
        yield log_dir


@pytest.fixture(autouse=True, scope="session")
def _sandbox_perezoso():
    """`APOLO_SANDBOX_PREWARM=0` en toda la suite: el worker del sandbox arranca con el primer
    script, no con la API (plan sandbox-caliente, D7). Hoy ningún test corre el arranque (un
    TestClient se presta SIN entrar: entrar abriría la SQLite real), pero uno que lo hiciera
    levantaría un proceso de ~370 MB y segundos de CPU en paralelo con la suite. Quien prueba
    el precalentado lo enciende con `monkeypatch.setenv`."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("APOLO_SANDBOX_PREWARM", "0")
        yield


@pytest.fixture(autouse=True, scope="session")
def _publicacion_aislada(tmp_path_factory):
    """La biblioteca de música (`APOLO_MUSICA_DIR`) en una carpeta vacía y la tienda por
    defecto, en toda la suite: `publicar generar` sin `--musica` elige la pista menos usada de
    `~/.apolo/musica` y anota su uso (fabrica-de-publicaciones D9); sin esto, un test usaría la
    biblioteca REAL de la PC y le sumaría usos, y una `APOLO_TIENDA_URL` de la consola cambiaría
    las URL esperadas. Quien prueba la biblioteca pasa su propia carpeta."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("APOLO_MUSICA_DIR", str(tmp_path_factory.mktemp("musica-vacia")))
        mp.delenv("APOLO_TIENDA_URL", raising=False)
        yield


@pytest.fixture(autouse=True)
def _sesion_api_aislada():
    """Cada test deja la sesión de la API como la encontró (D11 del plan
    `docs/plans/partir-api-main.md`): al terminar cancela el Timer del autosave y devuelve
    `apolo.api.session.S` (documento activo, almacén, proyecto y salud) a sus valores de
    antes. Medido en la F0: 250 tests terminaban con otro `api.DOC` y el siguiente heredaba
    ese documento; un test que dependiera de la fuga pasaba o fallaba según el orden.

    Sólo actúa si `apolo.api.session` ya está importado (no carga la API en los tests que
    no la usan) y no crea documentos: restaura los objetos que había. Corre su teardown
    DESPUÉS del de las fixtures del test (las autouse se instancian primero), así que una
    fixture que restaura lo suyo sigue funcionando igual."""
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
