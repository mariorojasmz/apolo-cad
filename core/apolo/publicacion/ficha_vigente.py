"""La `ficha.yaml` VENCIDA (plan puerta-de-publicacion, F6): la ficha se redacta sobre un modelo
y el modelo sigue cambiando; salió publicada una ficha con la carrera, la masa y las medidas de
antes. Como el guion (`guion_vigente.py`), la ficha se ata a la firma del log
(`services/guion_video.firma`) con la que se redactó o se re-validó por última vez:

- `ficha.firma.json` = {firma, como: "redactada" | "re-validada", cuando}. Lo escribe
  `flujo.guion` al dejar el borrador (la ficha nace con el log de ese guion) y lo re-sella
  `revalidar` (`publicar ficha --revisar --vigente --project N`) cuando quien la redactó confirma
  que el texto dice el modelo de HOY;
- una ficha de antes, sin ese archivo, se data por su guion: la del guion vencido
  (`guion.vencido.json`: el guion se rehízo, la ficha se quedó) o la del guion vigente;
- `exigir` (paso «ficha» de la fábrica): firma distinta de la de hoy → PARA y dice cómo
  re-validarla. No se re-sella sola: sólo quien la lee contra el modelo sabe si la carrera o
  la capacidad que nombra siguen valiendo.

Además, un verificador automático MÍNIMO de lo que sí se puede leer del modelo (`problemas`):
la masa («pesa 260 kg», «peso: 260 kg», «masa de 260 kg») y las medidas generales
(«4000 × 650 × 900 mm», también en m) que la descripción menciona, contra
`scene_mass_properties` (la misma masa y caja que la tarjeta del video, `guion_video.cifras`),
con ±2 %. Una cifra de CARGA («carga de 15 kg», «paquetes de hasta 15 kg», «capacidad») no es
la masa de la máquina y no se compara. Las medidas valen en el orden L × A × H con L sobre X o
sobre Y (H siempre es la altura).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from apolo.publicacion.paquete import FICHA_YAML, GUION

FIRMA = "ficha.firma.json"
TOLERANCIA = 0.02
_NUM = r"(\d{1,3}(?:[ . ]\d{3})+|\d+(?:[.,]\d+)?)"
_MASA_RE = re.compile(rf"\b(pesa|peso|masa)\b[^;\n\d]{{0,40}}?{_NUM}\s*kg\b", re.I)
_CARGA_RE = re.compile(r"\b(carga|capacidad|paquete|caja|producto|hasta|soporta|admite)", re.I)
_X = r"\s*[x×]\s*"
_MEDIDAS_RE = re.compile(rf"{_NUM}{_X}{_NUM}{_X}{_NUM}\s*(mm|m)\b", re.I)


def _numero(texto: str) -> float:
    t = texto.replace(" ", " ")
    if re.fullmatch(r"\d{1,3}(?:[ .]\d{3})+", t):
        return float(re.sub(r"[ .]", "", t))
    return float(t.replace(",", "."))


def _cerca(a: float, b: float) -> bool:
    return b > 0 and abs(a - b) <= TOLERANCIA * b


def cifras_del_modelo(doc) -> dict:
    """{masa_kg, bbox_mm} del modelo: la misma fuente que la tarjeta del video."""
    from apolo.services.guion_video import masa_y_medidas

    t = masa_y_medidas(doc)
    return {"masa_kg": float(t["masa_kg"]), "bbox_mm": [float(x) for x in t["bbox_mm"]]}


def problemas(descripcion: str, cifras: dict) -> list[str]:
    """Las cifras de masa y medidas generales de la descripción que no son las del modelo."""
    out = []
    masa = cifras.get("masa_kg") or 0.0
    for m in _MASA_RE.finditer(descripcion or ""):
        if _CARGA_RE.search(m.group(0)):
            continue
        dicho = _numero(m.group(2))
        if not _cerca(dicho, masa):
            out.append(f"la descripción dice «{m.group(0).strip()}» y el modelo pesa "
                       f"{masa:.1f} kg (±{TOLERANCIA:.0%})")
    dx, dy, dz = (cifras.get("bbox_mm") or [0.0, 0.0, 0.0])[:3]
    for m in _MEDIDAS_RE.finditer(descripcion or ""):
        k = 1000.0 if m.group(4).lower() == "m" else 1.0
        l_, a_, h_ = (_numero(m.group(i)) * k for i in (1, 2, 3))
        if not any(_cerca(l_, x) and _cerca(a_, y) and _cerca(h_, dz)
                   for x, y in ((dx, dy), (dy, dx))):
            out.append(f"la descripción dice «{m.group(0).strip()}» y el modelo mide "
                       f"{dx:.0f} × {dy:.0f} × {dz:.0f} mm (L × A × H, ±{TOLERANCIA:.0%})")
    return out


def sellar(carpeta, firma: str, como: str) -> None:
    datos = {"firma": firma, "como": como,
             "cuando": datetime.now().isoformat(timespec="seconds")}
    (Path(carpeta) / FIRMA).write_text(json.dumps(datos, indent=2) + "\n", encoding="utf-8")


def _firma_en(ruta: Path) -> str | None:
    try:
        g = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(g, dict):
        return None
    return g.get("firma") if "firma" in g else (g.get("documento") or {}).get("firma")


def firma_de_la_ficha(carpeta) -> tuple[str | None, str]:
    """(firma con que se redactó o re-validó la ficha, de dónde salió)."""
    from apolo.publicacion.guion_vigente import VENCIDO

    carpeta = Path(carpeta)
    for nombre, origen in ((FIRMA, FIRMA), (VENCIDO, f"su guion de entonces ({VENCIDO})"),
                           (GUION, f"su guion ({GUION})")):
        firma = _firma_en(carpeta / nombre)
        if firma:
            return firma, origen
    return None, "nada la data"


def _hoy(cliente, proyecto: int):
    from apolo.publicacion import flujo

    api = flujo._Api(cliente)
    api.abrir(proyecto)
    data = api.apolo()
    return flujo._firma_de(data), flujo._documento(data)


def _descripcion(carpeta) -> str:
    from apolo.publicacion.ficha import leer

    return str(leer(Path(carpeta) / FICHA_YAML).get("descripcion") or "")


def exigir(carpeta, cliente, proyecto: int, eco=print) -> dict:
    """El paso «ficha» de la fábrica: la ficha es del modelo de hoy y sus cifras de masa y
    medidas son las del modelo. `ValueError` con el porqué y cómo seguir; si no, {firma,
    cifras}."""
    hoy, doc = _hoy(cliente, proyecto)
    suya, origen = firma_de_la_ficha(carpeta)
    if suya != hoy:
        raise ValueError(
            f"{FICHA_YAML} se redactó sobre otra versión del modelo (firma {suya or '?'}, según "
            f"{origen}; hoy {hoy}): sus cifras (carrera, masa, medidas, capacidad) pueden ser "
            f"las de antes. Léela contra el modelo de hoy, corrígela y confírmalo con `publicar "
            f"ficha --revisar --vigente --project {proyecto}` (re-sella {FIRMA} con la firma de "
            "hoy); luego vuelve a correr `publicar fabrica` (retoma desde la ficha).")
    cif = cifras_del_modelo(doc)
    malos = problemas(_descripcion(carpeta), cif)
    if malos:
        raise ValueError(f"{FICHA_YAML} no dice el modelo de hoy:\n  - " + "\n  - ".join(malos)
                         + "\nCorrígela y vuelve a correr `publicar fabrica` (retoma desde la "
                         "ficha).")
    (eco or (lambda *_a: None))(f"{FICHA_YAML} es del modelo de hoy (firma {hoy}) y sus cifras "
                                "de masa y medidas coinciden con él.")
    return {"firma": hoy, "cifras": cif}


def revalidar(carpeta, cliente, proyecto: int, eco=print) -> dict:
    """`publicar ficha --revisar --vigente`: quien redactó la ficha confirma que dice el modelo
    de hoy. Pasa el verificador de cifras y re-sella `ficha.firma.json`."""
    hoy, doc = _hoy(cliente, proyecto)
    cif = cifras_del_modelo(doc)
    malos = problemas(_descripcion(carpeta), cif)
    if malos:
        raise ValueError(f"{FICHA_YAML} no dice el modelo de hoy (no la re-sello):\n  - "
                         + "\n  - ".join(malos))
    sellar(carpeta, hoy, "re-validada")
    (eco or (lambda *_a: None))(f"{FICHA_YAML} re-validada con la firma de hoy ({hoy}).")
    return {"firma": hoy, "cifras": cif}
