"""Extrae el fixture del criterio de uniones (plan mcp-sin-friccion, D6) de un proyecto con su
estructura declarada A MANO: lo que `services/criterio_uniones.criterio` necesita (nombre y
catálogo de cada pieza, los contactos de `detect_structure` sobre el log SIN `fasten`/`ground`,
lo que gira) y lo que se espera (cada unión declarada con su tipo). Sin geometría: el test corre
en milisegundos y no depende de la base local.

Uso (sobre una COPIA de la base, nunca la del árbol principal en uso):
    python -B scripts/fixture_estructura.py --db <copia>/apolo.db --proyecto 74 \
        --salida tests/data/estructura_piloto74.json
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import zipfile
from pathlib import Path


def sin_uniones(blob: bytes) -> bytes:
    """El `.apolo` con el log sin `fasten`/`ground` (las uniones que traen los super-comandos,
    como los contactos de `create_chain`, quedan: no son comandos aparte)."""
    zin = zipfile.ZipFile(io.BytesIO(blob))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename == "commands.json":
                cmds = json.loads(data)
                lista = cmds["commands"] if isinstance(cmds, dict) else cmds
                fil = [c for c in lista if c["type"] not in ("fasten", "ground")]
                if isinstance(cmds, dict):
                    cmds["commands"] = fil
                else:
                    cmds = fil
                data = json.dumps(cmds).encode()
            zout.writestr(it, data)
    return buf.getvalue()


def main() -> None:
    from apolo.assembly.autodetect import detect_structure, piezas_que_giran
    from apolo.doc import Document
    from apolo.library.catalog import CATALOG

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--proyecto", type=int, required=True)
    ap.add_argument("--salida", required=True)
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    blob = con.execute("SELECT data FROM projects WHERE id=?", (args.proyecto,)).fetchone()[0]
    con.close()

    doc = Document.from_apolo_bytes(blob, tolerant=True)
    limpio = Document.from_apolo_bytes(sin_uniones(blob), tolerant=True)
    det = detect_structure(limpio.scene, joints=limpio.joints)
    piezas = {}
    for fid, feat in limpio.scene.items():
        comp = CATALOG.get(getattr(feat, "component", None) or "")
        piezas[fid] = [feat.name, comp.category if comp else None, comp.name if comp else None]
    out = {
        "proyecto": args.proyecto,
        "grupos": sorted(limpio.groups),
        "piezas": piezas,
        "candidatos": [[f["a"], f["b"], f["direction"]] for f in det["fasteners"]],
        "moviles": piezas_que_giran(limpio.scene, limpio.joints),
        "esperado": sorted([f["a"], f["b"], f["kind"]] for f in doc.fasteners.values()),
    }
    Path(args.salida).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                                 encoding="utf-8")
    print(f"{len(out['candidatos'])} candidatos, {len(out['esperado'])} uniones esperadas")


if __name__ == "__main__":
    main()
