r"""Mide `diseno.sin_sobrantes` (`services/calidad_sobrantes.py`) sobre un `.apolo`: candidatas, costo
por candidata y por control, y el perfil de las funciones más caras (F0 de puerta-rapida).

No es un test: corre la fuente «seguridad» (que deja `f3.analisis` y `f3.sondas` en el `Contexto`,
como en la puerta) y luego `sobrantes(doc, contexto)` bajo cProfile, con la geometría de masa
memoizada como en `puerta_publicacion.reunir`. Lee el `.apolo` y nada más: no toca la base, ni la
API, ni el archivo.

    $env:PYTHONPATH = "$PWD\core"
    python -B scripts/medir_sobrantes.py <maquina>.apolo --json out.json --perfil out.prof

`--sin-perfil` mide sin cProfile (el perfilador infla ~1,5–2× lo que es Python puro). La salida
`--json` guarda la salida de `sobrantes` (el veredicto que hay que conservar) y una fila por
candidata (`probar`): ms de pared, ms de CPU, control que la pide y ms por etapa.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
import time
from pathlib import Path


def _filas_por_candidata(Prueba):
    """Envuelve `Prueba.probar` para medir cada candidata (sin cambiar lo que devuelve)."""
    filas: list[dict] = []
    original = Prueba.probar

    def probar(self, c):
        antes = dict(self.ms)
        t, cpu = time.perf_counter(), time.process_time()
        r = original(self, c)
        fila = {"id": c, "nombre": getattr(self.doc.scene.get(c), "name", c),
                "ms": round((time.perf_counter() - t) * 1000.0, 1),
                "cpu_ms": round((time.process_time() - cpu) * 1000.0, 1),
                "control": None if r is None else r["control"],
                "apoyo": None if r is None else ("tambien_tapa" if "tambien_tapa" in r else
                                                 "solo_apoyo" if "solo_apoyo" in r else None),
                "etapas": {k: round(v - antes.get(k, 0.0), 1) for k, v in self.ms.items()
                           if v - antes.get(k, 0.0) > 0.05}}
        filas.append(fila)
        return r

    Prueba.probar = probar
    return filas, lambda: setattr(Prueba, "probar", original)


def medir(ruta: Path, perfil: bool, top: int) -> dict:
    from apolo.doc import Document
    from apolo.library.engineering.mass import memo_de_geometria
    from apolo.services import calidad_sobrantes as cs
    from apolo.services.puerta_publicacion import Contexto, items_de_fuentes

    t = time.perf_counter()
    doc = Document.from_apolo_bytes(ruta.read_bytes(), tolerant=True)
    out: dict = {"archivo": str(ruta), "piezas": len(doc.scene),
                 "carga_s": round(time.perf_counter() - t, 1),
                 "puerta_primera": getattr(doc, "puerta_primera", None)}
    tiempos: dict = {}
    filas, restaurar = _filas_por_candidata(cs.Prueba)
    try:
        with memo_de_geometria():
            ctx = Contexto()
            t = time.perf_counter()
            items_de_fuentes(doc, None, ctx, tiempos)
            out["fuentes_s"] = round(time.perf_counter() - t, 1)
            out["tiempos_fuentes_s"] = {k: round(v, 2) for k, v in tiempos.items()}
            pr = cProfile.Profile() if perfil else None
            t, cpu = time.perf_counter(), time.process_time()
            if pr:
                pr.enable()
            sobra = cs.sobrantes(doc, ctx)
            if pr:
                pr.disable()
            out["sobrantes_s"] = round(time.perf_counter() - t, 1)
            out["sobrantes_cpu_s"] = round(time.process_time() - cpu, 1)
    finally:
        restaurar()
    out["sobrantes"] = sobra
    out["por_candidata"] = filas
    if pr:
        out["_perfil"] = pr
        for orden in ("tottime", "cumulative"):
            s = io.StringIO()
            pstats.Stats(pr, stream=s).sort_stats(orden).print_stats(top)
            out[f"perfil_{orden}"] = s.getvalue()
    return out


def resumen(m: dict) -> str:
    s = m["sobrantes"]
    lineas = [f"{m['archivo']}: {m['piezas']} piezas, carga {m['carga_s']} s, fuentes "
              f"{m.get('fuentes_s')} s, puerta_primera={m['puerta_primera']}"]
    if "error" in s:
        return "\n".join(lineas + [f"  error: {s['error']}"])
    lineas.append(f"  sobrantes: {m['sobrantes_s']} s pared, {m['sobrantes_cpu_s']} s CPU; "
                  f"{s['candidatas']} candidatas, {len(s['sobrantes'])} sobran, "
                  f"{len(s['necesarias'])} necesarias, {s['vueltas']} vueltas")
    for k, v in s["por_etapa"].items():
        lineas.append(f"    {k:<11} {v['pruebas']:>4} pruebas  {v['ms'] / 1000:8.1f} s")
    por: dict = {}
    for f in m["por_candidata"]:
        k = f["control"] or "sobra"
        if f["apoyo"]:
            k += f" ({f['apoyo']})"
        n, ms = por.get(k, (0, 0.0))
        por[k] = (n + 1, ms + f["ms"])
    lineas.append("  por control que la decide (pruebas, s):")
    for k, (n, ms) in sorted(por.items(), key=lambda x: -x[1][1]):
        lineas.append(f"    {k:<32} {n:>4}  {ms / 1000:8.1f} s  ({ms / max(n, 1):7.0f} ms c/u)")
    return "\n".join(lineas)


def veredicto(sobra: dict) -> dict:
    """La salida de `sobrantes` sin los tiempos: lo que un cambio de rendimiento no puede mover."""
    out = {k: v for k, v in sobra.items() if k != "ms"}
    if "por_etapa" in out:
        out["por_etapa"] = {k: {kk: vv for kk, vv in v.items() if kk != "ms"}
                            for k, v in out["por_etapa"].items()}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("apolo", type=Path, nargs="+")
    ap.add_argument("--json", type=Path, help="vuelca la medida (una lista, una por archivo)")
    ap.add_argument("--perfil", type=Path, help="guarda el .prof (con varios: sufijo por archivo)")
    ap.add_argument("--sin-perfil", action="store_true")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--contra", type=Path, help="un --json previo: sale con 1 si algún veredicto "
                    "(la salida de sobrantes sin tiempos) difiere")
    a = ap.parse_args(argv)
    previas = (json.loads(a.contra.read_text(encoding="utf-8")) if a.contra else None)
    todas = []
    for i, ruta in enumerate(a.apolo):
        m = medir(ruta, not a.sin_perfil, a.top)
        pr = m.pop("_perfil", None)
        if pr is not None and a.perfil:
            dest = a.perfil if len(a.apolo) == 1 else a.perfil.with_suffix(f".{i}.prof")
            pr.dump_stats(str(dest))
        print(resumen(m), flush=True)
        if "perfil_tottime" in m:
            print(m["perfil_tottime"], flush=True)
        todas.append(m)
    if a.json:
        a.json.write_text(json.dumps(todas, ensure_ascii=False, indent=1, default=str),
                          encoding="utf-8")
    if previas is not None:
        antes = {m["archivo"]: veredicto(m["sobrantes"]) for m in previas}
        distintas = [m["archivo"] for m in todas
                     if json.loads(json.dumps(veredicto(m["sobrantes"]), default=str))
                     != antes.get(m["archivo"])]
        print("veredictos iguales" if not distintas else f"VEREDICTO DISTINTO: {distintas}")
        return 1 if distintas else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
