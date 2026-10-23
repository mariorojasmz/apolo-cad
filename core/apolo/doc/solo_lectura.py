"""Proyecto que necesita una extensión AUSENTE → SÓLO LECTURA (D4 del plan
nucleo-abierto-extensiones-privadas, F1b).

Todo lo que nombra una extensión lleva su prefijo (F1a): comandos «x.algo» y refs de su catálogo
«x.algo». Un log que nombra un prefijo que esta instalación no tiene se abre para VERLO (lo que
regenera; lo de la extensión queda en `regen_suppressed`) y nunca para editarlo: editar a medias
perdería comandos (el `remove_commands` de los suprimidos dejaba un log que regeneraba estricto
y el autosave lo persistía sin ellos, medido en la F0).

- `detectar(commands, attachments)` (puro): los prefijos ausentes del log y de los logs de los
  adjuntos de `insert_project` (recursivo hasta `subproject.MAX_DEPTH`, con la caché por digest
  de `subproject._log_del_snapshot`) → `{"extensiones": [prefijos], "aviso": texto}` o None. Un
  comando desconocido SIN prefijo (deriva vieja de schema) no cuenta: sigue el camino tolerante
  de siempre (se suprime y el resto se edita).
- `marcar(doc)`: lo deja en `doc.solo_lectura`. Lo llama `Document.from_apolo_bytes` en TODA
  carga que regenera (arranque, open, restore, upload, duplicate); la marca obliga a la carga
  tolerante: un proyecto así siempre abre.
- `bloquear(doc)`: `DocumentError` con el aviso; lo llama `Document._snapshot()`, el paso previo
  de toda mutación del log y de deshacer/rehacer (para quien use `Document` sin la API). La API
  responde antes un 409 con el mismo texto (`api/guardia_documento.solo_lectura`) y el autosave
  no escribe un documento marcado.
"""

from __future__ import annotations

import re

from apolo.doc.errors import DocumentError

#: «prefijo.resto»: el prefijo de una extensión (como `extensiones._PREFIJO`) y un punto. Las
#: refs del núcleo van en MAYÚSCULAS («REMACHE-3.2») y sus comandos no llevan punto.
_CON_PREFIJO = re.compile(r"^([a-z][a-z0-9_]{1,23})\.\S+$")


def _enumerar(nombres: list[str]) -> str:
    """«a», «a» y «b», «a», «b» y «c» (igual que `ui/src/state/soloLectura.ts`)."""
    n = [f"«{x}»" for x in nombres]
    return f"{', '.join(n[:-1])} y {n[-1]}" if len(n) > 1 else n[0]


def aviso(extensiones: list[str], sujeto: str = "Este proyecto",
          cierre: str = "puedes verlo, no editarlo") -> str:
    """El texto de D4 (tuteo neutro), el mismo que arma la UI."""
    if len(extensiones) == 1:
        return (f"{sujeto} usa la extensión {_enumerar(extensiones)}, que no está instalada: "
                f"{cierre}.")
    return (f"{sujeto} usa las extensiones {_enumerar(extensiones)}, que no están instaladas: "
            f"{cierre}.")


def _prefijo(valor) -> str | None:
    m = _CON_PREFIJO.match(valor) if isinstance(valor, str) else None
    return m.group(1) if m else None


def faltantes(commands: list[dict], attachments: dict | None = None, _nivel: int = 0) -> set[str]:
    """Los prefijos de extensión que el log nombra y esta instalación no tiene: tipos de comando
    sin spec en `REGISTRY` y refs de `insert_component` que no están en el catálogo; también los
    de los proyectos insertados (sus adjuntos), hasta `MAX_DEPTH` niveles."""
    from apolo.commands.registry import REGISTRY
    from apolo.doc import subproject
    from apolo.library.catalog import CATALOG

    out: set[str] = set()
    for cmd in commands:
        tipo, params = cmd.get("type"), cmd.get("params") or {}
        if (p := _prefijo(tipo)) and tipo not in REGISTRY:
            out.add(p)
        elif tipo == "insert_component" and (p := _prefijo(params.get("component"))) \
                and params["component"] not in CATALOG:
            out.add(p)
        elif tipo == "insert_project" and _nivel < subproject.MAX_DEPTH:
            digest = params.get("attachment")
            data = (attachments or {}).get(digest) if isinstance(digest, str) else None
            if data is None:
                continue
            try:
                log, adjuntos = subproject._log_del_snapshot(digest, data)
            except DocumentError:
                continue  # un snapshot ilegible ya lo reporta el regenerate (suprimido)
            out |= faltantes(log, adjuntos, _nivel + 1)
    return out


def detectar(commands: list[dict], attachments: dict | None = None) -> dict | None:
    """`{"extensiones": [prefijos ordenados], "aviso": texto de D4}` o None (editable)."""
    extensiones = sorted(faltantes(commands, attachments))
    return {"extensiones": extensiones, "aviso": aviso(extensiones)} if extensiones else None


def marcar(doc) -> bool:
    """Marca `doc` al cargarlo; True si quedó en sólo lectura."""
    doc.solo_lectura = detectar(doc.commands, doc.attachments)
    return doc.solo_lectura is not None


def bloquear(doc) -> None:
    """`DocumentError` con el aviso si `doc` está en sólo lectura (nada se toca)."""
    marca = getattr(doc, "solo_lectura", None)
    if marca:
        raise DocumentError(marca["aviso"])
