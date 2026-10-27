"""El bloqueo de vástago de un cilindro: la cuenta que leen el ERC y la memoria (plan
bloqueo-de-vastago D2, D6, D7).

Un bloqueo es un dispositivo del carril con ficha `neumatico:` de tipo `bloqueo_vastago` (D1); el
cilindro lo nombra en `servicio.bloqueo` (D2). Aquí, puro (biblioteca estándar), sobre el
`Circuito` de `lineas.py`:
  - `de_cilindro(c, cil)`: (dispositivo de bloqueo, motivo si no lo es);
  - `retencion(...)`: la retención estática contra la fuerza máxima del cilindro, con su `calc`;
  - `liberacion(c, bloqueo)`: la válvula que lo libera (una 3/2 NC monoestable por su vía 2), o el
    motivo de por qué no la hay;
  - `nota_13849(ficha)`: lo que la ficha dice de ISO 13849-1 (nada se inventa: el B10d sin
    publicar queda «a confirmar»).
"""

from __future__ import annotations

import difflib

from . import calculo as K
from .cilindros import p_trabajo
from .lineas import Circuito, tipo

TIPO = "bloqueo_vastago"
#: La retención estática tiene que cubrir la fuerza máxima del cilindro × este factor: el de la
#: ficha Festo KEC-S [B1] («dynamic forces occurring during operation must not exceed the static
#: holding force»), sin margen extra.
FACTOR_RETENCION = 1.0
NORMA = ("ficha del fabricante (Festo KEC/KEC-S: la fuerza no supera la retención estática) · "
         "EN ISO 13849-1 (categoría que certifica la ficha)")


def bloqueos(c: Circuito) -> list:
    return [d for d in c.dispositivos.values() if tipo(d) == TIPO]


def de_cilindro(c: Circuito, cil) -> tuple[object | None, str]:
    """(dispositivo de bloqueo que declara `servicio.bloqueo`, motivo si no es uno)."""
    des = (cil.servicio or {}).get("bloqueo")
    if not des:
        return None, ""
    d = c.dispositivos.get(des)
    if d is not None and tipo(d) == TIPO:
        return d, ""
    hay = [x.designacion for x in bloqueos(c)]
    pista = difflib.get_close_matches(des, hay, n=1, cutoff=0.5)
    que = (f"«{des}» es un {tipo(d)}" if d is not None else f"«{des}» no es un dispositivo de aire del circuito")
    return None, (f"{que}, no un bloqueo de vástago" + (f". ¿Quisiste decir «{pista[0]}»?" if pista else "")
                  + (f" Bloqueos: {', '.join(hay)}." if hay else " Agrega uno con add_device (ref BLOQ-VAST-…)."))


def retencion(c: Circuito, cil, bloqueo) -> dict:
    """La retención estática del bloqueo contra la fuerza MÁXIMA del cilindro: p · A de avance (la
    mayor de las dos) a la presión más alta que le llega, × `FACTOR_RETENCION`."""
    m, f = cil.neumatico.modelo, bloqueo.neumatico.modelo
    p, hip = p_trabajo(c, cil)
    A_, _Ab, _a = K.areas(m["D_mm"], m["d_mm"])
    F = p * 0.1 * A_
    F_ret = f["F_retencion_N"]
    fs = F_ret / F if F > 0 else None
    ok = F_ret >= FACTOR_RETENCION * F * (1 - 1e-9)
    hip = hip + [f"F = p·A de avance (la mayor de las dos) a {p:g} bar: la que queda si una cámara retiene "
                 "la presión y la otra escapa", "retención estática de la ficha, en los dos sentidos",
                 nota_13849(bloqueo)]
    calc = {"titulo": f"Retención del bloqueo {bloqueo.designacion} ({bloqueo.ref})",
            "entradas": {"cilindro": f"Ø{m['D_mm']:g}/{m['d_mm']:g}", "presión": f"{p:g} bar",
                         "área de avance": f"{A_:.0f} mm²", "retención de la ficha": f"{F_ret:g} N"},
            "formula": f"F_ret ≥ {FACTOR_RETENCION:g} · p · A",
            "sustitucion": f"{F_ret:g} N ≥ {FACTOR_RETENCION:g} · {p:g} · 0,1 · {A_:.0f} = {F:.0f} N",
            "resultado": f"{F_ret:g} N contra {F:.0f} N (FS = {fs:.2f})" if fs else f"{F_ret:g} N",
            "criterio": f"retención estática ≥ {FACTOR_RETENCION:g} × la fuerza máxima del cilindro",
            "fs": round(fs, 2) if fs else None, "norma": NORMA}
    return {"estado": "ok" if ok else "error", "valor": {"F_N": F, "F_retencion_N": F_ret, "p_bar": p, "fs": fs},
            "hipotesis": hip, "calc": calc}


def liberacion(c: Circuito, bloqueo) -> tuple[object | None, str]:
    """(la 3/2 NC monoestable que libera el bloqueo por su vía 2, motivo si no la hay) — D3."""
    i = c.linea(bloqueo.designacion, "1")
    otros = [(des, p) for des, p in (c.miembros[i] if i is not None else []) if des != bloqueo.designacion]
    for des, p in otros:
        d = c.dispositivos[des]
        m = d.neumatico.modelo
        if tipo(d) == "valvula" and p == "2" and m.get("vias") == 3 and m.get("reposo") == "NC" \
                and m.get("mando") == "monoestable":
            return d, ""
    if not otros:
        return None, "su puerto 1 no tiene tubo: nada lo libera (queda bloqueado siempre)"
    que = ", ".join(f"{d}:{p}" for d, p in otros)
    return None, (f"su línea de liberación llega a {que}, no a la vía 2 de una 3/2 NC monoestable propia: "
                  "al pulsar la seta nadie la descarga")


def nota_13849(bloqueo) -> str:
    """Lo que la ficha dice de su papel en EN ISO 13849-1 (D7)."""
    f = bloqueo.neumatico.modelo
    b10 = (f"B10d = {f['B10d']:g} ciclos (ficha)" if f.get("B10d") else
           "B10d: la ficha no lo publica (a confirmar con el fabricante)")
    if f.get("categoria_iso13849"):
        cert = f", certificado {f['certificado']}" if f.get("certificado") else ""
        return (f"ISO 13849-1: componente probado para categoría {f['categoria_iso13849']}"
                f"{', PL ' + f['PL'] if f.get('PL') else ''}{cert} (ficha); no es la función de seguridad "
                f"completa: la seta, su válvula y el cableado son de la obra; {b10}")
    return f"ISO 13849-1: la ficha no lo certifica para mandos de seguridad; {b10}"
