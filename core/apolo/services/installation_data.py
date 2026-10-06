"""Datos de la lámina de INSTALACIÓN (V7.6 fase C): la hoja que el cliente lleva a la obra
civil. Resuelve sobre el documento los apoyos, la masa y el COG, la huella, las alturas, las
holguras de servicio y el suministro; el reparto de carga lo hace el motor puro
`library/engineering/installation.py` y la lámina la compone `drawing/installation.py`. El
llamador sostiene STATE_LOCK. Reglas: `services/CLAUDE.md` § Instalación."""

from __future__ import annotations

from apolo.services.roles import BED_RE, SERVICE_RE


def installation_data(doc) -> tuple[dict, dict]:
    """(datos, escena_anclada) para la lámina de INSTALACIÓN (V7.6 fase C). Resuelve la
    geometría —apoyos con `ground`, masa y COG reales, huella, alturas de interfaz,
    holguras de servicio y suministro de catálogo— y delega el reparto de carga al motor
    puro. Devuelve ({}, {}) si el proyecto no declara ningún ground: sin anclajes no hay
    plano de instalación que valga (mejor ausente que inventado). Bajo STATE_LOCK."""
    from apolo.library.catalog import CATALOG
    from apolo.library.engineering.installation import G_M_S2, anchor_loads
    from apolo.library.engineering.mass import scene_mass_properties

    from apolo.library.lints import _is_bolt

    supports = []
    for g in doc.grounds.values():
        fid = g.get("feature")
        feat = doc.scene.get(fid)
        if feat is None:
            continue
        # la TORNILLERÍA anclada no es un APOYO: los pernos de anclaje del 38 también
        # llevan ground, y contarlos como puntos de apoyo DILUYE la carga (30 «apoyos»
        # en vez de 6 placas → 5× menos por punto, y la obra dimensionaría de menos)
        if _is_bolt(feat, CATALOG):
            continue
        try:
            bb = feat.shape.bounding_box()
        except Exception:
            continue
        supports.append({"id": fid, "name": getattr(feat, "name", fid),
                         "x": (bb.min.X + bb.max.X) / 2.0, "y": (bb.min.Y + bb.max.Y) / 2.0})
    if not supports:
        return {}, {}

    # TODA la máquina, también lo oculto: la visibilidad es vista, no le quita peso al anclaje
    total = scene_mass_properties(doc.scene, CATALOG, default_material=doc.default_material(),
                                  include_hidden=True)["total"]
    masa = float(total.get("masa_kg") or 0.0)
    com = total.get("com_mm")
    carga = float((doc.requirements or {}).get("carga_kg") or 0.0)
    peso_n = (masa + carga) * G_M_S2
    cog = (float(com[0]), float(com[1])) if com and len(com) >= 2 else None
    anclaje = anchor_loads(supports, peso_n, cog)

    xs = [s["x"] for s in supports]
    ys = [s["y"] for s in supports]
    huella = {"largo": round(max(xs) - min(xs), 1), "ancho": round(max(ys) - min(ys), 1)}

    # alturas de interfaz: la superficie que transporta (cama/mesa/banda) y el punto más alto
    z_top = z_all = 0.0
    for feat in doc.scene.values():
        try:
            bb = feat.shape.bounding_box()
        except Exception:
            continue
        z_all = max(z_all, float(bb.max.Z))
        if BED_RE.search(getattr(feat, "name", "") or ""):
            z_top = max(z_top, float(bb.max.Z))

    # holgura de SERVICIO: lo que hay que dejar libre a un lado para extraer las piezas
    # que se mantienen (motorreductor, tambores) = su propia extensión transversal
    servicio = []
    for feat in doc.scene.values():
        nombre = getattr(feat, "name", "") or ""
        if not SERVICE_RE.search(nombre):
            continue
        try:
            bb = feat.shape.bounding_box()
        except Exception:
            continue
        servicio.append({"pieza": nombre, "holgura_mm": round(float(bb.max.Y - bb.min.Y), 0)})
    servicio = sorted(servicio, key=lambda s: -s["holgura_mm"])[:2]

    suministro = []
    for feat in doc.scene.values():
        comp = CATALOG.get(getattr(feat, "component", None) or "")
        if comp is None or "motorreductor" not in (comp.category or ""):
            continue
        # las claves del catálogo NO son homogéneas en mayúsculas («potencia_kW») →
        # búsqueda case-insensitive; sin potencia tabulada no se inventa el dato
        specs = comp.specs or {}
        low = {str(k).lower(): v for k, v in specs.items()}
        pot = low.get("potencia_kw") or low.get("kw")
        unidad = "kW"
        if not pot:
            pot, unidad = low.get("potencia_hp") or low.get("hp"), "HP"
        if pot:
            suministro.append({"concepto": "Suministro eléctrico", "valor": f"{pot} {unidad}",
                               "nota": str(specs.get("tipo", ""))[:28]})
        break

    datos = {
        "masa_kg": round(masa, 1), "carga_kg": carga or None,
        "anclaje": anclaje, "huella_mm": huella,
        "altura_trabajo_mm": round(z_top, 1) or None,
        "altura_total_mm": round(z_all, 1) or None,
        "servicio": servicio, "suministro": suministro,
        "notas": ["Nivelar los apoyos antes de anclar; el reparto supone piso rígido.",
                  "Cotas de anclaje entre EJES, desde el origen de máquina."],
    }
    anclada = {s["id"]: doc.scene[s["id"]] for s in supports if s["id"] in doc.scene}
    return datos, anclada
