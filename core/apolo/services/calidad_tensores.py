"""Insumos del control del TENSOR (plan puerta-de-publicacion, D3): los lazos del documento
(bandas y cadenas) con los mecanismos de tensado RECONOCIDOS que actúan sobre cada uno. El
control puro y el formato del lazo están en `library/calidad/tensor.py`. El llamador sostiene
STATE_LOCK.

Un tensor se reconoce por lo que ES, nunca por el nombre de una pieza:
- `create_take_up` / `create_drive_roller` (también dentro de un `create_roller_conveyor`): la
  carrera es lo que el eje corre entre las dos aletas del soporte, MEDIDA sobre el eje de cada
  perno tensor (`calidad_pernos`); el perno pasa el control de agarre en los dos extremos;
- una unidad de catálogo con su carrera de ficha (`specs.carrera_mm`: las UCT) o de la familia
  `tensores_trotadora` (sin carrera tabulada → SIN_EVALUAR la carrera);
- las ranuras del portamotor de la plantilla de rodillos (`tensado_mm` de su disposición) para
  la cadena motriz `{cmd}_cad_m`; los lazos rodillo a rodillo `{cmd}_cad{k}` no llevan tensor:
  van con `centros_fijos` (medidos) y el control decide (D3b);
- el metadato `doc.tensores` [{piezas, carrera_mm, eje}] (si entre sus piezas hay un perno, se
  le mide el agarre en la carrera como al de un take-up).

Un tensor actúa sobre un lazo si su caja toca la del lazo (banda, estirada a lo largo del eje de
sus tambores: el tensor va en el muñón) o la de un piñón (cadena), con `_HOLGURA_MM` de margen.
"""

from __future__ import annotations

import re

_HOLGURA_MM = 60.0
_ALCANCE_EJE_MM = 300.0  # cuánto sale el muñón de un tambor más allá del ancho de la banda
_BANDA_RE = re.compile(r"^(bandas?|cintas?)\b", re.I)  # sobre `piece_role` (como cosim_bandas)
_TAKE_UP = ("create_take_up", "create_drive_roller")
#: Un lazo rodillo a rodillo de la plantilla de rodillos (`receta_rodillos_cadena._cadenas`).
_RODILLO_A_RODILLO = re.compile(r"(.+)_cad\d+")


def _caja(shape):
    bb = shape.bounding_box()
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def _union_cajas(cajas):
    cajas = [c for c in cajas if c is not None]
    if not cajas:
        return None
    return (tuple(min(c[0][k] for c in cajas) for k in range(3)),
            tuple(max(c[1][k] for c in cajas) for k in range(3)))


def _tocan(a, b, holgura: float = _HOLGURA_MM) -> bool:
    return a is not None and b is not None and all(
        a[0][k] - holgura <= b[1][k] and a[1][k] + holgura >= b[0][k] for k in range(3))


def _caja_de(doc, fid):
    f = doc.scene.get(fid)
    try:
        return _caja(f.shape) if f is not None and f.shape is not None else None
    except Exception:  # noqa: BLE001
        return None


def eje_de_banda(shape):
    """La normal de las caras laterales del lazo (= el eje de sus tambores), o None."""
    for f in shape.faces():
        try:
            if len(f.wires()) >= 2 and "PLANE" in str(f.geom_type).upper():
                n = f.normal_at()
                return (n.X, n.Y, n.Z)
        except Exception:  # noqa: BLE001
            continue
    return None


def _caja_lazo(caja, eje):
    """La caja de la banda estirada `_ALCANCE_EJE_MM` a lo largo del eje de los tambores: el
    tensor va en el muñón del eje, FUERA del ancho de la banda."""
    if caja is None or eje is None:
        return caja
    k = max(range(3), key=lambda i: abs(eje[i]))
    lo, hi = list(caja[0]), list(caja[1])
    lo[k] -= _ALCANCE_EJE_MM
    hi[k] += _ALCANCE_EJE_MM
    return tuple(lo), tuple(hi)


def largo_de_banda(shape) -> tuple[float | None, str]:
    """(largo de la línea media del lazo, motivo si None). Un anillo de ancho w (entre sus dos
    caras laterales planas con agujero) y espesor t: V = P·t·w y A = 2·P·w + 2·P·t, así que
    P = (A − 2V/w) / (2w) — exacto para el lazo de pista del super-comando."""
    planas = []
    for f in shape.faces():
        try:
            if len(f.wires()) < 2 or "PLANE" not in str(f.geom_type).upper():
                continue
            n, c = f.normal_at(), f.center()
            planas.append(((n.X, n.Y, n.Z), (c.X, c.Y, c.Z)))
        except Exception:  # noqa: BLE001
            continue
    if len(planas) < 2:
        return None, "la banda no es un lazo cerrado (sin caras laterales con agujero)"
    (n, c0), (_, c1) = planas[0], planas[1]
    w = abs(sum(n[k] * (c1[k] - c0[k]) for k in range(3)))
    try:
        area, vol = float(shape.area), float(shape.volume)
    except Exception:  # noqa: BLE001
        return None, "no se pudo medir el área y el volumen de la banda"
    if w <= 1.0:
        return None, "no se pudo medir el ancho de la banda"
    largo = (area - 2.0 * vol / w) / (2.0 * w)
    return (largo, "") if largo > 0 else (None, "medida del lazo incoherente")


def lazos_banda(doc) -> list[dict]:
    from apolo.library.materials import piece_role

    out = []
    for fid, f in doc.scene.items():
        if getattr(f, "is_guide", False) or f.shape is None:
            continue
        if not (fid.endswith("_banda") or _BANDA_RE.match(piece_role(getattr(f, "name", "")))):
            continue
        largo, motivo = largo_de_banda(f.shape)
        if largo is None and "lazo cerrado" in motivo:
            continue  # una banda plana suelta no es un lazo
        out.append({"id": fid, "nombre": f.name, "tipo": "banda", "largo_mm": largo,
                    "motivo": motivo, "piezas": [fid],
                    "_caja": _caja_lazo(_caja_de(doc, fid), eje_de_banda(f.shape))})
    return out


def _plantilla_motriz(doc, cmd_id: str) -> float | None:
    """`tensado_mm` del portamotor de la plantilla de rodillos que corre `cmd_id`."""
    from apolo.commands.exec_rodillos_cadena import disposicion_de
    from apolo.commands.expressions import resolve_params
    from apolo.commands.models_rodillos_cadena import CreateRollerConveyorParams

    padre = cmd_id.rsplit("_", 2)[0] if cmd_id.endswith("_cad_m") else None
    cmd = next((c for c in doc.commands if c["id"] == padre
                and c["type"] == "create_roller_conveyor"), None)
    if cmd is None:
        return None
    try:
        p = CreateRollerConveyorParams.model_validate(
            resolve_params(cmd["params"], doc.variables_resolved), extra="ignore")
        m = disposicion_de(p).motriz
    except Exception:  # noqa: BLE001 — params rotos: el regenerate ya lo dijo
        return None
    return None if m is None else float(m.tensado_mm)


def lazos_cadena(doc) -> list[dict]:
    from apolo.commands.exec_rodillos_cadena import comandos_efectivos
    from apolo.commands.exec_transmision import medir_transmision
    from apolo.commands.expressions import resolve_params
    from apolo.commands.models_transmision import CreateChainParams

    from apolo.commands.exec_transmision import TOL_CENTROS_MM

    rodillos = {c["id"] for c in doc.commands if c["type"] == "create_roller_conveyor"}
    out = []
    for cmd in comandos_efectivos(doc.commands, doc.variables_resolved):
        if cmd["type"] != "create_chain":
            continue
        nombre = (cmd.get("params") or {}).get("name") or cmd["id"]
        t = None
        try:
            p = CreateChainParams.model_validate(
                resolve_params(cmd["params"], doc.variables_resolved), extra="ignore")
            t = medir_transmision(doc.scene, p)
            largo, motivo = t.largo_mm, ""
            pinones = [p.pinon_a, p.pinon_b]
        except Exception as exc:  # noqa: BLE001 — la regla de cadenas ya da el error
            largo, motivo, pinones = None, f"no se pudo medir la cadena: {exc}", []
        lazo = {"id": cmd["id"], "nombre": nombre, "tipo": "cadena", "largo_mm": largo,
                "motivo": motivo, "piezas": [cmd["id"], *pinones],
                "_caja": _union_cajas([_caja_de(doc, x) for x in pinones])}
        rr = _RODILLO_A_RODILLO.fullmatch(cmd["id"])
        if t is not None and rr and rr.group(1) in rodillos:  # D3b: lazo de centros fijos
            lazo["centros_fijos"] = {"eslabones": t.eslabones, "centros_mm": t.centros,
                                     "exactos_mm": t.centros_exactos, "paso_mm": t.paso,
                                     "tolerancia_mm": TOL_CENTROS_MM}
        tensado = _plantilla_motriz(doc, cmd["id"])
        lazo["_tensores"] = [] if tensado is None else [{
            "tipo": "plantilla", "id": cmd["id"], "nombre": "ranuras del portamotor",
            "carrera_mm": tensado, "motivo": "", "pernos": []}]
        out.append(lazo)
    return out


def _proyeccion(caja, origen, dir_) -> tuple[float, float]:
    ts = [sum((p[k] - origen[k]) * dir_[k] for k in range(3))
          for p in ((x, y, z) for x in (caja[0][0], caja[1][0]) for y in (caja[0][1], caja[1][1])
                    for z in (caja[0][2], caja[1][2]))]
    return min(ts), max(ts)


def perno_tensor(doc, insumo: dict, movil: str) -> dict | None:
    """{insumo, movil, antes, despues}: cuánto corre `movil` sobre el eje del perno hasta tocar
    lo que cruza antes y después (la carrera de un tensor de tornillo). La pieza tensada se
    proyecta por su caja (exacta para un eje redondo ⟂ al perno, alineado al mundo)."""
    caja = _caja_de(doc, movil)
    if caja is None or not insumo.get("evaluable") or "eje" not in insumo:
        return None
    m0, m1 = _proyeccion(caja, insumo["eje"]["asiento"], insumo["eje"]["dir"])
    otros = [t for t in insumo["tramos"] if t["fid"] != movil and t["rol"] != "tuerca"]
    antes = [t["t1"] for t in otros if t["t1"] <= m0 + 0.5]
    despues = [t["t0"] for t in otros if t["t0"] >= m1 - 0.5]
    despues += [m["t0"] for m in insumo.get("mas_alla", []) if m["fid"] != movil]
    if not antes or not despues:
        return None
    return {"insumo": insumo, "movil": movil, "antes": max(0.0, m0 - max(antes)),
            "despues": max(0.0, min(despues) - m1)}


def _tensor_de_pernos(doc, tid, nombre, pernos_ids, movil, tipo, carrera_decl=None) -> dict:
    from .calidad_pernos import insumos_pernos

    insumos = insumos_pernos(doc, set(pernos_ids)) if pernos_ids else []
    pernos = [pt for i in insumos if (pt := perno_tensor(doc, i, movil)) is not None]
    carreras = [p["antes"] + p["despues"] for p in pernos]
    carrera = min(carreras) if carreras else carrera_decl
    motivo = "" if carrera is not None else "no se pudo medir la carrera sobre el perno tensor"
    if carrera_decl is not None and carreras and carrera_decl > min(carreras) + 0.5:
        motivo = (f"declara {carrera_decl:g} mm pero entre las paredes corre {min(carreras):.1f}")
        carrera = min(carreras)
    return {"tipo": tipo, "id": tid, "nombre": nombre, "carrera_mm": carrera, "motivo": motivo,
            "pernos": pernos, "_piezas": [movil, *pernos_ids]}


def tensores_reconocidos(doc, medir: bool = True) -> list[dict]:
    """Los tensores del documento con su caja (`_caja`). Con `medir=False` no tira rayos (sólo
    reconoce: la adherencia de Eytelwein no necesita la carrera)."""
    from apolo.commands.exec_rodillos_cadena import comandos_efectivos
    from apolo.library.catalog import CATALOG

    out = []
    for cmd in comandos_efectivos(doc.commands, doc.variables_resolved):
        if cmd["type"] not in _TAKE_UP:
            continue
        cid = cmd["id"]
        fids = [f for f in doc.scene if f.startswith(f"{cid}_")]
        pernos = [f for f in fids if re.fullmatch(rf"{re.escape(cid)}_perno\d+", f)]
        nombre = (cmd.get("params") or {}).get("name") or cmd["type"]
        t = (_tensor_de_pernos(doc, cid, nombre, pernos, f"{cid}_eje", "take_up") if medir else
             {"tipo": "take_up", "id": cid, "nombre": nombre, "carrera_mm": None, "motivo": "",
              "pernos": []})
        t["_caja"] = _union_cajas([_caja_de(doc, f) for f in fids])
        out.append(t)
    for fid, f in doc.scene.items():
        comp = CATALOG.get(getattr(f, "component", None) or "")
        if comp is None:
            continue
        specs = comp.specs or {}
        if specs.get("carrera_mm") is None and comp.category != "tensores_trotadora":
            continue
        carrera = specs.get("carrera_mm")
        out.append({"tipo": "catalogo", "id": fid, "nombre": f.name,
                    "carrera_mm": None if carrera is None else float(carrera),
                    "motivo": "" if carrera is not None else
                    f"la ficha {comp.ref} no tabula su carrera de tensado",
                    "pernos": [], "_caja": _caja_de(doc, fid)})
    for k, decl in enumerate(getattr(doc, "tensores", None) or []):
        piezas = [p for p in decl.get("piezas", []) if p in doc.scene]
        caja = _union_cajas([_caja_de(doc, p) for p in piezas])
        nombre = decl.get("nota") or f"tensor declarado {k + 1}"
        pernos = [p for p in piezas if _es_perno(doc, p)]
        movil = next((p for p in piezas if p not in pernos), None)
        if medir and pernos and movil:
            t = _tensor_de_pernos(doc, f"tensores[{k}]", nombre, pernos, movil, "declarado",
                                  float(decl["carrera_mm"]))
        else:
            t = {"tipo": "declarado", "id": f"tensores[{k}]", "nombre": nombre,
                 "carrera_mm": float(decl["carrera_mm"]), "motivo": "", "pernos": []}
        t["_caja"], t["_piezas"] = caja, piezas
        out.append(t)
    return out


def _es_perno(doc, fid) -> bool:
    from apolo.library.catalog import CATALOG

    from .calidad_pernos import tipo_de_tornilleria

    return tipo_de_tornilleria(doc.scene[fid], CATALOG) is not None


def lazos(doc, medir: bool = True, cadenas: bool = True) -> list[dict]:
    """Los lazos con sus tensores (formato de `library/calidad/tensor.py`)."""
    tensores = tensores_reconocidos(doc, medir)
    out = []
    for lz in lazos_banda(doc) + (lazos_cadena(doc) if cadenas else []):
        propios = lz.pop("_tensores", [])
        caja = lz.pop("_caja")
        actuan = [t for t in tensores
                  if _tocan(t["_caja"], caja) or lz["id"] in t.get("_piezas", [])]
        lz["tensores"] = propios + [{k: v for k, v in t.items() if not k.startswith("_")}
                                    for t in actuan]
        out.append(lz)
    return out


def poner_tensores(doc, valor) -> list[dict]:
    """Reemplaza el metadato `doc.tensores` (manifest, fuera del log: raíz § «Metadato ≠
    comando»). Valida forma y piezas antes de tocar nada; `ServiceError(400)` con la corrección."""
    from apolo.library.calidad.tensor import validar_tensores

    from .errors import ServiceError

    try:
        limpio = validar_tensores(valor)
    except ValueError as exc:
        raise ServiceError(400, str(exc)) from exc
    faltan = sorted({p for t in limpio for p in t["piezas"] if p not in doc.scene})
    if faltan:
        raise ServiceError(400, f"tensores: pieza(s) inexistente(s) {', '.join(faltan)}")
    doc.tensores = limpio
    return doc.tensores


def tiene_tensor_reconocido(doc) -> bool:
    """¿Alguna banda tiene un tensor reconocido? (la adherencia de Eytelwein, `rules.py`)."""
    return any(lz["tensores"] for lz in lazos(doc, medir=False, cadenas=False))
