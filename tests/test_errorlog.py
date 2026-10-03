"""El registro de errores de la suite NO toca el `logs/errors.log` real (conftest)."""

from pathlib import Path


def test_errorlog_redirigido_fuera_del_repo(_errorlog_aislado):
    import logging

    from apolo import paths
    from apolo.api import errorlog

    real = (paths.logs_dir() / "errors.log").resolve()
    errorlog.log_error("test.aislamiento", "línea de prueba aislada")

    assert Path(errorlog.LOG_FILE).resolve() != real
    assert Path(errorlog.LOG_FILE).parent == _errorlog_aislado
    assert "línea de prueba aislada" in errorlog.read_log()
    destinos = {Path(h.baseFilename).resolve()
                for h in logging.getLogger("apolo.errors").handlers
                if isinstance(h, logging.FileHandler)}
    assert destinos and real not in destinos
