"""La posición INICIAL de una junta en un escenario, contra el documento (plan motor-a-eje-lineal F4).

`mecanica.juntas.<junta>.inicial` (mm en una prismática, grados en una de giro, medidos desde la
pose de diseño como el `q` de set_motion) dice dónde ARRANCA esa junta: la física parte de ahí
(qpos inicial de MuJoCo), y con ella los sensores por junta, las fotoceldas y el aire (la x del
vástago de un cilindro). Sin `inicial`, la pose de diseño: lo de siempre.

  - `validar(doc, esc)`: cada `inicial` contra su junta (que exista, que se mueva, sus límites),
    AL DECLARAR (`escenarios.poner`) y antes de preparar la dinámica (`cosim_snapshot`), con la
    regla única de `physics.dinamica_peticion.posicion_inicial`;
  - `hipotesis(doc, esc)`: lo que el resultado dice de esas posiciones.

El AIRE de un cilindro que arranca fuera de cero: cada cámara arranca a la presión de lo que su
válvula EN REPOSO le une (la fuente o la atmósfera; `HIPOTESIS_ARRANQUE` de `cosim/neumatica/red`)
y con el volumen de ESA posición. Es lo honesto para un cilindro en reposo: si la válvula alimenta
la cámara que lo sostiene contra su tope, está a la presión de la línea y la otra, a la atmósfera;
no hay una «presión de equilibrio» que declarar (la fuerza neta la absorbe el tope). Una cámara
bloqueada (centro cerrado) arranca a la atmósfera, como en la pose de diseño.

Todo error es `ServiceError(400, texto)`. Sin locks: el llamador sostiene STATE_LOCK.
"""

from __future__ import annotations

from .errors import ServiceError


def _iniciales(esc) -> dict:
    from apolo.cosim.escenario_mecanica import iniciales

    return iniciales(esc.mecanica or {})


def validar(doc, esc) -> None:
    """`ServiceError(400)` si un `inicial` no sirve para su junta del documento."""
    from apolo.physics.dinamica_peticion import posicion_inicial
    from apolo.physics.sim import PhysicsError

    juntas = doc.joints or {}
    moviles = [n for n, j in juntas.items() if j.get("type") != "fija"]
    for n, v in _iniciales(esc).items():
        try:
            posicion_inicial(n, v, juntas.get(n), moviles)
        except PhysicsError as exc:
            raise ServiceError(400, f"mecanica.{exc}") from exc


def hipotesis(doc, esc) -> list[str]:
    """Una línea por junta que arranca fuera de la pose de diseño (y, si hay productos, dónde van)."""
    ini = _iniciales(esc)
    if not ini:
        return []
    juntas = doc.joints or {}
    cil_de = {a["junta"]: des for des, a in (esc.cilindros or {}).items()}
    out = []
    for n, v in sorted(ini.items()):
        unidad = "mm" if (juntas.get(n) or {}).get("type") == "prismatica" else "°"
        texto = (f"{n} arranca en {v:g} {unidad} (mecanica.juntas.{n}.inicial; la pose de diseño es 0): "
                 "la física, sus sensores y lo que va montado en ella parten de ahí")
        if n in cil_de:
            texto += (f"; {cil_de[n]}: cada cámara a la presión de lo que su válvula en reposo le une, "
                      "con el volumen de esa posición")
        out.append(texto)
    if esc.productos:
        out.append("los productos se declaran en coordenadas del MUNDO: uno que va sobre una pieza que "
                   "arranca fuera de su pose de diseño se pone donde está esa pieza al arrancar")
    return out
