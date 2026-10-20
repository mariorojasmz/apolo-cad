"""El paquete de una publicación: puerta de calidad, niveles, zips, hashes y la carpeta
versionada (plan publicacion-tienda, D9–D14).

Carpeta: `publicaciones_dir()/<slug>/<version>/`. `publicar guion` la crea con `guion.json` y
`ficha.yaml`; `publicar generar` arma todo en `.generando/` y, sólo si todo salió bien, lo
mueve a su lugar y escribe `ficha.json` el ÚLTIMO: `ficha.json` presente = versión publicada,
que nunca se pisa (D14). Un `generar` que falló deja la carpeta como estaba.

Niveles (D10): `gratis/` (renders, plano de conjunto GA, BOM resumida, STEP) y `completo/`
(todos los entregables y el `.apolo` saneado), cada uno con LEEME, LICENCIA y AVISO y su zip
`<slug>-<version>-<nivel>.zip`; los DOS llevan la vista 3D (`vista-3d.glb`, `vista-3d.html` y
la miniatura, su póster: plan vista-3d-tienda F3). Lo que el destino no pide no entra: el costeo
y la cotización nunca (D11; los declara `entregables.py`). `ficha.json` (D9) lleva lo público de
la ficha, la validación en frases, las cifras, los capítulos, la vista 3D y cada archivo con su
sha256, también los de adentro de los zips; `url_video` queda vacía hasta subir el video.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from apolo.publicacion import textos
from apolo.publicacion.entregables import COMPLETO, GRATIS, NIVELES, NUNCA_PUBLICAR

GUION, FICHA_YAML, FICHA_JSON = "guion.json", "ficha.yaml", "ficha.json"
TEMPORAL = ".generando"
FORMATO = 1
VERDE = "VERDE"
TEXTOS_FIJOS = (("LEEME.md", "Este archivo"), ("LICENCIA.txt", "Licencia de este paquete"),
                ("AVISO.txt", "Aviso de responsabilidad: léelo antes de fabricar"))


class PublicacionError(RuntimeError):
    """La publicación no se puede hacer; el mensaje dice por qué y qué hacer."""


class PuertaRoja(PublicacionError):
    """La puerta de entrega no está en verde y no se forzó (D13)."""


# ------------------------------------------------------------------ carpeta versionada
def carpeta_version(raiz, slug: str, version: str) -> Path:
    return Path(raiz) / slug / version


def publicada(carpeta: Path) -> bool:
    return (Path(carpeta) / FICHA_JSON).exists()


def versiones(raiz, slug: str) -> list[str]:
    base = Path(raiz) / slug
    if not base.is_dir():
        return []
    return sorted((p.name for p in base.iterdir() if p.is_dir()), key=_clave_version)


def _clave_version(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (10**9, v)


def siguiente(version: str) -> str:
    """La versión de parche que sigue («1.0.3» → «1.0.4»)."""
    partes = version.split(".")
    try:
        partes[-1] = str(int(partes[-1]) + 1)
    except ValueError:
        return version + ".1"
    return ".".join(partes)


def exigir_no_publicada(carpeta: Path) -> None:
    carpeta = Path(carpeta)
    if publicada(carpeta):
        raise PublicacionError(
            f"La versión {carpeta.name} de «{carpeta.parent.name}» ya está publicada en {carpeta}: "
            "una versión publicada no se pisa. Arma otra con `publicar guion --version "
            f"{siguiente(carpeta.name)}`.")


# ------------------------------------------------------------------ puerta de calidad (D13)
def calidad(reporte: dict, *, forzar: bool) -> dict:
    """Lo que la publicación dice de la puerta de entrega (`POST /api/delivery-check`). Sin
    verde y sin `forzar`, `PuertaRoja`; forzada, queda «con observaciones»."""
    veredicto = reporte.get("veredicto")
    observaciones = [f"{x.get('regla')}: {x.get('detalle')}"
                     for x in (*reporte.get("bloqueantes", []), *reporte.get("avisos", []))]
    if veredicto != VERDE and not forzar:
        lista = "\n".join(f"  - {o}" for o in observaciones) or "  - (sin detalle)"
        raise PuertaRoja(
            f"La puerta de entrega está en {veredicto}: no se publica (D13).\n{lista}\n"
            "Corrige el modelo y vuelve a correr `publicar generar`, o usa --forzar para "
            f"publicarlo «{textos.CON_OBSERVACIONES}» (queda escrito en la ficha y en el LEEME).")
    return {
        "veredicto": veredicto,
        "con_observaciones": veredicto != VERDE,
        "chequeos_ok": list((reporte.get("resumen") or {}).get("chequeos_ok", [])),
        "no_aplica": list(reporte.get("no_aplica", [])),
        "observaciones": observaciones if veredicto != VERDE else [],
    }


# ------------------------------------------------------------------ niveles y zips
def armar(staging: Path, entregables_dir: Path, entregables: list, registros: list[dict], *,
          ficha: dict, cifras: list[dict], calidad_: dict, variables: dict,
          apolo: bytes, extras: list[tuple[Path, str]] = ()) -> dict[str, Path]:
    """Llena `staging/gratis` y `staging/completo` y escribe sus zips. Devuelve {nivel: zip}.
    `extras`: (archivo, qué es) que van a la raíz de los DOS niveles (la vista 3D: el GLB, su
    HTML y el póster que éste pide al lado, plan vista-3d-tienda F3)."""
    ok = {r["file"] for r in registros if r["status"] == "ok"}
    nombre_apolo = f"{ficha['slug']}.apolo"
    zips = {}
    for nivel in NIVELES:
        destino = staging / nivel
        archivos: list[tuple[str, str]] = []
        for e in entregables:
            if nivel in e.destinos and e.archivo in ok:
                ruta = destino / e.archivo
                ruta.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(entregables_dir / e.archivo, ruta)
                archivos.append((e.archivo, e.etiqueta[:1].upper() + e.etiqueta[1:]))
        for origen, descripcion in extras:
            destino.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origen, destino / Path(origen).name)
            archivos.append((Path(origen).name, descripcion))
        if nivel == COMPLETO:
            (destino / nombre_apolo).write_bytes(apolo)
            archivos.append((nombre_apolo, "Modelo paramétrico de Apolo CAD (ver abajo cómo abrirlo)"))
        archivos += list(TEXTOS_FIJOS)
        (destino / "LEEME.md").write_text(textos.leeme(
            ficha, nivel, cifras=cifras, calidad=calidad_, archivos=archivos,
            variables=variables, apolo=nombre_apolo if nivel == COMPLETO else None),
            encoding="utf-8")
        (destino / "LICENCIA.txt").write_text(textos.licencia(ficha["licencias"][nivel], ficha),
                                              encoding="utf-8")
        (destino / "AVISO.txt").write_text(textos.aviso(), encoding="utf-8")
        zips[nivel] = staging / f"{ficha['slug']}-{ficha['version']}-{nivel}.zip"
        comprimir(destino, zips[nivel])
    return zips


def comprimir(carpeta: Path, ruta_zip: Path) -> Path:
    """Zip de `carpeta` con sus archivos bajo una carpeta raíz del nombre del zip (al
    descomprimir no se riegan sueltos), en orden y con una sola fecha."""
    raiz = ruta_zip.stem
    fecha = datetime.now().timetuple()[:6]
    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for ruta in sorted(p for p in carpeta.rglob("*") if p.is_file()):
            prohibido = next((n for n in NUNCA_PUBLICAR if ruta.name == n), None)
            if prohibido:  # defensa en profundidad: entregables.py nunca los pide
                raise PublicacionError(f"{prohibido} no se publica nunca (D11)")
            info = zipfile.ZipInfo(f"{raiz}/{ruta.relative_to(carpeta).as_posix()}", fecha)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, ruta.read_bytes())
    return ruta_zip


# ------------------------------------------------------------------ ficha.json (D9)
def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def _info(ruta: Path, nombre: str, **extra) -> dict:
    return {"nombre": nombre, "bytes": ruta.stat().st_size, "sha256": sha256(ruta), **extra}


def ficha_json(ficha: dict, *, staging: Path, zips: dict[str, Path], video: Path,
               miniatura: Path, duracion_s: float, capitulos: list[tuple[int, str]],
               musica: dict | None, calidad_: dict, cifras: list[dict],
               vista_3d: dict | None = None) -> dict:
    """Lo público de la publicación, con cada archivo y su sha256 (también los de los zips).
    `vista_3d` (plan vista-3d-tienda F3): {glb, html} (rutas), `triangulos` y `etiquetas`; el
    póster es la miniatura. Sin ella, la ficha no tiene la sección."""
    archivos = []
    for nivel, ruta in zips.items():
        carpeta = staging / nivel
        contenido = [_info(p, p.relative_to(carpeta).as_posix())
                     for p in sorted(carpeta.rglob("*")) if p.is_file()]
        archivos.append(_info(ruta, ruta.name, nivel=nivel, contenido=contenido))
    archivos.append(_info(video, video.name, nivel=GRATIS))
    archivos.append(_info(miniatura, miniatura.name, nivel=GRATIS))
    extra = {}
    if vista_3d:
        glb, html = Path(vista_3d["glb"]), Path(vista_3d["html"])
        archivos += [_info(glb, glb.name, nivel=GRATIS), _info(html, html.name, nivel=GRATIS)]
        extra["vista_3d"] = {
            "modelo": glb.name, "html": html.name, "poster": miniatura.name,
            "bytes": glb.stat().st_size, "triangulos": vista_3d["triangulos"],
            "etiquetas": [{"grupo": e["grupo"], "cifra": e["cifra"]}
                          for e in vista_3d["etiquetas"]]}
    publica = {k: ficha[k] for k in ("titulo", "slug", "version", "descripcion", "nivel",
                                     "precio_usd", "licencias", "etiquetas", "url_tienda")}
    return {
        "formato": FORMATO,
        **publica,
        "url_video": "",
        "estado": textos.CON_OBSERVACIONES if calidad_["con_observaciones"] else "verificado",
        "validacion": {"veredicto": calidad_["veredicto"],
                       "resumen": textos.frases_validacion(calidad_),
                       "observaciones": calidad_["observaciones"]},
        "cifras": cifras,
        "video": {"archivo": video.name, "duracion_s": round(duracion_s, 3),
                  "capitulos": [{"inicio_s": s, "titulo": t} for s, t in capitulos],
                  "musica": musica},
        "miniatura": miniatura.name,
        **extra,
        "archivos": archivos,
        "generado": datetime.now().isoformat(timespec="seconds"),
        "generado_con": f"Apolo CAD {_version_apolo()}",
    }


def _version_apolo() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("apolo-cad")
    except PackageNotFoundError:
        import apolo

        return apolo.__version__


# ------------------------------------------------------------------ cierre
def instalar(staging: Path, carpeta: Path, ficha_publica: dict, extra: dict) -> None:
    """Mueve lo armado en `staging` a la carpeta de la versión y escribe `ficha.json` el
    ÚLTIMO (lo que marca la versión como publicada). `extra` va a `generacion.json`, el
    registro interno (tiempos, entregables, saneo): no se publica."""
    exigir_no_publicada(carpeta)
    for nombre in ("gratis", "completo"):
        if (carpeta / nombre).exists():  # de un intento anterior que no llegó a publicarse
            shutil.rmtree(carpeta / nombre)
    for item in staging.iterdir():
        if item.name == "entregables":
            continue
        os.replace(item, carpeta / item.name)
    shutil.rmtree(staging, ignore_errors=True)
    (carpeta / "generacion.json").write_text(
        json.dumps(extra, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (carpeta / FICHA_JSON).write_text(json.dumps(ficha_publica, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
