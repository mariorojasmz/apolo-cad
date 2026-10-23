"""F1 de V8.4: mide la sesión en vivo por el camino NUEVO (worker vivo en su proceso).

Dos pasos, como F0 (`scripts/v84_f0_vivo.py`), para que el bucle corra sin OCCT en el proceso
que mide:

    # 1) el snapshot de la sesión: escenario de base → `escenario_vivo` → `snapshot_cosim`
    python -B scripts/v84_f1_vivo.py preparar --apolo C:/t/v84f1/faja77.apolo --escenario marcha \
        --variante sin_cajas,cajas --salida C:/t/v84f1/vivo_{variante}.pkl
    # 2) el worker vivo (`cosim.proceso_vivo.ProcesoVivo`) al ritmo de la pared
    python -B scripts/v84_f1_vivo.py medir --snap C:/t/v84f1/vivo_cajas.pkl --dur 30 --ritmo 1

`sin_cajas` quita la cola de productos del escenario; `cajas` deja la del de base (en la 77,
10 cajas cada 2 s). En `medir` el script aprieta lo mismo que el escenario de base a su hora de
pared (las acciones con hora pasan a ser clics) y reporta: el factor de cada fotograma (el que
ve la UI), el factor total (virtual / pared), los fotogramas por segundo de pared, el retardo de
cada ack (pared, desde que se envió) y los avisos de factor. `--ritmo 0` = sin dormir.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import statistics
import sys
import threading
import time


def preparar(a) -> None:
    from apolo.cosim.vivo import escenario_vivo
    from apolo.doc.document import Document
    from apolo.services.cosim_snapshot import snapshot_cosim

    with open(a.apolo, "rb") as f:
        doc = Document.from_apolo_bytes(f.read())
    base = json.loads(json.dumps(doc.escenarios[a.escenario]["escenario"]))
    for variante in a.variante.split(","):
        esc = escenario_vivo(base)
        if variante == "sin_cajas":
            esc["eventos"] = []
        t0 = time.perf_counter()
        snap = snapshot_cosim(doc, esc)
        snap.acciones_base = [g for g in base.get("acciones") or []]  # las que `medir` aprieta
        salida = a.salida.format(variante=variante)
        with open(salida, "wb") as f:
            pickle.dump(snap, f, protocol=pickle.HIGHEST_PROTOCOL)
        print(json.dumps({"variante": variante, "snapshot_s": round(time.perf_counter() - t0, 2),
                          "productos": len(snap.dinamica.productos), "pickle_kb": round(os.path.getsize(salida) / 1024, 1)}))


def medir(a) -> None:
    import numpy as np

    from apolo.cosim.proceso_vivo import ProcesoVivo
    from apolo.cosim.vivo_fotograma import leer_fotograma

    with open(a.snap, "rb") as f:
        snap = pickle.load(f)  # noqa: S301 — lo escribió `preparar`
    acciones = sorted(getattr(snap, "acciones_base", []), key=lambda x: x["t"])
    fotos, jsons, enviados, acks = [], [], {}, {}
    hecho = threading.Event()

    def al_mensaje(etiqueta, cuerpo):
        ahora = time.perf_counter()
        if etiqueta == b"F":
            f = leer_fotograma(cuerpo)
            fotos.append((ahora, f["t"], f["factor"], len(cuerpo)))
        elif etiqueta == b"J":
            m = json.loads(cuerpo)
            jsons.append(m)
            if m.get("tipo") in ("ack", "rechazo") and m.get("id") in enviados:
                acks[m["id"]] = (ahora - enviados[m["id"]]) * 1000.0
        elif etiqueta is None:
            hecho.set()

    t0 = time.perf_counter()
    p = ProcesoVivo(snap, {"ritmo": a.ritmo, "max_s": a.dur}, al_mensaje)
    while not fotos and not hecho.is_set():
        time.sleep(0.005)
    t_inicio = time.perf_counter()
    arranque_s = t_inicio - t0
    for k, acc in enumerate(acciones):
        msg = {k2: v for k2, v in acc.items() if k2 != "t"} | {"id": k}
        objetivo = t_inicio + float(acc["t"]) / (a.ritmo or 50.0)
        while time.perf_counter() < objetivo and not hecho.is_set():
            time.sleep(0.002)
        enviados[k] = time.perf_counter()
        p.enviar(msg)
    hecho.wait(a.dur * 4 + 120)
    p.cerrar()
    pared = fotos[-1][0] - fotos[0][0]
    virtual = fotos[-1][1] - fotos[0][1]
    fac = [x[2] for x in fotos[30:]] or [x[2] for x in fotos]
    dts = np.diff([x[0] for x in fotos]) * 1000.0
    fin = next((m for m in jsons if m.get("tipo") == "fin"), {})
    print(json.dumps({
        "snap": os.path.basename(a.snap), "ritmo": a.ritmo, "productos": len(snap.dinamica.productos),
        "arranque_s": round(arranque_s, 2), "fotogramas": len(fotos), "bytes_fotograma": fotos[-1][3],
        "factor_total": round(virtual / pared, 3) if pared > 0 else None,
        "factor_fotograma": {"min": round(min(fac), 3), "p05": round(float(np.percentile(fac, 5)), 3),
                             "p50": round(statistics.median(fac), 3)},
        "fps_pared": round((len(fotos) - 1) / pared, 2) if pared > 0 else None,
        "entre_fotogramas_ms": {"p50": round(float(np.percentile(dts, 50)), 2),
                                "p95": round(float(np.percentile(dts, 95)), 2), "max": round(float(dts.max()), 2)},
        "ack_ms": {str(k): round(v, 1) for k, v in sorted(acks.items())},
        "avisos_factor": [m for m in jsons if m.get("tipo") == "factor"],
        "fin": {k: fin.get(k) for k in ("motivo", "t", "intercambios")},
        "grabacion": fin.get("grabacion"),
        "python": sys.version.split()[0],
    }, default=str))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar")
    p.add_argument("--apolo", required=True)
    p.add_argument("--escenario", default="marcha")
    p.add_argument("--variante", default="sin_cajas,cajas")
    p.add_argument("--salida", required=True, help="ruta del pickle; admite {variante}")
    m = sub.add_parser("medir")
    m.add_argument("--snap", required=True)
    m.add_argument("--dur", type=float, default=30.0, help="segundos virtuales (el tope de la sesión)")
    m.add_argument("--ritmo", type=float, default=1.0, help="1 = tiempo real; 0 = sin dormir")
    a = ap.parse_args()
    (preparar if a.cmd == "preparar" else medir)(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
