"""El estado de sesión de la API vive en UN objeto (`apolo.api.session.S`) y `api.DOC` es su
alias (D3 del plan `docs/plans/partir-api-main.md`).

Por qué existe este gate: con `main.py` partido en varios módulos, un global re-exportado se
COPIA por valor — un test que hiciera `api.DOC = d` escribiría en el `__dict__` de `main`
mientras el código movido seguiría leyendo el documento viejo, y el test daría verde sobre
otro documento. Lo impiden cuatro cosas, una por test:

1. `api.DOC` (y los otros 4) leen y ESCRIBEN `S.<campo>`, también con `monkeypatch`;
2. ninguno de los 5 nombres vive en el `__dict__` de `main` (sólo existen como alias);
3. ningún módulo de `apolo/api` los usa como variable suelta ni los declara `global`:
   el código de la API lee `S.<campo>`;
4. ningún test los importa por valor (`from apolo.api.main import DOC` congelaría el
   documento del momento del import).

Y, desde que `main` sólo compone (F6c del plan), el grafo de imports dentro de `apolo.api`:

5. cada módulo importa sólo de su capa de abajo (`CAPAS_API`), ningún router importa a otro y
   NADIE importa `main` — un router que importara `main` sería un ciclo, y uno que leyera un
   nombre de `main` leería la copia vieja de lo que un test reasignó.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import apolo.api.main as api
from apolo.api.session import S
from apolo.doc import Document

RAIZ = Path(__file__).resolve().parents[1]
API_DIR = RAIZ / "core" / "apolo" / "api"
TESTS_DIR = RAIZ / "tests"

#: nombre viejo en `main` → campo de `S`
SESION = {
    "DOC": "doc",
    "STORE": "store",
    "PROJECT_ID": "project_id",
    "AUTOSAVE_ERROR": "autosave_error",
    "STARTUP_ERROR": "startup_error",
}


def _valor_de_prueba(nombre: str):
    # un Document real para DOC (un Timer rezagado del autosave podría leerlo); el resto, un
    # centinela que ningún código confunde con un valor de verdad
    return Document("sesion-alias") if nombre == "DOC" else object()


# ── 1. el alias lee y escribe S ───────────────────────────────────────────────


@pytest.mark.parametrize("nombre", sorted(SESION))
def test_el_alias_de_main_lee_y_escribe_S(nombre):
    campo = SESION[nombre]
    previo = getattr(S, campo)
    nuevo, otro = _valor_de_prueba(nombre), _valor_de_prueba(nombre)
    try:
        setattr(api, nombre, nuevo)  # = `api.DOC = d` de los tests
        assert getattr(S, campo) is nuevo
        assert getattr(api, nombre) is nuevo
        setattr(S, campo, otro)  # = un swap de la API (abrir proyecto)
        assert getattr(api, nombre) is otro
    finally:
        setattr(S, campo, previo)
    assert getattr(api, nombre) is previo


@pytest.mark.parametrize("nombre", sorted(SESION))
def test_monkeypatch_sobre_el_alias_se_deshace(nombre):
    campo = SESION[nombre]
    previo = getattr(S, campo)
    nuevo = _valor_de_prueba(nombre)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(api, nombre, nuevo)
        assert getattr(S, campo) is nuevo
    assert getattr(S, campo) is previo
    with pytest.MonkeyPatch.context() as mp:  # la forma con ruta en texto también
        mp.setattr(f"apolo.api.main.{nombre}", nuevo)
        assert getattr(S, campo) is nuevo
    assert getattr(S, campo) is previo


# ── 2. ninguno vive en el __dict__ de main ────────────────────────────────────


def test_los_nombres_de_sesion_no_viven_en_main():
    assert not set(SESION) & set(vars(api))
    previo = S.doc
    try:
        api.DOC = Document("no-deja-copia")
        assert "DOC" not in vars(api)  # la asignación pasó por la propiedad, no al __dict__
    finally:
        S.doc = previo


# ── 3. la API lee S.<campo>, nunca un global suelto ───────────────────────────


def nombres_sueltos(codigo: str, archivo: str = "<texto>") -> list[str]:
    """`archivo:línea nombre` de cada uso de un nombre de sesión como variable (`Name`) o en
    un `global`/`nonlocal`."""
    out = []
    for n in ast.walk(ast.parse(codigo)):
        if isinstance(n, ast.Name) and n.id in SESION:
            out.append(f"{archivo}:{n.lineno} {n.id}")
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            out += [f"{archivo}:{n.lineno} global {x}" for x in n.names if x in SESION]
    return out


def test_ningun_modulo_de_la_api_usa_los_nombres_de_sesion_sueltos():
    archivos = sorted(API_DIR.rglob("*.py"))
    assert API_DIR / "main.py" in archivos and API_DIR / "session.py" in archivos
    malos = []
    for archivo in archivos:
        rel = archivo.relative_to(RAIZ).as_posix()
        malos += nombres_sueltos(archivo.read_text(encoding="utf-8-sig"), rel)
    assert not malos, (
        "El código de la API lee y swapea `S.<campo>` (apolo.api.session), jamás un global "
        "suelto:\n" + "\n".join(malos))


def test_el_gate_de_nombres_sueltos_caza_cada_forma():
    assert nombres_sueltos("x = DOC.scene")
    assert nombres_sueltos("def f():\n    global PROJECT_ID\n    PROJECT_ID = 1\n")
    assert nombres_sueltos("STORE = None")
    assert nombres_sueltos("f'{AUTOSAVE_ERROR}'")
    assert nombres_sueltos("def f():\n    nonlocal STARTUP_ERROR\n")
    # lo legítimo: el campo de S, el texto y el atributo de otro objeto
    assert not nombres_sueltos("x = S.doc.scene\ny = 'DOC'\nz = api.DOC\n")


# ── 4. ningún test los importa por valor ──────────────────────────────────────


def importes_por_valor(codigo: str, archivo: str = "<texto>") -> list[str]:
    """`from apolo.api.main import DOC` (o cualquiera de los 5): copia el valor del momento."""
    out = []
    for n in ast.walk(ast.parse(codigo)):
        if isinstance(n, ast.ImportFrom) and n.module == "apolo.api.main":
            out += [f"{archivo}:{n.lineno} {a.name}" for a in n.names if a.name in SESION]
    return out


def test_ningun_test_importa_la_sesion_por_valor():
    malos = []
    for archivo in sorted(TESTS_DIR.rglob("*.py")):
        rel = archivo.relative_to(RAIZ).as_posix()
        malos += importes_por_valor(archivo.read_text(encoding="utf-8-sig"), rel)
    assert not malos, (
        "Usa `api.DOC` (alias vivo de `S.doc`), no `from apolo.api.main import DOC`:\n"
        + "\n".join(malos))


def test_el_gate_de_importes_caza_cada_forma():
    assert importes_por_valor("from apolo.api.main import DOC")
    assert importes_por_valor("def f():\n    from apolo.api.main import _x, STORE as s\n")
    assert not importes_por_valor("from apolo.api.main import _cached_render")
    assert not importes_por_valor("import apolo.api.main as api\nx = api.DOC")


# ── 5. el grafo de imports dentro de apolo.api ────────────────────────────────

#: módulo de `apolo.api` → los módulos de `apolo.api` que PUEDE importar (lista cerrada; los
#: routers, como `routers.*`). Capas de abajo arriba: hojas (`errorlog`, `jobs`, `ws`,
#: `guardia_documento`) → `session` → `autosave` → `scene` → `common` → `sims`/`fea_runs` →
#: routers → `main`. Un router no importa a otro ni a `autosave`/`ws`/`jobs`/
#: `guardia_documento`: lo de transporte le llega de `common`. `main` es la raíz de
#: composición: importa lo que necesite, pero NADIE lo importa a él.
CAPAS_API = {
    "": set(),  # apolo/api/__init__.py
    "errorlog": set(),
    "jobs": set(),
    "ws": set(),
    "guardia_documento": set(),  # recibe el documento: no lee `S` (chat-cliente-igual D3)
    "session": {"errorlog"},
    "autosave": {"session", "ws", "errorlog"},
    "scene": {"session"},
    "common": {"session", "scene", "autosave", "ws", "jobs", "guardia_documento"},
    "sims": {"session", "common"},
    "fea_runs": {"session", "autosave", "guardia_documento"},
    "routers": set(),
    "routers.*": {"common", "scene", "session", "sims", "fea_runs"},
}


def importes_api(codigo: str, modulo: str, paquete: bool = False) -> set[str]:
    """Nombres con punto, relativos a `apolo.api`, que importa el módulo `modulo` de
    `apolo.api` (también los imports perezosos dentro de funciones). `from .common import x`
    da `common` y `common.x` (así `from .routers import core` da `routers.core`)."""
    partes = ["apolo", "api"] + [p for p in modulo.split(".") if p]
    base_paquete = partes if paquete else partes[:-1]
    out: set[str] = set()
    for n in ast.walk(ast.parse(codigo)):
        if isinstance(n, ast.ImportFrom):
            raiz = base_paquete[: len(base_paquete) - n.level + 1] if n.level else []
            mod = ".".join(raiz + ([n.module] if n.module else []))
            candidatos = [mod] + [f"{mod}.{a.name}" for a in n.names]
        elif isinstance(n, ast.Import):
            candidatos = [a.name for a in n.names]
        else:
            continue
        out |= {c.removeprefix("apolo.api.") for c in candidatos if c.startswith("apolo.api.")}
    return out


def _capa(modulo: str) -> set[str] | None:
    if modulo in CAPAS_API:
        return CAPAS_API[modulo]
    return CAPAS_API["routers.*"] if modulo.startswith("routers.") else None


def violaciones_de_capas(grafo: dict[str, set[str]]) -> list[str]:
    """`grafo`: módulo → lo que importa (`importes_api`). Sólo cuentan las dependencias que
    son módulos del grafo (`common.x` es un nombre de `common`, no un módulo)."""
    malos = []
    for modulo, deps in sorted(grafo.items()):
        if modulo == "main":
            continue
        permitidos = _capa(modulo)
        if permitidos is None:
            malos.append(f"{modulo}: módulo de apolo.api sin capa en CAPAS_API")
            continue
        malos += [f"{modulo} importa {d}" for d in sorted((deps & set(grafo)) - permitidos)]
    return malos


def _grafo_api() -> dict[str, set[str]]:
    grafo = {}
    for archivo in sorted(API_DIR.rglob("*.py")):
        partes = list(archivo.relative_to(API_DIR).with_suffix("").parts)
        paquete = partes[-1] == "__init__"
        modulo = ".".join(partes[:-1] if paquete else partes)
        grafo[modulo] = importes_api(archivo.read_text(encoding="utf-8-sig"), modulo, paquete)
    return grafo


def test_el_grafo_de_imports_de_la_api_respeta_sus_capas():
    grafo = _grafo_api()
    assert {"", "main", "session", "common", "scene", "routers", "routers.core"} <= set(grafo)
    malos = violaciones_de_capas(grafo)
    assert not malos, (
        "Imports de apolo.api fuera de capas (CAPAS_API en este archivo):\n" + "\n".join(malos))


def test_main_compone_los_routers_y_nadie_importa_main():
    grafo = _grafo_api()
    routers = {m for m in grafo if m.startswith("routers.")}
    assert len(routers) == 11 and routers <= grafo["main"]
    assert not [m for m, deps in grafo.items() if m != "main" and "main" in deps]


def test_el_gate_de_capas_caza_cada_forma():
    assert "main" in importes_api("from ..main import app", "routers.core")
    assert "autosave" in importes_api("def f():\n    from .autosave import _x\n", "common")
    assert "main" in importes_api("import apolo.api.main as api", "scene")
    assert {"routers.core", "routers.fea"} <= importes_api("from .routers import core, fea",
                                                           "main")
    assert "scene" in importes_api("from ..scene import x", "routers.core")
    grafo = {"main": set(), "session": {"errorlog"}, "errorlog": set(), "scene": {"common"},
             "common": set(), "routers.core": {"routers.fea", "autosave", "common.x"},
             "routers.fea": {"main"}, "autosave": set(), "nuevo": set()}
    malos = violaciones_de_capas(grafo)
    assert "scene importa common" in malos
    assert "routers.core importa routers.fea" in malos
    assert "routers.core importa autosave" in malos
    assert "routers.fea importa main" in malos
    assert any(m.startswith("nuevo:") for m in malos)
    assert not [m for m in malos if m.startswith(("session", "main"))]
