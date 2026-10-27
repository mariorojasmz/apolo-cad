"""La transmisión rotativo → lineal de un motor del escenario (plan motor-a-eje-lineal D1, D3–D5).

`acoples.motores["-M1"].transmision` dice cómo el eje de salida del reductor mueve una junta
PRISMÁTICA (elevador por cadena o cable, piñón-cremallera, correa dentada, husillo). Lleva UNA
fuente del radio r (v = ω·r):

  - `{"pinon": "<pieza>"}`: la pieza del documento cuyo componente de catálogo trae su diámetro
    primitivo (`d0` de los `PINON-*`): r = d0/2. Sale del MODELO: preferida (D3);
  - `{"diametro_primitivo_mm": 61.09, "fuente": "…"}`: tambor, polea dentada o un piñón sin ficha;
  - `{"avance_mm": 5, "fuente": "…"}`: husillo, el avance por vuelta del eje: r = avance/2π.

Un número declarado lleva su `fuente` (texto): nunca una cifra sin origen. `irreversible: true`
(D5) retiene la junta cuando el motor queda sin tensión (sinfín autoblocante); sin él la carga
la arrastra. Puro: stdlib; lanza `ValueError` con la corrección (el escenario la vuelve
`EscenarioInvalido`). Lo que necesita el documento (la pieza, su ficha) lo resuelve
`services/cosim_transmision.py`.
"""

from __future__ import annotations

import math

FUENTES = ("pinon", "diametro_primitivo_mm", "avance_mm")
CLAVES = frozenset(FUENTES) | {"fuente", "irreversible"}
FORMA = ('{"pinon": "<pieza con ficha PINON-*>"} | {"diametro_primitivo_mm": d, "fuente": "…"} '
         '| {"avance_mm": p, "fuente": "…"}, irreversible?: true|false')


def leer(t, donde: str) -> dict:
    """La transmisión validada (un dict con sólo lo declarado)."""
    if not isinstance(t, dict):
        raise ValueError(f"{donde}: se espera un objeto {FORMA}")
    sobra = sorted(set(t) - CLAVES)
    if sobra:
        raise ValueError(f"{donde}: clave(s) no reconocida(s) {sobra}; válidas: {sorted(CLAVES)}")
    fuentes = [k for k in FUENTES if t.get(k) is not None]
    if len(fuentes) != 1:
        raise ValueError(f"{donde}: lleva UNA fuente del radio ({', '.join(FUENTES)}); vinieron "
                         f"{fuentes or 'ninguna'}. Forma: {FORMA}")
    k = fuentes[0]
    out: dict = {}
    if k == "pinon":
        if not isinstance(t[k], str) or not t[k]:
            raise ValueError(f"{donde}: «pinon» es el id (o el nombre) de la pieza del piñón")
        out[k] = t[k]
    else:
        v = t[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0:
            raise ValueError(f"{donde}: «{k}» debe ser un número > 0 (mm), llegó {v!r}")
        fuente = t.get("fuente")
        if not isinstance(fuente, str) or not fuente.strip():
            raise ValueError(f"{donde}: «{k}» declarado pide «fuente» (de dónde sale: ficha del "
                             "fabricante, plano, medición); si el piñón es una pieza de catálogo, "
                             "usa «pinon»")
        out[k] = float(v)
        out["fuente"] = fuente.strip()
    if t.get("irreversible") is not None:
        if not isinstance(t["irreversible"], bool):
            raise ValueError(f"{donde}: «irreversible» es true o false")
        out["irreversible"] = t["irreversible"]
    return out


def radio_mm(t: dict, d0_mm: float | None = None) -> float:
    """r (mm) de una transmisión leída; `d0_mm` es el diámetro primitivo de la ficha del piñón."""
    if "pinon" in t:
        if not d0_mm or d0_mm <= 0:
            raise ValueError("el piñón no trae diámetro primitivo")
        return d0_mm / 2.0
    if "diametro_primitivo_mm" in t:
        return t["diametro_primitivo_mm"] / 2.0
    return t["avance_mm"] / (2.0 * math.pi)
