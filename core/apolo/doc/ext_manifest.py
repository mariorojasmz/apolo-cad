"""La clave `ext` del manifest: los datos de cada extensión en el `.apolo` (plan
nucleo-abierto-extensiones-privadas, F1d). Puro: no importa `apolo.extensiones` ni la API.

Forma: `{"<nombre de la extensión>": {...}}`. Cada valor es un dict de JSON PLANO (dict con
claves str, list, str, int, float finito, bool, None) que el núcleo no interpreta: lo escribe y
lo lee la extensión dueña (por la fachada de `apolo.extensiones_api`). Es METADATO, como
`motion` o `escenarios`: fuera del log, de los checkpoints y del undo (raíz § «Metadato ≠
comando»).

Reglas:
- **Se conserva siempre**, también la de una extensión que no está instalada: abrir y guardar
  (autosave, revisiones, duplicar, exportar, `store.load`, el adjunto de un `insert_project`)
  pasa por `to_apolo_bytes`/`from_apolo_bytes`, que la llevan tal cual. Perderla al abrir sin la
  extensión borraría los datos del dueño.
- **Sin datos, el manifest es el de siempre** (no aparece la clave): un `.apolo` viejo abre igual
  y uno sin `ext` se guarda byte a byte como antes.
- **La carga es tolerante y la escritura estricta**: al abrir se descarta (sin lanzar) lo que no
  tiene la forma (un `.apolo` subido a mano no tumba la apertura); `poner` valida y lanza
  `DocumentError` con la corrección.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Iterable

from apolo.doc.errors import DocumentError

CLAVE = "ext"
#: El nombre de una extensión (`Extension.nombre`: «ext-prueba», «pro»): letra o dígito al
#: inicio, después letras, dígitos, «_», «-» o «.», hasta 64.
NOMBRE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$")
#: Tope por extensión del JSON serializado: el manifest viaja en cada autosave.
TOPE_BYTES = 1_000_000


def _plano(x, ruta: str) -> None:
    """Lanza `ValueError` con la ruta de lo primero que no es JSON plano."""
    if x is None or isinstance(x, (bool, str, int)):
        return
    if isinstance(x, float):
        if not math.isfinite(x):
            raise ValueError(f"{ruta} es {x}: sólo números finitos")
        return
    if isinstance(x, dict):
        for k, v in x.items():
            if not isinstance(k, str):
                raise ValueError(f"{ruta} tiene la clave {k!r}: las claves son texto")
            _plano(v, f"{ruta}.{k}")
        return
    if isinstance(x, list):
        for i, v in enumerate(x):
            _plano(v, f"{ruta}[{i}]")
        return
    raise ValueError(f"{ruta} es {type(x).__name__}: sólo JSON plano (dict, list, texto, número, "
                     "bool o null)")


def validar(nombre, datos, conocidas: Iterable[str] | None = None) -> dict:
    """Los `datos` de la extensión `nombre`, validados y COPIADOS; `DocumentError` si no.
    `conocidas`: si se da, el nombre tiene que ser uno de ellos (las extensiones cargadas)."""
    if not isinstance(nombre, str) or not NOMBRE.match(nombre):
        raise DocumentError(f"ext: «{nombre}» no es un nombre de extensión (letras, dígitos, «_», "
                            "«-» o «.», hasta 64)")
    if conocidas is not None and nombre not in set(conocidas):
        raise DocumentError(f"ext: «{nombre}» no es una extensión cargada: sólo la extensión dueña "
                            "escribe sus datos")
    if not isinstance(datos, dict):
        raise DocumentError(f"ext[{nombre}] es {type(datos).__name__}: tiene que ser un dict "
                            "(None borra los datos)")
    try:
        _plano(datos, f"ext[{nombre}]")
    except ValueError as exc:
        raise DocumentError(str(exc)) from None
    tam = len(json.dumps(datos, ensure_ascii=False).encode())
    if tam > TOPE_BYTES:
        raise DocumentError(f"ext[{nombre}] ocupa {tam} bytes: el tope es {TOPE_BYTES} (va en cada "
                            "autosave; lo grande va en un adjunto)")
    return copy.deepcopy(datos)


def de_manifest(manifest: dict) -> dict[str, dict]:
    """Lo de `ext` de un manifest leído, tolerante: lo que no tiene la forma se descarta."""
    crudo = manifest.get(CLAVE)
    if not isinstance(crudo, dict):
        return {}
    out: dict[str, dict] = {}
    for nombre, datos in crudo.items():
        try:
            out[nombre] = validar(nombre, datos)
        except DocumentError:
            continue
    return out


def al_manifest(doc) -> dict:
    """El fragmento del manifest: `{"ext": …}` sólo si hay datos (sin ellos, el de siempre)."""
    ext = getattr(doc, "ext", None)
    return {CLAVE: ext} if ext else {}


def leer(doc, nombre: str) -> dict | None:
    """Una COPIA de los datos de `nombre`, o None si no tiene."""
    datos = (getattr(doc, "ext", None) or {}).get(nombre)
    return None if datos is None else copy.deepcopy(datos)


def poner(doc, nombre: str, datos, conocidas: Iterable[str] | None = None) -> dict | None:
    """Reemplaza los datos de `nombre` (None los borra). Valida ANTES de tocar nada y devuelve
    una copia de lo que quedó."""
    if datos is None:
        validar(nombre, {}, conocidas)  # los mismos errores de nombre
        doc.ext.pop(nombre, None)
        return None
    doc.ext[nombre] = validar(nombre, datos, conocidas)
    return copy.deepcopy(doc.ext[nombre])
