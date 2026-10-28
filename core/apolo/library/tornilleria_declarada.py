"""Tornillería de una unión DECLARADA sin pieza modelada (F6 de la puerta de publicación): un
`fasten(kind='perno', size='M6', qty=1, nota='tornillo autorroscante')` sostiene la máquina en la
validación, pero si nadie modela el tornillo la BOM no lo compra (revisor ciego del proyecto 8:
los autorroscantes de la guarda y los pernos del motor a los calzos). Puro: recibe la escena y los
fijadores (dicts), nunca un `Document`.

Qué se compra (la unión trae `size`, `qty` y una `nota` libre; no trae tipo ni largo):

- el FIJADOR, por la nota: «autorroscante» → tornillo autorroscante; «prisionero» → prisionero;
  «espárrago» → espárrago; DIN 7991 / ISO 10642 → tornillo avellanado; «punta roscada» / «eje
  roscado» → ninguno (el eje ES la rosca); si no, perno DIN 933 (la ficha `PERNO-HEX-M*`). Todos
  con el largo de la designación de la nota («M10x25 DIN 933», «M8x25 DIN 916») o SIN largo
  (`sin_largo`: la cotización no lo inventa y la fila lo pide);
- la TUERCA DIN 934 si la nota la nombra o dice «pasante».

Sin duplicar: una pieza de tornillería ya MODELADA cuenta para una unión si su caja cruza las de
las DOS piezas (fijador) o toca una de ellas con
el centro en la zona de la unión (las cajas de A y B ampliadas 3·d, intersecadas) o enhebrada en
un fijador que las cruza (tuerca). Dentro de un mismo PAR de piezas cada pieza cuenta una vez (dos
uniones «guarda ↔ larguero» de 1 perno piden dos); entre pares distintos se comparte: un perno
pasante que cierra techo, labio superior, labio inferior y piso sirve a las uniones de los dos
labios (proyecto 7), y la tuerca de una guarda no es de la unión vecina. Sólo falta lo que la unión
declara (`qty`) menos lo modelado que le cuenta. La tornillería que insertó el MISMO comando que
declara una unión (`join_bolted`: perno `c109_perno1` ↔ unión `jb_c109`) es de esa unión y de
ninguna otra, y una pieza de otra métrica no cuenta (F6, mezcladora 2026-10-27: los 6 M8×35 de las
guías cruzaban la caja de la caja de compuerta y le «cubrían» 6 de sus 8 M8×25).

Qué NO se compra: la nota que dice que la tornillería viene con la pieza («(incluido)», «incluido
con el detector») o que no hay perno suelto («sin perno suelto»).

El MATERIAL (F6): el campo `material_tornilleria` de la unión gana; si no, el de la nota (A2/A4
con su clase, AISI 304/316, «inox» → acero inoxidable); si no, el de la ficha (acero 8.8). Con
otro material que el de la ficha la fila pide la equivalente (`material_compra`), igual que una
ref con `set_material`.
"""

from __future__ import annotations

import re

from .catalog import CATALOG
from .designacion_comercial import categoria_de_compra
from .lints import es_nombre_de_tornilleria
from .material_compra import ajustar_fila, otro_material
from .materials import piece_role

ORIGEN = "union_declarada"
_TOL = 1.0  # mm: una caja que roza la otra la cruza
_AUTORROSCANTE = re.compile(r"autorroscante|auto-?perforante|rosca\s+chapa", re.I)
_PRISIONERO = re.compile(r"prisionero|tornillo\s+de\s+fijaci[óo]n|set\s*screw", re.I)
_EJE_ROSCADO = re.compile(r"(punta|extremo|eje|espiga)\s+(\w+\s+){0,3}roscad|roscad[oa]\s+en\s+el\s+eje",
                          re.I)
_TUERCA = re.compile(r"tuercas?|pasantes?", re.I)
_DESIGNACION = re.compile(r"(?<![A-Za-z])M\s*(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)", re.I)
_NORMA = re.compile(r"\b(DIN|ISO)\s*(\d+)\b", re.I)
_NORMAS_HEX = {"DIN 933", "DIN 931", "ISO 4017", "ISO 4014"}
_NORMAS_ALLEN = {"DIN 912", "ISO 4762"}
_NORMAS_AVELLANADO = {"DIN 7991", "ISO 10642"}
_ESPARRAGO = re.compile(r"\besp[áa]rragos?\b", re.I)
_NADA = re.compile(r"\bincluid[oa]s?\b|\bsin\s+pernos?\b", re.I)
_INOX_CLASE = re.compile(r"(?<![A-Za-z0-9])A([24])(?:-(\d{2}))?(?![\w-])")
_AISI = re.compile(r"\bAISI\s*(3\d\d)(L?)\b", re.I)
_INOX = re.compile(r"\binox", re.I)
_METRICA = re.compile(r"(?<![A-Za-z])M(\d{1,2})(?!\d)")


def material_de_nota(nota: str | None) -> str | None:
    """El material que la nota de la unión nombra («A2-70» → «acero inoxidable A2-70», «AISI
    316» → «acero inoxidable AISI 316», «inox» → «acero inoxidable»), o None."""
    nota = nota or ""
    if m := _INOX_CLASE.search(nota):
        return f"acero inoxidable A{m.group(1)}" + (f"-{m.group(2)}" if m.group(2) else "")
    if m := _AISI.search(nota):
        return f"acero inoxidable AISI {m.group(1)}{m.group(2).upper()}"
    return "acero inoxidable" if _INOX.search(nota) else None


def _metrica(feat) -> str | None:
    """«M8» de la tornillería modelada (por su ref o su nombre), o None si no se lee."""
    for texto in (getattr(feat, "component", None), getattr(feat, "name", None)):
        if texto and (m := _METRICA.search(texto)):
            return f"M{m.group(1)}"
    return None


def _admite(ref: str, largo: float | None) -> bool:
    """¿La ficha `ref` existe y vende ese largo (o el largo no se sabe)?"""
    from .largos_perno import en_catalogo, largos_catalogo

    if ref not in CATALOG:
        return False
    return largo is None and bool(largos_catalogo(ref)) or (
        largo is not None and en_catalogo(ref, largo))


def _caja(feat):
    try:
        bb = feat.shape.bounding_box()
    except Exception:  # noqa: BLE001
        return None
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def _cruza(c1, c2, tol: float = _TOL) -> bool:
    return all(c1[0][i] - tol <= c2[1][i] and c2[0][i] - tol <= c1[1][i] for i in range(3))


def _zona(ca, cb, m: float):
    lo = tuple(max(ca[0][i] - m, cb[0][i] - m) for i in range(3))
    hi = tuple(min(ca[1][i] + m, cb[1][i] + m) for i in range(3))
    return lo, hi


def _centro_en(c, zona) -> bool:
    return all(zona[0][i] <= (c[0][i] + c[1][i]) / 2.0 <= zona[1][i] for i in range(3))


def _tipo_modelado(feat) -> str | None:
    """'tuerca', 'fijador' o None (no es tornillería)."""
    comp = CATALOG.get(getattr(feat, "component", None) or "")
    if comp is not None:
        if comp.category == "tuercas":
            return "tuerca"
        if comp.category in ("pernos", "tornilleria", "tornilleria_madera"):
            return "fijador"
        return None
    nombre = getattr(feat, "name", "") or ""
    if re.match(r"tuercas?\b", piece_role(nombre), re.I):
        return "tuerca"
    if es_nombre_de_tornilleria(nombre) and categoria_de_compra(nombre) == "pernos":
        return "fijador"
    return None


def _lo_declarado(f: dict) -> tuple[dict | None, bool]:
    """(el fijador que la unión compra o None, ¿lleva tuerca?) leídos de su nota."""
    size = str(f.get("size") or "").upper()
    nota = f.get("nota") or ""
    if _NADA.search(nota):  # viene con la pieza o no hay perno suelto
        return None, False
    tuerca = bool(_TUERCA.search(nota))
    if _EJE_ROSCADO.search(nota):
        return None, tuerca
    largo, norma = None, "DIN 933"
    m = _DESIGNACION.search(nota)
    if m and f"M{m.group(1)}" == size:
        largo = float(m.group(2).replace(",", "."))
    n = _NORMA.search(nota)
    citada = f"{n.group(1).upper()} {n.group(2)}" if n else ""
    if _AUTORROSCANTE.search(nota):
        return {"ref": None, "descripcion": f"Tornillo autorroscante {size}",
                "largo": largo}, tuerca
    if _PRISIONERO.search(nota):  # con su designación («M8x25 DIN 916»), con su largo
        return {"ref": None, "descripcion": f"Prisionero {size} {citada}".strip(),
                "largo": largo}, tuerca
    if _ESPARRAGO.search(nota):  # espárrago (soldado: ISO 13918)
        return {"ref": None, "descripcion": f"Espárrago {size} {citada}".strip(),
                "largo": largo}, tuerca
    if citada in _NORMAS_AVELLANADO:
        return {"ref": None, "descripcion": f"Tornillo avellanado {size} {citada}",
                "largo": largo}, tuerca
    if n and f"{n.group(1).upper()} {n.group(2)}" in _NORMAS_HEX:
        norma = f"{n.group(1).upper()} {n.group(2)}"
    if n and f"{n.group(1).upper()} {n.group(2)}" in _NORMAS_ALLEN:  # cabeza Allen
        ref = next((r for r in (f"PERNO-{size}", f"DIN912-{size}") if _admite(r, largo)), None)
        if ref is None:
            return {"ref": None, "descripcion": f"Tornillo Allen {size} DIN 912",
                    "largo": largo}, tuerca
        return {"ref": ref, "descripcion": None, "largo": largo}, tuerca
    ref = f"PERNO-HEX-{size}"
    if ref not in CATALOG:
        return {"ref": None, "descripcion": f"Perno {size} {norma}", "largo": largo}, tuerca
    return {"ref": ref, "descripcion": None, "largo": largo, "norma": norma}, tuerca


def _fila(ref: str | None, descripcion: str | None, largo: float | None, union: str,
          categoria: str, material_union: str | None = None) -> dict:
    comp = CATALOG.get(ref or "")
    if comp is not None:
        desc = comp.name + (f" L={largo:g} mm" if largo else "")
        norma = (comp.specs or {}).get("norma", "")
        peso = round(comp.weight, 3)
        material = (comp.specs or {}).get("material", "")
        categoria = comp.category
    else:
        desc, norma, peso, material = descripcion or "", "", None, material_union or "acero"
    fila = {
        "ref": comp.ref if comp is not None else "COMPRA",
        "descripcion": desc,
        "categoria": categoria, "material": material, "norma": norma, "cantidad": 0,
        "longitud_mm": largo, "peso_unitario_kg": peso, "peso_total_kg": None,
        "origen": ORIGEN, "uniones": [union],
    }
    if comp is not None and otro_material(material_union, material):
        ajustar_fila(fila, str(material_union), material)  # la equivalente (`material_compra`)
    fila["descripcion"] += " (unión declarada sin pieza modelada)"
    if categoria != "tuercas" and largo is None:
        fila["sin_largo"] = True
        fila["aviso"] = ("largo sin declarar: escríbelo en la nota de la unión («M8x40 DIN 933») "
                         "o modela la tornillería")
    return fila


def _duenos(scene: dict, modelado: dict, fasteners: dict) -> dict[str, str]:
    """{tornillería modelada: la unión `perno` que la declara el MISMO comando que la insertó}
    (el `jb_<cmd>` de un `join_bolted` y sus `<cmd>_perno*`/`<cmd>_tuerca*`). Un comando con
    varias uniones (un `fasten` por conjuntos no inserta piezas) no reparte dueño."""
    por_cmd: dict[str, list[str]] = {}
    for f in fasteners.values():
        if f.get("kind") == "perno" and f.get("command_id"):
            por_cmd.setdefault(str(f["command_id"]), []).append(str(f.get("name") or ""))
    out = {}
    for fid in modelado:
        nombres = por_cmd.get(str(getattr(scene[fid], "command_id", None) or ""))
        if nombres and len(nombres) == 1:
            out[fid] = nombres[0]
    return out


def filas_declaradas(scene: dict, fasteners: dict) -> list[dict]:
    """Filas de BOM de la tornillería que las uniones `perno` declaran y nadie modeló (vacío si
    todo está modelado o no hay uniones con métrica)."""
    cajas: dict[str, tuple] = {}

    def caja(fid):
        if fid not in cajas:
            feat = scene.get(fid)
            cajas[fid] = _caja(feat) if feat is not None else None
        return cajas[fid]

    modelado = {fid: t for fid, feat in scene.items() if (t := _tipo_modelado(feat)) is not None}
    dueno = _duenos(scene, modelado, fasteners)
    usados: dict[tuple, set[str]] = {}  # por PAR de piezas (ver el docstring)
    filas: dict[tuple, dict] = {}
    for f in fasteners.values():
        size = str(f.get("size") or "").upper()
        if f.get("kind") != "perno" or not re.fullmatch(r"M\d{1,2}", size):
            continue
        ca, cb = caja(f.get("a")), caja(f.get("b"))
        if ca is None or cb is None:
            continue
        union = str(f.get("name") or "")
        qty = int(f.get("qty") or 1)
        fijador, con_tuerca = _lo_declarado(f)
        zona = _zona(ca, cb, 3.0 * float(size[1:]))
        faltan = {"fijador": qty if fijador is not None else 0, "tuerca": qty if con_tuerca else 0}
        par = (f.get("a"), f.get("b"))
        del_par = usados.setdefault(tuple(sorted(map(str, par))), set())
        for pieza in par:  # la unión nombra a la tornillería misma («perno ↔ eje roscado»)
            if (t := modelado.get(pieza)) is not None:
                faltan[t] = max(0, faltan[t] - 1)
        # candidatas: la propia del comando primero; la de OTRA unión o de otra métrica, nunca
        candidatas = sorted(((fid, t) for fid, t in modelado.items()
                             if dueno.get(fid, union) == union
                             and _metrica(scene[fid]) in (None, size)),
                            key=lambda kv: dueno.get(kv[0]) != union)
        # los fijadores que cruzan las dos piezas (asignados o no): la tuerca enhebrada en uno es
        # de esta unión aunque quede lejos, del otro lado de una pieza (el tirante del proyecto 8)
        cruzan = [c for fid, t in candidatas if t == "fijador" and fid not in par
                  and (c := caja(fid)) is not None and _cruza(c, ca) and _cruza(c, cb)]
        for fid, tipo in candidatas:
            if fid in del_par or fid in par or faltan[tipo] <= 0:
                continue
            c = caja(fid)
            if c is None:
                continue
            if dueno.get(fid) == union:
                propio = True  # la insertó el comando que declara la unión (join_bolted)
            elif tipo == "fijador":
                propio = _cruza(c, ca) and _cruza(c, cb)
            else:
                propio = (_cruza(c, ca) or _cruza(c, cb)) and (
                    _centro_en(c, zona) or any(_cruza(c, p, 0.0) for p in cruzan))
            if propio:
                del_par.add(fid)
                faltan[tipo] -= 1
        material = f.get("material_tornilleria") or material_de_nota(f.get("nota"))
        compras = []
        if faltan["fijador"] > 0:
            compras.append((fijador["ref"], fijador["descripcion"], fijador["largo"], "pernos",
                            faltan["fijador"]))
        if faltan["tuerca"] > 0:
            compras.append((f"TUERCA-{size}", f"Tuerca {size} DIN 934", None, "tuercas",
                            faltan["tuerca"]))
        for ref, desc, largo, cat, n in compras:
            if ref is not None and ref not in CATALOG:
                ref = None
            key = (ref, desc if ref is None else None, largo, (material or "").lower())
            if key not in filas:
                filas[key] = _fila(ref, desc, largo, union, cat, material)
            elif union not in filas[key]["uniones"]:
                filas[key]["uniones"].append(union)
            filas[key]["cantidad"] += n
    out = list(filas.values())
    for r in out:
        if r["peso_unitario_kg"] is not None:
            r["peso_total_kg"] = round(r["peso_unitario_kg"] * r["cantidad"], 3)
    out.sort(key=lambda r: (r["categoria"], r["ref"], r["longitud_mm"] or 0, r["descripcion"]))
    return out
