"""Los ajustes de PRUEBA de un escenario (plan cotizacion-identificada-y-ajustes-por-escenario D5).

Un escenario puede declarar `ajustes: {designación: {campo: valor}}` (p. ej. el `sobrecarga_s` de un
variador a 1 s para provocar el disparo en un atasco corto, cuando la placa dice 60 s). Valen SÓLO
dentro de la co-simulación de ese escenario:
  - `validar(me, ajustes)`: contra el tablero armado, igual que `add_device` (la ficha `modelo`
    de cada aparato con `library/electrico/ajustes.validar_ajustes` y, en uno de aire, los rangos
    de su ficha neumática con `commands/neumatica_eval._ajustes`): una designación que el tablero
    no tiene o un campo que su ficha no declara es `ServiceError(400)` con la corrección;
  - `aplicar(me, ajustes)`: un `ModeloElectrico` NUEVO con los ajustes encima de los del
    `add_device` (el modelo del documento es inmutable y no se toca) y la lista de lo que se usó,
    con el valor del proyecto al lado (`proyecto`: el del `add_device`, o el de la ficha si el
    `add_device` no lo fija);
  - `hipotesis(usados)`: una línea por ajuste para las hipótesis de la corrida.

El documento, el log y lo que leen el manual y la memoria (`services/electrico.modelo`) siguen
con el valor del proyecto (D7). Un ajuste del escenario entra a su `hash_escenario` (la vigencia
de SU resultado, D6): sin `ajustes` el escenario y su hash son los de siempre. Sin locks: el
llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from .errors import ServiceError


def _validar_uno(d, campos: dict) -> dict:
    from apolo.library.electrico.ajustes import validar_ajustes

    ref = f"{d.designacion} ({d.ref})"
    if d.neumatico is not None:  # como `neumatica_eval.dispositivo`: aire y lado eléctrico
        from apolo.commands.neumatica_eval import _ajustes

        ficha_e = SimpleNamespace(modelo=d.modelo) if d.modelo else None
        return _ajustes(campos, d.neumatico, ficha_e, ref)
    return validar_ajustes(campos, d.modelo, ref)


def validar(me, ajustes: dict) -> dict:
    """{designación: {campo: valor}} validado contra el tablero `me`, o `ServiceError(400)`."""
    from apolo.library.electrico.referencias import sufijo_sugerencia

    if not ajustes:
        return {}
    por_des = {d.designacion: d for d in me.dispositivos}
    out, errores = {}, []
    for des, campos in ajustes.items():
        d = por_des.get(des)
        if d is None:
            errores.append(f"«{des}» no es un aparato del tablero{sufijo_sugerencia(des, list(por_des))}")
            continue
        try:
            out[des] = _validar_uno(d, campos)
        except ValueError as exc:
            errores.append(str(exc))
    if errores:
        raise ServiceError(400, "ajustes del escenario: " + " | ".join(errores)
                           + " (son ajustes de PRUEBA: valen sólo en este escenario; los del "
                             "proyecto van en add_device.ajustes)")
    return out


def aplicar(me, ajustes: dict) -> tuple[object, list[dict]]:
    """(el `ModeloElectrico` con los ajustes del escenario encima, [{dispositivo, ajuste, valor,
    proyecto}]). Sin `ajustes`, el MISMO objeto y `[]`. Un ajuste deducido de la pieza que el
    escenario pisa deja de figurar como deducido (su hipótesis diría otro valor)."""
    validos = validar(me, ajustes)
    if not validos:
        return me, []
    usados, nuevos = [], []
    for d in me.dispositivos:
        campos = validos.get(d.designacion)
        if not campos:
            nuevos.append(d)
            continue
        for k, v in campos.items():
            usados.append({"dispositivo": d.designacion, "ajuste": k, "valor": v,
                           "proyecto": d.ajustes.get(k, d.modelo.get(k))})
        nuevos.append(replace(d, ajustes={**d.ajustes, **campos},
                              deducidos={k: o for k, o in d.deducidos.items() if k not in campos}))
    return replace(me, dispositivos=tuple(nuevos)), usados


def _txt(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)


def hipotesis(usados: list[dict]) -> list[str]:
    return [f"{u['dispositivo']}: {u['ajuste']} = {_txt(u['valor'])} es un ajuste de PRUEBA de este "
            f"escenario (el proyecto: {_txt(u['proyecto'])}); el documento no cambia" for u in usados]
