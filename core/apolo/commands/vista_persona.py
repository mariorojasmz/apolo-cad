"""Vista PERSONA del registro de comandos (`GET /api/schemas?vista=persona`).

El registro tiene un solo texto por comando —la `description` del modelo pydantic— y es
del AGENTE: largo a propósito, con nombres de parámetros y la versión del roadmap que lo
trajo. La vista agente (`command_schemas()`, la de siempre) no cambia ni un byte (D1). Esta
vista arma, sobre una COPIA, lo que lee una persona:

- `pista`: una frase que dice qué hace el comando (`pistas.PISTAS`; sin pista, la primera
  frase limpia de la descripción, como red).
- `detalle`: la descripción limpia, sólo si tiene más de una frase (va plegada en la UI).
- `pestana`: la pestaña del ribbon de su categoría (`pistas.PESTANAS`).
- en el schema: sin versiones del roadmap en ningún `title`/`description`, espacios
  normalizados, sin la `description` raíz (duplicaba la del comando), `x-unidad` en los
  campos cuya descripción empieza con una unidad y `x-pista` donde un campo anula a otro.

Plan: docs/plans/texto-agente-vs-persona.md (D2, D3, D6, D7, D8).
"""

from __future__ import annotations

import copy
import re

from .pistas import PESTANAS, PISTAS, PISTAS_CAMPO
from .registry import REGISTRY, command_schemas

#: La versión del roadmap («V6.8-E», «V5.2b»): el mismo regex que `HISTORIA` en
#: `ui/src/textoDeAyuda.test.ts` (`tests/test_pistas.py` compara el texto del patrón). Va con
#: `re.ASCII` porque en JS `\b` y `\w` son ASCII.
_V = r"\bV\d+(?:\.\d+)?[a-z]?(?:-[A-Z])?(?![\w.])"
_VERSION = re.compile(_V, re.ASCII)
_SOLA = re.compile(rf"\s*\(\s*{_V}\s*\)", re.ASCII)  # «Pestañas ricas (V5.5)»
_COLA = re.compile(rf"\s*,\s*{_V}(?=\s*\))", re.ASCII)  # «(layouts multi-máquina, V5.2b)»
_CABEZA = re.compile(rf"(?<=\()\s*{_V}\s*[,:;]\s*", re.ASCII)  # «(V6.8-E, pasa `cara`…)»
_SUELTA = re.compile(rf"[ \t]*{_V}", re.ASCII)  # «desde V7.2»

#: Oración nueva: signo de cierre, espacio y algo que arranca oración. Es `FIN_DE_ORACION`
#: de `ui/src/textoDeAyuda.test.ts` (sin `re.ASCII`: el `\s` de JS es Unicode); el texto
#: del patrón es idéntico al de la UI y `tests/test_pistas.py` lo compara.
FIN_DE_ORACION = re.compile(r'[.!?…]\s+(?=[A-ZÁÉÍÓÚÜÑ0-9¿¡«("])')

#: Lista CERRADA de unidades que se rotulan junto al campo (D6), la más larga primero.
UNIDADES = ("grados o mm", "mm", "grados")
_UNIDAD = re.compile(rf"({'|'.join(UNIDADES)})(?![\wáéíóúñ])")

#: Una línea que abre una viñeta en una docstring («- coincidente: …»).
_VINETA = re.compile(r"[-•] ")


def _normalizar(texto: str) -> str:
    """Espacios de docstring a texto: une las líneas cortadas por el ancho del código,
    conserva los párrafos (línea en blanco) y las viñetas («- …») en su propia línea. Una
    línea que vuelve a la sangría del guion (o menos) ya no es de la viñeta: abre otra."""
    parrafos = []
    for parrafo in re.split(r"\n[ \t]*\n", texto.strip()):
        lineas: list[str] = []
        guion: int | None = None  # sangría del guion de la viñeta abierta
        for cruda in parrafo.splitlines():
            linea = " ".join(cruda.split())
            if not linea:
                continue
            sangria = len(cruda) - len(cruda.lstrip())
            if _VINETA.match(linea):
                guion = sangria
                lineas.append(linea)
            elif lineas and (guion is None or sangria > guion):
                lineas[-1] += " " + linea
            else:
                guion = None
                lineas.append(linea)
        if lineas:
            parrafos.append("\n".join(lineas))
    return "\n\n".join(parrafos)


def limpiar_historia(texto: str) -> str:
    """Quita las versiones del roadmap («(V6.8-E)», «, V5.2b)», «desde V7.2») y normaliza
    los espacios. «220V» y «Vista 3D» no son versiones y quedan intactos."""
    if _VERSION.search(texto):
        texto = _SOLA.sub("", texto)
        texto = _COLA.sub("", texto)
        texto = _CABEZA.sub("", texto)
        texto = _SUELTA.sub("", texto)
    return _normalizar(texto)


def frases(texto: str) -> int:
    """Cuántas oraciones tiene un texto, como las cuenta el gate de la UI."""
    limpio = " ".join(texto.split())
    return 1 + len(FIN_DE_ORACION.findall(limpio)) if limpio else 0


def primera_frase(texto: str) -> str:
    """La primera oración de un texto, en una línea."""
    limpio = " ".join(texto.split())
    m = FIN_DE_ORACION.search(limpio)
    return limpio[: m.start() + 1] if m else limpio


def unidad_de(descripcion: str | None) -> str | None:
    """La unidad con la que EMPIEZA una descripción de campo («mm, 0 = pasante» → «mm»),
    o None. Sólo las de `UNIDADES`: una descripción que no arranca con unidad va a la ⓘ."""
    m = _UNIDAD.match(descripcion or "")
    return m.group(1) if m else None


def _limpiar_schema(nodo) -> None:
    """Sobre la copia: limpia todo `title`/`description` a cualquier profundidad y pone
    `x-unidad` en cada campo (una entrada de `properties`) cuya descripción la trae."""
    if isinstance(nodo, list):
        for v in nodo:
            _limpiar_schema(v)
        return
    if not isinstance(nodo, dict):
        return
    for clave in ("title", "description"):
        if isinstance(nodo.get(clave), str):
            nodo[clave] = limpiar_historia(nodo[clave])
    for campo in (nodo.get("properties") or {}).values():
        if isinstance(campo, dict):
            unidad = unidad_de(campo.get("description"))
            if unidad:
                campo["x-unidad"] = unidad
    for v in nodo.values():
        if isinstance(v, (dict, list)):
            _limpiar_schema(v)


def _pistas_de_campo(tipo: str, schema: dict) -> None:
    """Inyecta `x-pista` en los campos de `PISTAS_CAMPO` que tiene este comando: en su
    modelo raíz o en un sub-modelo de `$defs`."""
    raiz = REGISTRY[tipo].model.__name__
    for clave, pista in PISTAS_CAMPO.items():
        modelo, campo = clave.split(".", 1)
        if modelo == raiz:
            props = schema.get("properties") or {}
        else:
            props = (schema.get("$defs", {}).get(modelo) or {}).get("properties") or {}
        if isinstance(props.get(campo), dict):
            props[campo]["x-pista"] = pista


def _entrada_persona(entrada: dict) -> dict:
    e = copy.deepcopy(entrada)  # el dict del agente no se toca (D1)
    tipo = e["type"]
    descripcion = limpiar_historia(e.get("description") or "")
    schema = e["schema"]
    schema.pop("description", None)  # la raíz repetía la descripción del comando
    _limpiar_schema(schema)
    _pistas_de_campo(tipo, schema)
    return {
        "type": tipo,
        "title": limpiar_historia(e["title"]),
        "category": e["category"],
        "kind": e["kind"],
        "pestana": PESTANAS.get(e["category"]),
        "pista": PISTAS.get(tipo) or primera_frase(descripcion),
        "detalle": descripcion if frases(descripcion) > 1 else "",
        "schema": schema,
    }


def command_schemas_persona() -> list[dict]:
    """Los schemas de TODOS los comandos para la UI (la vista agente queda intacta)."""
    return [_entrada_persona(e) for e in command_schemas()]
