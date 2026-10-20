"""Las cifras de ingeniería que leen los rótulos del video (plan video-tienda-pulido, F1 · D1).

`datos_rotulos(doc)` lee el documento REGENERADO una vez y devuelve un `rotulos.DatosRotulo`
puro, sin shapes: por pieza, su referencia de catálogo (nombre, categoría, specs), el largo de
corte de un perfil, el espesor de la chapa (los params del `create_sheet_metal`, resueltos con
las variables), su centro y sus medidas; además, los requisitos del proyecto y el factor de
seguridad de potencia de cada cadena (`transmision_rules.chain_rules`, el mismo cálculo de la
memoria). Sólo cifras leídas del documento, del catálogo o de un cálculo ya hecho: un rótulo con
una cifra escrita a mano mentiría en cuanto cambie una variable (Riesgos del plan).

Capa `services`: `doc` explícito, sin locks; corre en el proceso de la publicación (D1 de
publicacion-tienda), igual que `construccion.pasos_visuales`. Punto de enganche: el material de
cada pieza saldrá de la tabla única de visor-realista (D5) cuando exista; hoy no se usa.
"""

from __future__ import annotations

import re

from apolo.services.rotulos import DatosRotulo, Pieza


def _medidas(shape) -> tuple[tuple, tuple]:
    try:
        bb = shape.bounding_box()
    except Exception:  # noqa: BLE001 — una pieza sin bbox no tiene cifras, no tumba el guion
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    centro = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
    return centro, tuple(sorted((bb.size.X, bb.size.Y, bb.size.Z)))


def _espesores_chapa(doc) -> dict[str, float]:
    """{command_id: espesor} de cada `create_sheet_metal`, con sus expresiones resueltas."""
    from apolo.commands.expressions import ExpressionError, resolve_params

    out = {}
    for cmd in doc.commands:
        if cmd.get("type") != "create_sheet_metal":
            continue
        try:
            e = resolve_params((cmd.get("params") or {}).get("espesor"), doc.variables_resolved)
        except (ExpressionError, ValueError, TypeError):
            continue
        if isinstance(e, (int, float)) and not isinstance(e, bool) and e > 0:
            out[cmd["id"]] = float(e)
    return out


def fs_cadenas(doc) -> dict[str, float]:
    """{fid de la cadena: factor de seguridad de potencia} de las cadenas que lo tienen (las
    que declaran `potencia_kw` y `rpm_a`). Las reglas agrupan los lazos iguales bajo el nombre
    del primero; un nombre con dos valores se queda con el menor."""
    from apolo.services.transmision_rules import chain_rules

    por_nombre: dict[str, float] = {}
    for regla in chain_rules(doc):
        calc = regla.get("calc") or {}
        fs, titulo = calc.get("fs"), calc.get("titulo") or ""
        prefijo = "Transmisión por cadena "
        if not isinstance(fs, (int, float)) or not titulo.startswith(prefijo):
            continue
        etiqueta = titulo[len(prefijo):]
        nombre = re.sub(r" y \d+ lazo\(s\) iguales$", "", etiqueta)
        por_nombre[nombre] = min(fs, por_nombre.get(nombre, fs))
    out = {}
    for cmd in doc.commands:
        if cmd.get("type") != "create_chain" or cmd["id"] not in doc.scene:
            continue
        nombre = (cmd.get("params") or {}).get("name") or cmd["id"]
        if nombre in por_nombre:
            out[cmd["id"]] = por_nombre[nombre]
    return out


def datos_rotulos(doc) -> DatosRotulo:
    """Los datos de los rótulos de `doc` (regenerado; reglas en el docstring del módulo)."""
    from apolo.library.catalog import CATALOG

    chapas = _espesores_chapa(doc)
    piezas = {}
    for fid, f in doc.scene.items():
        if getattr(f, "is_guide", False):
            continue
        comp = CATALOG.get(f.component) if f.component else None
        centro, medidas = _medidas(f.shape)
        piezas[fid] = Pieza(
            nombre=f.name or fid,
            ref=f.component,
            categoria=comp.category if comp else None,
            nombre_cat=comp.name if comp else None,
            specs=dict(comp.specs) if comp else {},
            largo_mm=f.cut_length if comp is not None and comp.cuttable else None,
            chapa_mm=chapas.get(f.command_id),
            centro=centro,
            medidas=medidas,
        )
    return DatosRotulo(piezas=piezas, requisitos=dict(doc.requirements or {}),
                       fs_cadena=fs_cadenas(doc))
