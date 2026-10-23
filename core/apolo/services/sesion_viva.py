"""Una sesión EN VIVO vuelta escenario por lote (plan V8.4 D10, F4).

La sesión (`WS /api/cosim/vivo`) graba las acciones y eventos que aceptó con su hora virtual; al
terminar, su `fin` trae la grabación, la duración, el escenario de base, la firma del documento
y el hash del escenario de base. Aquí se vuelve un escenario de la FAT (metadato D12) que, por
lote, da las MISMAS trazas que la sesión (el paso es el mismo, `cosim/corrida.py`):
  - del escenario de base quedan condiciones, acoples, mecánica, trazas y la cola de productos
    (`cosim.vivo.escenario_vivo`), y se suman las acciones y eventos grabados;
  - **la cola de cajas** (`fijar_cola`): en vivo, el pool sale de la duración del escenario de
    BASE (MuJoCo no crea cuerpos en marcha); por lote saldría de la duración de la SESIÓN. Cada
    producto queda con `cantidad` = las instancias que tuvo la sesión (con «hasta el final» y
    una sesión más larga que la base, el lote metería cajas que nunca nacieron en vivo) y sale
    si no tuvo ninguna. Recortar no cambia nada: una caja estacionada que no llega a nacer no
    toca la física (medido en F4: la misma huella con 9 y con 6 en el pool);
  - más de 60 s (la dinámica por lote) no se reproduce de una: `hasta_s` guarda el TRAMO
    inicial, que es exacto (lo que pasa después no cambia lo de antes);
  - se rechaza lo que ya no reproduciría: otra firma del documento (409), el escenario de base
    borrado (404) o cambiado (409).
Sin locks: el llamador sostiene `STATE_LOCK`.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

from .errors import ServiceError

MAX_GRABACION = 2000   # acciones y eventos de una sesión (clics de una persona)


def duracion_lote_max_s() -> float:
    from apolo.physics.dinamica_peticion import DURACION_MAX_S

    return DURACION_MAX_S


def fijar_cola(esc: dict, duracion_base: float) -> list[dict]:
    """Deja en `esc` (lo muta) cada producto con las instancias que tuvo la sesión: `cantidad` =
    las que caben en `duracion_base`; sin ninguna, el producto sale. Devuelve la cola, para la
    respuesta: [{nombre, cantidad, desde_s, cada_s?}]."""
    from apolo.physics.dinamica_peticion import instancias_producto

    eventos, cola = [], []
    for e in esc.get("eventos") or []:
        if not isinstance(e, dict) or e.get("tipo") != "producto":
            eventos.append(e)
            continue
        try:
            desde = float(e.get("desde_s", e.get("t", 0.0)) or 0.0)
            cada = None if e.get("cada_s") is None else float(e["cada_s"])
            cantidad = int(e.get("cantidad") or 0)
        except (TypeError, ValueError):
            eventos.append(e)  # lo rechaza la petición de la dinámica, con su texto
            continue
        n = len(instancias_producto(SimpleNamespace(desde_s=desde, cada_s=cada, cantidad=cantidad),
                                    duracion_base))
        if n == 0:
            continue
        e = {**e, "cantidad": n} if cada is not None else e
        eventos.append(e)
        cola.append({"nombre": e.get("nombre"), "cantidad": n, "desde_s": desde,
                     **({"cada_s": cada} if cada is not None else {})})
    esc["eventos"] = eventos
    return cola


def escenario_de_sesion(esc_vivo: dict, grabacion, duracion_s, *, base: str | None,
                        hasta_s: float | None = None) -> dict:
    """El escenario por lote de una sesión: {escenario, duracion_s, recortada, cola, n_acciones,
    n_eventos}. `esc_vivo` = el de la sesión (`escenario_vivo(base)`, con la duración de la
    base). `ServiceError(400)` si no se puede reproducir."""
    from apolo.cosim.vivo import escenario_grabado

    from .escenarios import leer

    if not isinstance(grabacion, list) or any(not isinstance(g, dict) for g in grabacion):
        raise ServiceError(400, "`grabacion` es la lista del mensaje `fin` de la sesión en vivo: "
                                "[{t, accion, dispositivo, …} | {t, tipo, …}]")
    if len(grabacion) > MAX_GRABACION:
        raise ServiceError(400, f"la grabación tiene {len(grabacion)} acciones y eventos (tope "
                                f"{MAX_GRABACION}): guarda un tramo con `hasta_s`")
    try:
        dur = float(duracion_s)
        dur_base = float(esc_vivo["duracion_s"])
    except (TypeError, ValueError, KeyError):
        raise ServiceError(400, "falta la duración de la sesión (`duracion_s`, el `t` del `fin`)") from None
    tope = duracion_lote_max_s()
    recortada = False
    if hasta_s is not None:
        if not isinstance(hasta_s, (int, float)) or not math.isfinite(hasta_s) or not 0 < hasta_s <= dur + 1e-9:
            raise ServiceError(400, f"`hasta_s` = {hasta_s!r}: el tramo va de 0 a la duración de la "
                                    f"sesión ({dur:g} s)")
        recortada = hasta_s < dur - 1e-9
        dur = min(dur, float(hasta_s))
    if not dur > 0:
        raise ServiceError(400, "la sesión no avanzó (duró 0 s): no hay nada que reproducir")
    if dur > tope + 1e-9:
        raise ServiceError(400, (
            f"la sesión duró {dur:g} s y la co-simulación por lote llega a {tope:g} s: guarda el "
            f"tramo inicial con `hasta_s` ≤ {tope:g} (se reproduce exacto: lo que pasó después no "
            "cambia lo de antes)"))
    tramo = [g for g in grabacion if _hora(g) <= dur + 1e-9]
    esc = escenario_grabado(esc_vivo, tramo, round(dur, 6))
    cola = fijar_cola(esc, dur_base)
    acciones = [g for g in tramo if "accion" in g]
    esc["descripcion"] = (f"grabada en vivo sobre «{base}»" if base else "grabada en vivo") + (
        f": {len(acciones)} acciones" + (f" y {len(tramo) - len(acciones)} eventos"
                                         if len(tramo) > len(acciones) else "")
        + (f", primeros {dur:g} s" if recortada else ""))
    leer(esc)  # lo que no se pueda correr, 400 con su corrección
    return {"escenario": esc, "duracion_s": round(dur, 6), "recortada": recortada, "cola": cola,
            "n_acciones": len(acciones), "n_eventos": len(tramo) - len(acciones)}


def _hora(g: dict) -> float:
    try:
        return float(g.get("t"))
    except (TypeError, ValueError):
        raise ServiceError(400, f"cada entrada de la grabación lleva su hora `t` (s): {g!r}") from None


def preparar(doc, nombre: str, sesion: dict, *, hasta_s: float | None = None,
             reemplazar: bool = False) -> dict:
    """Valida contra el documento y arma el escenario (ver `escenario_de_sesion`). `sesion` =
    {grabacion, duracion_s, base, firma, hash_base?} (lo que trae el `fin`)."""
    from apolo.cosim.vivo import escenario_vivo

    from . import escenarios as E

    nombre = E.validar_nombre(nombre)
    if nombre in doc.escenarios and not reemplazar:
        raise ServiceError(409, f"ya hay un escenario «{nombre}»: elige otro nombre o pasa "
                                "`reemplazar=true` para pisarlo")
    for clave in ("base", "firma"):
        if not sesion.get(clave):
            raise ServiceError(400, f"falta `{clave}` de la sesión (viene en su mensaje `fin`)")
    base = sesion["base"]
    if base not in doc.escenarios:
        raise ServiceError(404, f"el escenario de base «{base}» de la sesión ya no existe: sin él "
                                "no se sabe qué acoples, condiciones ni cola de cajas tenía. "
                                + E.no_existe(doc, base))
    base_dict = doc.escenarios[base]["escenario"]
    if sesion.get("hash_base") and sesion["hash_base"] != E.hash_escenario(base_dict):
        raise ServiceError(409, f"el escenario de base «{base}» cambió desde la sesión: la grabación "
                                "ya no reproduciría lo que se vio. Abre una sesión nueva y grábala.")
    if sesion["firma"] != E.firma_documento(doc):
        raise ServiceError(409, "la sesión se grabó con otro modelo (la máquina cambió desde que se "
                                "abrió, o es de otro proyecto): sus acciones ya no reproducen lo que "
                                "se vio. Reinicia la sesión en vivo con el modelo de ahora y grábala.")
    out = escenario_de_sesion(escenario_vivo(base_dict), sesion.get("grabacion"),
                              sesion.get("duracion_s"), base=base, hasta_s=hasta_s)
    return {"nombre": nombre, "base": base, **out}


def sugerir(esc: dict, res: dict) -> list[dict]:
    """Las aserciones sugeridas (`cosim/sugeridas.py`) que pasan sobre su corrida `res`."""
    from apolo.cosim.sugeridas import sugerir as _sugerir

    from .escenarios import leer

    return _sugerir(leer(esc), res)

