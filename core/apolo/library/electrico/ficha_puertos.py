"""Puertos de DATOS de una ref: el bloque `electrico.puertos` del YAML del catálogo (plan
plc-en-el-lazo, D12).

Un puerto de red (el RJ45 de un PLC o de un panel de operador) no es un borne: no lleva tensión
de mando ni potencia, no entra a la red que simula la co-simulación ni al ERC (que recorren
bornes) y va FUERA de `modelo` (no entra a la firma del documento ni es un ajuste). Dice qué
conectores de datos trae el aparato de serie, para quien arma la red de la máquina o exporta el
programa a un PLC real.

    puertos: [{id: X1, tipo: rj45}, …]

Lo que valida (al cargar el catálogo; un bloque mal escrito no carga):
  - es OPCIONAL; si viene, una lista no vacía de mapas {id, tipo} con claves conocidas;
  - `id` no vacío, sin espacios ni «:», ÚNICO y distinto de todo borne de la ref (un puerto y un
    borne con el mismo nombre se confundirían en «-K1:X1»);
  - `tipo` de `TIPOS` (hoy `rj45`: 8P8C de IEC 60603-7, el de Ethernet por par trenzado);
  - pide `fuente`: que la línea de referencia trae ese puerto DE SERIE sale de su ficha, no de
    memoria (un variador sin red de serie no gana puerto).

Puro: sólo la biblioteca estándar y `referencias.sugerir`; no importa el catálogo.
"""

from __future__ import annotations

from dataclasses import dataclass

from .referencias import sugerir

#: La clave del bloque en `electrico:`.
CLAVE = "puertos"
#: Tipos de puerto de datos que el catálogo sabe nombrar.
TIPOS = ("rj45",)
_CLAVES = ("id", "tipo")


@dataclass(frozen=True)
class Puerto:
    id: str
    tipo: str


def _parecida(valor: str, validos) -> str:
    hit = sugerir(valor, list(validos), 1)
    return f" ¿Quisiste decir «{hit[0]}»?" if hit else ""


def parse_puertos(err, crudo, *, ids_bornes: tuple[str, ...], fuente: str) -> tuple[Puerto, ...]:
    """`electrico.puertos` → `(Puerto, …)` en el orden del YAML. `err(ruta, msg)` arma el
    ValueError con la ref (el de `ficha.py`); `fuente` es la ya validada por `ficha_datos`."""
    if crudo is None:
        return ()
    if not isinstance(crudo, list) or not crudo:
        raise err(CLAVE, f"se espera una lista de puertos [{{id, tipo}}], p. ej. "
                         f"[{{id: X1, tipo: rj45}}], llegó {crudo!r}")
    out: list[Puerto] = []
    for i, p in enumerate(crudo):
        ruta = f"{CLAVE}[{i}]"
        if not isinstance(p, dict):
            raise err(ruta, f"se espera un mapa {{id, tipo}}, llegó {p!r}")
        for k in p:
            if k not in _CLAVES:
                raise err(ruta, f"clave desconocida «{k}»; válidas: {', '.join(_CLAVES)}."
                                f"{_parecida(str(k), _CLAVES)}")
        pid = str(p.get("id") or "").strip()
        if not pid:
            raise err(ruta, "falta `id` (el rótulo del conector en el aparato, p. ej. «X1»)")
        if any(c.isspace() for c in pid) or ":" in pid:
            raise err(ruta, f"el id «{pid}» no puede llevar espacios ni «:»")
        if pid in ids_bornes:
            raise err(ruta, f"«{pid}» ya es un borne de la ref: un puerto de datos lleva otro "
                            "nombre (no es un borne)")
        if any(x.id == pid for x in out):
            raise err(ruta, f"puerto «{pid}» repetido: cada puerto tiene un id único")
        tipo = p.get("tipo")
        if tipo not in TIPOS:
            raise err(f"{ruta}.tipo", f"«{tipo}» no es válido; opciones: {', '.join(TIPOS)}."
                                      f"{_parecida(str(tipo), TIPOS)}")
        out.append(Puerto(pid, tipo))
    if not fuente:
        raise err("fuente", "falta: con `puertos` va de dónde sale que la línea de referencia los "
                            "trae de serie (su ficha, documento y sección)")
    return tuple(out)


def payload(puertos: tuple[Puerto, ...]) -> list[dict]:
    """Los puertos en JSON para el catálogo (`ficha_payload`)."""
    return [{"id": p.id, "tipo": p.tipo} for p in puertos]
