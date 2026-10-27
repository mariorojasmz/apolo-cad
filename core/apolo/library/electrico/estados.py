"""Los ESTADOS de un aparato que se nombran (plan nombres-por-funcion, D1 y A4): la tabla única de
claves por tipo y su validación. Puro: recibe el `modelo` de la ficha eléctrica y el de la
neumática (dicts), nunca el catálogo ni el documento.

Qué estados tiene cada tipo (las claves de `add_device.estados`):
  - selector: las `posiciones` de su ficha («0», «I», «II»), la señal `<des>.posicion`;
  - electroválvula: las POSICIONES del carrete, no los lados con bobina: 5/2 «14» «12»; 5/3
    «14» «0» «12»; 3/2 y 2/2 «12» «0» (los nombres de `cosim/modelos/electrovalvula.py` y de
    `drawing/neumatica/valvulas.nombres_posiciones`);
  - seccionador y resguardo: «cerrado» y «abierto» (la señal `<des>.cerrado`);
  - pulsador con VARIOS actuadores (una botonera marcha/paro): sus actuadores;
  - el resto: ninguno (un `estados` no vacío es error).

Al ENTRAR (`validar`) una clave que la ficha no tiene es error con las válidas; al CARGAR
(`filtrar`) se ignora con aviso y el aparato se conserva (A5): un texto vencido nunca suprime un
dispositivo del tablero.
"""

from __future__ import annotations

TOPE_ESTADO = 30  # el mismo tope que el rótulo: un estado es texto de placa («Manual», «Ciclo»)
CERRADO_ABIERTO = ("cerrado", "abierto")


def _posiciones_valvula(neu: dict) -> tuple[str, ...]:
    vias, pos = int(neu.get("vias", 5)), int(neu.get("posiciones", 2))
    if vias == 5:
        return ("14", "0", "12") if pos == 3 else ("14", "12")
    return ("12", "0")


def claves(modelo: dict | None, neumatico: dict | None = None) -> tuple[str, ...]:
    """Las claves de `estados` del aparato, en el orden en que se muestran (la tabla A4)."""
    m = modelo or {}
    tipo = m.get("tipo")
    if tipo == "selector":
        return tuple(str(p) for p in m.get("posiciones") or ())
    if tipo == "electrovalvula" or (neumatico or {}).get("tipo") == "valvula":
        return _posiciones_valvula(neumatico or {})
    if tipo in ("seccionador", "resguardo"):
        return CERRADO_ABIERTO
    if tipo == "pulsador":
        actuadores = [str(a) for a in m.get("actuadores") or ()]
        return tuple(actuadores) if len(actuadores) > 1 else ()
    return ()


def _limpio(estados: dict) -> dict[str, str]:
    return {str(k): " ".join(str(v).split()) for k, v in (estados or {}).items()}


def validar(estados: dict, validas: tuple[str, ...], quien: str) -> dict[str, str]:
    """`estados` limpio, o `ValueError` accionable: la clave que sobra con las válidas, o el
    nombre vacío o largo."""
    out = _limpio(estados)
    sobran = [k for k in out if k not in validas]
    if sobran:
        if not validas:
            raise ValueError(f"{quien}: su tipo no tiene estados que nombrar (quita `estados`); sólo los "
                             "llevan el selector, el seccionador, el resguardo, la electroválvula y la botonera")
        raise ValueError(f"{quien}: `estados` no tiene la clave {', '.join(f'«{k}»' for k in sobran)}; "
                         f"las de su ficha: {', '.join(f'«{k}»' for k in validas)}")
    for k, v in out.items():
        if not v:
            raise ValueError(f"{quien}: el estado «{k}» va sin nombre (escríbelo o quítalo)")
        if len(v) > TOPE_ESTADO:
            raise ValueError(f"{quien}: el nombre del estado «{k}» pasa de {TOPE_ESTADO} caracteres: «{v}»")
    return out


def filtrar(estados: dict, validas: tuple[str, ...]) -> tuple[dict[str, str], tuple[str, ...]]:
    """(los estados que su ficha tiene, las claves ignoradas): la carga tolerante (A5)."""
    out = _limpio(estados)
    return ({k: v for k, v in out.items() if k in validas and v},
            tuple(k for k, v in out.items() if k not in validas or not v))
