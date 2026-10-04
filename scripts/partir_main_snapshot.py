"""Andamio TEMPORAL del plan `docs/plans/partir-api-main.md` (F1): congela el contrato
EXTERNO de `apolo.api.main` ANTES de partirlo, para que cada fase demuestre que por fuera
nada cambió. Se borra en F7 junto con `tests/test_partir_main_contrato.py`.

Congela en `tests/data/partir_main/`:
  (a) `rutas.json`      método(s), path y nombre de cada ruta, EN ORDEN (Starlette atiende
                        la primera que casa: el orden es contrato);
  (b) `openapi.json`    el esquema OpenAPI completo (operationId = nombre de función,
                        nombres de los modelos pydantic);
  (c) `textos.json`     las constantes de texto ≥ 12 caracteres de `main.py` (sin
                        docstrings): al mover código, cada una tiene que seguir existiendo en
                        `api/` o en `services/` — un texto de error perdido o cambiado lo caza;
  (d) `respuestas.json` ≈ 70 llamadas `TestClient` sobre dos documentos deterministas
                        (status, cabeceras clave y cuerpo normalizado), con errores a
                        propósito, más la salida de los mapas que F2+ mueven a `services`.

Uso, desde la raíz del worktree y con SU código (raíz CLAUDE.md § Sesiones concurrentes):
    $env:PYTHONPATH = "$PWD\\core"
    python -B scripts/partir_main_snapshot.py                 # congela
    python -B scripts/partir_main_snapshot.py --salida DIR    # escribe en otra carpeta
Congelar SOLO desde el código sin tocar de la base, tras 3 corridas idénticas.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "tests" / "data" / "partir_main"
API_DIR = RAIZ / "core" / "apolo" / "api"
SERVICES_DIR = RAIZ / "core" / "apolo" / "services"
MAIN_PY = API_DIR / "main.py"

TEXTO_MIN = 12
_SESION = ("DOC", "STORE", "PROJECT_ID", "AUTOSAVE_ERROR", "STARTUP_ERROR")


# ------------------------------------------------------------------ (a) y (b)
def capturar_rutas(app) -> list[dict]:
    """Las rutas de `app` EN ORDEN; los Mount (la UI estática, que depende de que exista
    `ui/dist`) quedan fuera."""
    out = []
    for r in app.routes:
        if type(r).__name__ == "Mount":
            continue
        out.append({
            "tipo": type(r).__name__,
            "metodos": sorted(getattr(r, "methods", None) or []),
            "path": r.path,
            "nombre": r.name,
        })
    return out


def capturar_openapi(app) -> dict:
    return json.loads(json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True))


# ------------------------------------------------------------------------ (c)
def textos_de(archivos: list[Path]) -> set[str]:
    """Constantes de texto ≥ TEXTO_MIN caracteres (incluidas las partes fijas de un
    f-string), sin docstrings ni strings sueltos como sentencia."""
    out: set[str] = set()
    for archivo in archivos:
        tree = ast.parse(archivo.read_text(encoding="utf-8"))
        sueltos = {id(n.value) for n in ast.walk(tree)
                   if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and len(n.value) >= TEXTO_MIN and id(n) not in sueltos):
                out.add(n.value)
    return out


def fuentes_api() -> list[Path]:
    """Dónde puede vivir hoy un texto que nació en `main.py`: el paquete `api` (routers
    incluidos) y `services`."""
    archivos = sorted(API_DIR.rglob("*.py"))
    if SERVICES_DIR.is_dir():
        archivos += sorted(SERVICES_DIR.rglob("*.py"))
    return archivos


# ------------------------------------------------------------------------ (d)
def _normalizar(obj, *, ordenar: bool = False):
    """Cuerpo comparable entre procesos: floats a 6 decimales; `epoch` (uuid por proceso),
    `rev` (contador de proceso) y `autosave_pending` (estado del programador) se
    reemplazan por su tipo. `ordenar` ordena las listas de escalares y las listas de
    listas (las que salen de iterar un set, p. ej. `components` de soundness)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("epoch", "rev", "autosave_pending"):
                out[k] = f"<{type(v).__name__}>"
            else:
                out[k] = _normalizar(v, ordenar=ordenar)
        return out
    if isinstance(obj, list):
        items = [_normalizar(v, ordenar=ordenar) for v in obj]
        if ordenar and (all(isinstance(v, (str, int, float)) for v in items)
                        or all(isinstance(v, list) for v in items)):
            items = sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
        return items
    if isinstance(obj, float):
        return round(obj, 6)
    return obj


_FECHAS = (re.compile(r"\d{4}-\d{2}-\d{2}"), re.compile(r"\d{2}/\d{2}/\d{4}"))


def _texto_pdf(content: bytes) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    lineas: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        texto = page.extract_text() or ""
        for f in _FECHAS:
            texto = f.sub("<fecha>", texto)
        lineas.append(f"--- página {i}")
        lineas += [ln.rstrip() for ln in texto.splitlines() if ln.strip()]
    return lineas


def _resumen(nombre: str, obj) -> dict:
    """Huella de un cuerpo grande que NO es de `main` (lo arma otro paquete): sólo su
    forma, para no atar el andamio al contenido que otros planes cambian."""
    if isinstance(obj, list):
        return {"lista": len(obj)}
    if isinstance(obj, dict):
        return {"claves": sorted(obj)}
    return {"tipo": type(obj).__name__, "sha": hashlib.sha256(repr(obj).encode()).hexdigest()}


def doc_a():
    """Documento determinista con lo que alimenta los mapas que se mudan: soldadura
    (datum), perno + barreno Ø13.5 de paso (GD&T), fit por nombre y por taladro, rosca,
    ground (instalación), cama y pieza de servicio por nombre, grupo, cadena de cotas por
    id (tolerancia justificada) y carga."""
    from apolo.doc import Document

    d = Document("partir-main-A")
    d.execute("set_variable", {"name": "L", "expression": "400"})
    placa = d.execute("create_box", {"name": "Placa base", "width": "=L", "depth": 200,
                                     "height": 12})
    costilla = d.execute("create_box", {"name": "Costilla (+Y)", "width": 20, "depth": 100,
                                        "height": 60, "position": {"x": 120, "z": 36}})
    eje = d.execute("create_cylinder", {"name": "Eje motriz Ø35 h7", "radius": 17.5,
                                        "height": 300, "axis": "y",
                                        "position": {"x": -100, "z": 40}})
    d.execute("drill_hole", {"feature": placa, "position": {"x": -150, "y": 60, "z": 6},
                             "axis": "-z", "diameter": 13.5})
    d.execute("drill_hole", {"feature": placa, "position": {"x": 150, "y": 60, "z": 6},
                             "axis": "-z", "thread": "M8"})
    d.execute("drill_hole", {"feature": costilla, "position": {"x": 110, "y": 0, "z": 50},
                             "axis": "x", "diameter": 20, "fit": "H7"})
    perno = d.execute("create_cylinder", {"name": "Perno M12", "radius": 6, "height": 40,
                                          "position": {"x": -150, "y": 60, "z": 0}})
    # roles por NOMBRE: la cama (altura de trabajo) y una pieza de servicio (holgura)
    d.execute("create_box", {"name": "Mesa de carga", "width": 200, "depth": 100,
                             "height": 4, "position": {"x": 120, "z": 68}})
    d.execute("create_cylinder", {"name": "Tambor de cola", "radius": 30, "height": 150,
                                  "axis": "y", "position": {"x": -100, "z": 120}})
    d.execute("fasten", {"name": "w1", "a": placa, "b": costilla, "kind": "soldadura",
                         "throat_mm": 4, "length_mm": 100})
    d.execute("fasten", {"name": "p1", "a": placa, "b": perno, "kind": "perno",
                         "size": "M12"})
    d.execute("fasten", {"name": "e1", "a": costilla, "b": eje, "kind": "contacto"})
    d.execute("ground", {"name": "g1", "feature": placa})
    d.execute("create_group", {"name": "Bastidor", "members": [placa, costilla],
                               "role": "estructura"})
    d.set_stackup("espesor placa", [{"id": placa, "eje": "z", "sentido": 1,
                                     "tol": {"pm": 0.1}}], {"entre": [11, 13]})
    d.set_requirements({"carga_kg": 25})
    return d


def doc_b():
    from apolo.doc import Document

    return Document("partir-main-B")


# (id, doc, método, path, kwargs de TestClient, modo de cuerpo)
#   modo: "json" | "json-ordenado" | "forma" | "pdf" | "sin-cuerpo"
LLAMADAS: list[tuple] = [
    ("health", "A", "GET", "/api/health", {}, "json"),
    ("scene-summary", "A", "GET", "/api/scene/summary", {}, "json"),
    ("scene-ids", "A", "GET", "/api/scene", {"params": {"ids": "c2,Bastidor"}}, "json"),
    ("scene-name", "A", "GET", "/api/scene", {"params": {"name": "PLACA"}}, "json"),
    ("document", "A", "GET", "/api/document", {}, "json"),
    ("groups", "A", "GET", "/api/groups", {}, "json"),
    ("find-type", "A", "GET", "/api/commands", {"params": {"type": "create_box"}}, "json"),
    ("find-feature", "A", "GET", "/api/commands", {"params": {"feature": "c2"}}, "json"),
    ("find-sin-filtro", "A", "GET", "/api/commands", {}, "json"),
    ("find-404-sugerencia", "A", "GET", "/api/commands", {"params": {"feature": "c22"}}, "json"),
    ("near-feature", "A", "GET", "/api/near", {"params": {"feature": "c2", "radius": 30}},
     "json"),
    ("near-sin-modo", "A", "GET", "/api/near", {}, "json"),
    ("near-point-malo", "A", "GET", "/api/near", {"params": {"point": "[1,2]"}}, "json"),
    ("measure", "A", "POST", "/api/measure", {"json": {"a": "c2", "b": "c3"}}, "json"),
    ("measure-404", "A", "POST", "/api/measure", {"json": {"a": "c2", "b": "placa"}}, "json"),
    ("topology-404", "A", "GET", "/api/features/c99/topology", {}, "json"),
    ("topology-anclas", "A", "GET", "/api/features/c3/topology",
     {"params": {"only": "anclas"}}, "json"),
    ("mass", "A", "GET", "/api/mass-properties", {}, "json"),
    ("mass-404", "A", "GET", "/api/mass-properties", {"params": {"ids": "c2,cNO"}}, "json"),
    ("bom", "A", "GET", "/api/bom", {}, "json"),
    ("bom-grupo", "A", "GET", "/api/bom", {"params": {"by_group": "true"}}, "json"),
    ("costing", "A", "GET", "/api/costing.json", {}, "json"),
    ("cutlist", "A", "GET", "/api/cutlist.json", {}, "json"),
    ("nesting-1d", "A", "GET", "/api/nesting.json",
     {"params": {"mode": "1d", "stock_w": 6000}}, "json"),
    ("connectivity", "A", "GET", "/api/connectivity", {}, "json"),
    ("mates", "A", "GET", "/api/mates", {}, "json"),
    ("constraints", "A", "GET", "/api/constraints", {}, "json"),
    ("kinematics", "A", "GET", "/api/kinematics", {}, "json"),
    ("motion", "A", "GET", "/api/motion", {}, "json"),
    ("requirements", "A", "GET", "/api/requirements", {}, "json"),
    ("stackup", "A", "GET", "/api/stackup", {}, "json"),
    ("stackup-auto", "A", "GET", "/api/stackup", {"params": {"scope": "auto"}}, "json"),
    ("stackup-scope-x", "A", "GET", "/api/stackup", {"params": {"scope": "x"}}, "json"),
    ("verify", "A", "POST", "/api/verify", {"json": {"checks": [
        {"tipo": "distancia", "a": "c2", "b": "c3", "max": 0.5},
        {"tipo": "bbox", "id": "c2", "eje": "x", "entre": [399, 401]},
        {"tipo": "sin_interferencia", "ids": ["Bastidor"]},
        {"tipo": "existe", "name": "costilla"},
    ]}}, "json"),
    ("verify-errores", "A", "POST", "/api/verify", {"json": {"checks": [
        {"tipo": "distancia", "a": "c2", "b": "c33", "max": 1},
        {"tipo": "volumen", "id": "c2", "maximo": 3},
        {"tipo": "distancia", "a": "c2", "b": "c3", "joint_values": {"nojunta": 5}},
    ]}}, "json"),
    ("checks", "A", "POST", "/api/checks", {"json": {}}, "json-ordenado"),
    ("delivery", "A", "POST", "/api/delivery-check", {"json": {}}, "json-ordenado"),
    ("dof", "A", "GET", "/api/assembly/dof", {}, "json"),
    ("soundness", "A", "POST", "/api/assembly/soundness", {"json": {}}, "json-ordenado"),
    ("autodetect", "A", "POST", "/api/assembly/autodetect", {}, "json-ordenado"),
    ("auto-group-dry", "A", "POST", "/api/assembly/auto-group", {"json": {"dry_run": True}},
     "json"),
    ("fits", "A", "GET", "/api/fits", {"params": {"nominal": 35, "hole": "H7",
                                                 "shaft": "g6"}}, "json"),
    ("fits-400", "A", "GET", "/api/fits", {"params": {"nominal": 35}}, "json"),
    ("threads", "A", "GET", "/api/threads", {"params": {"size": "M8"}}, "json"),
    ("threads-400", "A", "GET", "/api/threads", {"params": {"size": "M7"}}, "json"),
    ("resolve-expr", "A", "GET", "/api/resolve-expression", {"params": {"expr": "L*2+1"}},
     "json"),
    ("expr-grammar", "A", "GET", "/api/expression-grammar", {}, "json"),
    ("preview-data", "A", "POST", "/api/commands/preview", {"json": {"data": True, "actions": [
        {"type": "create_box", "params": {"name": "Fantasma", "width": 50, "depth": 50,
                                          "height": 50, "position": {"x": 120, "z": 36}}}]}},
     "json"),
    ("batch-contrato-falla", "A", "POST", "/api/commands/batch", {"json": {
        "actions": [{"type": "create_box", "params": {"name": "Tapa", "width": 50,
                                                      "depth": 50, "height": 10}}],
        "expect": [{"tipo": "bbox", "id": "$1", "eje": "x", "entre": [1, 2]}]}}, "json"),
    ("edit-404", "A", "PUT", "/api/commands/c99", {"json": {"params": {"width": 3}}}, "json"),
    ("batch-get-405", "A", "GET", "/api/commands/batch", {}, "json"),
    ("jobs-nope", "A", "GET", "/api/jobs/nope", {}, "json"),
    ("schema-404", "A", "GET", "/api/schemas/no_existe", {}, "json"),
    ("schema-persona-400", "A", "GET", "/api/schemas", {"params": {"vista": "x"}}, "forma"),
    ("fea-asm-vacio", "A", "POST", "/api/fea/assembly", {"json": {}}, "json"),
    ("fea-asm-grupo-404", "A", "POST", "/api/fea/assembly", {"json": {"group": "NoHay"}},
     "json"),
    ("fea-static-404", "A", "POST", "/api/fea/static",
     {"json": {"feature_id": "cX", "fixed": {"mode": "cara", "face": "base"}}}, "json"),
    ("fea-group-fringe-url", "A", "GET", "/api/fea/group/fringe.png", {}, "json"),
    ("fea-pieza-404", "A", "GET", "/api/fea/c2", {}, "json"),
    ("fea-grupo-fringe-404", "A", "GET", "/api/fea/group/Bastidor/fringe.png", {}, "json"),
    ("fea-pieza-fringe-404", "A", "GET", "/api/fea/c2/fringe.png", {}, "json"),
    ("sketch-drag-404", "A", "POST", "/api/sketch/drag",
     {"json": {"sketch": {"points": {}}, "point_id": "p9", "target_xy": [0, 0]}}, "json"),
    ("render-pan-400", "A", "GET", "/api/render.png", {"params": {"pan": "1"}}, "json"),
    ("render-isolate-400", "A", "GET", "/api/render.png",
     {"params": {"isolate": "cNO"}}, "json"),
    ("drawing-spec-isolate-400", "A", "POST", "/api/drawing/spec",
     {"json": {"isolate": ["cNO"]}}, "json"),
    ("drawing-spec-fit-400", "A", "POST", "/api/drawing/spec",
     {"json": {"hole_fits": {"veinte": "H7"}}}, "json"),
    ("sheetmetal-400", "A", "GET", "/api/sheetmetal/c2/flat.svg", {}, "json"),
    ("drawing-svg", "A", "GET", "/api/drawing.svg", {}, "sin-cuerpo"),
    ("drawingset-pdf", "A", "GET", "/api/drawingset.pdf", {}, "pdf"),
    ("calc-report", "A", "GET", "/api/calc-report.pdf", {}, "pdf"),
    ("bom-csv", "A", "GET", "/api/bom.csv", {}, "sin-cuerpo"),
    ("guidelines", "A", "GET", "/api/design-guidelines", {}, "forma"),
    ("schemas-persona", "A", "GET", "/api/schemas", {"params": {"vista": "persona"}}, "forma"),
    # documento vacío: estados sin proyecto / sin piezas
    ("b-health", "B", "GET", "/api/health", {}, "json"),
    ("b-scene", "B", "GET", "/api/scene", {}, "json"),
    ("b-delta", "B", "POST", "/api/scene/delta", {"json": {"epoch": "viejo"}}, "json"),
    ("b-calc-report-400", "B", "GET", "/api/calc-report.pdf", {}, "json"),
    ("b-export-step-400", "B", "GET", "/api/export/step", {}, "json"),
    ("b-delivery", "B", "POST", "/api/delivery-check", {"json": {}}, "json"),
    ("b-revisions-503", "B", "POST", "/api/revisions", {"json": {}}, "json"),
    ("b-projects-503", "B", "GET", "/api/projects", {}, "json"),
    ("b-color-vacio", "B", "POST", "/api/features/color", {"json": {"ids": []}}, "json"),
    ("b-conexion-404", "B", "POST", "/api/connections/remove", {"json": {"names": ["x"]}},
     "json"),
    ("b-variable-404", "B", "DELETE", "/api/variables/nope", {}, "json"),
    ("b-motion-gif-404", "B", "POST", "/api/motion.gif", {"json": {"name": "nope"}}, "json"),
    ("b-urdf-400", "B", "GET", "/api/export/urdf", {}, "json"),
]


def _cuerpo(resp, modo: str):
    if modo == "sin-cuerpo":
        return None
    if modo == "pdf":
        if resp.headers.get("content-type", "").startswith("application/pdf"):
            return _texto_pdf(resp.content)
        return resp.json()
    try:
        data = resp.json()
    except ValueError:
        return {"no-json": hashlib.sha256(resp.content).hexdigest()}
    if modo == "forma" and resp.status_code == 200:
        return _resumen("cuerpo", data)
    return _normalizar(data, ordenar=(modo == "json-ordenado"))


def _llamar(client, metodo: str, path: str, kwargs: dict, modo: str) -> dict:
    resp = client.request(metodo, path, **kwargs)
    entrada = {
        "status": resp.status_code,
        "content_type": resp.headers.get("content-type"),
        "cuerpo": _cuerpo(resp, modo),
    }
    for h in ("allow", "content-disposition"):
        if h in resp.headers:
            entrada[h] = resp.headers[h]
    return entrada


def _mapas(api, doc) -> dict:
    """Salida de los mapas de planos/instalación/stack-up que F2 muda a `services`
    (por sus nombres de compatibilidad en `main`: D4)."""
    datos, anclada = api._installation_data(doc)
    salida = {
        "piece_datum_sides": api._piece_datum_sides(doc),
        "piece_datum_frame": api._piece_datum_frame(doc),
        "piece_pos_tols": {k: {str(d): t for d, t in v.items()}
                           for k, v in api._piece_pos_tols(doc).items()},
        "piece_dim_tols": api._piece_dim_tols(doc),
        "feature_fit_maps": {k: {str(d): c for d, c in v.items()}
                             for k, v in api._feature_fit_maps(doc).items()},
        "hole_fit_map": {str(k): v for k, v in api._hole_fit_map(doc).items()},
        "scene_fit_map": {str(k): v for k, v in api._scene_fit_map(doc, doc.scene).items()},
        "hole_thread_map": {str(k): v for k, v in api._hole_thread_map(doc).items()},
        "thread_schedule": api._thread_schedule(doc),
        "installation_data": datos,
        "installation_anclada": sorted(anclada),
        "stackup_rules": api._stackup_rules(),
    }
    return json.loads(json.dumps(_normalizar(salida), ensure_ascii=False, default=list))


@contextlib.contextmanager
def _sin_montajes(app):
    """La UI estática (`app.mount("/", …)`) sólo existe si hay `ui/dist` (tras `npm run
    build`): con ella, una URL de la API sin ruta para ese método la atiende el Mount (404
    «Not Found») en vez del 405 + `Allow` de la API. Las respuestas se capturan SIN montajes
    —lo congelado no depende del entorno— y se reponen en su sitio al terminar."""
    rutas = app.router.routes
    montajes = [(i, r) for i, r in enumerate(rutas) if type(r).__name__ == "Mount"]
    for i, _ in reversed(montajes):
        del rutas[i]
    try:
        yield
    finally:
        for i, r in montajes:
            rutas.insert(i, r)


def capturar_respuestas(api) -> list[dict]:
    """Corre LLAMADAS (y los mapas) con los dos documentos y devuelve las respuestas
    normalizadas. Restaura el estado de sesión de la API al terminar."""
    from fastapi.testclient import TestClient

    previo = {n: getattr(api, n) for n in _SESION}
    docs = {"A": doc_a(), "B": doc_b()}
    out: list[dict] = []
    try:
        api.STORE = None
        api.PROJECT_ID = None
        api.AUTOSAVE_ERROR = None
        api.STARTUP_ERROR = None
        client = TestClient(api.app, raise_server_exceptions=False)
        with _sin_montajes(api.app):
            for ident, cual, metodo, path, kwargs, modo in LLAMADAS:
                api.DOC = docs[cual]
                entrada = {"id": ident, "doc": cual, "metodo": metodo, "path": path}
                entrada.update(_llamar(client, metodo, path, kwargs, modo))
                out.append(entrada)
        api.DOC = docs["A"]
        out.append({"id": "mapas", "doc": "A", "cuerpo": _mapas(api, docs["A"])})
    finally:
        for n, v in previo.items():
            setattr(api, n, v)
    return out


# ------------------------------------------------------------------------ main
@contextlib.contextmanager
def _errorlog_temporal():
    """Fuera de pytest no hay conftest: los 4xx a propósito NO deben ir al
    `logs/errors.log` real que se lee al «revisa»."""
    import logging

    from apolo.api import errorlog

    with tempfile.TemporaryDirectory() as tmp:
        viejo = (errorlog.LOG_DIR, errorlog.LOG_FILE, errorlog._logger)
        logger = logging.getLogger("apolo.errors")
        handlers = logger.handlers[:]
        for h in handlers:
            logger.removeHandler(h)
        errorlog.LOG_DIR, errorlog.LOG_FILE = Path(tmp), Path(tmp) / "errors.log"
        errorlog._logger = None
        try:
            yield
        finally:
            for h in logger.handlers[:]:
                logger.removeHandler(h)
                h.close()
            for h in handlers:
                logger.addHandler(h)
            errorlog.LOG_DIR, errorlog.LOG_FILE, errorlog._logger = viejo


def _escribir(ruta: Path, data) -> None:
    ruta.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
                    encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", type=Path, default=DATOS)
    args = ap.parse_args(argv)

    import apolo.api.main as api

    if Path(api.__file__).resolve() != MAIN_PY.resolve():
        print(f"apolo.api.main viene de {api.__file__}, no de este árbol: "
              "exporta PYTHONPATH=<worktree>\\core", file=sys.stderr)
        return 2
    args.salida.mkdir(parents=True, exist_ok=True)
    with _errorlog_temporal():
        respuestas = capturar_respuestas(api)
    _escribir(args.salida / "rutas.json", capturar_rutas(api.app))
    _escribir(args.salida / "openapi.json", capturar_openapi(api.app))
    _escribir(args.salida / "textos.json", sorted(textos_de([MAIN_PY])))
    _escribir(args.salida / "respuestas.json", respuestas)
    print(f"congelado en {args.salida}: {len(respuestas)} respuestas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
