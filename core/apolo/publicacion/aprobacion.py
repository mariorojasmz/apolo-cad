"""Revisión de taller, cuadros del video y familia nueva en la carpeta de la versión (plan
puerta-de-publicacion, F4 · D6, D7, D10, D11). Los veredictos los ponen agentes (no
deterministas) y Mario; aquí sólo se EXIGEN, sobre la misma firma y el mismo video que se
publican. Las reglas son puras, en `revision_check.py`; esto lee y escribe los archivos:

- `revision.json` (lo deja quien lanza al revisor de taller, formato en
  `docs/revisor-de-taller.md`) → `exigir_revision`, paso «revision» de la fábrica;
- `cuadros/` + `cuadros.json`: `preparar_cuadros` saca tres cuadros del video (armado, marcha,
  cierre) con ffmpeg y deja `cuadros.json` sin veredicto; un agente con visión los mira y pone
  `veredicto` («OK» | «RECHAZADO») y `revisor` → `exigir_cuadros`, paso «cuadros»;
- `familias.json` del repo privado (`paths.fabrica_dir()`, `APOLO_FABRICA`) → `exigir_familia`,
  paso «familia»; `aprobar` registra la aprobación de Mario (`publicar aprobar`).

`exigir_publicable` junta las tres para `tienda.subir`: nada sube sin ellas. Ninguna tiene
`--forzar` (D11).
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from apolo.publicacion import revision_check as rc
from apolo.publicacion.paquete import FICHA_JSON, FICHA_YAML, GUION, PublicacionError

REVISION_JSON, CUADROS_JSON, CUADROS_DIR = "revision.json", "cuadros.json", "cuadros"
FAMILIAS_JSON = "familias.json"
COMO_REVISAR = ("Lanza el revisor de taller (prompt en docs/revisor-de-taller.md; la orquestación, "
                "en el repo privado apolo-fabrica) sobre el proyecto con ESTA firma y guarda "
                "revision.json en la carpeta con el formato de ese documento.")
COMO_CUADROS = ("Que un agente con visión mire los cuadros de {dir}/ y ponga en cada uno de "
                "cuadros.json «veredicto» (OK | RECHAZADO) y una «nota», y «revisor» arriba.")


class AprobacionError(PublicacionError):
    """Falta un veredicto o no vale para lo que se publica; el mensaje dice cuál y cómo seguir."""


def _leer(ruta: Path) -> tuple[object, str | None]:
    """(datos, error): sin archivo, (None, None); con JSON roto, (None, el porqué)."""
    if not ruta.is_file():
        return None, None
    try:
        return json.loads(ruta.read_text(encoding="utf-8-sig")), None
    except (OSError, ValueError) as exc:
        return None, f"{ruta.name} no es JSON válido: {exc}"


def _escribir(ruta: Path, datos: dict) -> None:
    tmp = ruta.with_name(f".{ruta.name}.tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, ruta)


def _lista(problemas: list[str]) -> str:
    return "\n".join(f"  - {p}" for p in problemas)


def firma(carpeta) -> str | None:
    """La firma del modelo que aprobó la puerta (`calidad.json`): la que se publica."""
    from apolo.publicacion import calidad

    return (calidad.leer(carpeta) or {}).get("firma")


# ------------------------------------------------------------------ revisión de taller (D6)
def problemas_revision(carpeta) -> list[str]:
    datos, error = _leer(Path(carpeta) / REVISION_JSON)
    return [error] if error else rc.problemas_revision(datos, firma(carpeta))


def exigir_revision(carpeta) -> dict:
    carpeta = Path(carpeta)
    problemas = problemas_revision(carpeta)
    if problemas:
        raise AprobacionError(
            f"La revisión de taller no deja publicar {carpeta.name} (firma {firma(carpeta)}):\n"
            f"{_lista(problemas)}\n{COMO_REVISAR} Después vuelve a correr `publicar fabrica`: "
            "retoma desde «revision».")
    revs = _leer(carpeta / REVISION_JSON)[0]["revisiones"]
    return {"revisiones": len(revs), "vigente": revs[-1]["id"], "revisor": revs[-1]["revisor"]}


# ------------------------------------------------------------------ cuadros del video (D7)
def video(carpeta) -> Path:
    """El video del paquete: el de `ficha.json` o `video.mp4`."""
    carpeta = Path(carpeta)
    ficha = _leer(carpeta / FICHA_JSON)[0]
    nombre = ((ficha or {}).get("video") or {}).get("archivo") if isinstance(ficha, dict) else None
    return carpeta / (nombre or "video.mp4")


def sha_video(carpeta) -> str | None:
    from apolo.publicacion.tienda import sha256

    v = video(carpeta)
    return sha256(v) if v.is_file() else None


def momentos(guion: dict | None, duracion: float) -> list[tuple[str, float, str]]:
    """(momento, segundo, parte del video) de los tres cuadros: el medio de la última etapa
    (armado), de la marcha (o de la órbita si el video no la trae) y del cierre. Sin guion,
    proporciones del video."""
    tramos = []
    if guion:
        from apolo.services.linea_tiempo import tramos as _tramos

        try:
            fps = guion["video"]["fps"]
            tramos = [(t.parte, (t.inicio + t.fin) / 2 / fps) for t in _tramos(guion)]
        except (KeyError, TypeError, ZeroDivisionError):
            tramos = []
    medio = {}
    for parte, s in tramos:
        medio[parte] = s  # la última de cada parte (la última etapa)
    tope = max(duracion - 0.1, 0.0)
    elegidos = [("armado", medio.get("etapa"), "etapa"),
                ("marcha", medio.get("marcha", medio.get("orbita")),
                 "marcha" if "marcha" in medio else "orbita"),
                ("cierre", medio.get("cierre"), "cierre")]
    respaldo = {"armado": 0.4, "marcha": 0.75, "cierre": 0.97}
    return [(m, round(min(s if s is not None else respaldo[m] * duracion, tope), 2),
             p if s is not None else "proporcion") for m, s, p in elegidos]


def sacar_cuadros(ruta_video: Path, destino: Path, puntos) -> list[dict]:
    """Un PNG por momento con ffmpeg (`destino/<momento>.png`)."""
    from apolo.media.codificar import buscar_ffmpeg

    ffmpeg = buscar_ffmpeg()
    destino.mkdir(parents=True, exist_ok=True)
    out = []
    for momento, segundo, parte in puntos:
        png = destino / f"{momento}.png"
        res = subprocess.run([ffmpeg, "-v", "error", "-ss", f"{segundo:.2f}", "-i", str(ruta_video),
                              "-frames:v", "1", "-y", str(png)], capture_output=True, text=True,
                             timeout=120)
        if res.returncode != 0 or not png.is_file():
            raise PublicacionError(f"ffmpeg no sacó el cuadro «{momento}» ({segundo} s) de "
                                   f"{ruta_video.name}: {res.stderr.strip()[-400:]}")
        out.append({"momento": momento, "archivo": f"{destino.name}/{png.name}",
                    "segundo": segundo, "parte": parte, "veredicto": None, "nota": ""})
    return out


def preparar_cuadros(carpeta, *, eco=None) -> dict:
    """`cuadros.json` del video actual: si ya es de este video, se deja (con sus veredictos);
    si falta o es de otro, se sacan los cuadros de nuevo y queda sin veredicto."""
    from apolo.media.codificar import sondear

    carpeta = Path(carpeta)
    eco = eco or (lambda *_a, **_k: None)
    v, sha = video(carpeta), sha_video(carpeta)
    if sha is None:
        raise AprobacionError(f"No está el video {v.name} en {carpeta}: corre `publicar fabrica "
                              "--desde generar`.")
    previo, _error = _leer(carpeta / CUADROS_JSON)
    if isinstance(previo, dict) and ((previo.get("video") or {}).get("sha256") == sha):
        return previo
    if previo is not None or _error:
        eco(f"{CUADROS_JSON} era de otro video: saco los cuadros de nuevo (sus veredictos no "
            "valen para éste).")
    guion = _leer(carpeta / GUION)[0]
    puntos = momentos(guion if isinstance(guion, dict) else None, sondear(v)["duracion"])
    datos = {"formato": rc.FORMATO, "video": {"archivo": v.name, "sha256": sha},
             "cuadros": sacar_cuadros(v, carpeta / CUADROS_DIR, puntos),
             "revisor": None, "fecha": None}
    _escribir(carpeta / CUADROS_JSON, datos)
    eco(f"Saqué {len(datos['cuadros'])} cuadros del video a {carpeta / CUADROS_DIR}.")
    return datos


def problemas_cuadros(carpeta) -> list[str]:
    datos, error = _leer(Path(carpeta) / CUADROS_JSON)
    return [error] if error else rc.problemas_cuadros(datos, sha_video(carpeta))


def exigir_cuadros(carpeta) -> dict:
    carpeta = Path(carpeta)
    problemas = problemas_cuadros(carpeta)
    if problemas:
        raise AprobacionError(
            f"Los cuadros del video no están aprobados ({carpeta / CUADROS_JSON}):\n"
            f"{_lista(problemas)}\n{COMO_CUADROS.format(dir=carpeta / CUADROS_DIR)} Si alguno "
            "está mal, corrige y vuelve a generar (`publicar fabrica --desde generar`); si no, "
            "vuelve a correr `publicar fabrica`: retoma desde «cuadros».")
    datos = _leer(carpeta / CUADROS_JSON)[0]
    return {"revisor": datos["revisor"], "cuadros": [c["momento"] for c in datos["cuadros"]]}


# ------------------------------------------------------------------ familia nueva (D10)
def registro() -> tuple[Path, dict]:
    """(ruta de familias.json, su contenido). Sin el repo privado, `AprobacionError`: nunca
    pasa en silencio."""
    from apolo import paths

    dir_ = paths.fabrica_dir()
    if not dir_.is_dir():
        raise AprobacionError(
            f"No encuentro el repo privado apolo-fabrica en {dir_}: ahí vive el registro de "
            f"familias aprobadas ({FAMILIAS_JSON}, D10). Clónalo junto al repo de Apolo o apunta "
            "a él con $env:APOLO_FABRICA = '<ruta>'. Sin él no se publica.")
    ruta = dir_ / FAMILIAS_JSON
    datos, error = _leer(ruta)
    if error or (datos is not None and not isinstance(datos, dict)):
        raise AprobacionError(f"{ruta}: {error or 'debe ser un objeto JSON'}")
    return ruta, datos or {}


def familia(carpeta) -> str | None:
    from apolo.publicacion.ficha import FichaError, leer

    try:
        f = leer(Path(carpeta) / FICHA_YAML).get("familia")
    except FichaError:
        return None
    return f.strip() if isinstance(f, str) and f.strip() else None


def problemas_familia(carpeta, slug: str, version: str) -> list[str]:
    try:
        _ruta, reg = registro()
    except AprobacionError as exc:
        return [str(exc)]
    return rc.problemas_familia(reg, familia(carpeta), slug, version, firma(carpeta))


def exigir_familia(carpeta, slug: str, version: str) -> dict:
    problemas = problemas_familia(carpeta, slug, version)
    if problemas:
        raise AprobacionError(
            f"Familia nueva: «{slug}» {version} espera la aprobación de Mario (D10):\n"
            f"{_lista(problemas)}\nCuando la apruebe, vuelve a correr `publicar fabrica`: retoma "
            "desde «familia».")
    fam = familia(carpeta)
    return {"familia": fam, "aprobadas": len(rc.aprobadas(registro()[1], fam))}


def version_por_aprobar(raiz, slug: str) -> str:
    """La versión generada (con `ficha.json`) que la fábrica no terminó, la última; si todas
    terminaron, la última generada."""
    from apolo.publicacion import fabrica, paquete

    hechas = [v for v in paquete.versiones(raiz, slug)
              if paquete.publicada(paquete.carpeta_version(raiz, slug, v))]
    if not hechas:
        raise AprobacionError(f"«{slug}» no tiene ninguna versión generada en {raiz}: la fábrica "
                              "genera el paquete antes de pedir la aprobación.")
    abiertas = [v for v in hechas if not fabrica.terminada(
        fabrica.leer_estado(paquete.carpeta_version(raiz, slug, v)))]
    return (abiertas or hechas)[-1]


def aprobar(carpeta, *, slug: str, version: str, por: str = "Mario", eco=print) -> dict:
    """`publicar aprobar`: registra en familias.json que Mario aprobó ESTA versión (su firma).
    Sólo una versión con la puerta, la revisión y los cuadros aprobados: se aprueba lo que se va
    a publicar, no un borrador."""
    from apolo.publicacion import calidad

    carpeta = Path(carpeta)
    cal = calidad.leer(carpeta) or {}
    problemas = ([] if cal.get("aprobado") else
                 [f"la puerta de publicación no aprobó esta versión ({calidad.CALIDAD_JSON})"])
    problemas += problemas_revision(carpeta) + problemas_cuadros(carpeta)
    fam = familia(carpeta)
    if not fam:
        problemas.append("la ficha (ficha.yaml) no declara su «familia»")
    if problemas:
        raise AprobacionError(f"No registro la aprobación de «{slug}» {version}: antes tiene que "
                              f"pasar todo lo demás:\n{_lista(problemas)}")
    ruta, reg = registro()
    nuevo = rc.registrar(reg, fam, slug=slug, version=version, firma=cal["firma"], por=por,
                         fecha=datetime.now().isoformat(timespec="seconds"))
    _escribir(ruta, nuevo)
    n = len({a.get("slug") for a in rc.aprobadas(nuevo, fam)})
    eco(f"Aprobada: «{slug}» {version} (firma {cal['firma']}) en la familia «{fam}» "
        f"({n} de {rc.APROBADAS_MIN} máquinas aprobadas). Quedó en {ruta}; guárdalo en el repo "
        "privado:\n"
        f"  git -C {ruta.parent} add {FAMILIAS_JSON}\n"
        f"  git -C {ruta.parent} commit -m \"familias: aprueba {slug} {version}\"")
    return {"familia": fam, "aprobadas": n, "ruta": str(ruta)}


def exigir_publicable(carpeta) -> None:
    """Para `tienda.subir` (después de `calidad.exigir_subible`): revisión, cuadros y familia,
    todo junto en un mensaje."""
    carpeta = Path(carpeta)
    ficha = _leer(carpeta / FICHA_JSON)[0]
    ficha = ficha if isinstance(ficha, dict) else {}
    slug, version = ficha.get("slug") or carpeta.parent.name, ficha.get("version") or carpeta.name
    problemas = ([f"revisión de taller: {p}" for p in problemas_revision(carpeta)]
                 + [f"cuadros del video: {p}" for p in problemas_cuadros(carpeta)]
                 + [f"familia: {p}" for p in problemas_familia(carpeta, slug, version)])
    if problemas:
        raise AprobacionError(
            f"No subo {carpeta} a la tienda:\n{_lista(problemas)}\nNinguna máquina llega a la "
            "tienda sin la revisión de taller, los cuadros del video y, en una familia nueva, la "
            "aprobación de Mario (plan puerta-de-publicacion, D6/D7/D10): `publicar fabrica` "
            "los exige en orden.")
