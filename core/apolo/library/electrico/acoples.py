"""Quién MUEVE un bloque de contactos auxiliares (plan pedidos-de-extensiones, D4): la regla
única de `Dispositivo.acoplado_a`.

Un bloque auxiliar («-Q3A», caminos `accion: acople`) no tiene actuador propio: sus contactos
siguen al aparato cuya designación es la suya SIN el sufijo de letras («-Q3»), si ese aparato
existe y tiene algo que mueva contactos: bobina, protección o manija (`actuador_maestro`). Si no,
`None`: la co-simulación deja el bloque en reposo con su aviso.

Es la regla de la co-simulación (`services/cosim_red.py`), que la LEE del dispositivo; el carril
la aplica al cerrar el modelo (`commands/electrico_eval.py`). La colocación del tablero
(`colocacion.resolver_acoples`) decide dónde se MONTA el bloque con otra regla (prefijo, único
aparato del símbolo, override `acopla`) y puede diferir: no se unifican (plan, § Riesgos).

Puro: sólo dataclasses del modelo, sin catálogo ni documento.
"""

from __future__ import annotations

import re
from dataclasses import replace

_SUFIJO = re.compile(r"^(.*\d)[A-Za-z]+$")


def es_bloque_auxiliar(d) -> bool:
    """¿El dispositivo tiene contactos movidos por un acople (un bloque auxiliar)?"""
    return any(c.accion == "acople" for c in d.caminos)


def maestro_buscado(designacion: str) -> str:
    """La designación sin el sufijo de letras («-Q3A» → «-Q3»); sin sufijo, la misma."""
    return _SUFIJO.sub(r"\1", designacion)


def actuador_maestro(d) -> str | None:
    """Qué mueve los contactos del aparato maestro: «bobina», «cerrado» (su protección) o «mano»;
    `None` si no tiene nada que los mueva."""
    acciones = {(c.tipo, c.accion) for c in d.caminos}
    if any(a == "bobina" for _, a in acciones):
        return "bobina"
    if any(t == "proteccion" for t, _ in acciones):
        return "cerrado"
    if any(a == "mano" for _, a in acciones):
        return "mano"
    return None


def acoplado_a(d, dispositivos: dict) -> str | None:
    """La designación del aparato que mueve el bloque auxiliar `d`, o `None` (no es bloque, no
    hay aparato con su designación sin sufijo, o ese aparato no tiene bobina, protección ni
    manija). `dispositivos` = {designación: Dispositivo} del mismo modelo."""
    if not es_bloque_auxiliar(d):
        return None
    m = _SUFIJO.match(d.designacion)
    maestro = dispositivos.get(m.group(1)) if m else None
    return m.group(1) if maestro is not None and actuador_maestro(maestro) is not None else None


def cerrar_acoples(dispositivos) -> tuple:
    """Los dispositivos con su `acoplado_a` puesto (el carril al cerrar el modelo). Una
    designación repetida cuenta la primera, como la co-simulación."""
    por_des: dict = {}
    for d in dispositivos:
        por_des.setdefault(d.designacion, d)
    return tuple(replace(d, acoplado_a=acoplado_a(d, por_des)) for d in dispositivos)
