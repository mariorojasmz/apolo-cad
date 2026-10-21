"""`vista-3d.glb`: la máquina para girarla en la web (plan vista-3d-tienda, F1 · D1, D2, D6).

Sobre la copia privada del documento que ya tiene `publicar generar` (D1 de publicacion-tienda:
proceso aparte, sin locks):

  1. `piezas`: las piezas VISIBLES que se fabrican (fuera las guías de boceto y las superficies
     de construcción, como en la BOM), con su color y la ruta de grupos del documento, y
     nombradas por su grupo, no por su nombre (D5, F2).
  2. `apolo.kernel.glb.escribir_glb`: el GLB crudo de OCCT (metros, Y arriba, apoyado en
     Y = 0), con los triángulos dibujados bajo el tope (D2).
  3. `gltfpack -cc -kn` (meshoptimizer, MIT): compresión meshopt; `-kn` conserva los nodos de
     grupo (sin él, «Bastidor» y «Motorreductor» desaparecen: F0). Es un binario EXTERNO y
     OPCIONAL, como ffmpeg: `APOLO_GLTFPACK` (archivo o carpeta) o el PATH. Si falta o falla,
     el GLB sale sin comprimir (≈ 6× más pesado, igual de correcto) y el aviso queda en
     `generacion.json`. Nunca se descarga solo.

Material (D6): el acabado de cada pieza sale de la tabla D5 de visor-realista
(`library/apariencia.py`, la fuente ÚNICA: `ui/src/viewport/acabados.json` es su copia generada)
vía `services.apariencia.apariencias_documento`, la misma resolución que el payload del viewport
(material → rol → catálogo; albedo del acabado o el color asignado/de paleta si es pintable). El
GLB lleva por material el albedo, `metallicFactor` y `roughnessFactor` del acabado: sin ellos
glTF asume metal = 1 y rugosidad = 1 y un visor externo muestra la máquina oscura y apagada. La
textura procedural y el relieve son del visor de Apolo y no viajan. Una pieza con zonas de
acabado (la seta de emergencia) lleva una primitiva por estilo de zona, con su material
(`apariencias_render`, plan seta-de-emergencia F3).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

ARCHIVO = "vista-3d.glb"
#: Nombre de la instancia de una pieza sin grupo (D5: nunca el de la pieza).
SIN_GRUPO = "Pieza"
ENV_GLTFPACK = "APOLO_GLTFPACK"
OPCIONES_GLTFPACK = ("-cc", "-kn")
_NOMBRES = ("gltfpack.exe", "gltfpack.cmd", "gltfpack")
COMO_INSTALAR = (
    "Para comprimirlo (≈ 6× menos), instala gltfpack (meshoptimizer, MIT): el binario de "
    "https://github.com/zeux/meshoptimizer/releases en el PATH, o `npm install -g gltfpack` "
    f"(requiere Node), o apunta {ENV_GLTFPACK} al ejecutable o a su carpeta.")


def apariencia(ap: dict) -> dict:
    """{color «#rrggbb», metal, rugosidad} de la pieza en el GLB a partir de su apariencia D5
    (`apariencias_documento`): el albedo y el PBR del acabado, como en el viewport."""
    return {"color": ap["color"], "metal": ap["metalness"], "rugosidad": ap["roughness"]}


def _ruta_grupos(grupo: str | None, grupos: dict) -> tuple[str, ...]:
    ruta: list[str] = []
    while grupo is not None and grupo not in ruta and grupo in grupos:
        ruta.insert(0, grupo)
        grupo = (grupos.get(grupo) or {}).get("parent")
    return tuple(ruta)


def ids_glb(doc) -> list[str]:
    """Los ids de las piezas que entran al GLB (visibles, sin guías ni superficies), en el
    orden de la escena: los mismos para la malla y para sus etiquetas (`vista3d_html`)."""
    from apolo.kernel.shapes import is_surface

    return [fid for fid, feat in doc.scene.items()
            if feat.visible and not feat.is_guide and feat.shape is not None
            and not is_surface(feat.shape)]


def piezas(doc) -> list:
    """Las `PiezaGlb` del documento, en el orden de la escena. Cada instancia se llama como su
    grupo (D5: el GLB es sólo apariencia y no lleva los nombres de las piezas, que dirían cómo
    está hecho el diseño); una pieza sin grupo, `SIN_GRUPO`."""
    from apolo.kernel.glb import PiezaGlb
    from apolo.services.apariencia import apariencias_render

    aps = apariencias_render(doc)
    out = []
    for fid in ids_glb(doc):
        feat = doc.scene[fid]
        ruta = _ruta_grupos(feat.group, doc.groups)
        out.append(PiezaGlb(ruta[-1] if ruta else SIN_GRUPO, feat.shape, grupos=ruta,
                            **apariencia(aps[fid]), **_zonas(aps[fid])))
    return out


def _zonas(ap: dict) -> dict:
    """Los kwargs de zona de una `PiezaGlb` (plan seta-de-emergencia, F3: una primitiva por
    zona, con su material): vacío si la pieza va de un solo acabado."""
    from apolo.kernel.glb import ZonaGlb

    zonas = ap.get("zonas")
    if not zonas:
        return {}
    return {"zona_por_cara": tuple(zonas["por_cara"]),
            "zonas": tuple(ZonaGlb(nombre, **apariencia(z))
                           for nombre, z in zonas["aps"].items())}


def buscar_gltfpack() -> str | None:
    """Ruta de gltfpack: `APOLO_GLTFPACK` (el ejecutable o su carpeta) o el PATH; None si no
    está. Una variable que apunta a algo que no existe es un error: no se ignora callada."""
    valor = os.environ.get(ENV_GLTFPACK, "").strip()
    if valor:
        ruta = Path(valor)
        if ruta.is_dir():
            ruta = next((ruta / n for n in _NOMBRES if (ruta / n).is_file()), ruta / _NOMBRES[0])
        if not ruta.is_file():
            raise FileNotFoundError(f"{ENV_GLTFPACK}={valor}: ahí no hay gltfpack")
        return str(ruta)
    return shutil.which("gltfpack")


def comprimir(crudo: Path, destino: Path, exe: str) -> None:
    """`gltfpack -cc -kn` de `crudo` a `destino`; RuntimeError con el final de su salida."""
    try:
        r = subprocess.run([exe, "-i", str(crudo), "-o", str(destino), *OPCIONES_GLTFPACK],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"gltfpack no corrió: {exc}") from exc
    if r.returncode != 0 or not destino.is_file():
        raise RuntimeError(f"gltfpack salió con {r.returncode}: "
                           f"{(r.stderr or r.stdout).strip()[-400:]}")


def generar(doc, destino, *, titulo: str | None = None, tope: int | None = None,
            comprimir_: bool = True) -> dict:
    """Escribe el GLB en `destino` y devuelve su informe (va a `generacion.json`). Lanza
    ValueError si no hay nada visible y RuntimeError si el escritor de OCCT falla; la falta o
    el fallo de gltfpack NO lanza: deja el GLB sin comprimir y lo dice en `aviso`."""
    from apolo.kernel import glb
    from apolo.kernel.glb_resumen import resumen

    t0 = time.perf_counter()
    destino = Path(destino)
    crudo = destino.with_name(destino.stem + ".crudo.glb")
    inf = glb.escribir_glb(piezas(doc), crudo, titulo=titulo or doc.name,
                           tope=glb.TOPE_TRIANGULOS if tope is None else tope)
    aviso, herramienta = None, None
    try:
        exe = buscar_gltfpack() if comprimir_ else None
    except FileNotFoundError as exc:
        exe, aviso = None, f"{exc}. El GLB va sin comprimir."
    if exe:
        try:
            comprimir(crudo, destino, exe)
            herramienta = "gltfpack " + " ".join(OPCIONES_GLTFPACK)
        except RuntimeError as exc:
            aviso = f"{exc}. El GLB va sin comprimir."
    elif comprimir_ and aviso is None:
        aviso = "No encuentro gltfpack: el GLB va sin comprimir. " + COMO_INSTALAR
    if herramienta:
        crudo.unlink()
    else:
        destino.unlink(missing_ok=True)
        os.replace(crudo, destino)
    final = resumen(destino)
    if inf.sobre_tope:
        tope_aviso = (f"{inf.triangulos:,} triángulos dibujados aun con todo al detalle más "
                      f"grueso: pasa el tope de {inf.tope:,} (puede ir lento en un celular).")
        aviso = f"{aviso} {tope_aviso}" if aviso else tope_aviso
    return {
        "archivo": destino.name, "bytes": destino.stat().st_size, "bytes_crudo": inf.bytes,
        "comprimido_con": herramienta, "aviso": aviso,
        "triangulos": final["triangulos"], "triangulos_archivo": final["triangulos_archivo"],
        "tope_triangulos": inf.tope, "sobre_tope": inf.sobre_tope, "rebajados": inf.rebajados,
        "piezas": inf.piezas, "prototipos": inf.prototipos, "piso_mm": round(inf.piso_mm, 3),
        "caja_m": [[round(float(v), 4) for v in esquina] for esquina in final["caja"]],
        "segundos": round(time.perf_counter() - t0, 2),
    }
