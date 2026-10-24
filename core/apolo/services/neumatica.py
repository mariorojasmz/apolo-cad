"""El circuito de AIRE de un documento (plan V8.9 D1, D9, D13; F1b): lo que `get_circuit` y
`electrical_check` muestran del aire, en la MISMA salida que lo eléctrico.

Lee el `ModeloElectrico` del carril (`services/electrico.modelo`): los dispositivos con ficha
neumática y los tubos. Sin aire en el modelo no suma nada (la salida de siempre):
  - `puertos(c, d)`: los puertos de un dispositivo con su línea y si quedan libres;
  - `seccion(m, elegidos)`: `{lineas, tubos, resumen}` (la clave `neumatica` del circuito);
  - `reglas(m)`: el ERC neumático (`library/neumatica/erc.py`), filas con `medio: "aire"`.
Una sola fuente para el agente y, en F6, el panel «Neumática». El llamador sostiene STATE_LOCK.
"""

from __future__ import annotations


def hay_aire(m) -> bool:
    from apolo.library.neumatica.erc import hay_aire as _hay

    return _hay(m)


def analizar(m):
    from apolo.library.neumatica.lineas import analizar as _analizar

    return _analizar(m)


def _id_linea(i: int) -> str:
    return f"P{i + 1}"


def puertos(c, d) -> list[dict]:
    """Los puertos de un dispositivo neumático para el circuito (vacío si no tiene)."""
    out = []
    for p in d.puertos:
        i = c.linea(d.designacion, p.id)
        out.append({"id": p.id, "rol": p.rol, "rosca": p.rosca, "linea": _id_linea(i),
                    **({"conectado": False} if (d.designacion, p.id) not in c.conectados else {})})
    return out


def seccion(m, c, elegidos: set | None = None) -> dict:
    """Las líneas (puertos unidos por tubos, con la presión regulada que les llega) y los tubos;
    con `elegidos` (designaciones), sólo lo que los toca."""
    def toca(puntos) -> bool:
        return elegidos is None or any(p.rpartition(":")[0] in elegidos for p in puntos)

    lineas = []
    for i, miembros in enumerate(c.miembros):
        puntos = [f"{des}:{p}" for des, p in miembros]
        if (len(puntos) < 2 and i not in c.presion) or not toca(puntos):
            continue  # un puerto suelto ya sale en su dispositivo (`conectado: false`)
        pr = c.presion.get(i)
        lineas.append({"id": _id_linea(i), "puertos": puntos,
                       **({"presion_bar": pr[1] if pr[0] == pr[1] else [pr[0], pr[1]],
                           "desde_frl": pr[2]} if pr else {})})
    tubos = [{"comando": t.id, "desde": t.desde, "hasta": t.hasta, "ref": t.ref,
              **({"largo_m": t.largo_m} if t.largo_m else {})}
             for t in m.tubos if toca((t.desde, t.hasta))]
    aire = [d for d in c.dispositivos.values() if elegidos is None or d.designacion in elegidos]
    return {"lineas": lineas, "tubos": tubos,
            "resumen": {"n_dispositivos": len(aire), "n_tubos": len(m.tubos), "n_lineas": len(c.miembros)}}


def reglas(m) -> list[dict]:
    """El ERC neumático del modelo (`[]` sin aire)."""
    from apolo.library.neumatica.erc import erc

    return erc(m)
