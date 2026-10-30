"""`apoyo.capacidad` (plan hallazgos-del-revisor-en-la-puerta, D6 con los ajustes de la F0): cada
apoyo a tierra que se COMPRA resiste su reacción. Puro: reconoce el apoyo y su capacidad por su
nombre y su ficha, y juzga las filas que mide `services/calidad_apoyos.py`.

El defecto: un pie nivelador «(compra)» sin carga nominal bajo 500 kg de carga y 291 kg de mesa
(la mesa de soldadura con grilla Ø28, ronda 2: 4 en FALLA). Nadie podía comprarlo sabiendo que
aguanta, y la puerta no lo miraba.

**Qué es un apoyo de compra** (sólo los que la F0 midió sin falsos positivos):
- una ref de catálogo de las categorías de apoyo (`CATEGORIAS`: pie nivelador, garrucha, pata,
  rueda); un perfil de catálogo que hace de «Pata» se FABRICA (lo mide `estructura.pandeo`);
- una pieza a mano que se compra (`designacion_comercial.es_comercial`: rol de compra como «Pie
  nivelador» o la compra DECLARADA «(compra)») cuyo ROL, anclado al inicio, es pie, nivelador,
  pata, garrucha, rueda o regatón (`clase_de_rol`, con guarda: «Pie de amigo» es una riostra y
  «Rueda dentada» una transmisión).

Y sólo los anclados (`ground`): la reacción es la de `engineering/installation.anchor_loads`.

**Capacidad**: la de la ficha (`capacidad_kg` o `carga_kg`: la clave de `97_pies_niveladores`,
`110_garruchas` —la de rodadura, la menor— y `40_patas`) o la que el modelador ESCRIBE en la
designación de la compra a mano: «(compra, 1000 kg)» o «carga estática ≥ 1000 kg»
(`capacidad_del_nombre`; un «500 kg» suelto puede ser la carga de la mesa y no cuenta).

**Criterio** (criterio de diseño, no una cita de norma): reacción × `FS_APOYO` ≤ capacidad. La
reacción es la del reparto elástico de grupo con la masa de la máquina MÁS la carga de los
requisitos (`carga_kg`: sin ella caían testigos sanos), con el peso en el COG; esa hipótesis va en
la evidencia (un canto cargado no se evalúa: no hay requisito de carga excéntrica). Sin capacidad
conocida es FALLA salvo que se JUSTIFIQUE por escrito (`justificadas.py`, regla
`REGLA_SIN_CAPACIDAD`, por pieza o para todos); una capacidad que no alcanza jamás se justifica.
"""

from __future__ import annotations

import re

from ..designacion_comercial import compra_declarada
from ..materials import piece_role
from .entrada import Entrada, hay
from .item import FALLA, OK, SIN_EVALUAR, recortar
from .justificadas import citar, del_aviso

#: Criterio de diseño: la capacidad del apoyo sobre la reacción de servicio (golpes al apoyar la
#: carga, nivelación desigual del piso que el reparto de rigidez igual no ve).
FS_APOYO = 1.5
NORMA = ("criterio de diseño (reacción del reparto elástico de grupo × FS 1,5 ≤ la capacidad "
         "nominal de su ficha o su designación)")
#: La regla que se justifica por escrito (`justificadas`): el texto EXACTO de la evidencia.
REGLA_SIN_CAPACIDAD = "apoyo de compra sin capacidad declarada"
#: Categorías de catálogo que SON un apoyo que se compra → su clase.
CATEGORIAS = {"pies_niveladores": "pie", "garruchas": "garrucha", "patas": "pata",
              "ruedas": "rueda"}

_ROL = re.compile(r"^(?:(pies?|nivelador\w*)|(patas?)|(garruchas?)|(ruedas?)|(regat[oó]n\w*))\b",
                  re.I)
_CLASES = ("pie", "pata", "garrucha", "rueda", "regaton")
#: lo que empieza como un apoyo y no lo es
_NO_APOYO = re.compile(r"^(?:pies?\s+de\s+amigo|patas?\s+de\s+cabra|ruedas?\s+(?:dentada|de\s+"
                       r"cadena|motriz|conducida|de\s+transmisi\w*|libre|catalina))\b", re.I)
_NUM = r"(\d{1,3}(?:\.\d{3})+(?![\d,])|\d+(?:[.,]\d+)?)"
_KG = re.compile(_NUM + r"\s*kg\b", re.I)
#: «carga estática ≥1000 kg», «capacidad 350 kg», «admisible: 500 kg»
_CON_PALABRA = re.compile(r"\b(?:carga|capacidad|admisible|nominal)\b[^()\d]{0,25}?" + _NUM +
                          r"\s*kg\b", re.I)
_PARENTESIS = re.compile(r"\(([^()]*)\)")


def clase_de_rol(nombre: str | None) -> str | None:
    """La clase de apoyo del ROL de la pieza (tras el último « · », anclado al inicio) o None."""
    rol = piece_role(nombre or "").strip()
    if _NO_APOYO.match(rol):
        return None
    m = _ROL.match(rol)
    return next((c for c, g in zip(_CLASES, m.groups()) if g), None) if m else None


def _kg(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", ".") if re.fullmatch(
        r"\d{1,3}(?:\.\d{3})+", texto) else texto.replace(",", "."))


def capacidad_del_nombre(nombre: str | None) -> float | None:
    """La capacidad que la designación de una compra a mano declara: un «N kg» dentro del
    paréntesis de la compra («(compra, 1000 kg)») o detrás de «carga», «capacidad», «admisible» o
    «nominal». None si no la dice."""
    nombre = nombre or ""
    for m in _PARENTESIS.finditer(nombre):
        if compra_declarada(m.group(0)):
            k = _KG.search(m.group(1))
            if k:
                return _kg(k.group(1))
    m = _CON_PALABRA.search(nombre)
    return _kg(m.group(1)) if m else None


def capacidad_de_ficha(specs: dict | None) -> float | None:
    """`capacidad_kg` o `carga_kg` de la ficha (sin distinguir mayúsculas), o None."""
    low = {str(k).lower(): v for k, v in (specs or {}).items()}
    for clave in ("capacidad_kg", "carga_kg"):
        try:
            v = float(low.get(clave) or 0)
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v
    return None


def juzgar(f: dict, justificadas=None) -> tuple[str, str, list]:
    """(estado, por qué, justificaciones) de una fila {id, nombre, reaccion_kg, capacidad_kg}."""
    pide = max(0.0, float(f["reaccion_kg"])) * FS_APOYO
    cap = f.get("capacidad_kg")
    if cap is None:
        js = del_aviso(REGLA_SIN_CAPACIDAD, [f["id"]], justificadas)
        if js:
            return OK, f"sin capacidad declarada, justificado: {js[0]['porque']}", js
        return FALLA, f"pide {pide:.0f} kg y su capacidad no se conoce", []
    if pide <= float(cap):
        return OK, f"pide {pide:.0f} kg ≤ {float(cap):g} kg ({f.get('fuente_capacidad')})", []
    return FALLA, (f"pide {pide:.0f} kg (reacción {float(f['reaccion_kg']):g} kg × {FS_APOYO:g}) "
                   f"> {float(cap):g} kg ({f.get('fuente_capacidad')})"), []


COMO = ("declara la capacidad en su designación («Pie nivelador M16 (compra, 1000 kg)») o usa una "
        "ref de catálogo con su carga; si de verdad no se sabe, justifícalo por escrito "
        f"(set_justifications con la regla «{REGLA_SIN_CAPACIDAD}» y la pieza)")


def capacidad(ins: dict) -> dict:
    """El control del ítem: `ins["apoyos_compra"]` = {apoyos: [filas], hipotesis, carga_kg,
    masa_kg} (None: no se midió); `ins["justificadas"]` = el metadato."""
    datos = ins.get("apoyos_compra")
    if datos is None:
        return {"estado": SIN_EVALUAR, "detalle": "no se midieron los apoyos a tierra de compra"}
    casos, malos, js_usadas = [], [], []
    for f in datos.get("apoyos") or []:
        estado, motivo, js = juzgar(f, ins.get("justificadas"))
        js_usadas += js
        casos.append({k: f.get(k) for k in ("id", "nombre", "clase", "ref", "reaccion_kg",
                                             "capacidad_kg", "fuente_capacidad")}
                     | {"pide_kg": round(max(0.0, float(f["reaccion_kg"])) * FS_APOYO, 1),
                        "estado": estado, "motivo": motivo,
                        **({"regla": REGLA_SIN_CAPACIDAD} if f.get("capacidad_kg") is None
                           else {})})
        if estado != OK:
            malos.append((f, motivo))
    rec = recortar(casos)
    ev = {"fs": FS_APOYO, "apoyos": rec["casos"],
          **({"apoyos_omitidos": rec["casos_omitidos"]} if "casos_omitidos" in rec else {}),
          "hipotesis": datos.get("hipotesis"), "carga_kg": datos.get("carga_kg"),
          "masa_kg": datos.get("masa_kg")}
    if js_usadas:
        ev["justificadas"] = citar(js_usadas)
    if malos:
        texto = "; ".join(f"{f.get('nombre') or f['id']} ({f['id']}): {m}" for f, m in malos[:6])
        resto = f" (+{len(malos) - 6} más en la evidencia)" if len(malos) > 6 else ""
        return {"estado": FALLA, "evidencia": ev, "piezas": [f["id"] for f, _ in malos][:40],
                "detalle": f"{len(malos)} de {len(casos)} apoyo(s) de compra sin la capacidad "
                           f"para su reacción × {FS_APOYO:g}: {texto}{resto}. {COMO[0].upper()}"
                           f"{COMO[1:]}"}
    return {"estado": OK, "evidencia": ev,
            "detalle": f"{len(casos)} apoyo(s) de compra, cada uno con capacidad ≥ su reacción × "
                       f"{FS_APOYO:g}"}


ENTRADA = Entrada(
    "apoyo.capacidad", "Cada apoyo a tierra de compra resiste su reacción",
    "un pie nivelador, una garrucha o una pata que se compra sin saber cuánto aguanta: el taller "
    "compra el más barato y cede bajo la máquina cargada",
    NORMA, "estructura",
    hay("apoyos_de_compra", "sin apoyos a tierra de compra (pie, pata, garrucha, rueda o regatón "
                            "anclados)"),
    capacidad, "apoyos_de_compra")
