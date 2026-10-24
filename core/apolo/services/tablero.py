"""El tablero armado de un documento (plan V8.5, D15): lo que `layout_tablero` dejó en la escena,
leído desde el `Document`. El llamador sostiene `STATE_LOCK`.

- `dibujados`: los dispositivos que el layout dibujó (designación → id de su cuerpo). Ya cuentan
  en la escena con su ref: la BOM del carril (`bom_electrico.filas_electricas`) y el aviso
  «pieza sin ligar» del ERC no los cuentan otra vez (F1b: sin esto el variador se cobraba dos
  veces, 280 + 280 USD, como un dispositivo sin ligar).
- `regla_orden` (el lint de D1/A15): la firma del layout cambia con cada aparato de su
  ubicación, y lo que venga después se re-ejecuta al editar uno. Después de él sólo caben el
  carril, otro layout y las uniones que sujetan el gabinete (`fasten`, `ground`,
  `create_group`): lo demás es aviso (los `set_variable` el documento los sube a la cabecera).

F3b suma aquí lo que lee el panel (veredicto, ítems y detalle), la única fuente para el visor,
`get_circuit tablero=true` y el ERC.
"""

from __future__ import annotations

LAYOUT = "layout_tablero"
#: lo que puede ir DESPUÉS del layout sin costo
DESPUES_SIN_COSTO = frozenset({LAYOUT, "fasten", "ground", "create_group"})


def _ubicacion(texto) -> str:
    t = str(texto or "").strip()
    return f"+{t}" if t and not t.startswith("+") else t


def layouts(doc) -> list[tuple[str, str]]:
    """[(id del comando, ubicación)] de los `layout_tablero` VIVOS (su gabinete está en la escena)."""
    return [(c["id"], _ubicacion((c.get("params") or {}).get("ubicacion")))
            for c in doc.commands
            if c.get("type") == LAYOUT and f"{c['id']}_gabinete" in doc.scene]


def dibujados(doc, m=None) -> dict[str, str]:
    """{designación: id del cuerpo} de los dispositivos que dibujó un layout (los ligados a una
    `pieza` no: ya cuentan por su pieza)."""
    from apolo.library.catalog import CATALOG
    from apolo.library.electrico.armado import clave_aparato

    from .electrico import modelo

    vivos = layouts(doc)
    if not vivos:
        return {}
    m = m if m is not None else modelo(doc)
    out: dict[str, str] = {}
    for cid, u in vivos:
        for d in m.dispositivos:
            if d.ubicacion != u or d.pieza:
                continue
            comp = CATALOG.get(d.ref)
            if comp is not None and comp.electrico is not None and comp.electrico.simbolo == "gabinete":
                out[d.designacion] = f"{cid}_gabinete"
                continue
            base = f"{cid}_{clave_aparato(d.designacion)}"
            for fid in (base, f"{base}_1"):
                if fid in doc.scene:
                    out[d.designacion] = fid
                    break
    return out


def piezas_del_layout(doc) -> set[str]:
    """Los ids de todo lo que armó un layout (sus piezas llevan su command_id)."""
    ids = {cid for cid, _ in layouts(doc)}
    return {fid for fid, f in doc.scene.items() if getattr(f, "command_id", None) in ids}


def regla_orden(doc) -> list[dict]:
    """Aviso del ERC: un `layout_tablero` que no es el último comando de la escena."""
    from apolo.doc.carril import es_carril

    filas = []
    cmds = doc.commands
    for i, c in enumerate(cmds):
        if c.get("type") != LAYOUT:
            continue
        despues = [x for x in cmds[i + 1:] if not es_carril(x) and x.get("type") not in DESPUES_SIN_COSTO]
        if not despues:
            continue
        lista = ", ".join(f"{x['id']} ({x.get('type')})" for x in despues[:5])
        lista += f" y {len(despues) - 5} más" if len(despues) > 5 else ""
        u = _ubicacion((c.get("params") or {}).get("ubicacion"))
        filas.append({
            "regla": "layout del tablero al final", "estado": "aviso",
            "detalle": (f"el layout_tablero {c['id']} ({u}) no es el último de la escena: después "
                        f"vienen {lista}. Editar un aparato de {u} re-ejecuta el layout Y esos "
                        f"{len(despues)} comando(s). "
                        f"Rehazlo al final: remove_commands(['{c['id']}']) y run_command "
                        "layout_tablero con los mismos params (sus uniones al gabinete, después)"),
            "recomendacion": "El layout del tablero va al final de la escena; detrás, sólo el carril "
                             "y las uniones que sujetan el gabinete (fasten, ground).",
            "norma": "criterio de diseño", "elementos": [c["id"], *(x["id"] for x in despues[:5])]})
    return filas
