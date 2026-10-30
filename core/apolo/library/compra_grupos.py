"""Una compra modelada en VARIOS sólidos es UNA fila (D5 del plan hallazgos-del-revisor-en-la-puerta).
Puro sobre la escena: lo leen la BOM (`bom.bom_from_scene`, y por ella el costeo) y la cédula
(`cutlist.hardware_schedule`); la lista de corte salta sus sólidos.

Una bisagra modelada en dos medias hojas salía como 4 + 4 «medias bisagras», y un compás de 5
sólidos como 5 filas de compra. La compra entera se DECLARA: un GRUPO (`create_group`) cuyo nombre
lleva «compra» en un paréntesis (`designacion_comercial.compra_declarada`; de un subgrupo «A/B»,
el último tramo) se compra ENTERO. Nunca se adivina por contacto ni por nombre de las piezas.

- Sus sólidos (los miembros DIRECTOS: `Feature.group`, el derivado del regenerate) no salen
  sueltos en la BOM, el costeo, la cédula ni la lista de corte.
- Una fila por grupo IGUAL: la misma designación (la del nombre del grupo sin la marca ni el sufijo
  de instancia «(2)»: `designacion` si trae norma, si no `nombre_de_compra`) y las mismas piezas
  (ref o rol de cada sólido y su volumen). Cantidad = grupos iguales.
- La norma: la que nombra el grupo; si no nombra ninguna y todos sus sólidos son de catálogo con
  la MISMA norma de ficha (las dos medias bisagras EN 1935), ésa. El código de fabricante, el de
  su nombre (`codigo_de_fabricante`). El peso, la suma de sus sólidos.

Lo que el grupo no puede ser (sólidos con taladros de `join_bolted` hacia piezas de fuera: eso se
fabrica, no se compra) lo dice la puerta (`bom.comprable`, medido en
`services/calidad_bom.py`): aquí no se mira el log.
"""

from __future__ import annotations

from .catalog import CATALOG
from .designacion_comercial import (
    categoria_de_compra, codigo_de_fabricante, compra_declarada, designacion, nombre_de_compra,
    norma_del_nombre, sin_marca_de_compra,
)


def tramo(nombre: str | None) -> str:
    """El último tramo del nombre de un grupo («Mesa/Bisagra (compra)» → «Bisagra (compra)»)."""
    return (nombre or "").rsplit("/", 1)[-1].strip()


def es_grupo_de_compra(nombre: str | None) -> bool:
    return compra_declarada(tramo(nombre))


def designacion_de_grupo(nombre: str | None) -> str:
    """Lo que se pide: el nombre del grupo sin la marca de compra ni el sufijo de instancia."""
    from .bom import _base_name

    base = _base_name(sin_marca_de_compra(tramo(nombre)))
    return designacion(base) or nombre_de_compra(base)


def _es_pieza(feat) -> bool:
    from apolo.kernel.shapes import is_surface

    return not (getattr(feat, "is_guide", False) or is_surface(feat.shape))


def miembros(scene: dict) -> dict[str, str]:
    """{id de sólido: grupo de compra que lo trae} (sólo los miembros directos)."""
    return {fid: g for fid, f in scene.items()
            if (g := getattr(f, "group", None)) and es_grupo_de_compra(g) and _es_pieza(f)}


def por_grupo(scene: dict) -> dict[str, list[str]]:
    """{grupo de compra: [ids de sus sólidos]} en el orden de la escena."""
    out: dict[str, list[str]] = {}
    for fid, g in miembros(scene).items():
        out.setdefault(g, []).append(fid)
    return out


def _volumen(feat) -> float | None:
    try:
        return float(feat.shape.volume)
    except Exception:  # noqa: BLE001 — sin volumen medible: la pieza pesa 0 aquí
        return None


def _peso(feat, default_material) -> tuple[float, str]:
    """(kg, material) de un sólido: la ficha de catálogo o volumen × densidad."""
    from .materials import density, resolve_material
    from .peso_ficha import peso_de_ficha

    comp = CATALOG.get(getattr(feat, "component", None) or "")
    mat = resolve_material(feat, CATALOG, default_material)
    if comp is not None:
        return float(peso_de_ficha(comp, getattr(feat, "cut_length", None)) or 0.0), mat
    vol = _volumen(feat)
    return (vol * density(mat) if vol is not None else 0.0), mat


def _firma(scene: dict, fids: list[str]) -> tuple:
    """Las piezas del grupo: (ref, volumen) de cada sólido, sin orden (la geometría, no el nombre:
    «… (+Y)» y «… (-Y)» son la misma pieza)."""
    partes = []
    for fid in fids:
        f = scene[fid]
        vol = _volumen(f)
        partes.append((getattr(f, "component", None) or "", round(vol) if vol is not None else None))
    return tuple(sorted(partes, key=repr))


def _norma(grupo: str, scene: dict, fids: list[str]) -> str:
    norma = norma_del_nombre(tramo(grupo))
    if norma:
        return norma
    comps = [CATALOG.get(getattr(scene[f], "component", None) or "") for f in fids]
    normas = {(c.specs or {}).get("norma", "") for c in comps if c is not None}
    return normas.pop() if all(c is not None for c in comps) and len(normas) == 1 else ""


def compras(scene: dict, default_material: str | None = None,
            visibles: bool = False) -> list[dict]:
    """Una entrada por grupo de compra IGUAL: {clave, designacion, norma, codigo, categoria,
    material, cantidad, peso_ud_kg, _rep, grupos, incluye}. `visibles` (la cédula) cuenta sólo
    los grupos con algún sólido visible."""
    out: dict[tuple, dict] = {}
    for grupo, fids in por_grupo(scene).items():
        if visibles and not any(getattr(scene[f], "visible", True) for f in fids):
            continue
        desig = designacion_de_grupo(grupo)
        clave = (desig.lower(), _firma(scene, fids))
        c = out.get(clave)
        if c is None:
            pesos = [_peso(scene[f], default_material) for f in fids]
            c = out[clave] = {
                "clave": clave, "designacion": desig, "norma": _norma(grupo, scene, fids),
                "codigo": codigo_de_fabricante(tramo(grupo)),
                "categoria": categoria_de_compra(desig),
                "material": max(pesos, key=lambda p: p[0])[1] if pesos else "",
                "cantidad": 0, "peso_ud_kg": round(sum(p for p, _m in pesos), 3),
                "_rep": fids[0], "grupos": [], "incluye": [scene[f].name for f in fids],
            }
        c["cantidad"] += 1
        c["grupos"].append(grupo)
    return list(out.values())
