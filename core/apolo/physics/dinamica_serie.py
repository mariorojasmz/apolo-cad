"""La marcha como SERIE DE TIEMPO para el reproductor del visor (visor-realista D4).

Calcular ≠ mirar: el servidor simula (`simulate_dynamics`) y esto convierte su salida en lo
que el visor reproduce a 60 fps interpolando, sin volver a pedir nada:

- `t`: los instantes muestreados (≈ `hz` por segundo simulado; caen en un intercambio, así que
  el visor interpola por el `t` real, no por el índice).
- `cuerpos`: por cuerpo de junta, la transformación RELATIVA a su pose inicial,
  T(t) = P(t)·P(0)⁻¹, como `x, y, z, qx, qy, qz, qw` (mm; cuaternión en el orden de three.js)
  aplanados por muestra. El visor la aplica sobre la malla de diseño de cada pieza del cuerpo:
  no depende de dónde puso MuJoCo el origen del cuerpo (lo mismo hace el GIF).
- `productos`: pose ABSOLUTA del centro de cada caja desde la muestra `desde` (la primera en la
  que existe: con `cada_s` nacen en su hora); el visor dibuja la caja con `dims_mm`.
- `juntas`: el valor `q` de cada junta por muestra (grados o mm): el ángulo del piñón del que
  F3 deriva el avance de las cadenas.
- `bandas`: la velocidad de la cara superior por muestra (m/s, positiva hacia `direccion`): la
  textura de la faja corre con ella (D3: lo animado sale de la física).

Puro: recibe dicts y los `BandaDatos` del snapshot; no importa `doc`, `api` ni `state`.
"""

from __future__ import annotations

import math

import numpy as np

#: Tope de números de pose (7 por entidad y muestra) de una serie: ≈ 16 MB de JSON. Si una
#: petición lo pasa (muchas cajas × mucho tiempo), se baja la frecuencia y se avisa.
MAX_VALORES_POSE = 2_000_000
HZ_MIN = 10


def _quat_xyzw(r: np.ndarray) -> tuple[float, float, float, float]:
    """Cuaternión unitario (x, y, z, w) de una matriz de rotación 3×3 (método de Shepperd)."""
    tr = r[0, 0] + r[1, 1] + r[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * s, (r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        w, x, y, z = (r[2, 1] - r[1, 2]) / s, 0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s
    elif r[1, 1] > r[2, 2]:
        s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        w, x, y, z = (r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s
    else:
        s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        w, x, y, z = (r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s
    if w < 0:   # hemisferio fijo: dos muestras seguidas no saltan de q a −q
        w, x, y, z = -w, -x, -y, -z
    return x, y, z, w


def _pq(m: np.ndarray) -> list[float]:
    x, y, z, w = _quat_xyzw(m[:3, :3])
    return [round(float(m[0, 3]), 2), round(float(m[1, 3]), 2), round(float(m[2, 3]), 2),
            round(x, 6), round(y, 6), round(z, 6), round(w, 6)]


def hz_para(duracion_s: float, entidades: int, hz: int) -> int:
    """La frecuencia de muestreo que cabe en `MAX_VALORES_POSE` (≤ `hz`, ≥ `HZ_MIN`)."""
    muestras = max(1.0, duracion_s) * max(1, entidades) * 7
    return int(max(HZ_MIN, min(hz, MAX_VALORES_POSE // muestras)))


def serie_reproduccion(res: dict, bandas=(), *, hz: int) -> dict:
    """Serie del reproductor desde la salida de `simulate_dynamics` (con sus `frames`) y los
    `BandaDatos` del snapshot (`snap.bandas`)."""
    frames = res.get("frames") or []
    t = [f["t"] for f in frames]
    cuerpos = {}
    for c in res.get("cuerpos") or []:
        nombre = c["name"]
        mats = [np.asarray(f["poses"][nombre], float) for f in frames if nombre in f["poses"]]
        if len(mats) != len(frames) or not mats:
            continue
        p0_inv = np.linalg.inv(mats[0])
        poses = [v for m in mats for v in _pq(m @ p0_inv)]
        cuerpos[nombre] = {"junta": c["junta"], "piezas": list(c["piezas"]), "poses": poses}
    productos = []
    for p in res.get("productos") or []:
        nombre = p["name"]
        desde = next((k for k, f in enumerate(frames) if nombre in f["poses"]), None)
        if desde is None:   # nació después del final: no se ve
            continue
        poses = [v for f in frames[desde:] for v in _pq(np.asarray(f["poses"][nombre], float))]
        productos.append({"name": nombre, "producto": p.get("producto", nombre),
                          "dims_mm": [p["w"], p["d"], p["h"]], "desde": desde, "poses": poses})
    trazas = res.get("juntas") or {}
    juntas = {n: {"tipo": tr["tipo"], "unidad": tr["unidades"]["q"], "q": list(tr["q"])}
              for n, tr in trazas.items()}
    salida_bandas = []
    for b in bandas:
        tr = trazas.get(b.junta)
        if tr is None:
            continue
        v = [round(qd * 2 * math.pi / 60.0 * b.radio, 5) for qd in tr["qd"]]  # rpm → m/s
        salida_bandas.append({"pieza": b.pieza, "junta": b.junta, "radio_mm": round(b.radio * 1000, 2),
                              "direccion": [round(float(c), 6) for c in b.e], "v_m_s": v})
    return {
        "hz": hz,
        "duracion_s": t[-1] if t else 0.0,
        "t": t,
        "cuerpos": cuerpos,
        "productos": productos,
        "juntas": juntas,
        "bandas": salida_bandas,
        "resumen": res.get("resumen", {}),
        "avisos": list(res.get("avisos") or []),
        **({"mensaje": res["mensaje"]} if res.get("mensaje") else {}),
    }
