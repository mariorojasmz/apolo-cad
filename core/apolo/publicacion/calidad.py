"""La FICHA DE CALIDAD de una versión (plan puerta-de-publicacion, F1 · D8, D11): la puerta de
publicación de la API escrita en la carpeta de la versión, y las tres exigencias que la vuelven
obligatoria.

- `pedir`: `POST /api/puerta-publicacion` como job (simula gravedad y marcha: minutos) y espera;
- `escribir`: `calidad.json` (todos los ítems con estado y evidencia, la firma del modelo, la
  versión del registro y la de Apolo) y `calidad.md` (para una persona, `textos.calidad_md`);
- `exigir` (antes de `generar`): `calidad.json` aprobado y hecho sobre ESTE modelo (firma del
  `.apolo` que se va a publicar, `puerta_publicacion.firma_modelo`);
- `bloque_ficha`: lo que va a `ficha.json` (aprobado, conteos, versión del registro, firma y si se
  generó con `--forzar`);
- `exigir_subible` (en `tienda.subir`): sin `calidad.json` aprobado, con otra firma que la de la
  ficha o generado con `--forzar`, el paquete NUNCA sube.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from datetime import datetime
from pathlib import Path

from apolo.publicacion.paquete import FICHA_JSON, PublicacionError

CALIDAD_JSON, CALIDAD_MD = "calidad.json", "calidad.md"
ESPERA_S = 30.0          # cada consulta del job (long-poll de la API)
TOPE_S = 2 * 3600.0      # la puerta de una máquina grande tarda minutos, nunca horas


def pedir(api, *, eco=None, tope_s: float = TOPE_S) -> dict:
    """El resultado de la puerta de publicación del proyecto abierto en la API (`api` =
    `flujo._Api`). Va como job y espera con long-poll; `PublicacionError` si falla."""
    resp = api._pedir("POST", "/api/puerta-publicacion", "correr la puerta de publicación",
                      params={"async": "true"})
    if resp.status_code != 202:
        return resp.json()
    job = resp.json()["job_id"]
    fin = time.monotonic() + tope_s
    avisado = time.monotonic()
    while time.monotonic() < fin:
        j = api._pedir("GET", f"/api/jobs/{job}", "esperar la puerta de publicación",
                       params={"wait_s": ESPERA_S}).json()
        if j.get("estado") == "ok":
            return j["resultado"]
        if j.get("estado") == "error":
            raise PublicacionError(f"La puerta de publicación no corrió: {j.get('error')}")
        if eco and time.monotonic() - avisado > 60:
            avisado = time.monotonic()
            eco("  la puerta de publicación sigue corriendo (gravedad, marcha)…")
    raise PublicacionError(f"La puerta de publicación no terminó en {tope_s / 60:.0f} min (job {job})")


def escribir(carpeta, r: dict, *, titulo: str, proyecto: int | None = None) -> tuple[Path, Path]:
    """`calidad.json` y `calidad.md` en la carpeta de la versión (también si no aprobó: es la
    evidencia de por qué)."""
    from apolo.publicacion import textos
    from apolo.publicacion.paquete import _version_apolo

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    datos = {**r, "proyecto": proyecto, "generado": datetime.now().isoformat(timespec="seconds"),
             "generado_con": f"Apolo CAD {_version_apolo()}"}
    j, m = carpeta / CALIDAD_JSON, carpeta / CALIDAD_MD
    j.write_text(json.dumps(datos, indent=2, ensure_ascii=False, default=str) + "\n",
                 encoding="utf-8")
    m.write_text(textos.calidad_md(r, titulo), encoding="utf-8")
    return j, m


def leer(carpeta) -> dict | None:
    try:
        datos = json.loads((Path(carpeta) / CALIDAD_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) else None


def firma_de_apolo(data: bytes) -> str:
    """`firma_modelo` del `.apolo` (sin regenerarlo): la misma que la puerta calculó."""
    from apolo.services.puerta_publicacion import firma_modelo

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return firma_modelo(json.loads(zf.read("commands.json")),
                            json.loads(zf.read("manifest.json")))


def fallas(r: dict, n: int = 20) -> str:
    """Cada ítem que no pasó: familia, id, título, porqué y piezas (para el error de la fábrica)."""
    malos = [i for i in r.get("items", []) if i.get("estado") in ("FALLA", "SIN_EVALUAR")]
    lineas = [f"  - [{i.get('familia')}] {i['id']} ({i['estado']}): {i.get('titulo')} — "
              f"{i.get('detalle')}" + (f" · piezas: {', '.join((i.get('piezas') or [])[:8])}"
                                       if i.get("piezas") else "") for i in malos[:n]]
    if len(malos) > n:
        lineas.append(f"  … y {len(malos) - n} más (todas en {CALIDAD_MD})")
    return "\n".join(lineas) or "  - (sin detalle)"


def exigir(carpeta, data: bytes) -> dict:
    """Antes de generar: `calidad.json` aprobado y sobre este mismo modelo. `PublicacionError`
    con el porqué y cómo seguir."""
    carpeta = Path(carpeta)
    cal = leer(carpeta)
    if cal is None:
        raise PublicacionError(
            f"No hay {CALIDAD_JSON} en {carpeta}: la puerta de publicación no corrió. Córrela con "
            "`publicar fabrica` (paso «calidad») antes de generar el paquete.")
    if not cal.get("aprobado"):
        raise PublicacionError(f"La puerta de publicación NO aprobó esta versión "
                               f"({carpeta / CALIDAD_MD}):\n{fallas(cal)}")
    actual = firma_de_apolo(data)
    if cal.get("firma") != actual:
        raise PublicacionError(
            f"El modelo cambió desde la puerta de publicación (firma {cal.get('firma')} → "
            f"{actual}): lo aprobado no es lo que se publicaría. Vuelve a correr la puerta "
            "(`publicar fabrica --desde calidad`).")
    return cal


def bloque_ficha(cal: dict | None, forzado: bool) -> dict:
    """El bloque `calidad` de `ficha.json` (D8)."""
    cal = cal or {}
    return {"aprobado": bool(cal.get("aprobado")) and not forzado, "forzado": forzado,
            "conteos": cal.get("conteos") or {}, "version_registro": cal.get("version_registro"),
            "firma": cal.get("firma")}


def exigir_subible(carpeta) -> None:
    """D8/D11: la tienda sólo recibe un paquete con `calidad.json` aprobado, generado sin
    `--forzar` y sobre el mismo modelo que aprobó la puerta."""
    carpeta = Path(carpeta)
    cal = leer(carpeta)
    try:
        ficha = json.loads((carpeta / FICHA_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ficha = {}
    bloque = ficha.get("calidad") if isinstance(ficha, dict) else None
    problemas = []
    if cal is None:
        problemas.append(f"no tiene {CALIDAD_JSON} (la puerta de publicación no corrió)")
    elif not cal.get("aprobado"):
        problemas.append(f"la puerta de publicación no la aprobó:\n{fallas(cal)}")
    if not isinstance(bloque, dict):
        problemas.append(f"su {FICHA_JSON} no trae el bloque «calidad» (generada antes de la puerta)")
    else:
        if bloque.get("forzado"):
            problemas.append("se generó con --forzar (sólo para ensayos)")
        elif not bloque.get("aprobado"):
            problemas.append(f"su {FICHA_JSON} dice que la calidad no está aprobada")
        if cal is not None and bloque.get("firma") != cal.get("firma"):
            problemas.append(f"la firma de {FICHA_JSON} ({bloque.get('firma')}) no es la de "
                             f"{CALIDAD_JSON} ({cal.get('firma')})")
    if problemas:
        raise PublicacionError(
            f"No subo {carpeta} a la tienda: " + "; ".join(problemas) + ".\nNinguna máquina llega "
            "a la tienda sin pasar la puerta de publicación (plan puerta-de-publicacion, D8): "
            "`publicar fabrica` la corre y genera el paquete.")
