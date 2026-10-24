"""Lo dudoso se dice donde se cobra (plan V8.1, F4c: D-c1 y D-c2).

La cotización sumaba en silencio lo que el ERC ya sabía: un dispositivo que parece ser una pieza
3D y no la liga se cobra dos veces (el VFD, 280 + 280 USD), y un cable modelado en 3D que ningún
`add_cable` cubre no se cobra en ninguna parte. Aquí, sobre el `doc` explícito (el llamador
sostiene STATE_LOCK):

  - `cables_sin_cubrir`: los cables 3D (material «cable») que ningún add_cable cobra. Lo cubre
    el add_cable que lo LIGA (`piezas`) o, si no lo liga nadie, uno sin `piezas` con los mismos
    hilos × sección que dice su nombre («4x2.5 mm2» ↔ CABLE-4G2.5);
  - `avisos_cobro`: los avisos que tocan dinero, con el monto en riesgo y la llamada que lo
    arregla. No se descuenta nada solo: ligar es del modelo;
  - `costeo`: el costeo de `/api/costing.json` y de la cotización, con esos avisos.
"""

from __future__ import annotations

import json


def _cables_3d(doc) -> list[str]:
    from apolo.kernel.shapes import is_surface
    from apolo.library.catalog import CATALOG
    from apolo.library.materials import CABLE, resolve_material

    out = []
    for fid in sorted(doc.scene):
        f = doc.scene[fid]
        if getattr(f, "is_guide", False) or getattr(f, "component", None) or is_surface(f.shape):
            continue
        if resolve_material(f, CATALOG, doc.default_material()) == CABLE:
            out.append(fid)
    return out


def _firma_ref(cable) -> tuple[int, float] | None:
    if not cable.hilos or not cable.seccion_mm2:
        return None
    return len(cable.hilos), float(cable.seccion_mm2)


def cables_sin_cubrir(doc, m=None) -> list[dict]:
    """[{id, nombre, largo_mm, firma}] de los cables 3D que ningún add_cable cobra."""
    from apolo.library.piezas_electricas import firma_cable, recorrido_mm

    from .electrico import modelo

    m = m if m is not None else modelo(doc)
    ligadas = {fid for c in m.cables for fid in c.piezas}
    libres = {_firma_ref(c) for c in m.cables if not c.piezas} - {None}
    out = []
    for fid in _cables_3d(doc):
        f = doc.scene[fid]
        firma = firma_cable(f.name)
        if fid in ligadas or (firma is not None and _coincide(firma, libres)):
            continue
        out.append({"id": fid, "nombre": f.name or fid, "largo_mm": recorrido_mm(f.shape),
                    "firma": firma})
    return out


def _coincide(firma, libres) -> bool:
    return any(n == firma[0] and abs(s - firma[1]) < 1e-6 for n, s in libres)


def _texto_cable(c: dict) -> str:
    largo = f", recorrido ≈ {c['largo_mm'] / 1000.0:.2f} m" if c.get("largo_mm") else ""
    hilos = f" ({c['firma'][0]} hilos × {c['firma'][1]:g} mm²)" if c.get("firma") else ""
    return f"el cable 3D {c['id']} «{c['nombre']}»{hilos}{largo} no se cobra"


def regla_cables(doc, m) -> list[dict]:
    """Aviso del ERC (D-c2): un cable 3D sin add_cable que lo cubra. Sin hallazgos no suma fila."""
    return [{"regla": "cable 3D sin cobrar", "estado": "aviso",
             "detalle": (f"{_texto_cable(c)}: declara add_cable (ref del catálogo y largo_m) o "
                         f"lígalo con piezas=[\"{c['id']}\"]; hoy ningún add_cable lo cubre"),
             "recomendacion": "Cada cable modelado en 3D se compra por su add_cable: declara el "
                              "cable con su ref y largo, o liga sus tramos con `piezas`.",
             "norma": "criterio de diseño", "elementos": [c["id"]]}
            for c in cables_sin_cubrir(doc, m)]


def _doble_cobro(doc, m) -> list[dict]:
    """Un aviso por ref: los dispositivos sin ligar cuya ref es la de piezas 3D sin ligar. Monto
    en riesgo = unidades cobradas dos veces (mín. de las dos cuentas) × el precio de la ref."""
    from apolo.library.costing import costo_unitario_ref

    from .electrico import piezas_sin_ligar

    por_ref: dict[str, dict] = {}
    for d, fids in piezas_sin_ligar(doc, m):
        r = por_ref.setdefault(d.ref, {"disp": [], "fids": fids})
        r["disp"].append(d)
    out = []
    for ref, r in sorted(por_ref.items()):
        n = min(len(r["disp"]), len(r["fids"]))
        ud = costo_unitario_ref(ref)
        monto = round(n * ud, 2) if ud is not None else None
        d0, fid0 = r["disp"][0], r["fids"][0]
        arreglo = f"edit_command('{d0.id}', {json.dumps({'pieza': fid0})})"
        designaciones = ", ".join(d.designacion for d in r["disp"])
        piezas = ", ".join(r["fids"][:4]) + ("…" if len(r["fids"]) > 4 else "")
        out.append({
            "tipo": "pieza sin ligar", "ref": ref, "monto_en_riesgo_usd": monto,
            "detalle": (f"{designaciones} ({ref}) no liga su pieza 3D ({piezas}): se cobra dos "
                        f"veces, {n} × {ud:,.2f} USD." if ud is not None else
                        f"{designaciones} ({ref}) no liga su pieza 3D ({piezas}): se cobraría dos "
                        "veces (ref sin precio)."),
            "arreglo": f"Liga cada dispositivo a su pieza: {arreglo}",
            "elementos": [*(d.designacion for d in r["disp"]), *r["fids"][:4]]})
    return out


def avisos_cobro(doc, cables: list[dict] | None = None) -> list[dict]:
    """Los avisos que tocan dinero: [{tipo, detalle, monto_en_riesgo_usd, arreglo, elementos}].
    Vacío si no hay nada dudoso (la cotización queda como antes). `cables` = el
    `cables_sin_cubrir` ya calculado."""
    from .electrico import modelo, tiene_carril

    m = modelo(doc)
    avisos = _doble_cobro(doc, m) if tiene_carril(doc) else []
    for c in cables if cables is not None else cables_sin_cubrir(doc, m):
        avisos.append({"tipo": "cable 3D sin cobrar", "monto_en_riesgo_usd": None,
                       "detalle": f"{_texto_cable(c)}: ningún add_cable lo cubre.",
                       "arreglo": "Declara add_cable (ref y largo_m) o lígalo: add_cable(…, "
                                  f"piezas=[\"{c['id']}\"])",
                       "elementos": [c["id"]]})
    return avisos


def monto_en_riesgo(avisos: list[dict]) -> float:
    return round(sum(a.get("monto_en_riesgo_usd") or 0.0 for a in avisos), 2)


def filas_de_extensiones(doc) -> tuple[list[dict], list[dict]]:
    """(filas costeadas, avisos) de las fuentes de costeo de las extensiones cargadas
    (`Extension.costeo`; plan puntos-de-extension-entregables, D2). Una fuente que lanza o una
    fila que no tiene la forma no se cobra y lo dice un aviso de cobro: nunca tumba el costeo."""
    from apolo.library import costeo_extension as C

    filas: list[dict] = []
    avisos: list[dict] = []
    for nombre, fuente in C.vigentes():
        try:
            salida = list(fuente.filas(doc) or ())
        except Exception as exc:  # noqa: BLE001 — el código de la extensión puede lanzar
            salida, motivo = [], f"{type(exc).__name__}: {exc}"
            avisos.append(_aviso_extension(nombre, fuente.id, f"la fuente no corrió ({motivo})"))
        for d in salida:
            try:
                filas.append(C.fila(nombre, fuente, d))
            except ValueError as exc:
                avisos.append(_aviso_extension(nombre, fuente.id, str(exc)))
    return filas, avisos


def _aviso_extension(nombre: str, fid: str, motivo: str) -> dict:
    return {"tipo": "fila de extensión descartada", "monto_en_riesgo_usd": None,
            "detalle": f"la fuente de costeo «{fid}» de la extensión «{nombre}» dio algo que no se "
                       f"cobra: {motivo}"[:500],
            "arreglo": "Corrige la extensión: ese concepto NO está en el precio.",
            "elementos": [fid]}


def costeo(doc) -> dict:
    """El costeo del documento (escena + tablero + las filas de las extensiones, al final) con sus
    avisos de cobro. Sin avisos, el dict de siempre (`rows`, `totales`); con ellos, además `avisos`
    y `monto_en_riesgo_usd`; con extensiones de costeo cargadas, `extensiones`
    ({nombre: version_costeo})."""
    from apolo.library import costeo_extension
    from apolo.library.costing import scene_costing

    from .bom_filas import filas_extra
    from .incluidas import incluidas

    cables = cables_sin_cubrir(doc)
    sin = {c["id"] for c in cables}
    de_ext, avisos_ext = filas_de_extensiones(doc)
    data = scene_costing(doc.scene, doc.default_material(), filas_extra(doc) + de_ext, sin or None,
                         incluidas(doc) or None)
    if costeo_extension.DE_EXTENSION:
        data["extensiones"] = costeo_extension.versiones()
    avisos = avisos_cobro(doc, cables) + avisos_ext
    if avisos:
        data["avisos"] = avisos
        data["monto_en_riesgo_usd"] = monto_en_riesgo(avisos)
    return data
