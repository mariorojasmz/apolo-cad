"""Fixtures globales de la suite.

Mínimo a propósito: SOLO aísla el registro de errores. El resto del estado global
(api.DOC/STORE/PROJECT_ID, cachés de proceso) sigue a cargo de cada test.
"""

from __future__ import annotations

import logging

import pytest


@pytest.fixture(autouse=True, scope="session")
def _errorlog_aislado(tmp_path_factory):
    """Redirige `logs/errors.log` a un directorio temporal: sin esto, los tests que
    provocan 4xx o inyectan fallos (tortura: autosave «disco lleno (inyectado)», stores
    falsos) escribían cientos de errores FALSOS en el log REAL que el usuario lee al
    «revisa».

    `errorlog` resuelve la ruta al IMPORTAR (constantes LOG_DIR/LOG_FILE) y cachea el
    logger con su FileHandler (global `_logger` + handlers del logger «apolo.errors»),
    así que se parchean las tres cosas: rutas, caché y handlers ya enganchados.
    Alcance de SESIÓN (no por test): el autosave debounced corre en un Timer que puede
    disparar ENTRE tests — con un parche por test, ese rezagado re-crearía el handler
    sobre el log real."""
    from apolo.api import errorlog

    logger = logging.getLogger("apolo.errors")
    previos = logger.handlers[:]
    for h in previos:
        logger.removeHandler(h)
    log_dir = tmp_path_factory.mktemp("errorlog")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(errorlog, "LOG_DIR", log_dir)
        mp.setattr(errorlog, "LOG_FILE", log_dir / "errors.log")
        mp.setattr(errorlog, "_logger", None)
        yield log_dir
        for h in logger.handlers[:]:
            logger.removeHandler(h)
            h.close()
    for h in previos:
        logger.addHandler(h)
