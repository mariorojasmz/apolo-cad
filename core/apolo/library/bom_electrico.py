"""Filas de BOM del modelo eléctrico (plan V8.1, D10), con la forma de `bom_from_scene`.

La BOM de siempre sale de la ESCENA: un dispositivo sin cuerpo 3D no aparecería. Estas filas
suman lo que el tablero compra y la escena no tiene, sin duplicar:

  - un dispositivo LIGADO a una pieza (`pieza`) ya cuenta en la escena: no entra;
  - uno SIN pieza entra como fila de catálogo, agrupado por ref (una bornera, por borne);
  - la red de suministro (`specs.suministro`) no se compra: no entra;
  - los conductores sueltos entran por METRO, por `tipo`, con el `largo_m` declarado; los que
    no lo declaran van en una fila SIN largo y con `aviso` (su costo queda en blanco: no se
    inventa); un puente o un conductor sin `tipo` no se compra por metro (el sin tipo avisa);
  - un conductor dentro de un cable no se compra aparte: se compra el CABLE, por metro, igual.

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


def _por_metro(ref: str, largos: list[float | None], que: str) -> list[dict]:
    comp = CATALOG.get(ref)
    if comp is None:
        return []
    declarados = [x for x in largos if x]
    faltan = len(largos) - len(declarados)
    filas = [_fila(comp, 1, sum(declarados) * 1000.0)] if declarados else []
    if faltan:
        filas.append(_fila(comp, faltan, aviso=(
            f"{faltan} {que} sin largo declarado: declara el largo para comprarlo y costearlo "
            "(no se estima)")))
    return filas


def filas_electricas(modelo) -> list[dict]:
    """Las filas de BOM del `ModeloElectrico` (vacía si no hay carril), en orden estable:
    dispositivos por ref, cables y conductores por ref."""
    if modelo is None:
        return []
    filas: list[dict] = []
    por_ref: dict[str, int] = {}
    for d in modelo.dispositivos:
        comp = CATALOG.get(d.ref)
        if d.pieza or comp is None or (comp.specs or {}).get("suministro"):
            continue
        por_ref[d.ref] = por_ref.get(d.ref, 0) + (d.cantidad if d.bornera else 1)
    filas += [_fila(CATALOG[ref], n) for ref, n in sorted(por_ref.items())]
    cables: dict[str, list] = {}
    for c in modelo.cables:
        cables.setdefault(c.ref, []).append(c.largo_m)
    for ref, largos in sorted(cables.items()):
        filas += _por_metro(ref, largos, "cable(s)")
    conductores: dict[str, list] = {}
    sin_tipo = 0
    for c in modelo.conductores:
        if c.cable or c.tipo == PUENTE:
            continue
        if not c.tipo:
            sin_tipo += 1
            continue
        conductores.setdefault(c.tipo, []).append(c.largo_m)
    for ref, largos in sorted(conductores.items()):
        filas += _por_metro(ref, largos, "conductor(es)")
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
