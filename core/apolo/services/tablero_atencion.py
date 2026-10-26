"""Los ítems del panel «Tablero» del calentamiento y de los prensaestopas (plan V8.5 F3, D13): lo
que dicen `tablero_calor.evaluacion` y `tablero_prensas.del_tablero` en palabras de la persona
(ui/CLAUDE.md § Texto: sin comandos ni parámetros; el texto del ERC va en `tecnico`). Aquí no se
decide ninguna regla: la falla del calentamiento es la misma fila del ERC.
"""

from __future__ import annotations

NBSP = " "  # el mismo de `tablero_panel.NBSP`: cifra y unidad no se separan
MOTIVO_SIN_METODO = "No podemos calcular la temperatura de este tablero con el método de la norma (IEC 60890)."
#: la causa de un calentamiento sin evaluar (`tablero_calor.evaluacion`) → la frase para la persona
MOTIVOS = {"fuera_del_metodo": MOTIVO_SIN_METODO,
           "sin_tmax": "Ningún aparato trae en su ficha la temperatura máxima que soporta: no hay con qué comparar."}


def _cifra(x: float) -> str:
    return f"{x:.0f}"


def calor(ev: dict, gabinete: str, piezas: dict[str, str], tecnico: str | None) -> tuple[list[dict], list[dict]]:
    """(lo que pide atención, lo que está bien) del calentamiento."""
    from .tablero_panel import item  # la forma del ítem es del panel (que importa este módulo)

    estado = ev.get("estado")
    if estado == "sin_evaluar":
        return [item("calentamiento", "sin_evaluar", "Falta evaluar el calentamiento", piezas=[gabinete],
                     detalle=MOTIVOS.get(ev.get("causa"), MOTIVO_SIN_METODO), tecnico=ev.get("motivo"))], []
    peor = ev.get("peor") or {}
    if estado == "falla":
        malos = [a for a in ev["aparatos"] if a.get("pasa")]
        s = ev.get("sugerencia") or {}
        if s.get("refrigeracion"):
            que = "Con este ambiente ventilar no alcanza: hace falta un equipo de refrigeración."
        else:
            que = f"Ventílalo con al menos {_cifra(s.get('caudal_m3h') or 0)}{NBSP}m³/h"
            g = s.get("gabinete")
            que += (f" o usa la caja de {g['medidas_mm'][0]:g}{NBSP}×{NBSP}{g['medidas_mm'][2]:g}{NBSP}mm." if g else ".")
        return [item("calentamiento", "falla", "El tablero se calienta de más", valor=round(ev["T_arriba_C"]),
                     unidad="°C", piezas=[gabinete, *(piezas[a["designacion"]] for a in malos if a["designacion"] in piezas)],
                     detalle=(f"Arriba llega a {_cifra(ev['T_arriba_C'])}{NBSP}°C y {peor.get('designacion')} admite "
                              f"{_cifra(peor.get('T_max_C') or 0)}{NBSP}°C. {que}"),
                     tecnico=tecnico)], []
    return [], [item("calentamiento", "bien", "Temperatura arriba en el tablero", valor=round(ev["T_arriba_C"]),
                     unidad="°C", piezas=[gabinete],
                     detalle=(f"El más justo es {peor.get('designacion')}: {_cifra(peor.get('T_C') or 0)} de "
                              f"{_cifra(peor.get('T_max_C') or 0)}{NBSP}°C admisibles."))]


def prensaestopas(res: dict, gabinete: str) -> tuple[list[dict], list[dict]]:
    """(lo que pide atención, lo que está bien) de los prensaestopas."""
    from .tablero_panel import item

    atender, bien = [], []
    sin = [p for p in res.get("prensas", ()) if not p.get("ref")]
    con = [p for p in res.get("prensas", ()) if p.get("ref")]
    if sin:
        uno = len(sin) == 1
        atender.append(item(
            "prensaestopas", "aviso", "Cable sin un prensaestopas que lo sujete" if uno else
            "Cables sin un prensaestopas que los sujete", valor=len(sin), piezas=[gabinete],
            conductores=[p["cable"] for p in sin],
            detalle="Su diámetro no entra en ningún prensaestopas del catálogo: sin él, el cable no queda "
                    "sellado ni sujeto al salir.",
            tecnico="; ".join(f"{p['designacion']}: {p['motivo']}" for p in sin)))
    for a in res.get("avisos", ()):
        atender.append(item("prensaestopas-lugar", "aviso", "Los prensaestopas no entran en la placa pasacables",
                            piezas=[gabinete], detalle="Usa un gabinete con la placa más grande o saca cables por otra cara.",
                            tecnico=a))
    if con and not sin and not res.get("avisos"):
        cuenta: dict[str, int] = {}
        for p in con:
            cuenta[p["rosca"].split("x")[0]] = cuenta.get(p["rosca"].split("x")[0], 0) + 1
        lista = ", ".join(f"{n}{NBSP}{r}" for r, n in sorted(cuenta.items()))
        cara = "de abajo" if res.get("cara") == "inferior" else "de arriba"
        bien.append(item("prensaestopas", "bien", "Prensaestopas", valor=len(con), piezas=[gabinete],
                         detalle=f"Uno por cable que sale, en la cara {cara}: {lista}."))
    return atender, bien
