"""Carga del catálogo desde archivos de datos YAML (data-driven).

Un archivo por familia/categoría en `library/data/*.yaml`. Cada archivo declara
una `category` y `components` (piezas sueltas) y/o `families` (expandidas a
variantes). El loader produce los `Component` que consume el resto del sistema.

El directorio se resuelve relativo a ESTE módulo (nunca al cwd), porque los
tests y el agente se ejecutan desde directorios distintos.
"""

from __future__ import annotations

import glob
import math
import os

import yaml

from .acuerdos import validar_acuerdo
from .builders import BUILDERS as _BUILDERS_BASE
from .builders_rodaje import BUILDERS as _BUILDERS_RODAJE
from .builders_transmision import ANCLAS as _ANCLAS_TRANSMISION
from .builders_transmision import BUILDERS as _BUILDERS_TRANSMISION
from .electrico.ficha import fusionar as _fusionar_electrico
from .electrico.ficha import parse_ficha

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def merge_builders(*registros: dict) -> dict:
    """Une registros de builders en uno. Un nombre repetido es un ERROR: un builder no pisa a
    otro en silencio (el YAML que lo nombra construiría otra geometría sin aviso). Cada familia
    nueva va en su propio módulo (`builders.py` está congelado por el trinquete de tamaño)."""
    unido: dict = {}
    for registro in registros:
        for nombre, factory in registro.items():
            if nombre in unido:
                raise ValueError(f"Builder '{nombre}' registrado dos veces entre los módulos de builders")
            unido[nombre] = factory
    return unido


def merge_anclas(builders: dict, *registros: dict) -> dict:
    """Une los registros de anclas POR FAMILIA (`builder → (**params) -> anclas locales`), con la
    misma regla que los builders (nombre repetido = error) y además cada ancla debe nombrar un
    builder registrado (plan cadenas-pinones D6)."""
    unido = merge_builders(*registros)
    huerfanas = sorted(set(unido) - set(builders))
    if huerfanas:
        raise ValueError(f"Anclas de builders inexistentes: {', '.join(huerfanas)}")
    return unido


BUILDERS = merge_builders(_BUILDERS_BASE, _BUILDERS_RODAJE, _BUILDERS_TRANSMISION)
ANCLAS = merge_anclas(BUILDERS, _ANCLAS_TRANSMISION)


def eval_formula(expr: str, specs: dict) -> float:
    """Evalúa una fórmula de peso sobre las specs numéricas. Sin builtins."""
    ns = {k: v for k, v in specs.items() if isinstance(v, (int, float))}
    ns["math"] = math
    return float(eval(expr, {"__builtins__": {}}, ns))


def _component_from_item(item: dict, category: str):
    from .catalog import Component  # import perezoso: catalog importa este módulo

    ref = item["ref"]
    builder_name = item["builder"]
    factory = BUILDERS.get(builder_name)
    if factory is None:
        raise ValueError(f"Componente '{ref}': builder desconocido '{builder_name}'")
    params = item.get("params", {})
    builder_fn = factory(**params)
    anclas_fn = ANCLAS.get(builder_name)

    specs = item.get("specs", {})
    validar_acuerdo(specs, ref)  # r1/r2/pendiente_ala de norma (plan perfiles-con-acuerdo D1)
    if "weight" in item and item["weight"] is not None:
        weight = float(item["weight"])
    elif "weight_formula" in item:
        weight = round(eval_formula(item["weight_formula"], specs), 4)
    else:
        raise ValueError(f"Componente '{ref}': falta 'weight' o 'weight_formula'")

    return Component(
        ref=ref,
        name=item["name"],
        category=category,
        description=item.get("description", ""),
        specs=specs,
        weight=weight,
        cuttable=bool(item.get("cuttable", False)),
        default_length=item.get("default_length"),
        builder=builder_fn,
        anchors=anclas_fn(**params) if anclas_fn else None,
        # bloque `electrico:` (plan V8.1 D5): validado aquí; un bloque mal escrito no carga
        electrico=parse_ficha(item.get("electrico"), ref),
        familia=builder_name,
        params=dict(params),
    )


def _expand_family(fam: dict) -> list[dict]:
    """Convierte una familia paramétrica en items de componente individuales. El bloque
    `electrico` de la familia vale para cada variante; el de la variante lo completa (su
    `modelo`, p. ej. la placa del motor, se fusiona clave a clave) y NO pasa a sus specs."""
    param_keys = fam.get("param_keys", [])
    common = fam.get("specs_common", {})
    items = []
    for variant in fam["variants"]:
        ref = variant["ref"]
        var_specs = {k: v for k, v in variant.items() if k not in ("ref", "electrico")}
        specs = {**common, **var_specs}
        ctx = {"ref": ref, **specs}
        item = {
            "ref": ref,
            "name": fam["name_tpl"].format(**ctx),
            "description": fam.get("description_tpl", "").format(**ctx),
            "builder": fam["builder"],
            "specs": specs,
            "params": {k: var_specs[k] for k in param_keys},
            "cuttable": fam.get("cuttable", False),
            "default_length": fam.get("default_length"),
        }
        electrico = _fusionar_electrico(fam.get("electrico"), variant.get("electrico"))
        if electrico is not None:
            item["electrico"] = electrico
        if "weight" in variant:
            item["weight"] = variant["weight"]
        elif "weight_formula" in fam:
            item["weight_formula"] = fam["weight_formula"]
        elif "weight" in fam:
            item["weight"] = fam["weight"]
        items.append(item)
    return items


def load_catalog(data_dir: str | None = None) -> dict:
    """Lee todos los YAML de datos y devuelve {ref: Component}. Orden determinista."""
    directory = data_dir or DATA_DIR
    catalog: dict = {}
    for path in sorted(glob.glob(os.path.join(directory, "*.yaml"))):
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        category = doc.get("category")
        if not category:
            raise ValueError(f"{os.path.basename(path)}: falta 'category'")
        items = list(doc.get("components", []))
        for fam in doc.get("families", []):
            items.extend(_expand_family(fam))
        for item in items:
            comp = _component_from_item(item, category)
            if comp.ref in catalog:
                raise ValueError(f"Referencia duplicada en el catálogo: '{comp.ref}'")
            catalog[comp.ref] = comp
    return catalog
