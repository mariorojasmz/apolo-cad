"""Piezas eléctricas MODELADAS en 3D sin ref de catálogo (plan V8.1, F4c: D-c2 y D-c3).

El tablero se compra por su carril (`add_device`, `add_cable`, `add_wire`); lo que el agente
modela en 3D para verlo (un cable que recorre la máquina, una clavija, una prensaestopa) no se
fabrica en el taller. Aquí, puro y sin documento:

  - `recorrido_mm`: el largo de un cable 3D es el de su RECORRIDO (la directriz del barrido), no
    la mayor cota del bbox (un cable que sube, cruza y baja medía 99,7 mm en la BOM);
  - `firma_cable`: «4x2.5 mm2», «4G2,5», «7×1» del nombre → (hilos, sección mm²), para saber
    qué `add_cable` lo cubre;
  - `es_rol_electrico`: clavija, toma, prensaestopa, canaleta… por ROL: sin ref sale «sin
    precio», nunca estimada por peso como acero (la clavija de 4,23 kg salía a 15,87 USD).
"""

from __future__ import annotations

import re

from .materials import piece_role

# «4x2.5 mm2», «4G2,5», «7 × 1 mm²», «3X0.75»: hilos × sección
_FIRMA = re.compile(r"(?<![\d.,xX×])(\d{1,2})\s*[xX×gG]\s*(\d+(?:[.,]\d+)?)(?![\d.,]*\s*[xX×]\s*\d)")

#: Roles que SIEMPRE son eléctricos (no hay otra cosa que se llame así en una máquina).
_ROL_SIEMPRE = re.compile(r"^(tomacorrientes?|prensaestopas?|prensa\s*estopas?|borneras?|"
                          r"interruptor(es)?\s+(termomagn[eé]tico|diferencial)|"
                          r"canaletas?\s+(ranurada|portacables?|el[eé]ctrica))\b")
#: Roles que son eléctricos sólo con una SEÑAL eléctrica en el nombre: una «clavija» es también
#: la espiga de madera de un ensamble, una «toma» la de fuerza, una «canaleta» la del agua.
_ROL_CON_SENAL = re.compile(r"^(clavijas?|enchufes?|tomas?|canaletas?)\b")
_SENAL = re.compile(r"\b(\d+\s*v|\d+\s*a|[1-4]p(\s*\+\s*(t|n|pe))*|iec|60309|el[eé]ctric\w*|"
                    r"corriente|schuko|ip\s?\d\d|industrial|fases?|3f|monof[aá]sic\w*|"
                    r"trif[aá]sic\w*|cables?)\b")
_MADERA = re.compile(r"madera|haya|pino|roble|copaiba|tornillo|ensamble|dowel")


def recorrido_mm(shape) -> float | None:
    """Largo del recorrido de un cable 3D: volumen / sección. La sección es la cara PLANA más
    chica (los extremos del barrido; un tramo recto con codos de cilindros deja también sus
    tapas, todas iguales). Sin caras planas (un toro, una B-spline cerrada) o si el resultado no
    alcanza la mitad del bbox, la mayor cota del bbox (lo de antes). None si no se puede medir."""
    try:
        bb = shape.bounding_box()
        mayor = max(bb.size.X, bb.size.Y, bb.size.Z)
        vol = float(shape.volume)
        planas = [f.area for f in shape.faces() if "PLANE" in str(f.geom_type).upper()]
    except Exception:  # noqa: BLE001 — geometría rara: sin largo, nunca rompe la BOM
        return None
    seccion = min((a for a in planas if a > 1e-6), default=None)
    if seccion is None or vol <= 0:
        return round(mayor, 1)
    largo = vol / seccion
    return round(largo if largo >= 0.5 * mayor else mayor, 1)


def firma_cable(nombre: str | None) -> tuple[int, float] | None:
    """(hilos, sección mm²) que dice el nombre de un cable 3D, o None si no lo dice."""
    m = _FIRMA.search(nombre or "")
    if m is None:
        return None
    return int(m.group(1)), float(m.group(2).replace(",", "."))


def es_rol_electrico(nombre: str | None) -> bool:
    """¿El ROL de la pieza (tras el último « · ») es de material eléctrico que se compra?"""
    rol = piece_role((nombre or "").lower())
    if _ROL_SIEMPRE.match(rol):
        return True
    return bool(_ROL_CON_SENAL.match(rol)) and bool(_SENAL.search(rol)) and not _MADERA.search(rol)
