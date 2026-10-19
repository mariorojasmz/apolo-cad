r"""F0 del plan acceso-de-herramienta: ¿entra la llave en las revisiones del piloto?

READ-ONLY sobre la BD (URI `mode=ro`): carga cada revisión pedida con
`Document.from_apolo_bytes(tolerant=True)`, corre `tool_access_report` y mide su costo. En el
piloto (proyecto 74) la revisión de UPN-100 debe dar ROJO en las 40 tuercas M12 del eje (a
2.5 mm del ala) y la de ángulo L 75×6, todas libres. No es un test: regenerar el piloto tarda
~10-20 s por revisión y la BD no está en el repo (bitácora F0 del plan).

Uso (en un worktree, antes `$env:PYTHONPATH = "$PWD\core"`):
    .\.venv\Scripts\python.exe -B scripts\f0_acceso_herramienta.py --db data\apolo.db 124 125
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path


def main() -> int:
    from apolo.doc.document import Document
    from apolo.library.acceso_herramienta import tool_access_report
    from apolo.library.catalog import CATALOG

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default="data/apolo.db", help="SQLite de Apolo (se abre sólo lectura)")
    ap.add_argument("revisiones", nargs="+", type=int, help="id de la fila de `revisions`")
    args = ap.parse_args()
    uri = Path(args.db).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        for rid in args.revisiones:
            fila = con.execute("SELECT project_id, note, data FROM revisions WHERE id = ?",
                               (rid,)).fetchone()
            if fila is None:
                print(f"revisión {rid}: no existe")
                continue
            pid, nota, data = fila
            t = time.perf_counter()
            doc = Document.from_apolo_bytes(data, tolerant=True)
            t_carga = time.perf_counter() - t
            rep = tool_access_report(doc.scene, catalog=CATALOG) or {}
            print(f"revisión {rid} (proyecto {pid}): {nota[:70]}")
            print(f"  carga {t_carga:.1f} s · chequeo {rep.get('ms', 0) / 1000:.1f} s · "
                  f"{len(doc.scene)} sólidos")
            print(f"  evaluados {rep.get('evaluados', 0)} · ok {rep.get('ok', 0)} · "
                  f"sin herramienta {len(rep.get('sin_herramienta', []))} · "
                  f"sólo boca {len(rep.get('solo_boca', []))} · "
                  f"no evaluados {len(rep.get('no_evaluados', []))}")
            estorban = sorted({b for e in rep.get("sin_herramienta", []) + rep.get("solo_boca", [])
                               for b in e["bloquean"]})
            if estorban:
                print(f"  estorban: {', '.join(estorban)}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
