r"""Dónde se va el tiempo en una máquina grande (plan maquinas-grandes, F0): sólo lectura.

Carga un `.apolo` OFFLINE (`Document.from_apolo_bytes`, sin la API ni la base) y mide, por
etapa, la pared y el CPU del proceso (`time.process_time`: el trabajo es de un hilo; ojo, el
CPU de un HIJO —el worker de `run_script`— no cuenta en el padre: para eso, la pared):

- `regen`: el replay frío del log, con el costo por TIPO de comando y los comandos más caros
  (envuelve `apolo.doc.document.execute_command`) y lo que cuestan los checkpoints
  (`RegenState.copy`).
- `editar`: tras el replay, la edición de un comando TEMPRANO como la haría el MCP
  (`doc.edit(..., merge=True)`, un renombre que no cambia geometría): cuántos comandos re-ejecuta
  y, aparte, lo que la API hace después de mutar (`scene_payload`, `to_apolo_bytes` y
  `geomcache.pack` del autosave).
- `checks`: lo que corre `POST /api/checks` (la tool `check_interference` Y `engineering_check`
  llaman a la misma ruta): interferencia global, acotada (`--foco`), reglas de estructura y lints.
- `entrega`: `delivery_inputs` + `delivery_report` (la tool `delivery_check`, sin gravedad).
- `puerta`: `puerta_publicacion.reunir` sin gravedad ni marcha (las dos son de la API, con
  `PHYSICS_LOCK`); `--sin-sobrantes` salta `diseno.sin_sobrantes` (medido en puerta-rapida).

No escribe en el `.apolo`, la SQLite ni `data/`. Con `--perfil DIR` guarda un `.prof` por etapa.

    $env:PYTHONPATH = "$PWD\core"
    python -B scripts/medir_maquinas_grandes.py <maquina>.apolo --etapas regen,editar,checks `
        --editar c86 --foco c53,c88 --json out.json --perfil C:\t\perf
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ / "core") not in sys.path:  # mide ESTE árbol (en un worktree el venv apunta al principal)
    sys.path.insert(0, str(RAIZ / "core"))

ETAPAS = ("regen", "editar", "checks", "entrega", "puerta")


def _rss_mb() -> float | None:
    try:
        import psutil
    except ImportError:
        return None
    return round(psutil.Process().memory_info().rss / 2**20, 0)


_CAJAS = {"n": 0, "s": 0.0}


def _contar_cajas() -> None:
    """Cuenta `Shape.bounding_box` (la caja ÓPTIMA de build123d, `BRepBndLib.AddOptimal`): el
    perfil de la F0 la dio como el punto caliente común a regenerate, chequeos y entrega."""
    from build123d.topology import Shape

    original = Shape.bounding_box

    def bounding_box(self, *a, **k):
        t = time.perf_counter()
        try:
            return original(self, *a, **k)
        finally:
            dt = time.perf_counter() - t
            _CAJAS["n"] += 1
            _CAJAS["s"] += dt
            f = sys._getframe(1)  # el primer marco de apolo que la pidió
            while f is not None and "apolo" not in f.f_code.co_filename:
                f = f.f_back
            k_ = ("?" if f is None else
                  f"{Path(f.f_code.co_filename).name}:{f.f_code.co_name}")
            n, s = _POR_LLAMADOR.get(k_, (0, 0.0))
            _POR_LLAMADOR[k_] = (n + 1, s + dt)

    Shape.bounding_box = bounding_box


_POR_LLAMADOR: dict = {}


class Reloj:
    """Pared + CPU de cada bloque, con perfil opcional por bloque."""

    def __init__(self, perfil: Path | None, top: int):
        self.perfil, self.top, self.filas = perfil, top, {}

    @contextmanager
    def medir(self, nombre: str, perfilar: bool = True):
        pr = cProfile.Profile() if (self.perfil and perfilar) else None
        cajas, por = dict(_CAJAS), dict(_POR_LLAMADOR)
        t, cpu = time.perf_counter(), time.process_time()
        if pr:
            pr.enable()
        fila: dict = {}
        try:
            yield fila
        finally:
            if pr:
                pr.disable()
            fila.update(pared_s=round(time.perf_counter() - t, 2),
                        cpu_s=round(time.process_time() - cpu, 2), rss_mb=_rss_mb(),
                        cajas={"n": _CAJAS["n"] - cajas["n"],
                               "s": round(_CAJAS["s"] - cajas["s"], 1)})
            dif = {k: (n - por.get(k, (0, 0.0))[0], s - por.get(k, (0, 0.0))[1])
                   for k, (n, s) in _POR_LLAMADOR.items()}
            fila["cajas_por"] = [{"llamador": k, "n": n, "s": round(s, 1)} for k, (n, s)
                                 in sorted(dif.items(), key=lambda x: -x[1][1])[:8] if n]
            if pr:
                self.perfil.mkdir(parents=True, exist_ok=True)
                pr.dump_stats(str(self.perfil / f"{nombre}.prof"))
                s = io.StringIO()
                pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(self.top)
                fila["perfil_acumulado"] = s.getvalue()
                s = io.StringIO()
                pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(self.top)
                fila["perfil_propio"] = s.getvalue()
            self.filas[nombre] = fila
            print(f"[{nombre}] pared {fila['pared_s']} s, CPU {fila['cpu_s']} s, "
                  f"rss {fila['rss_mb']} MB, cajas {fila['cajas']['n']} "
                  f"({fila['cajas']['s']} s)", flush=True)


@contextmanager
def _por_comando(registro: list):
    """Envuelve `execute_command` del regenerate y `RegenState.copy` (los checkpoints)."""
    from apolo.commands.state import RegenState
    from apolo.doc import document as docmod

    original, copia = docmod.execute_command, RegenState.copy
    ckpt = {"n": 0, "s": 0.0}

    def envuelto(state, cid, ctype, params, *a, **k):
        t, cpu = time.perf_counter(), time.process_time()
        try:
            return original(state, cid, ctype, params, *a, **k)
        finally:
            registro.append((cid, ctype, (params or {}).get("name") if isinstance(params, dict)
                             else None, time.perf_counter() - t, time.process_time() - cpu,
                             len(state.scene)))

    def copiar(self):
        t = time.perf_counter()
        try:
            return copia(self)
        finally:
            ckpt["n"] += 1
            ckpt["s"] += time.perf_counter() - t

    docmod.execute_command, RegenState.copy = envuelto, copiar
    try:
        yield ckpt
    finally:
        docmod.execute_command, RegenState.copy = original, copia


def _resumen_comandos(registro: list, top: int) -> dict:
    por_tipo: dict = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    for _cid, ctype, _n, pared, cpu, _escena in registro:
        f = por_tipo[ctype]
        f[0] += 1
        f[1] += pared
        f[2] += cpu
        f[3] = max(f[3], pared)
    total = sum(r[3] for r in registro) or 1.0
    tipos = sorted(por_tipo.items(), key=lambda x: -x[1][1])
    # el costo por comando contra el tamaño de la escena en ese momento (¿crece con n?)
    tercios: dict = {}
    n = len(registro)
    for k, (a, b) in enumerate(((0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n))):
        trozo = registro[a:b]
        tercios[f"tercio{k + 1}"] = {
            "comandos": len(trozo), "pared_s": round(sum(r[3] for r in trozo), 1),
            "escena_al_final": trozo[-1][5] if trozo else 0}
    return {
        "comandos": n, "pared_s": round(total, 1), "cpu_s": round(sum(r[4] for r in registro), 1),
        "por_tipo": [{"tipo": t, "n": f[0], "pared_s": round(f[1], 1), "cpu_s": round(f[2], 1),
                      "max_s": round(f[3], 2), "pct": round(100 * f[1] / total, 1)}
                     for t, f in tipos],
        "mas_caros": [{"id": r[0], "tipo": r[1], "nombre": r[2], "pared_s": round(r[3], 2),
                       "cpu_s": round(r[4], 2)} for r in sorted(registro, key=lambda r: -r[3])[:top]],
        "por_tercio": tercios,
    }


def etapa_regen(ruta: Path, reloj: Reloj, top: int, out: dict, cache: Path | None = None):
    """El replay frío; con `cache` (un blob de `geomcache.pack` que ESTE script escribió en una
    corrida anterior: pickle, nunca uno ajeno) abre en caliente y salta el replay."""
    from apolo.doc import Document, geomcache

    data = ruta.read_bytes()
    if cache is not None and cache.exists():
        with reloj.medir("carga_caliente", perfilar=False):
            doc = Document.from_apolo_bytes(data, tolerant=True,
                                            warm=geomcache.unpack(cache.read_bytes()))
        out["piezas"], out["comandos"] = len(doc.scene), len(doc.commands)
        return doc
    registro: list = []
    with reloj.medir("carga_sin_regen", perfilar=False):
        doc = Document.from_apolo_bytes(data, regenerate=False, tolerant=True)
    with _por_comando(registro) as ckpt, reloj.medir("regen") as fila:
        doc.regenerate(tolerant=True)
    fila["checkpoints"] = {"n": ckpt["n"], "pared_s": round(ckpt["s"], 2)}
    fila["suprimidos"] = len(doc.regen_suppressed)
    out["piezas"] = len(doc.scene)
    out["comandos"] = len(doc.commands)
    out["regen_por_comando"] = _resumen_comandos(registro, top)
    if cache is not None:
        blob = geomcache.pack(doc)
        if blob:
            cache.write_bytes(blob)
    return doc


def etapa_editar(doc, cid: str, reloj: Reloj, top: int, out: dict):
    from apolo.doc import geomcache

    cmd = next((c for c in doc.commands if c["id"] == cid), None)
    if cmd is None:
        out["editar"] = {"error": f"{cid} no está en el log"}
        return
    from apolo.doc import carril

    escena = carril.separar(doc.commands)[0]
    pos = next(i for i, c in enumerate(escena) if c["id"] == cid)
    nombre = (cmd["params"] or {}).get("name") or cid
    registro: list = []
    with reloj.medir("editar_snapshot", perfilar=False):
        doc._snapshot()
    with _por_comando(registro), reloj.medir("editar"):
        doc.edit(cid, {"name": f"{nombre} "}, merge=True)  # sólo el nombre: misma geometría
    info = {"id": cid, "tipo": cmd["type"], "posicion": pos, "log": len(doc.commands),
            "escena_log": len(escena), "re_ejecutados": len(registro)}
    info.update(_resumen_comandos(registro, top))
    out["editar"] = info
    # lo que la API hace después de toda mutación, bajo STATE_LOCK (common._state_or_error y
    # el flush del autosave)
    from apolo.api.session import S

    S.doc = doc
    from apolo.api.scene import scene_payload

    with reloj.medir("api_scene_payload"):
        payload = scene_payload()
    out["payload_mb"] = round(len(json.dumps(payload, default=str)) / 2**20, 1)
    with reloj.medir("api_scene_payload_otra_vez", perfilar=False):
        scene_payload()  # con las mallas ya en la caché por id(shape)
    with reloj.medir("api_to_apolo_bytes", perfilar=False):
        doc.to_apolo_bytes()
    with reloj.medir("api_geomcache_pack"):
        blob = geomcache.pack(doc)
    out["geomcache_mb"] = None if blob is None else round(len(blob) / 2**20, 1)
    with reloj.medir("deshacer"):
        doc.undo()


def _expand(doc):
    from apolo.api.common import _expand_ids
    from apolo.api.session import S

    S.doc = doc
    return _expand_ids


def etapa_checks(doc, foco: list[str] | None, reloj: Reloj, out: dict):
    from apolo.commands.expressions import resolve_params
    from apolo.library import interference_report
    from apolo.library.checks import hardware_ids, joint_pairs, same_command_pairs
    from apolo.library.lints import predelivery_lints
    from apolo.services.calidad_agujeros import agujeros_atribuidos
    from apolo.services.engineering_rules import requirement_inputs, structure_rules

    with reloj.medir("checks_exclusiones", perfilar=False):
        excl_pares = joint_pairs(doc) | same_command_pairs(doc)
        excl_ids = hardware_ids(doc)
    with reloj.medir("checks_interferencia_global") as fila:
        r = interference_report(doc.scene, exclude_pairs=excl_pares, exclude_ids=excl_ids)
    fila["resultado"] = {k: r.get(k) for k in ("solidos", "parejas_analizadas", "truncado")}
    if foco:
        ids = _expand(doc)(foco)
        with reloj.medir("checks_interferencia_acotada") as fila:
            r = interference_report(doc.scene, exclude_pairs=excl_pares, exclude_ids=excl_ids,
                                    focus=ids)
        fila["resultado"] = {k: r.get(k) for k in ("solidos", "parejas_analizadas", "truncado")}
        fila["foco"] = len(ids)
    _req, carga, _l, _a = requirement_inputs(doc, None, None, None)
    with reloj.medir("checks_estructura") as fila:
        reglas = structure_rules(doc, carga, None)
    fila["reglas"] = len(reglas)
    with reloj.medir("checks_lints") as fila:
        lints = predelivery_lints(
            doc.scene, doc.commands, doc.fasteners, doc.grounds, doc.joints, doc.mates,
            resolve=lambda p: resolve_params(p, doc.variables_resolved),
            material_vertical=doc.default_material(),
            agujeros_declarados=lambda: agujeros_atribuidos(doc))
    fila["lints"] = len(lints)
    # los cuatro lints por separado (y la medida de `union.agujeros` que el primero inyecta)
    from apolo.library import lints as lm
    from apolo.library.catalog import CATALOG
    from apolo.library.lint_asiento import asiento_zona_plana_lint
    from apolo.library.lint_soldadura import soldadura_imposible_lint

    with reloj.medir("lint_barreno_sin_perno", perfilar=False):
        lm._hole_bolt_lint(doc.scene, doc.commands, CATALOG,
                           lambda p: resolve_params(p, doc.variables_resolved), None)
    with reloj.medir("lint_agujeros_atribuidos", perfilar=False):
        agujeros_atribuidos(doc)
    with reloj.medir("lint_pieza_suelta", perfilar=False):
        lm._loose_part_lint(doc.scene, doc.fasteners, doc.grounds, doc.joints, doc.mates, CATALOG)
    with reloj.medir("lint_asiento", perfilar=False):
        asiento_zona_plana_lint(doc.scene, CATALOG)
    with reloj.medir("lint_soldadura", perfilar=False):
        soldadura_imposible_lint(doc.scene, doc.fasteners, CATALOG, default=doc.default_material())
    out["checks"] = True


def etapa_entrega(doc, reloj: Reloj, out: dict):
    from apolo.library.delivery import delivery_report
    from apolo.services.delivery_inputs import delivery_inputs

    tiempos: dict = {}
    with reloj.medir("entrega") as fila:
        r = delivery_report(**delivery_inputs(doc, expand=_expand(doc), tiempos=tiempos),
                            gravedad=None)
    fila["por_regla_s"] = tiempos
    fila["veredicto"] = r.get("veredicto")


def etapa_puerta(doc, sobrantes: bool, reloj: Reloj, out: dict):
    from apolo.services import puerta_publicacion as pp

    tiempos: dict = {}
    with reloj.medir("puerta") as fila:
        pp.reunir(doc, expand=_expand(doc), gravedad={"resultado": None, "motivo": "offline"},
                  tiempos=tiempos, sobrantes=sobrantes)
    fila["tiempos_s"] = {k: round(v, 1) for k, v in tiempos.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("apolo", type=Path)
    ap.add_argument("--etapas", default="regen,editar,checks,entrega",
                    help=f"separadas por coma, de {','.join(ETAPAS)} (regen va siempre)")
    ap.add_argument("--editar", default=None, help="id del comando temprano a renombrar "
                    "(por defecto, el primero de escena con `name` tras el bloque de variables)")
    ap.add_argument("--foco", default=None, help="ids o grupos para la interferencia acotada")
    ap.add_argument("--sin-sobrantes", action="store_true")
    ap.add_argument("--perfil", type=Path)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--cache", type=Path, help="blob de geomcache propio: si existe, abre en "
                    "caliente (sin medir el replay); si no, lo escribe tras el replay")
    a = ap.parse_args(argv)
    etapas = {e.strip() for e in a.etapas.split(",") if e.strip()}
    _contar_cajas()
    reloj = Reloj(a.perfil, a.top)
    out: dict = {"archivo": str(a.apolo)}
    doc = etapa_regen(a.apolo, reloj, a.top, out, a.cache)
    print(f"{out['piezas']} piezas, {out['comandos']} comandos", flush=True)
    try:
        if "editar" in etapas:
            cid = a.editar or next(c["id"] for c in doc.commands
                                   if c["type"] != "set_variable" and (c["params"] or {}).get("name"))
            etapa_editar(doc, cid, reloj, a.top, out)
        if "checks" in etapas:
            etapa_checks(doc, a.foco.split(",") if a.foco else None, reloj, out)
        if "entrega" in etapas:
            etapa_entrega(doc, reloj, out)
        if "puerta" in etapas:
            etapa_puerta(doc, not a.sin_sobrantes, reloj, out)
    finally:
        out["etapas"] = reloj.filas
        if a.json:
            a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str),
                              encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
