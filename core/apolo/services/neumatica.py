"""El circuito de AIRE de un documento (plan V8.9 D1, D9, D13; F1b): lo que `get_circuit` y
`electrical_check` muestran del aire, en la MISMA salida que lo eléctrico.

Lee el `ModeloElectrico` del carril (`services/electrico.modelo`): los dispositivos con ficha
neumática y los tubos. Sin aire en el modelo no suma nada (la salida de siempre):
  - `puertos(c, d)`: los puertos de un dispositivo con su línea y si quedan libres;
  - `seccion(m, elegidos)`: `{lineas, tubos, resumen}` (la clave `neumatica` del circuito);
  - `reglas(m, doc)`: el ERC neumático (`library/neumatica/erc.py`), filas con `medio: "aire"`.
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


def amortiguadores() -> dict:
    """{ref: FichaAmortiguador} de los amortiguadores hidráulicos del catálogo (plan
    amortiguador-externo D1): la regla de energía de un extremo con amortiguador externo."""
    from apolo.library.catalog import CATALOG
    from apolo.library.neumatica.amortiguador import FAMILIA, parse_ficha

    return {r: parse_ficha(c.specs, r) for r, c in CATALOG.items() if c.familia == FAMILIA}


def paquetes_min(doc) -> float | None:
    """La capacidad nominal (`requirements.paquetes_por_minuto`), o None: los ciclos por hora del
    amortiguador externo cuando el cilindro no declara su cadencia (plan amortiguador-externo D5)."""
    v = ((getattr(doc, "requirements", None) or {}) if doc is not None else {}).get("paquetes_por_minuto")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def refs_escena(doc) -> frozenset | None:
    """Las refs de catálogo que hay en 3D, o None si la escena no tiene piezas (un circuito sin
    máquina en 3D no es un modelo a medias: la regla de `campo_sin_pieza`)."""
    escena = (getattr(doc, "scene", None) or {}) if doc is not None else {}
    if not escena:
        return None
    return frozenset(f.component for f in escena.values() if getattr(f, "component", None))


def reglas(m, doc=None) -> list[dict]:
    """El ERC neumático del modelo (`[]` sin aire). La regla del presostato (V8.9 F8) sabe si su
    contacto está cableado por la red eléctrica del carril (`library/electrico/redes`), que se
    analiza sólo si la pide. Con `doc`, la regla del amortiguador externo ve la capacidad nominal
    y las refs de la escena."""
    from apolo.library.electrico.redes import analizar as redes
    from apolo.library.neumatica.erc import erc

    an: list = []

    def cableado(des: str, borne: str) -> bool:
        if not an:
            an.append(redes(m))
        return an[0].conectado(des, borne)

    def seta(valvula) -> tuple[bool, str]:  # plan bloqueo-de-vastago D6: ¿la corta la cadena de la seta?
        from apolo.library.electrico.cadena_seta import cortada_por_seta

        if not an:
            an.append(redes(m))
        bornes = [b for c in valvula.cargas if c.tipo == "bobina" for b in c.bornes]
        return cortada_por_seta(an[0], valvula.designacion, bornes)

    return erc(m, disponibles=disponibles(), cableado=cableado, amortiguadores=amortiguadores(),
               paquetes_min=paquetes_min(doc), refs_escena=refs_escena(doc), seta=seta,
               deslizados=deslizados(doc) if doc is not None else None)


def deslizados(doc) -> dict:
    """{bloqueo: {escenario: {t_desliza_s, sobrerrecorrido_mm}}} de los escenarios VIGENTES con aire
    en que el vástago deslizó con el bloqueo cerrado (`resultado.aire.bloqueos`, plan
    bloqueo-de-vastago D5). Un escenario con ajustes de PRUEBA no mide la máquina del proyecto."""
    from . import escenarios as E

    out: dict = {}
    if not getattr(doc, "escenarios", None):
        return out
    firma, cache = E.firma_documento(doc), {}
    for nombre, ent in sorted(doc.escenarios.items()):
        bl = ((ent.get("resultado") or {}).get("aire") or {}).get("bloqueos") or {}
        malos = {des: f for des, f in bl.items() if f.get("deslizo")}
        if not malos or (ent.get("escenario") or {}).get("ajustes"):
            continue
        if E.estado(doc, nombre, firma, cache)["estado"] in (E.SIN_CORRER, E.VENCIDO):
            continue
        for des, f in malos.items():
            out.setdefault(des, {})[nombre] = f
    return out


#: Eventos de un escenario que no son una falla provocada: el que sólo trae productos es «sano».
EVENTOS_SANOS = frozenset({"producto"})
#: mm: una carrera medida a menos de esto del mayor recorrido de todos los escenarios es completa.
TOL_CARRERA_MM = 2.0


def _sano(ent: dict) -> bool:
    """Sin falla provocada ni ajustes de PRUEBA (D7 de cotizacion-identificada-y-ajustes-por-
    escenario: un escenario con `ajustes` no mide la máquina del proyecto)."""
    esc = ent.get("escenario") or {}
    if esc.get("ajustes"):
        return False
    eventos = esc.get("eventos") or []
    return all(isinstance(e, dict) and e.get("tipo") in EVENTOS_SANOS for e in eventos)


def _nominal(filas: list[tuple[str, dict, bool]]) -> tuple[str, dict] | None:
    """El escenario NOMINAL de un cilindro (V8.9 F7b, defecto 1): de los que lo llevaron por su
    carrera COMPLETA (el mayor recorrido de todos, ± `TOL_CARRERA_MM`), los sanos (sin una falla
    provocada) antes que los de falla, y de ellos el de avance más LENTO (la cota conservadora del
    tiempo de ciclo); empate por nombre. Una seta o una bobina cortada que corta la carrera no es
    el tiempo de carrera del cilindro."""
    medidas = [(n, f, s) for n, f, s in filas if f.get("t_avance_s") is not None]
    if not medidas:
        movidos = [(n, f, s) for n, f, s in filas if (f.get("x_max_mm") or 0.0) > 0.5]
        if not movidos:
            return None
        n, f, _s = max(movidos, key=lambda x: (x[1]["x_max_mm"], x[0]))
        return n, f
    xref = max(f.get("x_max_mm") or 0.0 for _n, f, _s in medidas)
    completas = [(n, f, s) for n, f, s in medidas if (f.get("x_max_mm") or 0.0) >= xref - TOL_CARRERA_MM]
    sanas = [x for x in completas if x[2]] or completas
    n, f, _s = max(sanas, key=lambda x: (x[1]["t_avance_s"], x[0]))
    return n, f


def cosim_vigente(doc) -> dict:
    """{cilindro: lo medido} de los escenarios VIGENTES con aire (`resultado["aire"]`, que guarda
    `escenarios.resultado_compacto`), elegido por `lecturas` (un vencido o sin correr no cuenta)."""
    from . import escenarios as E

    if not doc.escenarios:
        return {}
    firma, cache = E.firma_documento(doc), {}
    vigentes = {nombre: ent for nombre, ent in doc.escenarios.items()
                if (ent.get("resultado") or {}).get("aire")
                and E.estado(doc, nombre, firma, cache)["estado"] not in (E.SIN_CORRER, E.VENCIDO)}
    return lecturas(vigentes)


def lecturas(escenarios: dict) -> dict:
    """{cilindro: lo medido} de `escenarios` ({nombre: {escenario, resultado}}, ya filtrados por
    vigencia). Por cilindro, dos lecturas DISTINTAS (V8.9 F7b, defecto 1):
      - el tiempo de carrera y hasta dónde llegó (`x_max_mm`, `t_avance_s`, `t_retroceso_s`,
        `escenario`, `medicion`) salen del escenario NOMINAL (`_nominal`: carrera completa, sin
        falla);
      - `pico` = {v_max_m_s, escenario}: la mayor velocidad de TODOS (también uno de falla: el
        peor caso para el impacto y el caudal).
    Puro."""
    out: dict = {}
    por_cil: dict[str, list] = {}
    medicion: dict[str, str] = {}
    for nombre, ent in escenarios.items():
        aire = (ent.get("resultado") or {}).get("aire")
        if not aire:
            continue
        medicion[nombre] = aire.get("medicion", "")
        for des, fila in (aire.get("cilindros") or {}).items():
            if fila.get("t_avance_s") is None and not fila.get("v_max_m_s"):
                continue  # no se movió en ese escenario
            por_cil.setdefault(des, []).append((nombre, fila, _sano(ent)))
    for des, filas in por_cil.items():
        filas.sort(key=lambda x: x[0])
        nom = _nominal(filas)
        pn, pf, _s = max(filas, key=lambda x: (x[1].get("v_max_m_s") or 0.0, x[0]))
        pico = {"v_max_m_s": pf.get("v_max_m_s") or 0.0, "escenario": pn}
        if nom is None:  # sólo ruido de muestreo: ninguna carrera que medir
            out[des] = {"escenario": pn, "medicion": medicion.get(pn, ""), "pico": pico}
            continue
        n, f = nom
        out[des] = {**f, "escenario": n, "medicion": medicion.get(n, ""), "pico": pico}
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
                          fugas_pct=float(fugas) if isinstance(fugas, (int, float)) else None,
                          amortiguadores=amortiguadores(), paquetes_min=paquetes_min(doc))
