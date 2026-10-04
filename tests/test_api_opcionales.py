"""Importar la API no carga las librerías pesadas u opcionales: se cargan al usarlas.

gmsh, scikit-fem y meshio (FEA), MuJoCo y Pillow (física, GIF), VTK y matplotlib (render),
PlaneGCS (croquis), anthropic (chat) y mcp viven en imports PEREZOSOS dentro de las
funciones: así la API arranca sin los extras instalados y sin pagar segundos de import que
nadie pidió. Al partir `api/main.py` en módulos (plan `docs/plans/partir-api-main.md`), un
import que suba a nivel de módulo cambiaría el arranque sin que ningún otro test lo note.
Medido en la F0 de ese plan: de esta lista, `import apolo.api.main` no carga ninguno.

Corre en un proceso aparte: en el de la suite, otros tests ya los importaron.
"""

from __future__ import annotations

import json
import subprocess
import sys

#: Módulos que `import apolo.api.main` NO debe cargar (medido el 2026-10-03, F0).
OPCIONALES = (
    "gmsh", "skfem", "meshio",   # FEA (extra `fea`)
    "mujoco", "PIL",             # física y GIF (extra `physics`)
    "vtk", "vtkmodules", "matplotlib",  # render
    "planegcs",                  # croquis
    "anthropic", "mcp",          # chat y MCP
)


def test_importar_la_api_no_carga_opcionales():
    codigo = (
        "import json, sys\n"
        "import apolo.api.main\n"
        f"print(json.dumps(sorted(m for m in {OPCIONALES!r} if m in sys.modules)))\n"
    )
    res = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True,
                         text=True, timeout=300)
    assert res.returncode == 0, res.stderr[-2000:]
    cargados = json.loads(res.stdout.strip().splitlines()[-1])
    assert cargados == [], (
        f"`import apolo.api.main` carga {cargados}: un import perezoso subió a nivel de "
        "módulo (devuélvelo a la función que lo usa)."
    )
