"""El material que se COMPRA de una ref de catálogo: el asignado gana a la ficha (F6).

`set_material(features=[…], material="acero inoxidable AISI 304")` sobre un `TUBOR-2` o un
`PERNO-HEX-M10` no cambiaba lo que decía la BOM («acero ASTM A500», «acero grado 8.8»: tres
máquinas de alimentos de 2026-10-27, el revisor lo vio con `get_bom`). Una ref de catálogo es un
EJEMPLO (library/CLAUDE.md): con otro material asignado se compra la EQUIVALENTE en ese material, y
la fila lo dice: material = el asignado, `material_ficha` = el de la ficha, la descripción
«… en acero inoxidable AISI 304 (la ref de catálogo es de acero ASTM A500: pedir la equivalente)»,
el peso escalado por densidad y el costo de la ficha escalado por USD/kg × densidad (la ficha da el
precio de SU material). La norma de la ficha que es de su MATERIAL («ASTM A500 round HSS» de un
tubo A500) no se arrastra; la de su FORMA («DIN 933» de un perno), sí.

Lo mismo para la tornillería de una unión DECLARADA con su material (`fasten.material` o la nota:
`tornilleria_declarada.py`). Puro: recibe la ficha y el material, nunca un `Document`.
"""

from __future__ import annotations

import re

from .materials import cost_per_kg, density

_CON_DIGITO = re.compile(r"[A-Za-z]*\d[\w.]*")


def otro_material(asignado: str | None, ficha: str | None) -> bool:
    """¿El material asignado es OTRO que el de la ficha? (sin distinguir mayúsculas ni espacios;
    sin asignado o sin material de ficha, no: no hay nada que contradecir)."""
    a = " ".join((asignado or "").lower().split())
    f = " ".join((ficha or "").lower().split())
    return bool(a) and bool(f) and a != f


def material_de_compra(feat, comp) -> tuple[str, str | None]:
    """(material que se compra, material de la ficha si el asignado es otro; si no, None). Una
    ficha sin material (un aparato eléctrico) sigue como siempre: no hay equivalente que pedir."""
    ficha = str((comp.specs or {}).get("material", "") or "")
    asignado = getattr(feat, "material", None)
    if otro_material(asignado, ficha):
        return str(asignado), ficha
    return ficha, None


def descripcion(desc: str, material: str, ficha: str) -> str:
    """La designación de compra con el material que se compra."""
    return f"{desc} en {material} (la ref de catálogo es de {ficha}: pedir la equivalente)"


def factor_peso(material: str, ficha: str) -> float:
    """Peso de la equivalente / peso de la ficha (la misma forma, otra densidad)."""
    return density(material) / density(ficha)


def factor_costo(material: str, ficha: str) -> float:
    """Costo de la equivalente / costo de la ficha: USD/kg × densidad de cada material."""
    return (cost_per_kg(material) * density(material)) / (cost_per_kg(ficha) * density(ficha))


def norma(norma_ficha: str, ficha: str) -> str:
    """La norma de la ficha si sigue valiendo con otro material: '' si comparte con el material
    de la ficha una designación con dígitos («A500» en «ASTM A500 round HSS» y «acero ASTM
    A500»): es la norma del MATERIAL, no de la forma («DIN 933» de un perno 8.8 se queda)."""
    tokens = {t.lower() for t in _CON_DIGITO.findall(ficha or "")}
    if tokens & {t.lower() for t in _CON_DIGITO.findall(norma_ficha or "")}:
        return ""
    return norma_ficha or ""


def ajustar_fila(fila: dict, material: str, ficha: str) -> dict:
    """Pasa una fila de BOM de catálogo (la de la ficha) al material que se compra: material,
    `material_ficha`, descripción, norma y peso unitario. Muta y devuelve `fila`."""
    fila["material"] = material
    fila["material_ficha"] = ficha
    fila["descripcion"] = descripcion(fila["descripcion"], material, ficha)
    fila["norma"] = norma(fila.get("norma", ""), ficha)
    if fila.get("peso_unitario_kg") is not None:
        fila["peso_unitario_kg"] = round(fila["peso_unitario_kg"] * factor_peso(material, ficha), 3)
    return fila
