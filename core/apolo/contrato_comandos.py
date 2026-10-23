"""Los dos trinquetes del contrato de los comandos con los logs guardados, como funciones puras
sobre CUALQUIER registro: los usan `tests/test_contrato_comandos.py` del núcleo (sobre `REGISTRY`)
y la suite de una extensión (sobre sus `CommandSpec`), con los MISMOS criterios. Viajan en la wheel
(plan nucleo-abierto-extensiones-privadas, F1c); cada suite guarda su `CAMPOS` y su `VERSIONES`.

- **Campos (D12 de estado-regen-y-params-estrictos):** un `.apolo` guarda los params tal cual y el
  replay IGNORA la clave que el modelo ya no declara. `problemas_de_campos` dice qué ruta
  (`field_paths`: `position.x`, `flaps[].child.altura`) desapareció sin upcaster y cuál apareció
  sin declarar.
- **Versiones (D11):** la caché de geometría se indexa por params, no por código.
  `problemas_de_version` compara `{tipo: (version, huella del executor)}` con el registro: código
  que cambió sin decidir su versión, versión que bajó o que subió sin declarar.

`literal_campos`/`literal_versiones` imprimen los literales actuales para pegar.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Mapping

from apolo.commands.strict import field_paths

__all__ = ["huella", "literal_campos", "literal_versiones", "problemas_de_campos",
           "problemas_de_version", "rutas"]


def rutas(registro: Mapping) -> dict[str, list[str]]:
    """`{tipo: [rutas de sus params]}` de cada comando del registro, ordenado por tipo."""
    return {t: field_paths(spec.model) for t, spec in sorted(registro.items())}


def huella(fn) -> str:
    """sha1 (16 hex) del código fuente de `fn`, con los saltos de línea normalizados: la
    huella no depende de cómo el checkout guarde los finales de línea."""
    fuente = inspect.getsource(fn).replace("\r\n", "\n")
    return hashlib.sha1(fuente.encode("utf-8")).hexdigest()[:16]


def problemas_de_campos(registro: Mapping, declarados: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """`(perdidos, nuevos)` contra `declarados` (`{tipo: "ruta ruta …"}`): lo que desapareció
    (o el comando que ya no existe) y lo que apareció sin declarar (o el comando nuevo)."""
    actuales = rutas(registro)
    perdidos: list[str] = []
    for tipo, decl in declarados.items():
        if tipo not in actuales:
            perdidos.append(f"  {tipo}: el comando ya no existe (sus logs no tienen executor)")
            continue
        faltan = [r for r in decl.split() if r not in set(actuales[tipo])]
        if faltan:
            perdidos.append(f"  {tipo}: {', '.join(faltan)}")
    nuevos: list[str] = []
    for tipo, rs in actuales.items():
        if tipo not in declarados:
            nuevos.append(f"  {tipo}: comando nuevo")
            continue
        sobran = [r for r in rs if r not in set(declarados[tipo].split())]
        if sobran:
            nuevos.append(f"  {tipo}: {', '.join(sobran)}")
    return perdidos, nuevos


def problemas_de_version(registro: Mapping, declaradas: Mapping[str, tuple[int, str]]) -> list[str]:
    out = []
    for tipo, spec in sorted(registro.items()):
        if tipo not in declaradas:
            out.append(f"  {tipo}: comando sin declarar en VERSIONES")
            continue
        version, declarada = declaradas[tipo]
        actual = huella(spec.executor)
        if spec.version < version:
            out.append(f"  {tipo}: la versión BAJÓ de {version} a {spec.version} (nunca baja: "
                       "volvería a casar con las firmas de cachés de una versión vieja)")
        elif spec.version > version:
            out.append(f'  {tipo}: subiste a v{spec.version}: declara ({spec.version}, "{actual}")')
        elif actual != declarada:
            out.append(f"  {tipo}: el código de su executor cambió y su versión no (v{version})")
    out += [f"  {t}: ya no existe en el registro" for t in declaradas if t not in registro]
    return out


def literal_versiones(registro: Mapping) -> str:
    out = ["VERSIONES: dict[str, tuple[int, str]] = {"]
    for tipo, spec in sorted(registro.items()):
        out.append(f'    "{tipo}": ({spec.version}, "{huella(spec.executor)}"),')
    return "\n".join(out + ["}"])


def _envuelve(rs: list[str], ancho: int = 88) -> list[str]:
    lineas, actual = [], ""
    for r in rs:
        if actual and len(actual) + 1 + len(r) > ancho:
            lineas.append(actual + " ")
            actual = r
        else:
            actual = f"{actual} {r}" if actual else r
    return lineas + [actual]


def literal_campos(registro: Mapping) -> str:
    out = ["CAMPOS: dict[str, str] = {"]
    for tipo, rs in rutas(registro).items():
        partes = _envuelve(rs)
        if len(partes) == 1 and len(tipo) + len(partes[0]) < 86:
            out.append(f'    "{tipo}": "{partes[0]}",')
        else:
            out.append(f'    "{tipo}": (')
            out += [f'        "{p}"' for p in partes]
            out.append("    ),")
    return "\n".join(out + ["}"])
