"""El `.apolo` que se publica, saneado (plan publicacion-tienda, D11 y D12).

Opera sobre el ZIP, sin regenerar: el log no cambia (salvo lo que se dice abajo) y el archivo
se abre y regenera igual en Apolo. Inventario del formato (`Document.to_apolo_bytes`):
`manifest.json`, `commands.json` y `attachments/<digest>.bin`. Se quita:
  - `agent_notes`: la memoria del agente, notas internas de trabajo (D12);
  - en `requirements`, `tipo_cambio` y `moneda`: precios internos y locales (D11);
  - en cada `insert_project`, `project_id`: apunta a la base de proyectos de quien publica y,
    con el snapshot embebido, sobra (editarlo a vacío re-materializaría OTRO proyecto);
  - los snapshots embebidos (`insert_project`) se sanean igual, recursivamente: también traen
    sus `agent_notes`. Su digest cambia, así que se reescribe el `attachment` que los nombra.
Se renombra el documento con el título público. Lo demás se conserva: es el diseño (comandos,
variables, variantes, colores, materiales, movimiento, requisitos técnicos, FEA, cadenas de
cotas y los escenarios de prueba de V8.3 con su último veredicto: la FAT virtual). Los adjuntos que NO son un `.apolo` (STEP importados) se conservan pero se informan:
pueden ser modelos de un proveedor que no se pueden redistribuir, y eso lo decide una persona.

Lista BLANCA: una clave del manifest o una entrada del ZIP que este módulo no conoce se quita
y se informa (`tests/test_publicacion_paquete.py` exige que la lista cubra el formato actual:
una clave nueva obliga a decidir si es pública).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

#: Claves del manifest que se publican (todas las de `to_apolo_bytes` menos `agent_notes`).
MANIFEST_PUBLICO = (
    "app", "version", "name", "units", "hidden", "seq", "configurations",
    "configurations_format", "colors", "materials", "sketch_guides", "vertical", "motion",
    "requirements", "fea", "stackups", "escenarios",
)
#: Requisitos que son precios, no ingeniería (D11).
REQUISITOS_PRIVADOS = ("tipo_cambio", "moneda")
_PROFUNDIDAD_MAX = 4  # insert_project anida hasta 3 niveles (doc/subproject.py)


class SaneoError(ValueError):
    """El `.apolo` no se puede sanear (ZIP o JSON roto)."""


def _es_apolo(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            nombres = set(zf.namelist())
    except zipfile.BadZipFile:
        return False
    return {"manifest.json", "commands.json"} <= nombres


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]  # = Document.add_attachment


def sanear_apolo(data: bytes, *, nombre: str | None = None) -> tuple[bytes, dict]:
    """(bytes saneados, informe). El informe dice qué se quitó (`quitado`), qué adjuntos
    externos quedan para revisar (`adjuntos`) y qué se ignoró por desconocido."""
    informe = {"quitado": [], "adjuntos": [], "desconocido": []}
    saneado = _sanear(data, nombre, informe, 0, "")
    return saneado, informe


def _sanear(data: bytes, nombre: str | None, informe: dict, nivel: int, donde: str) -> bytes:
    if nivel > _PROFUNDIDAD_MAX:
        raise SaneoError("Demasiados proyectos anidados en el .apolo")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            entradas = {n: zf.read(n) for n in zf.namelist()}
        manifest = json.loads(entradas["manifest.json"])
        comandos = json.loads(entradas["commands.json"])
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise SaneoError(f"El .apolo{donde} no se puede leer: {exc}") from exc

    adjuntos = {n.removeprefix("attachments/").removesuffix(".bin"): b
                for n, b in entradas.items() if n.startswith("attachments/") and n.endswith(".bin")}
    for n in entradas:
        if n not in ("manifest.json", "commands.json") and not (
                n.startswith("attachments/") and n.endswith(".bin")):
            informe["desconocido"].append(f"entrada «{n}»{donde}")

    # los snapshots embebidos primero: su digest nuevo se reescribe en el log
    renombres: dict[str, str] = {}
    for digest, blob in list(adjuntos.items()):
        if _es_apolo(blob):
            nuevo = _sanear(blob, None, informe, nivel + 1, f" embebido {digest}")
            adjuntos.pop(digest)
            adjuntos[_digest(nuevo)] = nuevo
            renombres[digest] = _digest(nuevo)
        else:
            informe["adjuntos"].append({"digest": digest, "bytes": len(blob),
                                        "usado_por": _usos(comandos, digest)})
    _limpiar_comandos(comandos, renombres, informe, donde)
    publico = _limpiar_manifest(manifest, informe, donde)
    if nombre:
        publico["name"] = nombre

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(publico, indent=2))
        zf.writestr("commands.json", json.dumps(comandos, indent=2))
        for digest, blob in adjuntos.items():
            zf.writestr(f"attachments/{digest}.bin", blob)
    return buf.getvalue()


def _usos(comandos: list[dict], digest: str) -> list[str]:
    return [f"{c.get('id')} ({c.get('type')})" for c in comandos
            if (c.get("params") or {}).get("attachment") == digest]


def _limpiar_comandos(comandos: list[dict], renombres: dict, informe: dict, donde: str) -> None:
    for c in comandos:
        params = c.get("params") or {}
        viejo = params.get("attachment")
        if viejo in renombres:
            params["attachment"] = renombres[viejo]
        if c.get("type") == "insert_project" and params.get("project_id") is not None:
            if params.get("attachment"):
                params.pop("project_id")
                informe["quitado"].append(f"project_id del insert_project {c.get('id')}{donde}")
            else:  # sin snapshot el comando no regeneraría: no se publica a medias
                raise SaneoError(f"El insert_project {c.get('id')}{donde} no tiene el proyecto "
                                 "embebido: ábrelo en Apolo para que lo materialice")


def _limpiar_manifest(manifest: dict, informe: dict, donde: str) -> dict:
    notas = manifest.get("agent_notes") or []
    if notas:
        informe["quitado"].append(f"{len(notas)} nota{'' if len(notas) == 1 else 's'} del "
                                  f"agente{donde}")
    for k in manifest:
        if k not in MANIFEST_PUBLICO and k != "agent_notes":
            informe["desconocido"].append(f"clave «{k}» del manifest{donde}")
    publico = {k: manifest[k] for k in MANIFEST_PUBLICO if k in manifest}
    requisitos = dict(publico.get("requirements") or {})
    for k in REQUISITOS_PRIVADOS:
        if k in requisitos:
            requisitos.pop(k)
            informe["quitado"].append(f"requisito {k}{donde}")
    if "requirements" in publico:
        publico["requirements"] = requisitos
    return publico
