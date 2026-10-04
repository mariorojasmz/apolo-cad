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
