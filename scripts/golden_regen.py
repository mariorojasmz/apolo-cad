r"""Golden de regeneración: tus proyectos guardados tienen que regenerar IDÉNTICOS.

Gate de cada fase del plan `docs/plans/estado-regen-y-params-estrictos.md` (D1): regenera en
FRÍO cada documento de una COPIA congelada de la SQLite y guarda su huella (features con
volumen/área/bbox/caras/aristas/mesh_key/matrix/anclas; juntas, mates, restricciones,
fijadores, anclajes y grupos en JSON canónico; variables resueltas, suprimidos, integridad
sin «degradado» y la ÚLTIMA firma del log).

SEGURIDAD: la SQLite de Mario sólo se abre por URI `mode=ro`, y sólo en `--freeze` (copia con la
API de backup). Todo lo demás lee la COPIA, también `mode=ro`. No importa `ProjectStore` (su
`load` ESCRIBE la caché) ni `apolo.paths` (crea carpetas). En un worktree, PYTHONPATH=core y -B:
    python -B scripts\golden_regen.py --freeze $env:TEMP\apolo-golden\copia.db --src <apolo.db>
    python -B scripts\golden_regen.py --db <copia.db> --out <base.json> [--revisions]
    python -B scripts\golden_regen.py --compare <base.json> <nuevo.json>   # código 1 si difiere
    python -B scripts\golden_regen.py --db <copia.db> --scan-keys [--revisions]
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
import time
import zipfile
from contextlib import closing
from pathlib import Path

DEFAULT_SRC = Path(__file__).resolve().parents[1] / "data" / "apolo.db"
SECCIONES = ("joints", "mates", "constraints", "fasteners", "grounds", "groups")


def _connect_ro(path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def freeze(src: str | Path, dest: str | Path) -> dict:
    """Copia `src` a `dest` con la API de backup, leyendo `src` SÓLO por URI `mode=ro`."""
    src, dest = Path(src).resolve(), Path(dest).resolve()
    if not src.is_file():
        raise SystemExit(f"No existe la base de origen: {src} (pásala con --src)")
    if dest.is_dir():
        dest = dest / f"apolo-{time.strftime('%Y%m%d-%H%M%S')}.db"
    if dest == src or (dest.exists() and dest.samefile(src)):
        raise SystemExit("El destino no puede ser la base de origen")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect_ro(src)) as origen, closing(sqlite3.connect(dest)) as copia:
        origen.backup(copia)
    with closing(_connect_ro(dest)) as con:
        n_p, n_r = (con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("projects", "revisions"))
    return {"copia": str(dest), "proyectos": n_p, "revisiones": n_r}


def iter_docs(db: str | Path, revisions: bool):
    """(clave, etiqueta, bytes .apolo) de cada proyecto y, con `revisions`, cada revisión."""
    tablas = [("proyecto", "projects", "name")] + ([("revision", "revisions", "note")] * revisions)
    with closing(_connect_ro(db)) as con:
        for tipo, tabla, col in tablas:
            for rid, label in con.execute(f"SELECT id, {col} FROM {tabla} ORDER BY id").fetchall():
                data = con.execute(f"SELECT data FROM {tabla} WHERE id=?", (rid,)).fetchone()[0]
                yield f"{tipo}:{rid}", str(label), data


def _r(x) -> float:
    x = float(x)
    return 0.0 if abs(x) < 1e-9 else float(f"{x:.10g}")  # 10 cifras: inmune al ruido de ULP


def canon(obj):
    """Estructura JSON canónica: floats a 10 cifras, tuplas → listas, sets ordenados."""
    if obj is None or isinstance(obj, (bool, str, int)):
        return obj
    if isinstance(obj, float):
        return _r(obj)
    if hasattr(obj, "tolist"):  # array o escalar numpy
        return canon(obj.tolist())
    if isinstance(obj, dict):
        return {str(k): canon(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [canon(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted((canon(v) for v in obj), key=lambda v: json.dumps(v, sort_keys=True))
    if all(hasattr(obj, a) for a in ("X", "Y", "Z")):  # Vector de build123d
        return [_r(obj.X), _r(obj.Y), _r(obj.Z)]
    return str(obj)


def _feature(f) -> dict:
    out = {
        "name": f.name, "command_id": f.command_id, "mesh_key": f.mesh_key,
        "matrix": canon(f.matrix), "anchors": canon(f.anchors), "component": f.component,
        "cut_length": canon(f.cut_length), "miter": canon(f.miter), "material": f.material,
        "group": f.group, "visible": f.visible, "is_guide": f.is_guide,
    }
    try:
        s = f.shape
        bb = s.bounding_box()
        out.update({
            "volume": _r(s.volume), "area": _r(s.area),
            "bbox": [_r(v) for v in (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)],
            "faces": len(s.faces()), "edges": len(s.edges()),
        })
    except Exception as exc:  # noqa: BLE001 — la huella registra el fallo, no lo oculta
        out["geom_error"] = f"{type(exc).__name__}: {exc}"
    return out


def fingerprint(data: bytes) -> dict:
    """Huella de UN documento regenerado en frío (carga tolerante, como el open real)."""
    from apolo.commands.registry import DEFINITIONS
    from apolo.doc import subproject
    from apolo.doc.document import Document

    DEFINITIONS.clear()  # cada documento parte de cachés vacías: sin herencia del anterior
    subproject._CACHE.clear()
    subproject._depth = 0
    try:
        doc = Document.from_apolo_bytes(data, tolerant=True)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "n_commands": len(doc.commands),
        "order": list(doc.scene),
        "features": {fid: _feature(f) for fid, f in doc.scene.items()},
        "variables": canon(doc.variables_resolved),
        "suppressed": canon(doc.regen_suppressed),
        "integrity": [i for i in doc.check_integrity() if not i.startswith("degradado")],
        "last_sig": doc._regen_sigs[-1] if doc._regen_sigs else None,
    } | {sec: canon(getattr(doc, sec)) for sec in SECCIONES}


def build_golden(db: str | Path, revisions: bool, log=print) -> dict:
    docs, tiempos, t0 = {}, {}, time.perf_counter()
    for key, label, data in iter_docs(db, revisions):
        t = time.perf_counter()
        d = docs[key] = {"label": label, **fingerprint(data)}
        tiempos[key] = round(time.perf_counter() - t, 2)
        log(f"{key:>14} {tiempos[key]:7.2f} s {d.get('n_commands', '-'):>4} cmd "
            f"sup={len(d.get('suppressed', []))}{'  ERROR ' + d['error'] if 'error' in d else ''}")
    meta = {
        "db": str(Path(db).resolve()), "revisions": revisions,
        "n_docs": len(docs), "n_commands": sum(d.get("n_commands", 0) for d in docs.values()),
        "seconds": round(time.perf_counter() - t0, 1), "tiempos": tiempos,
        "suppressed_docs": {k: len(d["suppressed"]) for k, d in docs.items() if d.get("suppressed")},
        "error_docs": sorted(k for k, d in docs.items() if "error" in d),
    }
    return {"meta": meta, "docs": docs}


def _js(v) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def _short(v, n: int = 90) -> str:
    return _js(v) if len(_js(v)) <= n else _js(v)[: n - 1] + "…"


def _diff_dict(nombre: str, a: dict, b: dict, lim: int = 6) -> list[str]:
    out = [f"  {nombre}: falta '{k}'" for k in sorted(set(a) - set(b))][:lim]
    out += [f"  {nombre}: sobra '{k}'" for k in sorted(set(b) - set(a))][:lim]
    for k in sorted(set(a) & set(b)):
        if _js(a[k]) == _js(b[k]):
            continue
        if isinstance(a[k], dict) and isinstance(b[k], dict):
            campos = [c for c in sorted(set(a[k]) | set(b[k])) if _js(a[k].get(c)) != _js(b[k].get(c))]
            out += [f"  {nombre}['{k}'].{c}: {_short(a[k].get(c))} → {_short(b[k].get(c))}"
                    for c in campos[:4]]
        else:
            out.append(f"  {nombre}['{k}']: {_short(a[k])} → {_short(b[k])}")
        if len(out) >= 3 * lim:
            out.append("  …")
            break
    return out


def compare(a: dict, b: dict) -> list[str]:
    """Diferencias legibles entre dos goldens (lista vacía = idénticos). Ignora `meta`."""
    out: list[str] = []
    da, db_ = a["docs"], b["docs"]
    for k in sorted(set(da) | set(db_)):
        if k not in db_ or k not in da:
            out.append(f"{k}: sólo está en {'A' if k in da else 'B'}")
            continue
        x, y = da[k], db_[k]
        if _js(x) == _js(y):
            continue
        out.append(f"{k} ({x.get('label', '')}):")
        for campo in sorted(set(x) | set(y)):
            vx, vy = x.get(campo), y.get(campo)
            if _js(vx) == _js(vy):
                continue
            if isinstance(vx, dict) and isinstance(vy, dict):
                out += _diff_dict(campo, vx, vy)
            else:
                out.append(f"  {campo}: {_short(vx)} → {_short(vy)}")
    return out


def _scan_doc(data: bytes, grupo: str, acc: dict, depth: int = 0) -> None:
    """Valida cada comando con `extra="forbid"` POR LLAMADA (con sus variables resueltas) y
    cuenta las claves que hoy el replay ignora en silencio. Baja a los `insert_project`."""
    from pydantic import ValidationError

    from apolo.commands.expressions import resolve_all, resolve_params
    from apolo.commands.registry import REGISTRY

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        commands = json.loads(zf.read("commands.json"))
        adj = {Path(n).stem: zf.read(n) for n in zf.namelist() if n.startswith("attachments/")}
    g = acc.setdefault(grupo, {"docs": 0, "commands": 0, "con_claves": 0, "otras": 0, "tipos": 0})
    g["docs"] += 1
    raw = {c["params"].get("name"): c["params"].get("expression")
           for c in commands if c.get("type") == "set_variable"}
    try:
        variables = resolve_all(raw)
    except Exception:  # noqa: BLE001
        variables = {}
    for c in commands:
        g["commands"] += 1
        spec = REGISTRY.get(c.get("type"))
        if spec is None:
            g["tipos"] += 1
            continue
        params = c.get("params") or {}
        try:
            data_v = params if spec.kind == "vars" else resolve_params(params, variables)
            spec.model.model_validate(data_v, extra="forbid")
        except ValidationError as exc:
            extra = [e for e in exc.errors() if e["type"] == "extra_forbidden"]
            g["otras"] += len(extra) < len(exc.errors())
            g["con_claves"] += bool(extra)
            for e in extra:
                ruta = ".".join("[]" if isinstance(p, int) else str(p) for p in e["loc"])
                fila = acc["claves"].setdefault(f"{c['type']}.{ruta}", {"veces": 0, "docs": set()})
                fila["veces"] += 1
                fila["docs"].add(acc["_doc"])
        except Exception:  # noqa: BLE001 — una expresión que no resuelve
            g["otras"] += 1
        if c.get("type") == "insert_project" and depth < 3 and params.get("attachment") in adj:
            _scan_doc(adj[params["attachment"]], "snapshots embebidos", acc, depth + 1)


def scan_keys(db: str | Path, revisions: bool) -> dict:
    acc: dict = {"claves": {}}
    for key, _label, data in iter_docs(db, revisions):
        acc["_doc"] = key
        _scan_doc(data, "proyectos" if key.startswith("proyecto") else "revisiones", acc)
    acc.pop("_doc", None)
    return acc


def _print_scan(acc: dict) -> None:
    print("| | documentos | comandos | con claves desconocidas | fallan por otra causa "
          "| tipo desconocido |\n|---|---:|---:|---:|---:|---:|")
    for grupo, g in acc.items():
        if grupo != "claves":
            print(f"| {grupo} | {g['docs']} | {g['commands']} | {g['con_claves']} | "
                  f"{g['otras']} | {g['tipos']} |")
    print("\n| clave desconocida | veces | documentos |\n|---|---:|---:|")
    for clave, f in sorted(acc["claves"].items(), key=lambda kv: -kv[1]["veces"]):
        print(f"| `{clave}` | {f['veces']} | {len(f['docs'])} |")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--freeze", metavar="DESTINO")
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--db", metavar="COPIA")
    ap.add_argument("--out", metavar="JSON")
    ap.add_argument("--revisions", action="store_true", help="también las revisiones")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"))
    ap.add_argument("--scan-keys", action="store_true")
    a = ap.parse_args(argv)
    if a.freeze:
        print(json.dumps(freeze(a.src, a.freeze), ensure_ascii=False))
        return 0
    if a.compare:
        ga, gb = (json.loads(Path(p).read_text(encoding="utf-8")) for p in a.compare)
        diffs = compare(ga, gb)
        print("\n".join(diffs) if diffs else f"Sin diferencias ({len(ga['docs'])} documentos).")
        return 1 if diffs else 0
    if not a.db or not (a.scan_keys or a.out):
        ap.error("falta --db COPIA con --out o --scan-keys (o bien --freeze / --compare)")
    if a.scan_keys:
        _print_scan(scan_keys(a.db, a.revisions))
        return 0
    golden = build_golden(a.db, a.revisions)
    Path(a.out).write_text(json.dumps(golden, sort_keys=True, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    m = golden["meta"]
    print(f"{m['n_docs']} documentos · {m['n_commands']} comandos · {m['seconds']} s · "
          f"suprimidos en {len(m['suppressed_docs'])} · errores en {len(m['error_docs'])}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
