"""El tablero eléctrico de un documento (plan V8.1, D8, D10 y D11): circuito, ERC y BOM.

Lee `doc.electrico`, el `ModeloElectrico` que el carril del documento dejó en el último
regenerate (`doc/carril.py`), y lo entrega a sus clientes:
  - `circuito`: dispositivos con sus bornes y la red de cada uno, redes con su potencial y la
    tensión inferida, conductores y cables (`GET /api/electrico/circuito`, tool `get_circuit`);
  - `chequeo`: el ERC con su resumen (`GET /api/electrico/check`, tool `electrical_check`);
  - `reglas_erc`: el ERC para la puerta de entrega y la aserción `{"erc": "sin_errores"}`
    (None sin carril: la puerta no cambia);
  - `filas_bom`: las filas de BOM del tablero (`library/bom_electrico.py`).
El llamador sostiene STATE_LOCK. El modelo es inmutable: el ERC corre sobre él (~1 ms en la faja
piloto) sin copiarlo.
"""

from __future__ import annotations

from .errors import ServiceError


def modelo(doc):
    """El `ModeloElectrico` del documento (vacío si no tiene carril)."""
    from apolo.library.electrico.modelo import ModeloElectrico

    m = getattr(doc, "electrico", None)
    return m if isinstance(m, ModeloElectrico) else ModeloElectrico()


def tiene_carril(doc) -> bool:
    m = modelo(doc)
    return bool(m.dispositivos or m.conductores or m.cables)


def reglas_erc(doc) -> list[dict] | None:
    """Las reglas del ERC, o None si el documento no tiene carril."""
    if not tiene_carril(doc):
        return None
    from apolo.library.electrico.erc import erc

    return erc(modelo(doc))


def chequeo(doc) -> dict:
    """El ERC del tablero: `{estado, errores, avisos, reglas}`. Sin carril, estado «sin_carril»
    (no es verde: no hay nada que revisar)."""
    from apolo.library.electrico.erc import resumen

    reglas = reglas_erc(doc)
    if reglas is None:
        return {"estado": "sin_carril", "errores": 0, "avisos": 0, "reglas": [],
                "detalle": "El proyecto no declara tablero eléctrico (add_device, add_wire, "
                           "add_cable)."}
    m = modelo(doc)
    return {**resumen(reglas), "n_dispositivos": len(m.dispositivos),
            "n_conductores": len(m.conductores), "n_cables": len(m.cables), "reglas": reglas}


def _coincide(designacion: str, filtro: str) -> bool:
    """«=Faja1-Q1» casa con «=Faja1-Q1», con su aspecto «=Faja1» y con «-Q1» (el producto);
    «=Faja1» también con lo anidado («=Faja1.Sub-K1»)."""
    return (designacion == filtro or designacion.startswith((filtro + "-", filtro + "."))
            or (filtro.startswith("-") and designacion.endswith(filtro)))


def circuito(doc, designacion: str | None = None) -> dict:
    """Dispositivos, redes, conductores y cables; con `designacion`, sólo lo de esos
    dispositivos (los que casan por designación completa, aspecto de función o producto) y las
    redes y conductores que los tocan. Una designación que no casa → 404 con sugerencias."""
    from apolo.library.electrico.redes import analizar
    from apolo.library.electrico.referencias import sufijo_sugerencia

    m = modelo(doc)
    a = analizar(m)
    dispositivos = list(m.dispositivos)
    if designacion:
        filtro = designacion.strip()
        dispositivos = [d for d in dispositivos if _coincide(d.designacion, filtro)]
        if not dispositivos:
            raise ServiceError(404, f"No hay dispositivo {filtro} en el tablero."
                               f"{sufijo_sugerencia(filtro, [d.designacion for d in m.dispositivos])}")
    elegidos = {d.designacion for d in dispositivos}
    redes_vistas: set[int] = set()
    salida_disp = []
    for d in dispositivos:
        bornes = []
        for b in d.bornes:
            idx = a.red(d.designacion, b.id)
            redes_vistas.add(idx)
            bornes.append({"id": b.id, "rol": b.rol, "red": a.redes[idx].id,
                           **({"conectado": False} if not a.conectado(d.designacion, b.id) else {})})
        salida_disp.append({
            "designacion": d.designacion, "ref": d.ref, "funcion": d.funcion,
            **({"ubicacion": d.ubicacion} if d.ubicacion else {}),
            **({"pieza": d.pieza} if d.pieza else {}),
            **({"ajustes": d.ajustes} if d.ajustes else {}),
            "comando": d.id, "bornes": bornes,
        })
    redes = [{"id": r.id, **({"nombre": r.nombre} if r.nombre else {}), "puntos": list(r.puntos),
              **({"tension": r.tension} if r.tension else {})}
             for i, r in enumerate(a.redes) if not designacion or i in redes_vistas]
    conductores = []
    for i, c in enumerate(m.conductores):
        if designacion and not any(p.rsplit(":", 1)[0] in elegidos for p in c.puntos):
            continue
        idx = a.conductor_red.get(i)
        conductores.append({
            "comando": c.id, "puntos": list(c.puntos),
            **{k: v for k, v in (("seccion_mm2", c.seccion_mm2), ("color", c.color),
                                 ("tipo", c.tipo), ("cable", c.cable), ("hilo", c.hilo),
                                 ("potencial", c.potencial), ("largo_m", c.largo_m)) if v},
            **({"red": a.redes[idx].id} if idx is not None else {}),
        })
    usados = {c.get("cable") for c in conductores}
    cables = [{"designacion": c.designacion, "ref": c.ref, "comando": c.id,
               "hilos": {h.id: h.color for h in c.hilos},
               **{k: v for k, v in (("desde", c.desde), ("hasta", c.hasta),
                                    ("largo_m", c.largo_m)) if v}}
              for c in m.cables if not designacion or c.designacion in usados]
    return {"dispositivos": salida_disp, "redes": redes, "conductores": conductores,
            "cables": cables,
            "resumen": {"n_dispositivos": len(m.dispositivos), "n_conductores": len(m.conductores),
                        "n_cables": len(m.cables), "n_redes": len(a.redes)}}


def filas_bom(doc) -> list[dict]:
    """Las filas de BOM del tablero (sin duplicar lo que la escena ya cuenta: D10)."""
    if not tiene_carril(doc):
        return []
    from apolo.library.bom_electrico import filas_electricas

    return filas_electricas(modelo(doc))
