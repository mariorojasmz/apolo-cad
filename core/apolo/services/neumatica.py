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


def disponibles() -> frozenset:
    """Los `modelo.tipo` neumáticos que ofrece el catálogo: las reglas de silenciador y de regulación
    de velocidad corren sólo si hay refs con qué cumplirlas (V8.9 F4, D16)."""
    from apolo.library.catalog import CATALOG

    return frozenset(c.neumatico.tipo for c in CATALOG.values()
                     if c.neumatico is not None and c.neumatico.tipo)


def reglas(m) -> list[dict]:
    """El ERC neumático del modelo (`[]` sin aire)."""
    from apolo.library.neumatica.erc import erc

    return erc(m, disponibles=disponibles())


def cosim_vigente(doc) -> dict:
    """{cilindro: lo medido} de los escenarios VIGENTES con aire (`resultado["aire"]`, que guarda
    `escenarios.resultado_compacto`): por cilindro, el del escenario en que fue MÁS RÁPIDO (el peor
    caso para el impacto y el caudal), con su nombre. Un vencido o sin correr no cuenta."""
    from . import escenarios as E

    out: dict = {}
    if not doc.escenarios:
        return out
    firma, cache = E.firma_documento(doc), {}
    for nombre, ent in doc.escenarios.items():
        aire = (ent.get("resultado") or {}).get("aire")
        if not aire or E.estado(doc, nombre, firma, cache)["estado"] in (E.SIN_CORRER, E.VENCIDO):
            continue
        for des, fila in (aire.get("cilindros") or {}).items():
            if fila.get("t_avance_s") is None and not fila.get("v_max_m_s"):
                continue  # no se movió en ese escenario
            previo = out.get(des)
            if previo is None or fila.get("v_max_m_s", 0) > previo.get("v_max_m_s", 0):
                out[des] = {**fila, "escenario": nombre, "medicion": aire.get("medicion", "")}
    return out


def memoria(doc) -> list[dict]:
    """Las verificaciones del aire para la memoria de cálculo (V8.9 D10, `library/neumatica/
    memoria.py`): con lo medido en la co-simulación vigente y el % de fugas de los requisitos
    (`fugas_aire_pct`). `[]` sin aire: la memoria de siempre."""
    from apolo.library.neumatica.memoria import reglas as reglas_memoria

    from .electrico import modelo

    m = modelo(doc)
    if not hay_aire(m):
        return []
    fugas = (doc.requirements or {}).get("fugas_aire_pct")
    return reglas_memoria(analizar(m), cosim=cosim_vigente(doc),
                          fugas_pct=float(fugas) if isinstance(fugas, (int, float)) else None)
