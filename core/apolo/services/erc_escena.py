"""Las reglas del ERC que miran la ESCENA además del circuito (plan V8.5 F5b). El llamador
sostiene `STATE_LOCK`; sólo corren con carril eléctrico (`electrico.reglas_erc`).

- «pieza de seguridad sin circuito» (ERROR): una pieza de catálogo de la familia de seguridad
  (`modelo.tipo` seta, resguardo o relé de seguridad) en la escena que ningún dispositivo liga
  con `pieza` (ni la dibujó un `layout_tablero`): al pulsarla no para nada y la BOM la compra.
  Venía de la faja 77 (F5: tres setas sueltas con `delivery_check` VERDE).
- «altura de los mandos» (aviso): el mando de un seccionador, una seta, un pulsador o un
  selector, medido en el centro de su pieza (la ligada o la que dibujó el layout), fuera de
  `ALTURA_MANDO_MM` sobre el nivel de servicio. El seccionador por IEC 60204-1 §5.3.4 (su mando
  entre 0,6 y 1,7 m); el resto, criterio de diseño con la misma banda. El nivel de servicio es el
  PISO (`nivel_servicio`): lo más bajo de las piezas ancladas a tierra, o de la máquina si no hay
  anclajes; se dice como supuesto (una plataforma de servicio no se ve en el modelo).
"""

from __future__ import annotations

#: Las familias de seguridad (`electrico.modelo.tipo`) y cómo se nombran.
SEGURIDAD = {"seta": "seta de emergencia", "resguardo": "interruptor de resguardo",
             "rele_seguridad": "relé de seguridad"}
#: Los mandos cuya altura se mide (`modelo.tipo`) → su norma.
MANDOS = {"seccionador": "IEC 60204-1 §5.3.4 (verificar con el texto vigente)",
          "seta": "criterio de diseño", "pulsador": "criterio de diseño", "selector": "criterio de diseño"}
#: Banda de altura del mando sobre el nivel de servicio (mm): IEC 60204-1 §5.3.4 para el
#: seccionador; la misma como criterio de diseño para los demás mandos.
ALTURA_MANDO_MM = (600.0, 1700.0)

SIN_CIRCUITO = "pieza de seguridad sin circuito"
ALTURA = "altura de los mandos"


def _bbox(f):
    bb = f.shape.bounding_box()
    return bb.min.Z, bb.max.Z


def _ficha_modelo(ref: str | None) -> dict:
    from apolo.library.catalog import CATALOG

    comp = CATALOG.get(ref or "")
    e = getattr(comp, "electrico", None) if comp is not None else None
    return dict(e.modelo or {}) if e is not None else {}


# ── pieza de seguridad sin circuito ──────────────────────────────────────────────────────


def piezas_seguridad_sueltas(doc, m) -> list[tuple[str, str, str]]:
    """[(fid, ref, tipo)] de las piezas de seguridad de la escena que ningún dispositivo liga."""
    from .tablero import piezas_del_layout

    ligadas = {d.pieza for d in m.dispositivos if d.pieza} | piezas_del_layout(doc)
    out = []
    for fid in sorted(doc.scene):
        f = doc.scene[fid]
        ref = getattr(f, "component", None)
        if not ref or fid in ligadas or getattr(f, "is_guide", False):
            continue
        tipo = _ficha_modelo(ref).get("tipo")
        if tipo in SEGURIDAD:
            out.append((fid, ref, tipo))
    return out


def regla_seguridad(doc, m) -> list[dict]:
    filas = []
    for fid, ref, tipo in piezas_seguridad_sueltas(doc, m):
        f = doc.scene[fid]
        cmd = getattr(f, "command_id", None) or fid
        filas.append({
            "regla": SIN_CIRCUITO, "estado": "error",
            "detalle": (f"{fid} «{f.name or fid}» ({ref}, {SEGURIDAD[tipo]}) está en la máquina y ningún "
                        "dispositivo del circuito la liga: al accionarla no para nada, y la BOM la compra. "
                        f"Lígala a su dispositivo (add_device con ref «{ref}» y pieza «{fid}», o "
                        f"edit_command del que ya la nombra, con sus conductores en serie con la cadena "
                        f"de parada) o bórrala: remove_commands(['{cmd}'], con_dependientes=true)"),
            "recomendacion": "Toda seta, interruptor de resguardo o relé de seguridad de la máquina va en "
                             "el circuito de parada; uno suelto da una seguridad que no existe.",
            "norma": "criterio de diseño", "elementos": [fid]})
    return filas


# ── altura de los mandos ─────────────────────────────────────────────────────────────────


def nivel_servicio(doc) -> tuple[float | None, str]:
    """(z del piso en mm, cómo se tomó): lo más bajo de las piezas ancladas a tierra (`ground`) o,
    sin anclajes, lo más bajo de la máquina."""
    anclas = [g.get("feature") for g in (doc.grounds or {}).values()]
    zs = [_bbox(doc.scene[a])[0] for a in anclas if a in doc.scene and doc.scene[a].shape is not None]
    if zs:
        z = min(zs)
        return z, (f"nivel de servicio = el piso en z {z:.0f} mm (lo más bajo de las piezas ancladas a "
                   "tierra); si el operador trabaja sobre una plataforma, mide desde ella")
    zs = [_bbox(f)[0] for f in doc.scene.values()
          if f.shape is not None and not getattr(f, "is_guide", False)]
    if not zs:
        return None, ""
    z = min(zs)
    return z, (f"nivel de servicio = z {z:.0f} mm, lo más bajo de la máquina (ninguna pieza está anclada a "
               "tierra con ground); si el operador trabaja sobre una plataforma, mide desde ella")


def alturas_mandos(doc, m) -> tuple[list[tuple], str]:
    """([(dispositivo, tipo, fid, altura en mm)] de los mandos con pieza en la escena, supuesto del
    piso). Sin mandos medibles, ([], "")."""
    from .tablero import dibujados

    del_layout = dibujados(doc, m)
    cand = []
    for d in m.dispositivos:
        tipo = (d.modelo or {}).get("tipo")
        if tipo not in MANDOS:
            continue
        fid = d.pieza or del_layout.get(d.designacion)
        f = doc.scene.get(fid) if fid else None
        if f is not None and f.shape is not None:
            cand.append((d, tipo, fid, f))
    if not cand:
        return [], ""
    piso, supuesto = nivel_servicio(doc)
    if piso is None:
        return [], ""
    out = []
    for d, tipo, fid, f in cand:
        z0, z1 = _bbox(f)
        out.append((d, tipo, fid, round((z0 + z1) / 2 - piso, 1)))
    return out, supuesto


def regla_alturas(doc, m) -> tuple[list[dict], str | None]:
    """(filas, supuesto del piso o None si no hay mandos que medir)."""
    medidos, supuesto = alturas_mandos(doc, m)
    if not medidos:
        return [], None
    lo, hi = ALTURA_MANDO_MM
    filas = []
    for d, tipo, fid, h in medidos:
        if lo <= h <= hi:
            continue
        que = "bajo" if h < lo else "sobre"
        filas.append({
            "regla": ALTURA, "estado": "aviso",
            "detalle": (f"el mando de {d.designacion} ({d.ref}, {tipo}) queda a {h / 1000:.2f} m del nivel de "
                        f"servicio ({fid}, centro de la pieza), {que} la banda de {lo / 1000:.1f}–"
                        f"{hi / 1000:.1f} m. {supuesto}. Sube o baja el aparato (o el tablero) hasta la banda"
                        + (", o lleva el seccionador a la placa con mando prolongado en la puerta"
                           if tipo == "seccionador" else "")),
            "recomendacion": "El mando del seccionador va entre 0,6 y 1,7 m sobre el nivel de servicio "
                             "(IEC 60204-1 §5.3.4); setas, pulsadores y selectores, en la misma banda, al "
                             "alcance del puesto del operador.",
            "norma": MANDOS[tipo], "elementos": [d.designacion, fid]})
    return filas, supuesto
