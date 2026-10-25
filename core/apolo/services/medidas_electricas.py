"""Las cifras eléctricas MEDIDAS de una co-simulación (plan pedidos-de-extensiones D7): la caída de
tensión de cada motor en el arranque y en régimen, y cada disparo de una protección con su hora,
su corriente y su causa. Las lee la memoria de cálculo (o una extensión de entregables) sin volver
a simular: `escenarios.resultado_compacto` las guarda en `resultado["electrico"]` (las trazas no se
guardan), como el aire en `aire_resultado.py`.

Dos partes:
  - `referencias(doc)`: lo que la medida necesita del DOCUMENTO (la API la arma bajo su lock, nunca
    el worker): por motor, la tensión nominal de la red que lo alimenta (`U_ref_V`), su corriente
    de placa en su conexión (`In_A`) y si va tras un variador (`tras_variador`), con la propagación
    de `library/electrico/redes.analizar` (de qué fuente le llegan las fases);
  - `resumen_electrico(res, refs)`: PURO, sobre el resultado del worker (con trazas). Sin motores
    ni disparos devuelve None y el compacto queda como siempre.

Cómo se mide (criterio de medición, declarado en `medicion`):
  - las señales: `<motor>.U_V` (la tensión de línea en sus bornes, la que usa el modelo del motor),
    `<motor>.I_A` y `<protección>.I_disparo_A` (la mayor corriente de sus polos en el paso del
    disparo, retenida hasta rearmar: el muestreo de 50 Hz no la pierde); un diferencial dispara
    por la residual y publica `I_residual_disparo_mA`: su disparo lleva `I_residual_mA`, nunca
    `I_A` (un 30 mA no «dispara con 3,2 A»);
  - ARRANQUE: desde la primera muestra con U > 0 hasta la primera con I < 1,5·In de placa (el
    primer arranque de la corrida); `U_min_arranque_V` es la menor U muestreada en ese tramo. Las
    analógicas van a `analogicas_hz` (50 Hz por defecto: una muestra cada 20 ms) y un arranque
    directo de un motor chico dura menos que eso: el mínimo entre muestras puede ser más bajo (con
    `trazas.analogicas_hz: 500` se ve cada intercambio de 2 ms);
  - RÉGIMEN: la mediana de U en el último 0,5 s alimentado con I < 1,5·In, después del arranque
    (un motor trabado no está en régimen);
  - ΔU = (U_ref − U)/U_ref en %, contra la tensión nominal de la red que lo alimenta: un evento
    `caida_de_red` también cuenta (es lo que vio el motor). Tras un variador la tensión en bornes es
    la salida V/f del variador, no una caída de la red: lleva `tras_variador: true` y no lleva ΔU;
  - DISPARO: cada vez que `<des>.disparado` pasa a verdadero en una protección que publica
    `I_disparo_A` o `I_residual_disparo_mA`; `causa` es la que publica («térmico», «magnético», «diferencial», «avería»;
    un fusible no la publica: «fusión», o «avería» con la falla `abierto`).
"""

from __future__ import annotations

from statistics import median

#: Fin del arranque: la corriente del motor baja de este múltiplo de su In de placa.
UMBRAL_ARRANQUE_IN = 1.5
#: Ventana del régimen: el último tramo alimentado, en s.
VENTANA_REGIMEN_S = 0.5
#: Lo que dice quien lee un resultado guardado antes de que existieran estas cifras (D8): sigue
#: vigente (`COSIM_EPOCH` no subió), sólo le faltan.
SIN_CIFRAS = ("el resultado es de antes de que se midieran las cifras eléctricas (sigue vigente): "
              "córrelo de nuevo para tenerlas")
_EPS_T = 1e-9
#: La señal que retiene cada protección al disparar → la clave del disparo en `electrico`: la
#: corriente de sus polos, o la RESIDUAL en un diferencial (dispara por ella, no por la de fase).
SENALES_DISPARO = (("I_disparo_A", "I_A", 3), ("I_residual_disparo_mA", "I_residual_mA", 3))


# ── del documento (bajo el lock del llamador) ──────────────────────────────────────────────


def _modelo_de(d):
    """El modelo de co-simulación de un dispositivo, con un ajuste obligatorio que falte en su
    punto medio (sólo se leen datos de placa); None si no se puede armar."""
    from apolo.cosim.modelos import MODELOS, Fusible, RecolectorAjustes

    clase = MODELOS.get((d.modelo or {}).get("tipo"))
    if clase is None:
        return None
    p = RecolectorAjustes(d.designacion, d.ref, d.modelo, d.ajustes)
    try:
        return clase(p, int(d.cantidad or 1)) if clase is Fusible else clase(p)
    except (ValueError, TypeError):  # ModeloIncompleto es ValueError: el snapshot ya lo dijo
        return None


def referencias(doc) -> dict:
    """{motor: {U_ref_V?, In_A?, tras_variador}} de los motores del tablero; {} sin motores."""
    from .electrico import modelo

    m = modelo(doc)
    motores = [(d, c) for d in m.dispositivos for c in d.cargas if c.tipo == "motor"]
    if not motores:
        return {}
    from apolo.library.electrico.redes import analizar

    a = analizar(m)
    out: dict = {}
    for d, c in motores:
        fuentes = set()
        for b in c.bornes:
            idx = a.red(d.designacion, b)
            if idx is not None:
                fuentes |= {ll.potencial.designacion for ll in a.llegadas[idx] if not ll.potencial.referencia}
        tipos = {f: (a.dispositivos[f].modelo or {}).get("tipo") for f in fuentes if f in a.dispositivos}
        ref: dict = {"tras_variador": "variador" in tipos.values()}
        redes = sorted(f for f, t in tipos.items() if t == "red")
        red = _modelo_de(a.dispositivos[redes[0]]) if redes else None
        if red is not None:
            ref["U_ref_V"] = float(red.Un)
        mot = _modelo_de(d)
        if mot is not None and hasattr(mot, "In"):
            ref["In_A"] = float(mot.In)
        out[d.designacion] = ref
    return out


# ── del resultado del worker (puro) ────────────────────────────────────────────────────────


def _pct(u_ref: float, u: float) -> float:
    return round(100.0 * (u_ref - u) / u_ref, 3)


def _motor(t: list, U: list, I: list, ref: dict) -> dict:
    if ref.get("tras_variador"):
        return {"tras_variador": True}
    out: dict = {}
    u_ref, In = ref.get("U_ref_V"), ref.get("In_A")
    if u_ref:
        out["U_ref_V"] = u_ref
    n = len(t)
    k0 = next((k for k in range(n) if (U[k] or 0.0) > 0.0), None)
    if k0 is None:
        out["alimentado"] = False
        return out
    umbral = UMBRAL_ARRANQUE_IN * In if In else None
    fin = None
    k = k0
    while k < n and (U[k] or 0.0) > 0.0:
        if umbral is not None and I[k] is not None and I[k] < umbral:
            fin = k
            break
        k += 1
    tramo = [U[j] for j in range(k0, max(fin if fin is not None else k, k0 + 1))]
    out["U_min_arranque_V"] = round(min(tramo), 3)
    if fin is not None:
        reg = [j for j in range(fin, n) if (U[j] or 0.0) > 0.0 and I[j] is not None and I[j] < umbral]
        if reg:
            t_fin = t[reg[-1]]
            ventana = [U[j] for j in reg if t[j] >= t_fin - VENTANA_REGIMEN_S - _EPS_T]
            out["U_regimen_V"] = round(median(ventana), 3)
    if u_ref:
        out["dU_arranque_pct"] = _pct(u_ref, out["U_min_arranque_V"])
        if "U_regimen_V" in out:
            out["dU_regimen_pct"] = _pct(u_ref, out["U_regimen_V"])
    return out


def _valor_en(cambios: list, t: float, defecto=None):
    """El valor de una discreta en t (el último cambio en o antes de t)."""
    v = defecto
    for tt, x in cambios or ():
        if tt > t + _EPS_T:
            break
        v = x
    return v


def _disparos(t: list, senales: dict, discretas: dict, final: dict) -> list[dict]:
    out = []
    for nombre in sorted(discretas):
        if not nombre.endswith(".disparado"):
            continue
        des = nombre[: -len(".disparado")]
        hay = [(f"{des}.{s}", k, r) for s, k, r in SENALES_DISPARO
               if f"{des}.{s}" in senales or f"{des}.{s}" in final]
        if not hay:
            continue
        clave, sale, decimales = hay[0]
        col = senales.get(clave) or []
        previo = False
        for tt, v in discretas[nombre]:
            if v and not previo:
                j = next((j for j in range(len(t)) if t[j] >= tt - _EPS_T and col[j] is not None), None)
                corriente = col[j] if j is not None else final.get(clave)
                causa = _valor_en(discretas.get(f"{des}.causa"), tt)
                if causa is None:  # un fusible no publica causa
                    causa = "avería" if "abierto" in str(_valor_en(discretas.get(f"{des}.averia"), tt, "")) else "fusión"
                out.append({"dispositivo": des, "t_s": round(tt, 4),
                            sale: round(corriente, decimales) if corriente else None, "causa": causa})
            previo = bool(v)
    return sorted(out, key=lambda d: (d["t_s"], d["dispositivo"]))


def resumen_electrico(res: dict, refs: dict | None = None) -> dict | None:
    """{motores: {des: {U_ref_V, U_min_arranque_V, U_regimen_V, dU_arranque_pct, dU_regimen_pct} o
    {tras_variador: true}}, disparos: [{dispositivo, t_s, I_A (o I_residual_mA), causa}], medicion:
    «…»} o None si
    la corrida no tiene motores (de `refs`) ni disparos."""
    tr = res.get("trazas") or {}
    an = tr.get("analogicas") or {}
    t, senales = an.get("t") or [], an.get("senales") or {}
    discretas, final = tr.get("discretas") or {}, res.get("final") or {}
    motores = {}
    for des in sorted(refs or {}):
        U, I = senales.get(f"{des}.U_V"), senales.get(f"{des}.I_A")
        if U is None or I is None:
            continue
        motores[des] = _motor(t, U, I, refs[des])
    disparos = _disparos(t, senales, discretas, final)
    if not motores and not disparos:
        return None
    out: dict = {}
    if motores:
        out["motores"] = motores
    if disparos:
        out["disparos"] = disparos
    dt = (t[1] - t[0]) if len(t) > 1 else None
    out["medicion"] = (
        f"arranque: desde que U pasa de 0 hasta que I baja de {UMBRAL_ARRANQUE_IN:g}·In de placa (el "
        f"primer arranque; U mínima muestreada); régimen: mediana de U en el último "
        f"{VENTANA_REGIMEN_S:g} s alimentado con I < {UMBRAL_ARRANQUE_IN:g}·In; ΔU contra la tensión "
        f"nominal de la red que alimenta al motor; disparo: la mayor corriente de sus polos en el paso "
        f"en que abrió (un diferencial, la residual); "
        + (f"muestras cada {dt * 1000:g} ms (el mínimo del arranque puede caer entre dos muestras)"
           if dt else "sin muestras analógicas"))
    return out


def cifras(resultado: dict | None, motores: list[str] | tuple = ()) -> dict | None:
    """Lo que lee de un resultado guardado quien quiere las cifras (la memoria, una extensión):
    su `electrico`; si no lo trae y el tablero tiene `motores`, `{"aviso": SIN_CIFRAS}` (un
    resultado de antes de D7, vigente); None si no hay nada que medir."""
    el = (resultado or {}).get("electrico")
    if el:
        return el
    if resultado and motores:
        return {"aviso": SIN_CIFRAS}
    return None
