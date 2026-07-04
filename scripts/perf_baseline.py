r"""Línea base de RENDIMIENTO (V6.1) — la vara para medir el progreso de V6.2.

READ-ONLY sobre la BD: NUNCA guarda en `data/apolo.db` (el autosave se mide contra una
SQLite temporal en scratch). Mide con 3 repeticiones y toma la MEDIANA. Si los proyectos
de referencia (faja 38, layout 53) están en la BD local, los usa; si no —esta máquina no
los tiene—, sintetiza modelos comparables en memoria (marcado con `source` en el JSON).

Los números son MÁQUINA-DEPENDIENTES: solo comparan contra corridas en la misma máquina.

Uso:
    .\.venv\Scripts\python.exe scripts\perf_baseline.py   [--db data\apolo.db] [--out docs\perf_baseline.json]
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPS = 3


def _median_time(fn) -> float:
    ts = []
    for _ in range(REPS):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return round(statistics.median(ts), 4)


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


def _load_or_synth(store, project_id: int, synth) -> tuple[bytes, str]:
    if store is not None:
        try:
            return store.load_bytes(project_id), f"proyecto {project_id}"
        except Exception:
            pass
    return synth(), "sintético"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(Path("data") / "apolo.db"))
    ap.add_argument("--out", default=str(Path("docs") / "perf_baseline.json"))
    args = ap.parse_args()

    import apolo.api.main as api
    from apolo.doc import Document

    store = None
    try:
        from apolo.projects import ProjectStore

        if Path(args.db).exists():
            store = ProjectStore(args.db)
    except Exception:
        store = None

    medidas: dict = {}
    fuentes: dict = {}
    conteos: dict = {}

    # 1) OPEN en frío del proyecto tipo-faja (from_apolo_bytes completo, regen desde 0)
    faja_bytes, faja_src = _load_or_synth(store, 38, _synth_conveyor)
    fuentes["faja"] = faja_src
    medidas["open_frio_faja_s"] = _median_time(lambda: Document.from_apolo_bytes(faja_bytes))
    faja_doc = Document.from_apolo_bytes(faja_bytes)
    conteos["faja_solidos"] = len(faja_doc.scene)
    conteos["faja_comandos"] = len(faja_doc.commands)

    # 2) regenerate tras editar el PRIMER set_variable (+0): mide el peor caso incremental
    var_cmd = next((c for c in faja_doc.commands if c["type"] == "set_variable"), None)
    if var_cmd is not None:
        expr = var_cmd["params"]["expression"]

        def _edit_regen():
            faja_doc.edit(var_cmd["id"], {"name": var_cmd["params"]["name"], "expression": expr})

        medidas["regenerate_edit_temprano_s"] = _median_time(_edit_regen)
    else:
        medidas["regenerate_edit_temprano_s"] = None

    # 3) scene_payload del proyecto tipo-layout + tamaño del payload
    layout_bytes, layout_src = _load_or_synth(store, 53, _synth_layout)
    fuentes["layout"] = layout_src
    layout_doc = Document.from_apolo_bytes(layout_bytes)
    conteos["layout_solidos"] = len(layout_doc.scene)
    old_doc = api.DOC
    api.DOC = layout_doc
    try:
        medidas["scene_payload_layout_s"] = _median_time(api.scene_payload)
        conteos["payload_bytes"] = len(json.dumps(api.scene_payload()).encode())
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

    out = {
        "nota": "línea base de V6.1 (máquina-dependiente); compara solo contra la misma máquina",
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
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
