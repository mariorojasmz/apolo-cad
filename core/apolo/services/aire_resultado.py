"""Lo que la memoria lee del AIRE de una co-simulación (plan V8.9 D10, F4): el tiempo de carrera de
cada cilindro, su velocidad máxima y el aire que contó cada FRL, medidos sobre las trazas.

`resumen_aire(res)` corre sobre el resultado del worker (con trazas) y lo guarda
`escenarios.resultado_compacto` en `resultado["aire"]` (las trazas no se guardan: pesan cientos de
KB). Sin cilindros en las trazas devuelve None y el compacto queda como siempre.

Cómo se mide (criterio de medición, declarado en `medicion`):
  - el cilindro se reconoce por su señal `<des>.pA_bar` (D7); su recorrido, por `<des>.x_mm`;
  - una carrera de AVANCE es el tramo en que x sube del 2 % al 98 % del máximo que alcanzó en la
    corrida; la de RETROCESO, el tramo siguiente en que baja del 98 % al 2 %. Los cruces se
    interpolan linealmente entre muestras (las analógicas van a `analogicas_hz`, 50 Hz por
    defecto: la resolución se declara);
  - `x_max_mm` dice hasta dónde llegó: si no llega a la carrera, la carga lo frenó o el tope de la
    junta no se alcanzó (la memoria lo compara con la carrera del servicio);
  - `v_max_m_s`: la mayor |v| muestreada de `<des>.v_m_s` (el pico entre muestras puede ser algo
    mayor);
  - `consumo_NL` de cada FRL: su `<des>.consumo_NL` final (acumulado en la corrida).
Puro: sólo lee el dict del resultado.
"""

from __future__ import annotations

BAJO, ALTO = 0.02, 0.98


def _cruce(t, x, i: int, nivel: float) -> float:
    """El instante interpolado en que x cruza `nivel` entre las muestras i-1 e i."""
    x0, x1 = x[i - 1], x[i]
    if x1 == x0:
        return t[i]
    return t[i - 1] + (nivel - x0) / (x1 - x0) * (t[i] - t[i - 1])


def _carreras(t: list, x: list) -> dict:
    xmax = max(x)
    out: dict = {"x_max_mm": round(xmax, 3)}
    if xmax <= 0.5:
        return out
    lo, hi = BAJO * xmax, ALTO * xmax
    t_lo = t_hi = None
    k = 0
    for i in range(1, len(x)):  # avance: el último cruce de `lo` hacia arriba antes de llegar a `hi`
        if x[i - 1] < lo <= x[i]:
            t_lo = _cruce(t, x, i, lo)
        if x[i - 1] < hi <= x[i] and t_lo is not None:
            t_hi, k = _cruce(t, x, i, hi), i
            break
    if t_hi is None:
        return out
    out["t_avance_s"] = round(t_hi - t_lo, 4)
    t_baja = None
    for i in range(k + 1, len(x)):  # retroceso: de `hi` hacia abajo hasta `lo`
        if t_baja is None and x[i - 1] > hi >= x[i]:
            t_baja = _cruce(t, x, i, hi)
        if t_baja is not None and x[i - 1] > lo >= x[i]:
            out["t_retroceso_s"] = round(_cruce(t, x, i, lo) - t_baja, 4)
            break
    return out


def resumen_aire(res: dict) -> dict | None:
    """{cilindros: {des: {x_max_mm, t_avance_s?, t_retroceso_s?, v_max_m_s}}, frl: {des:
    {consumo_NL}}, medicion: «…»} o None si la corrida no tiene cilindros."""
    an = ((res.get("trazas") or {}).get("analogicas")) or {}
    t, senales = an.get("t") or [], an.get("senales") or {}
    final = res.get("final") or {}
    nombres = set(senales) | set(final)
    cilindros = sorted(n[: -len(".pA_bar")] for n in nombres if n.endswith(".pA_bar"))
    if not cilindros:
        return None
    out: dict = {"cilindros": {}}
    for des in cilindros:
        xs = senales.get(f"{des}.x_mm") or []
        par = [(ti, xi) for ti, xi in zip(t, xs) if xi is not None]
        fila = _carreras([p[0] for p in par], [p[1] for p in par]) if len(par) > 1 else {}
        vs = [abs(v) for v in (senales.get(f"{des}.v_m_s") or []) if v is not None]
        if vs:
            fila["v_max_m_s"] = round(max(vs), 4)
        out["cilindros"][des] = fila
    frl = {n[: -len(".consumo_NL")]: {"consumo_NL": round(float(final[n]), 4)}
           for n in sorted(final) if n.endswith(".consumo_NL") and isinstance(final[n], (int, float))}
    if frl:
        out["frl"] = frl
    dt = (t[1] - t[0]) if len(t) > 1 else None
    out["medicion"] = (f"carrera = del {BAJO:.0%} al {ALTO:.0%} del recorrido máximo, cruces interpolados; "
                       f"muestras cada {dt * 1000:.0f} ms" if dt else "sin muestras analógicas")
    return out
