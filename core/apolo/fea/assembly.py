"""Orquestador del FEA de ENSAMBLAJE BONDED (V7.4) — sin ``Document``.

El bastidor SOLDADO completo bajo la carga de diseño, no una pata aislada: N sólidos
pegados (interfaces con nodos compartidos, sin pares de contacto), multi-material
(E/ν/σy por pieza), FS reportado POR PIEZA. La capa API resuelve material/selectores y
exporta un STEP por pieza bajo STATE_LOCK; aquí se malla + resuelve FUERA de cualquier
lock del documento y se devuelve un resumen JSON-serializable con el bloque ``calc`` en
el formato exacto de ``rules._check`` + las HIPÓTESIS declaradas — la memoria lo consume
tal cual (con chequeo de vigencia por volumen del grupo).

Bonded lineal es la hipótesis CORRECTA para un bastidor soldado, no un atajo: lo que un
despacho firma. La verificación ANALÍTICA de flecha/pandeo NO se reemplaza — el FEA la
CONTRASTA (dos caminos independientes al mismo número = confianza para firmar).
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from . import FeaError, _require_fea
from .mesher import FaceDesc, PieceMesh, mesh_assembly
from .solver import FeaField, solve_assembly_elasticity

G_M_S2 = 9.81


def _estado(fs: float | None, fs_min: float) -> str:
    if fs is None:
        return "aviso"
    if fs < 1.2:
        return "error"
    if fs < fs_min:
        return "aviso"
    return "ok"


def run_assembly_analysis(pieces: list[dict], *, grupo: str,
                          fixed: list[FaceDesc], loads: list[dict],
                          self_weight: bool = False,
                          gravity: tuple[float, float, float] = (0.0, 0.0, -G_M_S2),
                          excluded: list[dict] | None = None,
                          mesh_size_mm: float | None = None,
                          fs_min: float = 2.0) -> tuple[dict, FeaField]:
    """FEA bonded end-to-end de un ensamblaje. `pieces`: [{key, name, step_path,
    e_mpa, nu, yield_mpa, density_kg_mm3, material, volumen_mm3}]. `loads`:
    [{"descs":[FaceDesc], "force_n"/"pressure_mpa"}]. `excluded`: herraje sacado de la
    malla [{"name", "masa_kg"}] (su peso ya lo metió la API como load — aquí solo se
    DECLARA). Devuelve (resumen, campo global para el fringe)."""
    _require_fea()
    if not pieces:
        raise FeaError(f"El grupo '{grupo}' no tiene piezas sólidas que analizar")
    if not fixed:
        raise FeaError(
            "Falta el empotramiento: el ensamblaje necesita al menos una pieza con "
            "ground (placa de anclaje a piso) o caras fijas explícitas"
        )
    if not loads and not self_weight:
        raise FeaError("Sin cargas: da al menos un load (carga de diseño) o self_weight")

    excluded = excluded or []

    # 1) preparar la malla bonded + los grupos de carga con nombres estables
    piece_meshes = [PieceMesh(key=p["key"], step_path=p["step_path"]) for p in pieces]
    load_groups: dict[str, list[FaceDesc]] = {}
    solver_loads: list[dict] = []
    for i, load in enumerate(loads):
        gname = f"load_{i}"
        load_groups[gname] = load["descs"]
        entry: dict = {"group": gname}
        if load.get("force_n") is not None:
            entry["force_n"] = load["force_n"]
        elif load.get("pressure_mpa") is not None:
            entry["pressure_mpa"] = load["pressure_mpa"]
        else:
            raise FeaError(f"Carga {i} sin force_n ni pressure_mpa")
        solver_loads.append(entry)

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="apolo_fea_asm_") as tmp:
        msh = str(Path(tmp) / "ensamblaje.msh")
        malla = mesh_assembly(piece_meshes, fixed, load_groups, msh, mesh_size_mm)
        t_malla = time.perf_counter() - t0

        # solo las piezas que SOBREVIVIERON la fragmentación tienen subdominio
        surviving = {g["key"]: g["name"] for g in malla["piece_groups"]}
        by_key = {p["key"]: p for p in pieces}
        solver_pieces = [
            {"name": name, "key": key, "e_mpa": by_key[key]["e_mpa"],
             "nu": by_key[key]["nu"], "density_kg_mm3": by_key[key]["density_kg_mm3"]}
            for key, name in surviving.items()
        ]
        t0 = time.perf_counter()
        field, per = solve_assembly_elasticity(
            msh, pieces=solver_pieces, loads=solver_loads,
            gravity=gravity if self_weight else None,
        )
        t_solve = time.perf_counter() - t0

    # 2) FS por pieza (σy de CADA pieza) → la GOBERNANTE es la mínima
    piezas_out = []
    for r in per:
        p = by_key[r.key]
        sy = float(p["yield_mpa"])
        fs = round(sy / r.vm_max, 2) if r.vm_max > 1e-9 else None
        piezas_out.append({
            "pieza": p["name"], "feature_id": r.key, "material": p["material"],
            "sigma_vm_max_mpa": round(r.vm_max, 2), "ubicacion_mm": list(r.vm_max_xyz),
            "yield_mpa": round(sy, 1), "fs": fs, "estado": _estado(fs, fs_min),
            "desplazamiento_max_mm": round(r.u_max_mm, 4),
        })
    piezas_out.sort(key=lambda d: (d["fs"] is not None, d["fs"] if d["fs"] is not None else 9e9))
    fs_gobernante = next((d["fs"] for d in piezas_out if d["fs"] is not None), None)
    pieza_critica = next((d["pieza"] for d in piezas_out if d["fs"] == fs_gobernante), "—")
    estado = _estado(fs_gobernante, fs_min)

    # ¿el máximo global cae junto a un empotramiento? (concentración numérica)
    en_encastre = any(
        sum((field.vm_max_xyz[k] - d.center[k]) ** 2 for k in range(3)) <= d.area_mm2
        for d in fixed
    )

    # 3) flecha máx vs criterio L/240 (L = mayor dimensión del ensamblaje) — CONTRASTE
    coords = field.coords
    span = float(max(coords[k].max() - coords[k].min() for k in range(3)))
    flecha_lim = span / 240.0
    flecha_ok = field.u_max_mm <= flecha_lim if span > 0 else None

    cargas_txt = []
    for load in loads:
        if load.get("force_n") is not None:
            fx, fy, fz = load["force_n"]
            mag = (fx ** 2 + fy ** 2 + fz ** 2) ** 0.5
            cargas_txt.append(f"F=({fx:g}, {fy:g}, {fz:g}) N (|F|={mag:.0f} N)")
        else:
            cargas_txt.append(f"p={load['pressure_mpa']:g} MPa")
    if self_weight:
        cargas_txt.append("peso propio (densidad por pieza, g=9.81)")

    materiales = sorted({p["material"] for p in pieces})
    hipotesis = [
        "ensamblaje PEGADO (bonded): nodos compartidos en las interfaces, sin contacto/fricción",
        "elasticidad lineal (pequeñas deformaciones, sin plasticidad)",
        f"multi-material por pieza: {', '.join(materiales)} (E/ν/σy propios)",
        "cargas estáticas; empotramiento ideal rígido en las caras con ground",
        f"malla tet P2: {field.n_nodos} nodos, {field.n_tets} tets, size {malla['size_mm']} mm",
        "sin pandeo (se verifica aparte con Euler; el FEA lo contrasta con la flecha)",
        "σ_vm en el empotramiento/esquinas puede sobreestimarse (concentración numérica)",
    ]
    if excluded:
        masa_h = sum(float(e.get("masa_kg") or 0) for e in excluded)
        nombres = ", ".join(e["name"] for e in excluded[:6]) + (" …" if len(excluded) > 6 else "")
        hipotesis.append(
            f"herraje de catálogo EXCLUIDO de la malla ({len(excluded)} pza, {masa_h:.1f} kg: "
            f"{nombres}) — su peso entra como carga sustituta, no como rigidez"
        )
    if malla["shared_volumes"]:
        hipotesis.append(
            f"{malla['shared_volumes']} volumen(es) de SOLAPE asignados a la pieza declarada "
            f"antes (juntas soldadas/traslapes de diseño)"
        )
    if malla["absorbidas"]:
        hipotesis.append(
            f"pieza(s) absorbida(s) por solape total, sin FS propio: {', '.join(malla['absorbidas'])}"
        )

    detalle = (
        f"{len(piezas_out)} pieza(s) bonded. FS gobernante = {fs_gobernante} en «{pieza_critica}» "
        f"(σ_vm = {field.vm_max:.1f} MPa máx global en {field.vm_max_xyz}), "
        f"desplazamiento máx = {field.u_max_mm:.3f} mm."
    )
    if en_encastre:
        detalle += " El máximo global cae junto al empotramiento (probable concentración numérica)."
    if flecha_ok is not None:
        detalle += (f" Flecha {field.u_max_mm:.3f} mm "
                    f"{'≤' if flecha_ok else '>'} L/240 = {flecha_lim:.3f} mm.")

    resumen = {
        "grupo": grupo,
        "tipo": "ensamblaje_bonded",
        "n_piezas": len(piezas_out),
        "materiales": materiales,
        "fs": fs_gobernante,
        "fs_min": fs_min,
        "pieza_critica": pieza_critica,
        "sigma_vm_max_mpa": round(field.vm_max, 2),
        "ubicacion_mm": list(field.vm_max_xyz),
        "max_en_encastre": en_encastre,
        "desplazamiento_max_mm": round(field.u_max_mm, 4),
        "flecha_lim_mm": round(flecha_lim, 4),
        "flecha_ok": flecha_ok,
        "span_mm": round(span, 1),
        "estado": estado,
        "detalle": detalle,
        "cargas": cargas_txt,
        "excluidos": [{"nombre": e["name"], "masa_kg": round(float(e.get("masa_kg") or 0), 2)}
                      for e in excluded],
        "piezas": piezas_out,
        "n_nodos": field.n_nodos,
        "n_tets": field.n_tets,
        "mesh_size_mm": malla["size_mm"],
        "shared_volumes": malla["shared_volumes"],
        "tiempo_s": round(t_malla + t_solve, 1),
        "hipotesis": hipotesis,
        "calc": {
            "titulo": f"FEA del bastidor (bonded) · {grupo}",
            "entradas": {
                "piezas": f"{len(piezas_out)} sólidos pegados ({', '.join(materiales)})",
                "cargas": "; ".join(cargas_txt),
                "malla": f"tet P2 · {field.n_tets} elem · size {malla['size_mm']} mm",
                "sujecion": f"empotramiento en {len(fixed)} cara(s) con ground",
            },
            "formula": "FS_i = σy,i / σ_vm,max,i (von Mises por pieza) → gobierna el mínimo",
            "sustitucion": (f"FS = {piezas_out[0]['yield_mpa']:g} / {field.vm_max:.1f}"
                            if piezas_out else "—"),
            "resultado": (
                f"FS gobernante = {fs_gobernante} en «{pieza_critica}» · "
                f"σ_vm,max = {field.vm_max:.1f} MPa · δ_max = {field.u_max_mm:.3f} mm "
                f"(L/240 = {flecha_lim:.3f} mm)"
            ),
            "criterio": f"FS ≥ {fs_min:g} y δ ≤ L/240 (estático)",
            "fs": fs_gobernante,
            "norma": "FEA estático lineal bonded — FS = σy/σ_vm (von Mises) · flecha L/240 (AISC)",
        },
    }
    return resumen, field
