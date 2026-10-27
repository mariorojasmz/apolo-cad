"""La forma del bloque `mecanica` de un escenario, AL DECLARAR (sale de `escenario.py`, trinquete
de tamaño): los `sumideros` (F6 de puerta-de-publicacion) y las opciones de cada junta, con su
`inicial` (plan motor-a-eje-lineal F4). Lo demás de `mecanica` (bandas, timestep, nstep…) pasa tal
cual a la petición de V8.2, que lo valida al preparar la dinámica.

Lo que necesita el documento (que la junta exista, sus límites) no va aquí: lo revisa
`services/escenarios.poner` al declarar y la dinámica al preparar, con la MISMA regla
(`physics.dinamica_peticion.posicion_inicial`). Puro: stdlib.
"""

from __future__ import annotations

import math

from .escenario import EscenarioInvalido, _claves, _num
from .flujo import FlujoInvalido, validar_nombre_sumidero

#: Las opciones de una junta en `mecanica.juntas` (las de la petición de V8.2 + `inicial`).
CLAVES_JUNTA = ("amortiguamiento", "friccion", "armadura", "inicial")


def _vec3(v, donde: str, *, unitario: bool = False) -> None:
    if (not isinstance(v, list) or len(v) != 3
            or any(not isinstance(c, (int, float)) or isinstance(c, bool) or not math.isfinite(c) for c in v)):
        raise EscenarioInvalido(f"{donde}: se espera [x, y, z] (tres números), llegó {v!r}")
    if unitario and not any(v):
        raise EscenarioInvalido(f"{donde}: la normal no puede ser [0, 0, 0] (apunta al lado que retira)")


def _sumideros(mecanica: dict) -> None:
    """`mecanica.sumideros` (los de la petición de V8.2, F6 de puerta-de-publicacion): planos
    {punto_mm, normal, nombre?} que RETIRAN el producto que los pasa (el nombre: la salida que
    cuenta el balance, plan balance-de-producto D3). Se validan al declarar el escenario, no a
    mitad de la preparación de la dinámica."""
    lista = mecanica.get("sumideros")
    if lista is None:
        return
    if not isinstance(lista, list):
        raise EscenarioInvalido("mecanica: «sumideros» es una lista de {punto_mm: [x, y, z], normal: [x, y, z]}")
    for k, s in enumerate(lista):
        donde = f"mecanica.sumideros[{k}]"
        s = _claves(s, {"punto_mm", "normal", "nombre"}, donde)
        for c in ("punto_mm", "normal"):
            if s.get(c) is None:
                raise EscenarioInvalido(f"{donde}: falta «{c}» [x, y, z] (el plano que retira el producto "
                                        "que lo pasa: punto en mm y normal hacia el lado que retira)")
        _vec3(s["punto_mm"], f"{donde}.punto_mm")
        _vec3(s["normal"], f"{donde}.normal", unitario=True)
        if s.get("nombre") is not None:
            try:
                validar_nombre_sumidero(s["nombre"], donde)
            except FlujoInvalido as exc:
                raise EscenarioInvalido(str(exc)) from None


def _juntas(mecanica: dict) -> None:
    """`mecanica.juntas` = {junta: {amortiguamiento?, friccion?, armadura?, inicial?}}. `inicial`
    es dónde ARRANCA la junta: mm (prismática) o grados (de giro), medidos desde la pose de diseño
    como el `q` de set_motion; sin ella, la pose de diseño (lo de siempre)."""
    juntas = mecanica.get("juntas")
    if juntas is None:
        return
    if not isinstance(juntas, dict):
        raise EscenarioInvalido("mecanica: «juntas» es {junta: {friccion?, amortiguamiento?, armadura?, inicial?}}")
    for n, op in juntas.items():
        donde = f"mecanica.juntas.{n}"
        op = _claves(op, set(CLAVES_JUNTA), donde)
        for c in CLAVES_JUNTA:
            _num(op, c, donde, minimo=None if c == "inicial" else 0.0)


def revisar(mecanica: dict) -> None:
    """La forma de `mecanica` que se valida al declarar. `EscenarioInvalido` con la corrección."""
    _sumideros(mecanica)
    _juntas(mecanica)


def iniciales(mecanica: dict) -> dict:
    """{junta: inicial} de las juntas que lo declaran (mm o grados; ya revisado)."""
    return {str(n): float(op["inicial"]) for n, op in (mecanica.get("juntas") or {}).items()
            if isinstance(op, dict) and op.get("inicial") is not None}
