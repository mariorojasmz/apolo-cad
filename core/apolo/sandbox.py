"""Sandbox de ejecución de scripts build123d (IA Nivel 2).

El código se ejecuta en un subproceso aislado con timeout y el resultado
vuelve como STEP. La frontera de seguridad principal del producto es la
revisión humana: el usuario ve el código en la tarjeta de acción antes de
aceptar. El sandbox añade aislamiento de fallos y límite de tiempo.

Caché LRU por hash(código + variables): la regeneración del documento no
re-ejecuta scripts que no cambiaron.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path

SCRIPT_TIMEOUT_S = 60
_CACHE_MAX = 32
_cache: OrderedDict[str, bytes] = OrderedDict()


class ScriptError(Exception):
    pass


def _cache_key(code: str, variables: dict) -> str:
    payload = code + "\n#vars#" + json.dumps(variables, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_script_to_step(code: str, variables: dict | None = None) -> bytes:
    """Ejecuta el script en el sandbox y devuelve los bytes del STEP resultante."""
    variables = variables or {}
    key = _cache_key(code, variables)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]

    try:
        compile(code, "<script_ia>", "exec")
    except SyntaxError as exc:
        raise ScriptError(f"Error de sintaxis en el script (línea {exc.lineno}): {exc.msg}") from exc

    with tempfile.TemporaryDirectory(prefix="apolo_sandbox_") as tmp:
        tmp_path = Path(tmp)
        code_file = tmp_path / "script.py"
        out_step = tmp_path / "result.step"
        vars_file = tmp_path / "vars.json"
        code_file.write_text(code, encoding="utf-8")
        vars_file.write_text(json.dumps(variables, default=str), encoding="utf-8")

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "apolo.agent.script_wrapper", str(code_file), str(out_step), str(vars_file)],
                capture_output=True,
                text=True,
                timeout=SCRIPT_TIMEOUT_S,
                cwd=str(tmp_path),
            )
        except subprocess.TimeoutExpired as exc:
            raise ScriptError(f"El script superó el límite de {SCRIPT_TIMEOUT_S}s") from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            # quedarse con las últimas líneas útiles del traceback
            lines = [l for l in stderr.splitlines() if l.strip()]
            detail = "\n".join(lines[-6:]) if lines else f"código de salida {proc.returncode}"
            raise ScriptError(f"El script falló:\n{detail}")
        if not out_step.exists():
            raise ScriptError("El script terminó sin producir geometría")
        data = out_step.read_bytes()

    _cache[key] = data
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return data


def step_bytes_to_shape(data: bytes):
    """Importa un STEP (bytes) como forma de build123d."""
    from build123d import import_step

    with tempfile.TemporaryDirectory(prefix="apolo_step_") as tmp:
        path = Path(tmp) / "in.step"
        path.write_bytes(data)
        return import_step(str(path))


def run_script_to_shape(code: str, variables: dict | None = None):
    return step_bytes_to_shape(run_script_to_step(code, variables))
