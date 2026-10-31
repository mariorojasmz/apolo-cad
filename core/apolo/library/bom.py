"""Lista de materiales (BOM) calculada desde la escena.

Las piezas de catálogo se agrupan por referencia + longitud de corte; las
piezas a medida (geometría propia) se agrupan por el comando que las creó. Una pieza a mano
COMERCIAL (rol de compra o norma con designación: `designacion_comercial`) sale con ref `COMPRA`
en la categoría de compra del catálogo («pernos», «tornilleria»…), no en «a medida» (F6).

Una COMPRA con norma se agrupa por su DESIGNACIÓN (rol + medida + norma, `designacion`) + largo
+ material, no por el nombre de cada pieza ni por su geometría: «Perno M10x25 DIN 933 del
tensado» (4) y «… del eje» (40) son UNA línea de 44, con `ubicaciones` [{nombre, cantidad}] que
dice dónde va cada una (F6: el mismo artículo salía en dos líneas).

Una ref de catálogo con OTRO material asignado (`set_material`) se compra en ese material: fila
propia con el material asignado, `material_ficha` y la designación «… en <material> (la ref de
catálogo es de <ficha>: pedir la equivalente)» (`material_compra`).

Plan bom-de-compra-fiel (`bom_compra.py`): la chapa con ficha sale con espesor, desarrollo y
norma (D1); un perfil de catálogo, con su largo y su corte MEDIDOS, y la copia de un patrón
agrupa con su original (D2); lo cortado de la misma ref con otros taladros no comparte fila y
las filas que se describen igual llevan su `marca` (D3).

Plan hallazgos-del-revisor-en-la-puerta (D4, D5): la compra que se pide por largo (varilla, barra:
`se_pide_por_largo`) lleva el suyo (el nominal o, sin él, el MEDIDO); la compra con «tipo Marca
código» lleva su `codigo`; la banda sin fin, su designación medida (`banda_lazo.campos_banda`); la
madera, la norma que escribe su material; y un grupo «(compra)» es UNA fila (`compra_grupos`). Si
cada fila alcanza para comprar o cortar lo juzga la puerta (`bom_comprable.motivo`).

Plan pie-nivelador (D6): la fila de un pie nivelador de catálogo lleva su ficha de compra (rosca ×
largo del vástago, base, material, carga de servicio, tuerca incluida) en la descripción y en
`ficha` (`pies_ficha.py`).

Lo EXISTENTE del sitio («Calamina existente», «Mesa del cliente», «(no suministrado)»:
`suministro.no_suministrada`) no sale: la máquina no lo suministra.
"""

from __future__ import annotations

import csv
import io
import re

from apolo.kernel.caja import caja
from apolo.kernel.shapes import is_surface

from .banda_lazo import campos_banda, es_banda, largo_de_lazo
from .bom_compra import (
    campos_chapa,
    forma_de,
    marcar,
    medida_perfil,
    norma_de_material,
    variante,
    volumen,
)
from .catalog import CATALOG
from .compra_grupos import compras as compras_de_grupos
from .compra_grupos import miembros as miembros_de_compra
from .designacion_comercial import (
    categoria_de_compra, codigo_de_fabricante, designacion, es_comercial, nombre_de_compra,
    norma_del_nombre, se_pide_por_largo,
)
from .incluidas import vastagos_incluidos
from .largo_tornilleria import largo_de_compra_con_aviso, largo_nominal_a_medida
from .material_compra import ajustar_fila, material_de_compra
from .materials import CABLE, density, resolve_material
from .peso_ficha import peso_de_ficha
from .pies_ficha import ficha as ficha_pie
from .pies_ficha import texto as texto_pie
from .piezas_electricas import recorrido_mm
from .suministro import no_suministrada

# sufijos de instancia que añaden los patrones/espejos/copias: " (2)", " (1,2)",
# " (espejo)", " (copia)". Se quitan para agrupar piezas idénticas en una fila.
_INSTANCE_SUFFIX = re.compile(r"\s*\((?:espejo|copia|\d+(?:,\s*\d+)*)\)")

#: ref de la pieza COMERCIAL modelada a mano (la de la cédula): se compra, no se fabrica (F6)
COMPRA = "COMPRA"


def _base_name(name: str) -> str:
    return _INSTANCE_SUFFIX.sub("", name or "").strip()


def _medida(comp, cut) -> str:
    """« L=… mm» de lo cortado; « carrera … mm» de un cilindro neumático (V8.9 D5: la ref se
    pide con su carrera)."""
    if not cut:
        return ""
    neu = getattr(comp, "neumatico", None)
    if neu is not None and neu.tipo == "cilindro":
        return f" carrera {cut:g} mm"
    return f" L={cut:g} mm"


def _eslabones(comp, cut) -> str:
    """« (30 eslabones)» en una cadena de rodillos cortada (lo que se pide en el mostrador:
    plan cadenas-pinones D7); vacío en todo lo demás."""
    paso = (comp.specs or {}).get("paso")
    if not (comp.cuttable and cut and paso and "kg_m" in (comp.specs or {})):
        return ""
    return f" ({round(cut / paso)} eslabones)"


def fila_de_grupo(c: dict, by_group: bool = False) -> dict:
    """La fila de BOM de un grupo de compra (`compra_grupos.compras`, D5 de hallazgos-del-revisor):
    ref `COMPRA`, su designación y los sólidos que trae en `incluye`."""
    return {
        "ref": COMPRA, "descripcion": c["designacion"], "categoria": c["categoria"],
        "material": c["material"], "norma": c["norma"], "cantidad": c["cantidad"],
        "longitud_mm": None, "peso_unitario_kg": c["peso_ud_kg"], "peso_total_kg": None,
        "_rep": c["_rep"], "grupos_compra": list(c["grupos"]), "incluye": list(c["incluye"]),
        **({"codigo": c["codigo"]} if c["codigo"] else {}),
        **({"grupo": c["grupos"][0]} if by_group else {}),
    }


def bom_from_scene(scene: dict, default_material: str | None = None,
                   by_group: bool = False, incluidas: dict | None = None) -> list[dict]:
    """BOM agrupado por referencia+corte (catálogo) o firma geométrica (a medida).
    Con `by_group=True` (V5.2) cada fila lleva además su `grupo` (sub-ensamblaje) y
    las piezas iguales de grupos DISTINTOS salen en filas separadas — para subtotales
    por sub-ensamblaje. El default es byte-idéntico al histórico.
    `incluidas` = {id de pieza: id de la pieza que la trae} (V8.5 F2: la puerta y la placa que
    vienen con su gabinete): no salen en fila propia; la fila de quien las trae las nombra en
    `incluye`. El vástago de un cilindro neumático viene siempre con su ref (V8.9 F2,
    `incluidas.vastagos_incluidos`): no hace falta pasarlo."""
    rows: dict[tuple, dict] = {}
    memo: dict = {}  # medidas compartidas por las instancias intactas (`cutlist_medida`)
    variantes: dict[tuple, list] = {}  # D3: volúmenes vistos por clave de ref + corte
    incluidas = {**vastagos_incluidos(scene), **(incluidas or {})}
    traen: dict[str, list[str]] = {}
    for sid, quien in incluidas.items():
        if sid in scene:
            traen.setdefault(quien, []).append(scene[sid].name or sid)
    de_grupo = miembros_de_compra(scene)  # D5: la compra en varios sólidos, una fila por grupo
    for sid, feat in scene.items():
        if is_surface(feat.shape) or getattr(feat, "is_guide", False):
            continue  # superficie desnuda o boceto-guía = geometría de construcción, no es pieza
        if sid in incluidas or sid in de_grupo:
            continue  # viene con otra pieza de compra o en su grupo de compra (su fila la nombra)
        if no_suministrada(feat.name):
            continue  # existente del sitio o del cliente: la máquina no la suministra
        grp = getattr(feat, "group", None) if by_group else None
        component = getattr(feat, "component", None)
        if component and component in CATALOG:
            comp = CATALOG[component]
            cut = getattr(feat, "cut_length", None)
            largo, aviso = cut, ""
            if cut is None and not comp.cuttable:  # tornillería: se compra por su largo
                largo, aviso = largo_de_compra_con_aviso(feat, comp)
                if (comp.specs or {}).get("length") is None:
                    cut = largo  # a medida: el largo va en la fila (la ficha fija ya lo nombra)
            miter = getattr(feat, "miter", None)
            mtr = tuple(miter) if miter else None  # ingleteado ≠ recto del mismo largo
            angs = ""
            if mtr:  # α None en un extremo = ese lado recto (0°)
                angs = " ∠" + "/".join(f"{a:g}°" if a is not None else "0°" for a in mtr)
            medido = medida_perfil(feat, comp, memo)  # D2: el corte MEDIDO manda
            if medido is not None:
                cut = largo = medido["largo"]
                mtr, angs = medido["clave"], medido["angulos"]
                aviso = medido["aviso"] or aviso
            key = (component, round(largo, 1) if largo else None, mtr, grp) if by_group else (
                component, round(largo, 1) if largo else None, mtr)
            mat_compra, ficha_otra = material_de_compra(feat, comp)  # set_material gana (F6)
            if ficha_otra:
                key = key + ("material", mat_compra.lower())
            if comp.cuttable:  # D3: lo cortado de la misma ref con otros taladros, otra fila
                key = key + ("variante", variante(variantes.setdefault(key, []), volumen(feat)))
            if key not in rows:
                unit_weight = peso_de_ficha(comp, cut)  # un cilindro: + por_mm × carrera (V8.9)
                rows[key] = {
                    "ref": comp.ref,
                    "descripcion": comp.name + _medida(comp, cut)
                    + _eslabones(comp, cut) + angs + texto_pie(comp),  # el pie, con su ficha
                    "categoria": comp.category,
                    "material": (comp.specs or {}).get("material", ""),
                    "norma": (comp.specs or {}).get("norma", ""),
                    "cantidad": 0,
                    "longitud_mm": largo,
                    "peso_unitario_kg": round(unit_weight, 3),
                    "peso_total_kg": 0.0,
                    "_rep": sid,  # pieza representante (globos en lámina)
                    **({"grupo": grp} if by_group else {}),
                    **({"aviso": aviso} if aviso else {}),
                    **({"ficha": pie} if (pie := ficha_pie(comp)) else {}),
                }
                if ficha_otra:  # la equivalente en el material asignado (`material_compra`)
                    ajustar_fila(rows[key], mat_compra, ficha_otra)
            elif aviso and "aviso" not in rows[key]:
                rows[key]["aviso"] = aviso
            rows[key]["cantidad"] += 1
            if sid in traen:
                rows[key].setdefault("incluye", []).extend(traen[sid])
        else:
            mat = resolve_material(feat, CATALOG, default_material)
            base = donde = _base_name(feat.name)
            comercial = es_comercial(base)  # F6: se COMPRA → categoría de compra, no «a medida»
            desig = designacion(base) if comercial else None
            if comercial:
                base = desig or nombre_de_compra(base)
            vol = None
            dims = None
            try:
                vol = float(feat.shape.volume)
                bb = caja(feat.shape)
                dims = tuple(sorted((
                    round(bb.max.X - bb.min.X, 1),
                    round(bb.max.Y - bb.min.Y, 1),
                    round(bb.max.Z - bb.min.Z, 1),
                )))
            except Exception:
                pass
            # agrupa por firma geométrica (nombre base sin sufijo de instancia +
            # material + volumen + bbox): patrones, espejos y copias idénticos colapsan
            # en una fila con su cantidad, sin confundir piezas DISTINTAS.
            key = ("__custom__", base, mat, round(vol, 1) if vol is not None else None, dims)
            por_largo = comercial and se_pide_por_largo(base)  # D4: la varilla, por su largo
            nominal = largo_nominal_a_medida(feat)
            if desig:  # la misma compra, venga de donde venga (F6)
                key = ("__compra__", desig.lower(), mat, nominal if nominal is not None or
                       not por_largo else (dims[-1] if dims else None))
            if by_group:
                key = key + (grp,)
            if key not in rows:
                largo = dims[-1] if dims else None
                if mat == CABLE:  # V8.1 F4c (D-c2): el RECORRIDO, no la mayor cota del bbox
                    largo = recorrido_mm(feat.shape) or largo
                elif es_banda(feat.name) and (lazo := largo_de_lazo(feat.shape)):
                    largo = round(lazo, 1)  # la banda se compra por su LAZO, no por su caja
                elif nominal is not None:
                    largo = nominal  # «Perno … M12x150»: se compra por 150, no por 157,5 medido
                elif comercial and not por_largo and categoria_de_compra(base) not in (
                        "pernos", "bandas"):
                    largo = None  # arandela, seeger, rodamiento: se piden por designación, sin corte
                rows[key] = {
                    "ref": COMPRA if comercial else "A-MEDIDA",
                    "descripcion": base,
                    "categoria": categoria_de_compra(base) if comercial else "a medida",
                    "material": mat,
                    # comercial modelada: «… DIN 933»; del nombre ENTERO (la compra declarada
                    # trae su norma en el paréntesis que `nombre_de_compra` conserva)
                    "norma": norma_del_nombre(donde),
                    "cantidad": 0,
                    "longitud_mm": largo,
                    "peso_unitario_kg": round(vol * density(mat), 3) if vol is not None else None,
                    "peso_total_kg": None,
                    "_rep": sid,
                    **({"grupo": grp} if by_group else {}),
                    **({"_donde": {}} if desig else {}),
                }
                if comercial and (codigo := codigo_de_fabricante(donde)):  # D4: «tipo Marca …»
                    rows[key]["codigo"] = codigo
                if comercial and es_banda(feat.name) and (b := campos_banda(feat.shape, mat)):
                    rows[key].update(b)  # D4: la banda sin fin, por lo que mide (su lazo)
                chapa = None if comercial else campos_chapa(feat, mat)
                if chapa is not None:  # D1: espesor, desarrollo y norma de su ficha
                    fila = rows[key]
                    fila["descripcion"] += chapa.pop("texto")
                    fila["longitud_mm"] = chapa["desarrollo_mm"][1]
                    fila.update(chapa)
                elif not comercial and not rows[key]["norma"]:  # D3 de hallazgos-del-revisor
                    rows[key]["norma"] = norma_de_material(mat, feat.name, forma_de(feat.name))
            rows[key]["cantidad"] += 1
            if desig:
                rows[key]["_donde"][donde] = rows[key]["_donde"].get(donde, 0) + 1
    for c in compras_de_grupos(scene, default_material):  # D5: un grupo «(compra)», una fila
        rows[("__grupo_compra__",) + c["clave"]] = fila_de_grupo(c, by_group)

    out = []
    for row in rows.values():
        donde = row.pop("_donde", None)
        if donde and (len(donde) > 1 or next(iter(donde)) != row["descripcion"]):
            row["ubicaciones"] = [{"nombre": n, "cantidad": c} for n, c in sorted(donde.items())]
        if row["peso_unitario_kg"] is not None:
            row["peso_total_kg"] = round(row["peso_unitario_kg"] * row["cantidad"], 3)
        out.append(row)
    marcar(out, scene)  # D3: filas que se describen igual y son piezas distintas
    out.sort(key=lambda r: (r["categoria"], r["ref"], r["longitud_mm"] or 0))
    return out


def bom_to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    writer.writerow(["Ref", "Descripción", "Categoría", "Cantidad", "Longitud (mm)", "Peso ud (kg)", "Peso total (kg)"])
    total = 0.0
    for r in rows:
        writer.writerow([
            r["ref"], r["descripcion"], r["categoria"], r["cantidad"],
            r["longitud_mm"] if r["longitud_mm"] is not None else "",
            r["peso_unitario_kg"] if r["peso_unitario_kg"] is not None else "",
            r["peso_total_kg"] if r["peso_total_kg"] is not None else "",
        ])
        total += r["peso_total_kg"] or 0
    writer.writerow(["", "", "", "", "", "TOTAL", round(total, 3)])
    return buf.getvalue()
