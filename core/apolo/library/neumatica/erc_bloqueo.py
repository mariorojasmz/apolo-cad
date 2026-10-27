"""ERC del bloqueo de vástago (plan bloqueo-de-vastago D6): la regla «bloqueo de vástago».

Por cada cilindro con `servicio.bloqueo` (y por cada bloqueo que ningún cilindro declara):
  - el bloqueo declarado no existe o no es un bloqueo (error, con la parecida);
  - el Ø del vástago de su ficha no es el del cilindro (error);
  - retención estática < 1,0 × la fuerza máxima del cilindro (error, con su `calc`);
  - no es normalmente bloqueado (error: sin aire no sostiene);
  - la ficha no admite frenar un movimiento (error: la seta lo hace morder en marcha);
  - la presión que le llega no alcanza la mínima de liberación (error: muerde a medias);
  - su liberación no es una 3/2 NC propia (error) o la bobina de esa 3/2 no la corta la cadena
    cableada de la seta (aviso: depende del programa; sólo si quien llama da `seta`);
  - deslizó en un escenario vigente (error; sólo con `deslizados`);
  - un bloqueo que ningún cilindro declara (aviso: no muerde nada).
Sin bloqueos ni `servicio.bloqueo`, ninguna fila (el ERC de antes). Puro.
"""

from __future__ import annotations

from . import bloqueo as B
from .lineas import Circuito, tipo

REGLA = "bloqueo de vástago"
NORMA = B.NORMA


def _r(estado: str, detalle: str, recomendacion: str | None, elementos: list[str], calc: dict | None = None) -> dict:
    out = {"regla": REGLA, "estado": estado, "detalle": detalle}
    if recomendacion:
        out["recomendacion"] = recomendacion
    out.update({"norma": NORMA, "elementos": elementos, "medio": "aire"})
    if calc is not None:
        out["calc"] = calc
    return out


def _del_cilindro(c: Circuito, cil, seta, deslizados) -> list[dict]:
    quien = f"{cil.designacion} ({cil.ref})"
    bl, motivo = B.de_cilindro(c, cil)
    if bl is None:
        return [_r("error", f"{quien}: servicio.bloqueo {motivo}", None, [cil.designacion])]
    f, m = bl.neumatico.modelo, cil.neumatico.modelo
    el = [cil.designacion, bl.designacion]
    nombre = f"{quien} con {bl.designacion} ({bl.ref})"
    out = []
    if abs(f["d_vastago_mm"] - m["d_mm"]) > 1e-6:
        out.append(_r("error", f"{nombre}: el bloqueo muerde un vástago Ø{f['d_vastago_mm']:g} y el del cilindro es "
                               f"Ø{m['d_mm']:g}.", f"Un bloqueo para vástago Ø{m['d_mm']:g} (BLOQ-VAST-{m['d_mm']:g}-S).", el))
    r = B.retencion(c, cil, bl)
    v = r["valor"]
    calc = {**r["calc"], "hipotesis": r["hipotesis"]}
    if r["estado"] != "ok":
        out.append(_r("error", f"{nombre}: retiene {v['F_retencion_N']:g} N y el cilindro empuja {v['F_N']:.0f} N a "
                               f"{v['p_bar']:g} bar: el vástago desliza.",
                      "Un bloqueo de más retención, menos presión o un cilindro menor.", el, calc))
    if not f["normalmente_bloqueado"]:
        out.append(_r("error", f"{nombre}: la ficha no lo bloquea SIN aire; al cortar el aire o pulsar la seta no sostiene.",
                      "Un bloqueo por resorte (normalmente bloqueado, liberado con aire).", el))
    if not f["frenado_dinamico"]:
        out.append(_r("error", f"{nombre}: la ficha sólo lo admite para SOSTENER un vástago parado; su liberación la "
                               "corta la seta en marcha, así que muerde un vástago en movimiento.",
                      "La variante apta para frenado (del orden de Festo KEC-…-S, categoría 1).", el))
    pr = c.presion_de(bl)
    if pr is not None and pr[0] < f["p_liberacion_min_bar"]:
        out.append(_r("error", f"{nombre}: le llegan {pr[0]:g} bar y libera desde {f['p_liberacion_min_bar']:g} bar: "
                               "muerde a medias y arrastra el vástago.",
                      f"Sube la presión regulada a {f['p_liberacion_min_bar']:g} bar o más.", el))
    val, motivo = B.liberacion(c, bl)
    cadena = ""
    if val is None:
        out.append(_r("error", f"{nombre}: {motivo}.",
                      f"Libéralo con una 3/2 NC monoestable propia (VAL-32-NC-…): su vía 2 a {bl.designacion}:1, la 1 "
                      "aguas abajo del corte con escape y el escape 3 con silenciador; su bobina, en la cadena de la seta.", el))
    elif seta is not None:
        ok, por_que = seta(val)
        cadena = f"; {por_que}" if ok else ""
        if not ok:
            out.append(_r("aviso", f"{nombre}: lo libera {val.designacion}, pero {por_que}.",
                          f"Alimenta la bobina de {val.designacion} a través del NC de la seta (o de un relé de seguridad "
                          "que ella corta): para la categoría 1 la corta la cadena cableada, no el programa.",
                          el + [val.designacion]))
    for escenario, d in sorted(((deslizados or {}).get(bl.designacion) or {}).items()):
        t = f" a los {d['t_desliza_s']:g} s" if d.get("t_desliza_s") is not None else ""
        out.append(_r("error", f"{nombre}: en el escenario «{escenario}» el vástago DESLIZÓ{t} con el bloqueo cerrado "
                               f"(la fuerza del aire pasó su sujeción; anduvo {d.get('sobrerrecorrido_mm', 0):.1f} mm).",
                      "Un bloqueo de más retención o menos presión en las cámaras al bloquear.", el))
    if not out:
        val_txt = f" y lo libera {val.designacion}" if val is not None else ""
        out.append(_r("ok", f"{nombre}: retiene {v['F_retencion_N']:g} N contra {v['F_N']:.0f} N (FS = {v['fs']:.2f}), "
                            f"bloquea sin aire{val_txt}{cadena}.", None, el, calc))
    return out


def reglas(c: Circuito, *, seta=None, deslizados: dict | None = None) -> list[dict]:
    """Las filas de la regla (ver el módulo). `seta(valvula) -> (bool, motivo)`: si la bobina de la
    válvula la corta la cadena de la seta (la da quien tiene la red eléctrica); `deslizados`:
    {bloqueo: {escenario: {t_desliza_s, sobrerrecorrido_mm}}} de los escenarios vigentes."""
    out, usados = [], set()
    for cil in [d for d in c.dispositivos.values() if tipo(d) == "cilindro"]:
        if not (cil.servicio or {}).get("bloqueo"):
            continue
        usados.add(cil.servicio["bloqueo"])
        out += _del_cilindro(c, cil, seta, deslizados)
    for bl in B.bloqueos(c):
        if bl.designacion not in usados:
            out.append(_r("aviso", f"{bl.designacion} ({bl.ref}): ningún cilindro lo declara (servicio.bloqueo): no "
                                   "muerde nada en el cálculo ni en la co-simulación.",
                          f'Declara en el servicio de su cilindro {{"bloqueo": "{bl.designacion}"}}.', [bl.designacion]))
    return out


def memoria(c: Circuito) -> list[dict]:
    """La retención de cada bloqueo declarado, para la memoria (con su `calc` y la nota de ISO
    13849-1 en las hipótesis)."""
    out = []
    for cil in [d for d in c.dispositivos.values() if tipo(d) == "cilindro"]:
        bl, _m = B.de_cilindro(c, cil)
        if bl is None:
            continue
        r = B.retencion(c, cil, bl)
        v = r["valor"]
        calc = dict(r["calc"])
        calc["titulo"] = f"{cil.designacion} · {calc['titulo']}"
        out.append({"regla": REGLA, "estado": r["estado"],
                    "detalle": f"{bl.designacion} ({bl.ref}) retiene {v['F_retencion_N']:g} N; {cil.designacion} empuja "
                               f"{v['F_N']:.0f} N a {v['p_bar']:g} bar.",
                    "elementos": [cil.designacion, bl.designacion], "medio": "aire", "calc": calc,
                    "hipotesis": list(r["hipotesis"]), "valor": dict(v)})
    return out
