r"""Línea base de RENDIMIENTO (V6.1) — la vara para medir el progreso.

READ-ONLY sobre la BD: la abre por URI `mode=ro` y NUNCA escribe en ella (el autosave se mide
contra una SQLite temporal en scratch). Cada medida es la MEDIANA de 3 repeticiones, salvo
`open_frio_faja_primera_s`. Si los proyectos de referencia (faja 38, layout 53) están en la
BD, los usa; si no, sintetiza modelos comparables en memoria (marcado con `source`).

El frío es frío de verdad (plan sandbox-caliente, D9): la caché del sandbox se vacía antes de
cada repetición del open frío (si no, la 2.ª y la 3.ª no ejecutan ningún script) y la 1.ª
apertura del proceso, que además levanta el worker, se reporta aparte. Qué mide cada cifra:
`nota` del JSON.

Los números son MÁQUINA-DEPENDIENTES: sólo comparan contra corridas en la misma máquina, con
la API detenida (su worker y su CPU compiten) y sobre una COPIA de la base.

Uso (en un worktree, antes `$env:PYTHONPATH = "$PWD\core"`):
    .\.venv\Scripts\python.exe -B scripts\perf_baseline.py --db <copia.db> [--out docs\perf_baseline.json]
"""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

REPS = 3

NOTA = [
    "Línea base de rendimiento, dependiente de la máquina: compara sólo contra corridas en el "
    "mismo host, con la API detenida. Cada medida es la mediana de `reps` repeticiones, salvo "
    "open_frio_faja_primera_s.",
    "open_frio_faja_primera_s: la 1.ª apertura en frío del proceso (from_apolo_bytes, replay "
    "completo); incluye levantar el worker del sandbox y llenar las cachés del proceso "
    "(definiciones del catálogo).",
    "open_frio_faja_s: apertura en frío con el worker ya vivo y la caché del sandbox vaciada "
    "antes de cada repetición: cada run_script se ejecuta; las cachés del catálogo siguen "
    "llenas.",
    "geom_cache_write_faja_s: empacar el estado regenerado en la caché de geometría (pack).",
    "open_caliente_faja_s: apertura reanudando de la caché de geometría (unpack + warm).",
    "regenerate_edit_temprano_s: editar la 1.ª variable de la cabecera al MISMO valor (las "
    "firmas no cambian: no replaya).",
    "edit_variable_faja_s: editar la 1.ª variable a un valor nuevo (x1,1; +k en la repetición "
    "k, para que ninguna acierte en la caché): replay completo, scripts re-ejecutados.",
    "edit_variable_vuelta_faja_s: volver al valor original: replay completo con los scripts "
    "servidos por la caché del sandbox.",
    "scene_payload_layout_s: armar el payload de escena completo del layout.",
    "autosave_faja_s: to_apolo_bytes + guardar en una SQLite temporal.",
    "fuzz_100ops_s: 100 operaciones al azar (crear, editar, deshacer, rehacer) sobre 60 cajas.",
    "worker_arranque_s: levantar el worker del sandbox (prewarm hasta su «listo»): el import de "
    "build123d en un proceso nuevo.",
]


def _tiempos(fn, n: int = REPS, antes=None) -> list[float]:
    """`n` mediciones de `fn`; `antes` (sin cronometrar) corre antes de cada una."""
    ts = []
    for _ in range(n):
        if antes is not None:
            antes()
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return ts


def _median_time(fn, antes=None) -> float:
    return round(statistics.median(_tiempos(fn, antes=antes)), 4)


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "desconocido"


def _synth_conveyor() -> bytes:
    """~72 sólidos: aproxima la faja de referencia (id 38)."""
    from apolo.doc import Document

    d = Document("synth-faja")
    d.execute("set_variable", {"name": "L", "expression": "4000"})
    d.execute("create_conveyor", {"largo": "=L", "ancho": 600, "altura": 750, "paso": 100})
    return d.to_apolo_bytes()


def _synth_layout() -> bytes:
    """~150 sólidos: aproxima el layout de referencia (id 53) con un transportador +
    un patrón masivo de primitivas (barato, determinista)."""
    from apolo.doc import Document

    d = Document("synth-layout")
    d.execute("create_conveyor", {"largo": 3000, "ancho": 500, "altura": 700, "paso": 150})
    seed = d.execute("create_box", {"width": 60, "depth": 40, "height": 30, "position": {"y": 1500}})
    d.execute("pattern_group", {"source": seed, "count": 80, "spacing": {"x": 90}})
    return d.to_apolo_bytes()


def _load_or_synth(db: Path, project_id: int, synth) -> tuple[bytes, str]:
    """Los bytes del proyecto leídos por URI `mode=ro` (sin `ProjectStore`: su constructor
    abre la base para escribir), o el modelo sintético si no está."""
    if db.is_file():
        try:
            uri = db.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=30)) as con:
                row = con.execute("SELECT data FROM projects WHERE id=?", (project_id,)).fetchone()
            if row is not None:
                return row[0], f"proyecto {project_id}"
        except sqlite3.Error:
            pass
    return synth(), "sintético"


def _edit_variable(doc, sandbox) -> tuple[float, float] | None:
    """Edita la 1.ª variable de la cabecera a un valor nuevo y la devuelve a la original,
    `REPS` veces: (mediana de la ida, mediana de la vuelta). Cada ida usa un valor que la
    caché del sandbox no vio (x1,1 + k); cada vuelta acierta (el original quedó en la caché
    al abrir). Deja el documento como estaba."""
    var = next((c for c in doc.commands if c["type"] == "set_variable"), None)
    if var is None:
        return None
    cid, nombre, original = var["id"], var["params"]["name"], var["params"]["expression"]

    def nuevo(k: int) -> str:
        try:
            return f"{float(original) * 1.1 + k:.10g}"
        except ValueError:
            return f"({original}) * 1.1 + {k}"

    ida, vuelta = [], []
    try:
        for k in range(REPS):
            antes = sandbox.cache_info()["entradas"]
            ida += _tiempos(lambda k=k: doc.edit(cid, {"name": nombre, "expression": nuevo(k)}), 1)
            print(f"edit_variable: {nombre} = {nuevo(k)} ejecutó "
                  f"{sandbox.cache_info()['entradas'] - antes} scripts", file=sys.stderr)
            vuelta += _tiempos(lambda: doc.edit(cid, {"name": nombre, "expression": original}), 1)
    finally:
        actual = next(c for c in doc.commands if c["id"] == cid)["params"]["expression"]
        if actual != original:
            doc.edit(cid, {"name": nombre, "expression": original})
    return round(statistics.median(ida), 4), round(statistics.median(vuelta), 4)


def _arrancar_worker(sandbox) -> None:
    """Lo que hace el arranque de la API (D7): `prewarm` y esperar al worker listo."""
    limite = time.perf_counter() + sandbox.WORKER_START_TIMEOUT_S
    sandbox.prewarm()
    while sandbox.worker_info() is None:
        if time.perf_counter() > limite:
            raise RuntimeError("el worker del sandbox no arrancó")
        time.sleep(0.01)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path("data") / "apolo.db"))
    ap.add_argument("--out", default=str(Path("docs") / "perf_baseline.json"))
    args = ap.parse_args()

    import apolo.api.main as api
    from apolo import sandbox
    from apolo.doc import Document

    db = Path(args.db)
    medidas: dict = {}
    fuentes: dict = {}
    conteos: dict = {}

    # 1) OPEN en frío del proyecto tipo-faja (from_apolo_bytes completo, regen desde 0). La 1.ª
    # del proceso levanta el worker (nada lo levantó todavía); las demás, con la caché del
    # sandbox vacía, ejecutan cada script en el worker vivo.
    faja_bytes, faja_src = _load_or_synth(db, 38, _synth_conveyor)
    fuentes["faja"] = faja_src
    sandbox.shutdown()  # no-op: nada lo levantó, y la 1.ª tiene que pagar el arranque
    medidas["open_frio_faja_primera_s"] = round(
        _tiempos(lambda: Document.from_apolo_bytes(faja_bytes), 1)[0], 4)
    medidas["open_frio_faja_s"] = _median_time(
        lambda: Document.from_apolo_bytes(faja_bytes), antes=sandbox.clear_cache)
    faja_doc = Document.from_apolo_bytes(faja_bytes)
    conteos["faja_solidos"] = len(faja_doc.scene)
    conteos["faja_comandos"] = len(faja_doc.commands)
    conteos["faja_run_scripts"] = sum(c["type"] == "run_script" for c in faja_doc.commands)

    # 1b) OPEN CALIENTE (V6.2a): con la caché poblada. Mide unpack + warm-open (= lo que hace
    # store.load en producción); el coste del pack (escritura) va aparte.
    from apolo.doc.geomcache import pack, unpack

    medidas["geom_cache_write_faja_s"] = _median_time(lambda: pack(faja_doc))
    _blob = pack(faja_doc)
    if _blob is not None and unpack(_blob) is not None:
        medidas["open_caliente_faja_s"] = _median_time(
            lambda: Document.from_apolo_bytes(faja_bytes, warm=unpack(_blob))
        )
    else:
        medidas["open_caliente_faja_s"] = None

    # 2) regenerate tras editar el PRIMER set_variable (+0): mide el peor caso incremental
    var_cmd = next((c for c in faja_doc.commands if c["type"] == "set_variable"), None)
    if var_cmd is not None:
        expr = var_cmd["params"]["expression"]

        def _edit_regen():
            faja_doc.edit(var_cmd["id"], {"name": var_cmd["params"]["name"], "expression": expr})

        medidas["regenerate_edit_temprano_s"] = _median_time(_edit_regen)
    else:
        medidas["regenerate_edit_temprano_s"] = None

    # 2b) editar la PRIMERA variable a un valor NUEVO y volver (el caso del plan
    # sandbox-caliente: en el 38 es `largo_total`, de la que cuelgan todos los scripts)
    ida_vuelta = _edit_variable(faja_doc, sandbox)
    medidas["edit_variable_faja_s"], medidas["edit_variable_vuelta_faja_s"] = (
        ida_vuelta if ida_vuelta is not None else (None, None))

    # 3) scene_payload del proyecto tipo-layout + tamaño del payload
    layout_bytes, layout_src = _load_or_synth(db, 53, _synth_layout)
    fuentes["layout"] = layout_src
    layout_doc = Document.from_apolo_bytes(layout_bytes)
    conteos["layout_solidos"] = len(layout_doc.scene)
    old_doc = api.DOC
    api.DOC = layout_doc
    try:
        api._GEOM_REVS.clear()
        medidas["scene_payload_layout_s"] = _median_time(api.scene_payload)
        full = api.scene_payload()
        conteos["payload_bytes"] = len(json.dumps(full).encode())
        # 3b) delta de escena SIN cambios (V6.2b): bytes del delta vs payload completo
        known = {"revs": {f["id"]: f["rev"] for f in full["features"]},
                 "defs": list(full["definitions"].keys())}
        conteos["scene_delta_nochange_bytes"] = len(
            json.dumps(api.scene_payload(known=known)).encode()
        )
    finally:
        api.DOC = old_doc

    # 4) autosave: to_apolo_bytes + save a una SQLite TEMPORAL (jamás la BD real).
    # ignore_cleanup_errors: sqlite en Windows retiene el handle hasta el GC (el patrón
    # `with self._conn()` de projects.py hace commit pero no close) → el rmtree falla.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        from apolo.projects import ProjectStore

        tmp_store = ProjectStore(str(Path(tmp) / "perf.db"))
        pid = tmp_store.create(faja_doc)
        medidas["autosave_faja_s"] = _median_time(lambda: tmp_store.save(pid, faja_doc))

    # 5) fuzz 100 ops sobre un modelo sintético de ~60 sólidos
    def _fuzz():
        import random

        rng = random.Random(0)
        d = Document("perf-fuzz")
        for i in range(60):
            d.execute("create_box", {"width": 20 + i, "position": {"x": i * 40}})
        for _ in range(100):
            op = rng.choice(["execute", "edit", "undo", "redo"])
            try:
                if op == "execute":
                    d.execute("create_box", {"width": rng.randint(20, 80), "position": {"x": rng.randint(0, 9000)}})
                elif op == "edit" and d.commands:
                    d.edit(rng.choice(d.commands)["id"], {"width": rng.randint(20, 90)}, merge=True)
                elif op == "undo" and d.can_undo:
                    d.undo()
                elif op == "redo" and d.can_redo:
                    d.redo()
            except Exception:
                pass

    medidas["fuzz_100ops_s"] = _median_time(_fuzz)

    # 6) arranque del worker del sandbox: matar el vivo y levantar uno nuevo como el arranque
    medidas["worker_arranque_s"] = _median_time(
        lambda: _arrancar_worker(sandbox), antes=sandbox.shutdown)
    sandbox.shutdown()

    out = {
        "nota": NOTA,
        "host": platform.node(),
        "plataforma": platform.platform(),
        "python": sys.version.split()[0],
        "commit": _git_commit(),
        "reps": REPS,
        "fuentes": fuentes,
        "medidas_s": medidas,
        "conteos": conteos,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
