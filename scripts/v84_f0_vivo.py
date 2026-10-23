"""F0 de V8.4: mide el planificador de V8.3 en un bucle «vivo» de prueba (sólo medición).

Dos pasos, para que el bucle corra como en el worker (sin OCCT cargado, BLAS de un hilo):

    # 1) snapshot (OCCT: regenera el .apolo y hornea la co-simulación) → pickle
    python -B scripts/v84_f0_vivo.py preparar --apolo C:/t/v84f0/faja77.apolo --escenario marcha \
        --variante sin_cajas --dur 20 --salida C:/t/v84f0/snap_sin.pkl
    # 2) bucle vivo sin dormir: factor, fotograma binario, acción del operador sin hora
    python -B scripts/v84_f0_vivo.py medir --snap C:/t/v84f0/snap_sin.pkl

Variantes: `sin_cajas` (sin productos), `cajas_2` (10 cajas cada 2 s), `cajas_1_5` (cada 1,5 s).
En `medir` el escenario pierde sus acciones con hora: `pulsar -S1` (0,3 s) se INYECTA sin hora en
el intercambio de t = 0,5 s (el mismo instante que el lote) y otra vez a mitad de la corrida. La
huella sale igual a la del lote con la acción agendada: la inyección es determinista.

No toca código de producción: el bucle es una copia de `planificador.correr` con el reloj abierto.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import statistics
import sys
import time

VENTANA_S = 1.0 / 30.0  # publicar a 30 Hz (D2)
N_SENALES = 200


def preparar(a) -> None:
    from apolo.doc.document import Document

    t0 = time.perf_counter()
    with open(a.apolo, "rb") as f:
        doc = Document.from_apolo_bytes(f.read())
    t_doc = time.perf_counter() - t0
    for variante in a.variante.split(","):
        _preparar_una(a, doc, variante, t_doc)


def _preparar_una(a, doc, variante: str, t_doc: float) -> None:
    from apolo.services.cosim_snapshot import snapshot_cosim

    esc = json.loads(json.dumps(doc.escenarios[a.escenario]["escenario"]))
    esc["duracion_s"] = a.dur
    esc["aserciones"] = []
    prods = [e for e in esc.get("eventos", []) if e.get("tipo") == "producto"]
    otros = [e for e in esc.get("eventos", []) if e.get("tipo") != "producto"]
    if variante == "sin_cajas":
        esc["eventos"] = otros
    else:
        cada = {"cajas_2": 2.0, "cajas_1_5": 1.5}[variante]
        for p in prods:
            p["cada_s"], p["cantidad"], p["t"] = cada, 10, 2.0
        esc["eventos"] = otros + prods
    t1 = time.perf_counter()
    snap = snapshot_cosim(doc, esc)
    t_snap = time.perf_counter() - t1
    salida = a.salida.format(variante=variante)
    with open(salida, "wb") as f:
        pickle.dump(snap, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(json.dumps({"variante": variante, "regenerar_s": round(t_doc, 2), "snapshot_s": round(t_snap, 2),
                      "pickle_kb": round(os.path.getsize(salida) / 1024, 1),
                      "acciones": [x.__dict__ for x in snap.escenario.acciones]}, default=str))


def _numericas(fuentes, extra) -> list[float]:
    vals = []
    for _pref, s in fuentes:
        for v in s.values():
            if isinstance(v, (bool, int, float)):
                vals.append(float(v))
    vals.extend(float(v) for v in extra.values())
    return vals


def medir(a) -> None:
    os.environ.update({"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
    import numpy as np

    from apolo.cosim import planificador as P
    from apolo.cosim.acople import AcopleMecanico
    from apolo.cosim.agenda import Agenda
    from apolo.cosim.escenario import Accion
    from apolo.cosim.tablero import Tablero
    from apolo.cosim.trazas import Trazas, huella
    from apolo.physics.dinamica_integrador import Integrador
    from apolo.plc import PLC

    with open(a.snap, "rb") as f:
        snap = pickle.load(f)  # noqa: S301 — lo escribió `preparar`
    esc = snap.escenario
    agendadas = list(esc.acciones)
    if not a.agendado:
        esc.acciones = []  # en vivo las acciones llegan sin hora

    integ = Integrador(snap.dinamica)
    tab = Tablero(snap.red, snap.dispositivos)
    plcs = {}
    for p in snap.programas:
        plc = PLC(p.compilado, ciclo_ms=p.ciclo_ms, ciclos=p.ciclos or None)
        plc.cortar()
        plcs[p.plc] = plc
    acople = AcopleMecanico(integ, snap.motores, snap.sensores)
    agenda = Agenda(esc, tab, acople)
    dt = integ.dt_int
    paso_ms = P._paso_ms(dt)
    trazas = Trazas(esc.analogicas_hz, dt)
    extra = set(esc.senales_extra)
    signos = P._signos_banda(snap)
    n = integ.n_int
    k_inyeccion = {} if a.agendado else {int(round(0.5 / dt)): "arranque", **({} if a.solo_arranque else {n // 2: "mitad"})}
    acc_s1 = next((x for x in agendadas if x.dispositivo == "-S1"), None)

    ventanas, frame_gather, frame_pack, inyecciones, costo_k = [], [], [], [], []
    prox_pub = VENTANA_S
    t_ini_ventana = time.perf_counter()
    t0 = t_ini_ventana
    n_cuerpos_max, bytes_frame = 0, 0
    import tracemalloc

    tracemalloc.start()  # lo que el bucle ACUMULA (trazas, fotogramas de V8.2): crece con la sesión
    for k in range(n + 1):
        t = k * dt
        a0 = time.perf_counter()
        if k in k_inyeccion and acc_s1 is not None:
            # ── la acción sin hora: se inserta en la agenda donde va y la consume `aplicar(t)` ──
            ai = time.perf_counter()
            agenda.items.insert(agenda.i, (t, -1, Accion(t, acc_s1.accion, acc_s1.dispositivo,
                                                         acc_s1.valor, acc_s1.durante_s,
                                                         acc_s1.actuador), False))
            agenda.aplicar(t)
            inyecciones.append({"cuando": k_inyeccion[k], "t": t,
                                "aplicar_us": round((time.perf_counter() - ai) * 1e6, 1)})
        else:
            agenda.aplicar(t)
        tab.mec, tab.detecta = acople.leer()
        tab.paso(dt)
        for des, plc in plcs.items():
            P._plc(des, plc, tab, k * paso_ms, esc.plc_run)
        fuentes = tab.salidas_por_prefijo() + P._fuentes_plc(plcs)
        trazas.registrar(k, t, fuentes, lambda: {**tab.senales_red(extra), **P._mecanica(integ, signos)},
                         forzar=k == n)
        if k == n:
            break
        integ.intercambio(control=acople.control(tab.comandos))
        if inyecciones and inyecciones[-1]["t"] == t and "intercambio_us" not in inyecciones[-1]:
            inyecciones[-1]["intercambio_us"] = round((time.perf_counter() - a0) * 1e6, 1)
        costo_k.append(time.perf_counter() - a0)
        tv = (k + 1) * dt
        if tv >= prox_pub - 1e-9:
            # ── el fotograma binario de 30 Hz con lo que el planificador ya tiene ──
            g0 = time.perf_counter()
            d = integ.d
            ids = list(integ.bid_cuerpo.values()) + [b for kk, b in enumerate(integ.bid_prod)
                                                     if integ.activo[kk]]
            vals = _numericas(fuentes, {**tab.senales_red(extra), **P._mecanica(integ, signos)})
            g1 = time.perf_counter()
            senales = np.zeros(N_SENALES, np.float32)
            m = min(len(vals), N_SENALES)
            senales[:m] = vals[:m]
            cuerpo = np.concatenate([d.xpos[ids], d.xquat[ids]], axis=1).astype(np.float32)
            buf = (np.array([tv, len(ids)], np.float32).tobytes() + cuerpo.tobytes() + senales.tobytes())
            g2 = time.perf_counter()
            frame_gather.append(g1 - g0)
            frame_pack.append(g2 - g1)
            n_cuerpos_max = max(n_cuerpos_max, len(ids))
            bytes_frame = max(bytes_frame, len(buf))
            ahora = time.perf_counter()
            ventanas.append(ahora - t_ini_ventana)
            t_ini_ventana = ahora
            prox_pub += VENTANA_S
    pared = time.perf_counter() - t0
    mem_mb = tracemalloc.get_traced_memory()[0] / 1e6
    tracemalloc.stop()
    salida = trazas.salida()
    final = trazas.cerrar()
    dur = n * dt
    v_ms = sorted(w * 1000 for w in ventanas)
    # D1: dormir lo que sobre en cada ventana → una ventana lenta NO se recupera (deuda)
    con_sueno = sum(max(w, VENTANA_S) for w in ventanas)
    # reloj absoluto: se duerme hasta la hora de pared de la ventana; si va atrás, no duerme y
    # recupera la deuda en las ventanas rápidas
    pared_abs, objetivo = 0.0, 0.0
    for w in ventanas:
        objetivo += VENTANA_S
        pared_abs = max(pared_abs + w, objetivo)
    q = statistics.quantiles(v_ms, n=100) if len(v_ms) > 2 else v_ms
    print(json.dumps({
        "duracion_s": round(dur, 3), "intercambios": n, "pared_s": round(pared, 3),
        "factor_sin_dormir": round(dur / pared, 3),
        "factor_vivo_dormir_por_ventana": round(dur / con_sueno, 3),
        "factor_vivo_reloj_absoluto": round(dur / pared_abs, 3),
        "ventana_ms": {"p50": round(statistics.median(v_ms), 2), "p95": round(q[94], 2),
                       "p99": round(q[98], 2), "max": round(v_ms[-1], 2),
                       "frac_lentas_gt_33ms": round(sum(w > VENTANA_S * 1000 for w in v_ms) / len(v_ms), 4)},
        "intercambio_us_p50": round(statistics.median(costo_k) * 1e6, 1),
        "memoria_acumulada_mb": round(mem_mb, 1),  # con tracemalloc (el factor de esta corrida baja)
        "fotograma": {"bytes": bytes_frame, "cuerpos_max": n_cuerpos_max,
                      "senales_numericas": len(vals), "reunir_us_p50": round(statistics.median(frame_gather) * 1e6, 1),
                      "empacar_us_p50": round(statistics.median(frame_pack) * 1e6, 1)},
        "inyecciones": inyecciones,
        "eventos": agenda.eventos,
        "huella": huella(salida, agenda.eventos, final),
        "final": {k2: final.get(k2) for k2 in ("-M1.rpm", "-K1.Main.cuenta", "-H1.encendido") if k2 in final},
        "agendado": bool(a.agendado),
        "python": sys.version.split()[0],
    }, default=str))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar")
    p.add_argument("--apolo", required=True)
    p.add_argument("--escenario", default="marcha")
    p.add_argument("--variante", default="sin_cajas",
                   help="sin_cajas, cajas_2, cajas_1_5 (varias separadas por coma)")
    p.add_argument("--dur", type=float, default=20.0)
    p.add_argument("--salida", required=True, help="ruta del pickle; admite {variante}")
    m = sub.add_parser("medir")
    m.add_argument("--snap", required=True)
    m.add_argument("--agendado", action="store_true", help="la acción con hora del escenario (el lote)")
    m.add_argument("--solo-arranque", action="store_true", help="sin la inyección de la mitad (compara con el lote)")
    a = ap.parse_args()
    (preparar if a.cmd == "preparar" else medir)(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
