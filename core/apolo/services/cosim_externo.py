"""El PLC de AFUERA que pide una corrida (plan plc-en-el-lazo, D6 y D7), validado ANTES del worker.

`plc_externo: {"-K1": {"conector": "x.y", "config": {…}}}` lo trae el PEDIDO de la corrida, nunca
el documento: probar contra un PLC de banco no cambia la máquina, así que nada de esto entra al
log, a la firma ni al `.apolo`. `leer` lo valida contra el tablero y los programas del snapshot:
  - la designación es un PLC del tablero y tiene programa (el del carril o el que puso encima la
    prueba): el PLC de afuera corre el programa que se probó aquí y el conector lee sus bornes;
  - el conector está cargado (`cosim.puerto_plc.CONECTORES`, los suma una extensión con
    `conectores_plc`) y su `validar_config` no tiene problemas.
Todo lo que falla sale junto, como `ServiceError(400)` con qué corregir. Sin `plc_externo`, `{}`.

`de_query` lee el de la sesión en vivo (`?plc_externo=` JSON ≤ 1 KB, sin `ritmo` ≠ 1; F1b2),
`resultado` arma el `plc_externo` del resultado y `veredicto_nulo` el veredicto que no se da
(D7). Sin locks: el llamador sostiene `STATE_LOCK` (lee el tablero); `de_query` no lee nada.
"""

from __future__ import annotations

import json

from .errors import ServiceError

FORMA = '{"-K1": {"conector": "<prefijo.nombre>", "config": {…}}}'
MOTIVO = ("con un PLC externo no hay veredicto: la corrida no es determinista (reloj de pared, "
          "programa fuera del documento) y no se guarda como resultado del escenario")


def _plcs(me) -> list[str]:
    return [d.designacion for d in me.dispositivos if (d.modelo or {}).get("tipo") == "plc"]


def leer(pedido, me, programas) -> dict:
    """{designación: (clase del conector, config)} del pedido. `ServiceError(400)` con todos los
    problemas juntos."""
    if not pedido:
        return {}
    if not isinstance(pedido, dict):
        raise ServiceError(400, f"`plc_externo` es {FORMA}, no {type(pedido).__name__}")
    from apolo.cosim.puerto_plc import CONECTORES

    from apolo.library.electrico.referencias import sufijo_sugerencia

    plcs, con_programa = _plcs(me), {p.plc for p in programas}
    cargados = ", ".join(sorted(CONECTORES)) or ("ninguno (los suma una extensión con "
                                                 "`conectores_plc`: mira GET /api/extensiones)")
    out, problemas = {}, []
    for des, pedido_des in pedido.items():
        donde = f"plc_externo.{des}"
        if des not in plcs:
            problemas.append(f"{donde}: «{des}» no es un PLC del tablero; PLC: {', '.join(plcs) or 'ninguno'}."
                             f"{sufijo_sugerencia(str(des), plcs)}")
            continue
        if des not in con_programa:
            problemas.append(f"{donde}: el PLC no tiene programa: el PLC de afuera corre el programa "
                             f"probado aquí y el conector lee sus bornes; declara su ST con "
                             f'add_program (plc="{des}")')
            continue
        if not isinstance(pedido_des, dict) or "conector" not in pedido_des or set(pedido_des) - {"conector", "config"}:
            problemas.append(f"{donde}: cada PLC externo es {{\"conector\": \"<prefijo.nombre>\", "
                             f"\"config\": {{…}}}} (sin otras claves)")
            continue
        nombre, config = pedido_des["conector"], pedido_des.get("config", {})
        clase = CONECTORES.get(nombre) if isinstance(nombre, str) else None
        if clase is None:
            problemas.append(f"{donde}: el conector «{nombre}» no está cargado; conectores: {cargados}")
            continue
        if not isinstance(config, dict):
            problemas.append(f"{donde}.config: es un objeto JSON, no {type(config).__name__}")
            continue
        try:
            malos = [str(m) for m in (clase.validar_config(config) or [])]
        except Exception as exc:  # noqa: BLE001 — el código del conector también puede lanzar
            malos = [f"validar_config del conector falló: {type(exc).__name__}: {exc}"]
        if malos:
            problemas += [f"{donde}.config: {m}" for m in malos]
            continue
        out[des] = (clase, json.loads(json.dumps(config)))  # una copia JSON pura viaja al worker
    if problemas:
        raise ServiceError(400, " | ".join(problemas))
    return out


MAX_QUERY = 1024  # bytes del JSON de `?plc_externo=` (D6: una URL no es un cuerpo)


def de_query(texto: str | None, ritmo: str | None) -> dict | None:
    """El `plc_externo` de la query de `WS /api/cosim/vivo` (D6, D9), aún sin validar contra el
    tablero (eso lo hace `leer` en el snapshot): JSON ≤ `MAX_QUERY` bytes con un objeto, y la
    sesión al ritmo de la pared (`ritmo` ausente o 1). None sin `plc_externo`;
    `ServiceError(400)` con qué corregir."""
    if texto is None or not texto.strip():
        return None
    if len(texto.encode("utf-8")) > MAX_QUERY:
        raise ServiceError(400, f"`plc_externo` pasa de {MAX_QUERY} bytes: en la query va sólo la "
                                f"conexión ({FORMA}); lo demás, en la configuración del conector")
    try:
        pedido = json.loads(texto)
    except ValueError as exc:
        raise ServiceError(400, f"`plc_externo` no es JSON ({exc}): {FORMA}, codificado en la URL") from exc
    if not isinstance(pedido, dict) or not pedido:
        raise ServiceError(400, f"`plc_externo` es {FORMA}")
    if ritmo is not None:
        try:
            r = float(ritmo)
        except ValueError:
            r = None
        if r != 1.0:
            raise ServiceError(400, f"con un PLC externo la sesión va al ritmo de la pared (el PLC de "
                                    f"afuera vive en tiempo real): quita ?ritmo o pon ritmo=1, no «{ritmo}»")
    return pedido


def resultado(pedido: dict) -> dict:
    """D7: {designación: {conector, extension, version}} de un pedido ya validado."""
    from apolo.cosim.puerto_plc import DE_EXTENSION

    out = {}
    for des, p in pedido.items():
        ext, version = DE_EXTENSION.get(p["conector"], (None, None))
        out[des] = {"conector": p["conector"], "extension": ext, "version": version}
    return out


def veredicto_nulo() -> dict:
    """D7: sin veredicto (ni aserciones evaluadas), con su motivo."""
    return {"veredicto": None, "aserciones": [], "n_fallidas": 0, "motivo": MOTIVO}
