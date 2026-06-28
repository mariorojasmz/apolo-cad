"""Wrapper del sandbox de scripts: se ejecuta como subproceso aislado.

Uso: python -m apolo.agent.script_wrapper <code_file> <out_step> <vars_json_file>

Ejecuta el código con el namespace completo de build123d + math + V (variables
del proyecto resueltas). El script debe asignar la variable `result` (una forma
o una lista de formas). El resultado se exporta a STEP para que el proceso
padre lo importe.
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    code_file, out_step, vars_file = sys.argv[1], sys.argv[2], sys.argv[3]

    import math

    import build123d
    from build123d import Compound, export_step

    namespace: dict = {"__builtins__": __builtins__}
    for name in dir(build123d):
        if not name.startswith("_"):
            namespace[name] = getattr(build123d, name)
    namespace["math"] = math
    with open(vars_file, encoding="utf-8") as fh:
        namespace["V"] = json.load(fh)

    with open(code_file, encoding="utf-8") as fh:
        code = fh.read()

    exec(compile(code, "<script_ia>", "exec"), namespace)  # noqa: S102 - sandbox deliberado

    result = namespace.get("result")
    if result is None:
        print("El script debe asignar la variable 'result' (forma o lista de formas)", file=sys.stderr)
        return 2

    shapes = list(result) if isinstance(result, (list, tuple)) else [result]
    if not shapes:
        print("'result' está vacío", file=sys.stderr)
        return 2
    target = shapes[0] if len(shapes) == 1 else Compound(children=shapes)
    if not hasattr(target, "wrapped"):
        print(f"'result' no es geometría de build123d: {type(result).__name__}", file=sys.stderr)
        return 2
    export_step(target, out_step)
    return 0


if __name__ == "__main__":
    sys.exit(main())
