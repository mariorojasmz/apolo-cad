"""Filas de BOM del modelo eléctrico (plan V8.1, D10), con la forma de `bom_from_scene`.

La BOM de siempre sale de la ESCENA: un dispositivo sin cuerpo 3D no aparecería. Estas filas
suman lo que el tablero compra y la escena no tiene, sin duplicar:

  - un dispositivo LIGADO a una pieza (`pieza`) ya cuenta en la escena: no entra; tampoco uno
    que dibujó un `layout_tablero` (V8.5: su cuerpo lleva la ref);
  - uno SIN pieza entra como fila de catálogo, agrupado por ref (una bornera, por borne);
  - la red de suministro (`specs.suministro`) no se compra: no entra;
  - los conductores sueltos entran por METRO, por `tipo`, con el `largo_m` declarado o, dentro
    de un tablero armado, con el RUTEADO (V8.5 F2: `largo_origen` dice cuánto es de cada uno);
    los que no tienen ninguno van en una fila SIN largo y con `aviso` (su costo queda en blanco:
    no se inventa); un puente o un conductor sin `tipo` no se compra por metro (el sin tipo avisa);
  - un conductor dentro de un cable no se compra aparte: se compra el CABLE, por metro, igual;
    sin `largo_m`, con el CALCULADO por su recorrido de campo (`add_cable.por`, V8.5 F4);
  - los tubos de aire (`add_tubo`, V8.9 D1) por METRO y por ref con su `largo_m` declarado; los
    que no lo tienen, en una fila «sin largo» con aviso, como los conductores. Un dispositivo de
    aire sin pieza (cilindro, válvula, FRL) entra como cualquier dispositivo;
  - V8.9 F7b: un tubo SIN largo hacia un silenciador es el silenciador ROSCADO directo al puerto
    (no se compra tubo); cada extremo de tubo en un puerto roscado suma su RACOR recto macho
    (rosca del puerto × Ø del tubo, `_racores`).

Cada fila lleva `origen: "electrico"`; `sin_largo: True` le dice al costeo que no la estime.
Recibe el `ModeloElectrico` (puro), nunca un documento.
"""

from __future__ import annotations

from .catalog import CATALOG

ORIGEN = "electrico"
PUENTE = "puente"


def _fila(comp, cantidad: int, largo_mm: float | None = None, aviso: str | None = None) -> dict:
    specs = comp.specs or {}
    if comp.cuttable and largo_mm:
        peso_ud = comp.weight * largo_mm / 1000.0
        desc = f"{comp.name} — {largo_mm / 1000.0:g} m"
    else:
        peso_ud = None if comp.cuttable else comp.weight
        desc = comp.name + (" — largo sin declarar" if comp.cuttable else "")
    fila = {
        "ref": comp.ref,
        "descripcion": desc,
        "categoria": comp.category,
        "material": specs.get("material", ""),
        "norma": specs.get("norma", ""),
        "cantidad": cantidad,
        "longitud_mm": round(largo_mm, 1) if largo_mm else None,
        "peso_unitario_kg": round(peso_ud, 3) if peso_ud is not None else None,
        "peso_total_kg": round(peso_ud * cantidad, 3) if peso_ud is not None else None,
        "origen": ORIGEN,
    }
    if aviso:
        fila["sin_largo"] = True
        fila["aviso"] = aviso
    return fila


def _por_metro(ref: str, largos: list[float | None], que: str,
               ruteados: list[float] | None = None) -> list[dict]:
    comp = CATALOG.get(ref)
    if comp is None:
        return []
    ruteados = ruteados or []
    declarados = [x for x in largos if x]
    faltan = len(largos) - len(declarados)
    total = sum(declarados) + sum(ruteados)
    filas = [_fila(comp, 1, total * 1000.0)] if total else []
    if ruteados:  # V8.5 F2: de dónde sale cada metro
        filas[0]["largo_origen"] = {"ruteado_m": round(sum(ruteados), 3), "n_ruteados": len(ruteados),
                                    "declarado_m": round(sum(declarados), 3), "n_declarados": len(declarados)}
    if faltan:
        filas.append(_fila(comp, faltan, aviso=(
            f"{faltan} {que} sin largo declarado: declara el largo para comprarlo y costearlo "
            "(no se estima)")))
    return filas


def _roscados_directos(modelo) -> set[int]:
    """id() de los tubos SIN largo con un extremo en un silenciador: el silenciador va roscado
    directo al puerto de la otra punta (V8.9 F7b): ni tubo ni racor que comprar."""
    sil = {d.designacion for d in modelo.dispositivos
           if getattr(getattr(d, "neumatico", None), "tipo", None) == "silenciador"}
    return {id(t) for t in getattr(modelo, "tubos", ()) if not t.largo_m
            and any(e.rpartition(":")[0] in sil for e in (t.desde, t.hasta))}


def _racores(modelo, directos: set[int]) -> list[dict]:
    """Un racor recto macho instantáneo por cada extremo de tubo en un puerto ROSCADO (V8.9 F7b,
    defecto 12: la BOM del aire no servía para comprar), por rosca del puerto × Ø exterior del
    tubo, con la ref del catálogo que los declara (`specs.racor_rosca`/`racor_tubo_mm`); sin ref,
    una fila sin costo con su aviso (no se inventa). Un puerto «Ø6» ya es instantáneo: nada."""
    roscas = {(d.designacion, p.id): p.rosca for d in modelo.dispositivos for p in getattr(d, "puertos", ())}
    cuenta: dict[tuple[str, float], int] = {}
    for t in getattr(modelo, "tubos", ()):
        if id(t) in directos or not t.D_ext_mm:
            continue
        for extremo in (t.desde, t.hasta):
            des, _, pid = extremo.rpartition(":")
            rosca = roscas.get((des, pid))
            if rosca and not rosca.startswith("Ø"):
                clave = (rosca, float(t.D_ext_mm))
                cuenta[clave] = cuenta.get(clave, 0) + 1
    refs = {(str(c.specs["racor_rosca"]), float(c.specs["racor_tubo_mm"])): c for c in CATALOG.values()
            if (c.specs or {}).get("racor_rosca") and (c.specs or {}).get("racor_tubo_mm")}
    filas = []
    for (rosca, d), n in sorted(cuenta.items()):
        comp = refs.get((rosca, d))
        if comp is not None:
            filas.append(_fila(comp, n))
            continue
        filas.append({
            "ref": "RACOR-SIN-REF", "descripcion": f"Racor recto macho {rosca} × tubo Ø{d:g}",
            "categoria": "aire_comprimido", "material": "", "norma": "", "cantidad": n,
            "longitud_mm": None, "peso_unitario_kg": None, "peso_total_kg": None,
            "origen": ORIGEN, "sin_largo": True,
            "aviso": f"{n} racor(es) {rosca} × Ø{d:g} sin ref en el catálogo: cotízalos con el proveedor",
        })
    return filas


def filas_electricas(modelo, dibujados: frozenset = frozenset(),
                     ruteados: dict | None = None, cables_calculados: dict | None = None) -> list[dict]:
    """Las filas de BOM del `ModeloElectrico` (vacía si no hay carril), en orden estable:
    dispositivos por ref, cables y conductores por ref. `dibujados` = las designaciones que un
    `layout_tablero` dibujó en la escena (V8.5): cuentan por su cuerpo, como una `pieza`.
    `ruteados` = {id del conductor: m} que salen del RUTEO de un tablero armado (V8.5 F2: los de
    dentro, sueltos y sin largo declarado): se compran por ese largo; el declarado manda (D3).
    `cables_calculados` = {id del add_cable: m} de su recorrido de campo (V8.5 F4), igual."""
    if modelo is None:
        return []
    filas: list[dict] = []
    por_ref: dict[str, int] = {}
    for d in modelo.dispositivos:
        comp = CATALOG.get(d.ref)
        if d.pieza or d.designacion in dibujados or comp is None or (comp.specs or {}).get("suministro"):
            continue
        por_ref[d.ref] = por_ref.get(d.ref, 0) + (d.cantidad if d.bornera else 1)
    filas += [_fila(CATALOG[ref], n) for ref, n in sorted(por_ref.items())]
    cables: dict[str, list] = {}
    cables_ruteo: dict[str, list] = {}
    calculados = cables_calculados or {}
    for c in modelo.cables:
        if not c.largo_m and calculados.get(c.id):
            cables_ruteo.setdefault(c.ref, []).append(calculados[c.id])
            cables.setdefault(c.ref, [])
            continue
        cables.setdefault(c.ref, []).append(c.largo_m)
    for ref, largos in sorted(cables.items()):
        filas += _por_metro(ref, largos, "cable(s)", cables_ruteo.get(ref))
    conductores: dict[str, list] = {}
    por_ruteo: dict[str, list] = {}
    ruteados = ruteados or {}
    sin_tipo = 0
    for c in modelo.conductores:
        if c.cable or c.tipo == PUENTE:
            continue
        if not c.tipo:
            sin_tipo += 1
            continue
        if not c.largo_m and ruteados.get(c.id):
            por_ruteo.setdefault(c.tipo, []).append(ruteados[c.id])
            conductores.setdefault(c.tipo, [])
            continue
        conductores.setdefault(c.tipo, []).append(c.largo_m)
    for ref, largos in sorted(conductores.items()):
        filas += _por_metro(ref, largos, "conductor(es)", por_ruteo.get(ref))
    tubos: dict[str, list] = {}  # V8.9 D1: el tubo de aire, por metro (el largo declarado manda)
    directos = _roscados_directos(modelo)
    for t in getattr(modelo, "tubos", ()):
        if id(t) not in directos:
            tubos.setdefault(t.ref, []).append(t.largo_m)
    for ref, largos in sorted(tubos.items()):
        filas += _por_metro(ref, largos, "tubo(s) de aire")
    filas += _racores(modelo, directos)
    if sin_tipo:
        filas.append({
            "ref": "CONDUCTOR-SIN-TIPO", "descripcion": "Conductor sin tipo de catálogo",
            "categoria": "conexion_electrica", "material": "", "norma": "", "cantidad": sin_tipo,
            "longitud_mm": None, "peso_unitario_kg": None, "peso_total_kg": None,
            "origen": ORIGEN, "sin_largo": True,
            "aviso": f"{sin_tipo} conductor(es) sin tipo: declara el conductor del catálogo "
                     "(p. ej. COND-H07VK-1.5) para comprarlo y costearlo",
        })
    return filas
