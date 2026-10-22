"""La biblioteca de música de la fábrica (plan fabrica-de-publicaciones, D9).

Cada PC tiene la suya en `paths.home()/musica` (`APOLO_HOME` o `~/.apolo`; `APOLO_MUSICA_DIR`
la cambia, p. ej. en los tests): las pistas que bajó una persona (Pixabay Music: uso comercial
sin atribución) y `pistas.json`, la lista que las describe:

    [{"archivo": "pista.mp3", "titulo": "…", "autor": "…", "fuente": "Pixabay Music",
      "licencia": "Pixabay Content License", "atribucion": "…"}]

`archivo` es relativo a la carpeta (o absoluto); `atribucion` es opcional (el texto que la
licencia pide citar). `pistas.json` lo escribe una persona y aquí NUNCA se reescribe: las
veces que se usó cada pista van en `usos.json`, al lado ({archivo: n}). `publicar generar` sin
`--musica` elige la menos usada (a igualdad, la primera de la lista) y la anota sólo si el
paquete salió. Una biblioteca rota (JSON inválido, una pista sin licencia o que no está en
disco) es un error con todos sus problemas: un video con una pista sin licencia registrada no
se publica (riesgo de derechos de autor del plan). Sin `pistas.json`, o vacío: no hay pistas.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from apolo.publicacion.paquete import PublicacionError

PISTAS = "pistas.json"
USOS = "usos.json"
MUSICA_ENV = "APOLO_MUSICA_DIR"
OBLIGATORIAS = ("archivo", "titulo", "autor", "fuente", "licencia")
CLAVES = (*OBLIGATORIAS, "atribucion")


class MusicaError(PublicacionError):
    """`pistas.json` no se puede usar: el mensaje lista cada problema."""


def carpeta(entorno=None) -> Path:
    """La carpeta de la biblioteca: `APOLO_MUSICA_DIR` o `paths.home()/musica`."""
    from apolo import paths

    entorno = os.environ if entorno is None else entorno
    return Path(entorno.get(MUSICA_ENV) or paths.home() / "musica").expanduser()


def pistas(dir_) -> list[dict]:
    """Las pistas de `pistas.json` con su `ruta` absoluta; [] si no hay lista. Lanza
    `MusicaError` con todos los problemas de una lista rota."""
    dir_ = Path(dir_)
    ruta = dir_ / PISTAS
    if not ruta.is_file():
        return []
    try:  # utf-8-sig: el `Set-Content -Encoding utf8` de PowerShell 5.1 escribe con BOM
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise MusicaError(f"No pude leer {ruta}: {exc}") from None
    if not isinstance(datos, list):
        raise MusicaError(f"{ruta} debe ser una lista [{{archivo, titulo, autor, fuente, "
                          "licencia}}, …]")
    errores, out = [], []
    for i, p in enumerate(datos):
        donde = f"pistas[{i}]"
        if not isinstance(p, dict):
            errores.append(f"{donde}: debe ser un objeto {{archivo, titulo, …}}")
            continue
        errores += [f"{donde}: clave desconocida «{k}» (válidas: {', '.join(CLAVES)})"
                    for k in p if k not in CLAVES]
        faltan = [k for k in OBLIGATORIAS if not isinstance(p.get(k), str) or not p[k].strip()]
        if faltan:
            errores.append(f"{donde}: faltan {', '.join(faltan)} (la pista, su fuente y su "
                           "licencia quedan registradas)")
            continue
        if any("<" in str(v) or ">" in str(v) for v in p.values()):
            errores.append(f"{donde}: YouTube rechaza «<» y «>» en el crédito")
        archivo = (dir_ / p["archivo"]).resolve()
        if not archivo.is_file():
            errores.append(f"{donde}: no encuentro {archivo}")
            continue
        out.append({**{k: p.get(k, "") for k in CLAVES}, "ruta": archivo})
    if errores:
        raise MusicaError(f"{ruta} tiene {len(errores)} problema"
                          f"{'' if len(errores) == 1 else 's'}:\n  - " + "\n  - ".join(errores))
    return out


def usos(dir_) -> dict[str, int]:
    """{archivo: veces usada}; un `usos.json` roto o ausente cuenta como ninguno."""
    try:
        datos = json.loads((Path(dir_) / USOS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {str(k): v for k, v in datos.items() if isinstance(v, int) and not isinstance(v, bool)}


def elegir(dir_) -> dict | None:
    """La pista menos usada (a igualdad, la primera de la lista), con `usos`; None sin pistas."""
    lista = pistas(dir_)
    if not lista:
        return None
    cuenta = usos(dir_)
    i = min(range(len(lista)), key=lambda j: (cuenta.get(lista[j]["archivo"], 0), j))
    return {**lista[i], "usos": cuenta.get(lista[i]["archivo"], 0), "carpeta": Path(dir_)}


def anotar_uso(dir_, archivo: str) -> None:
    """Suma un uso a `archivo` en `usos.json` (temporal + `os.replace`)."""
    dir_ = Path(dir_)
    cuenta = usos(dir_)
    cuenta[archivo] = cuenta.get(archivo, 0) + 1
    tmp = dir_ / f".{USOS}.tmp"
    tmp.write_text(json.dumps(cuenta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, dir_ / USOS)


def para_la_ficha(pista: dict) -> dict:
    """La pista en la forma de `ficha.musica` (con la ruta local en `archivo`)."""
    return {**{k: pista.get(k, "") for k in CLAVES}, "archivo": str(pista["ruta"])}
