"""Orquestador del análisis estático lineal de UNA pieza (sin `Document`).

Recibe rutas y valores puros (el mapeo feature→material/selectores/STEP lo hace la
capa API bajo STATE_LOCK); malla + resuelve FUERA de cualquier lock del documento y
devuelve (resumen JSON-serializable, FeaField para el fringe). El resumen incluye el
bloque ``calc`` en el formato exacto de ``rules._check`` y las HIPÓTESIS declaradas
— la memoria de cálculo lo consume tal cual.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from . import FeaError, _require_fea
from .mesher import FaceDesc, mesh_step
from .solver import FeaField, solve_linear_elasticity

G_M_S2 = 9.81


def _estado(fs: float | None, fs_min: float) -> str:
    if fs is None:
        return "aviso"
    if fs < 1.2:
        return "error"
    if fs < fs_min:
        return "aviso"
    return "ok"


def run_static_analysis(step_path: str, *, pieza: str,
                        fixed: list[FaceDesc], loads: list[dict],
                        e_mpa: float, yield_mpa: float,
                        density_kg_mm3: float, material: str,
                        nu: float = 0.3, self_weight: bool = False,
                        gravity: tuple[float, float, float] = (0.0, 0.0, -G_M_S2),
                        mesh_size_mm: float | None = None,
                        fs_min: float = 2.0) -> tuple[dict, FeaField]:
    """FEA estático lineal end-to-end sobre un STEP ya exportado.

    `loads`: [{"descs": [FaceDesc...], "force_n": [x,y,z]} | {..., "pressure_mpa": p}].
    Devuelve (resumen, campo). El resumen es honesto: hipótesis siempre declaradas y
    σ_vm máx separado de su ubicación (si cae en el empotramiento, se avisa)."""
    _require_fea()
    if not fixed:
        raise FeaError("Falta el grupo de caras fijas (empotramiento)")
    if not loads and not self_weight:
        raise FeaError("Sin cargas: da al menos un load (force_n/pressure_mpa) o self_weight")

    groups: dict[str, list[FaceDesc]] = {"fixed": fixed}
    solver_loads: list[dict] = []
    for i, load in enumerate(loads):
        name = f"load_{i}"
        groups[name] = load["descs"]
        entry: dict = {"group": name}
        if load.get("force_n") is not None:
            entry["force_n"] = load["force_n"]
        elif load.get("pressure_mpa") is not None:
            entry["pressure_mpa"] = load["pressure_mpa"]
        else:
            raise FeaError(f"Carga {i} sin force_n ni pressure_mpa")
        solver_loads.append(entry)

    body_force = None
    if self_weight:
        body_force = tuple(density_kg_mm3 * g for g in gravity)  # N/mm³

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="apolo_fea_") as tmp:
        msh = str(Path(tmp) / "pieza.msh")
        malla = mesh_step(step_path, groups, msh, mesh_size_mm)
        t_malla = time.perf_counter() - t0
        t0 = time.perf_counter()
        field = solve_linear_elasticity(
            msh, e_mpa=e_mpa, nu=nu, loads=solver_loads, body_force=body_force,
        )
        t_solve = time.perf_counter() - t0

    fs = round(yield_mpa / field.vm_max, 2) if field.vm_max > 1e-9 else None
    estado = _estado(fs, fs_min)

    # ¿el máximo cae en una cara fija? → probable concentración del empotramiento
    en_encastre = any(
        abs(field.vm_max_xyz[0] - d.center[0]) ** 2
        + abs(field.vm_max_xyz[1] - d.center[1]) ** 2
        + abs(field.vm_max_xyz[2] - d.center[2]) ** 2
        <= d.area_mm2  # radio² ~ área: heurística de cercanía a la cara fija
        for d in fixed
    )

    cargas_txt = []
    for load in loads:
        if load.get("force_n") is not None:
            fx, fy, fz = load["force_n"]
            mag = (fx**2 + fy**2 + fz**2) ** 0.5
            cargas_txt.append(f"F=({fx:g}, {fy:g}, {fz:g}) N (|F|={mag:.0f} N)")
        else:
            cargas_txt.append(f"p={load['pressure_mpa']:g} MPa")
    if self_weight:
        cargas_txt.append(f"peso propio (ρ={density_kg_mm3:.2e} kg/mm³, g=9.81)")

    hipotesis = [
        "elasticidad lineal (pequeñas deformaciones, sin plasticidad)",
        "material isótropo homogéneo",
        "cargas estáticas",
        "empotramiento ideal rígido en las caras fijas",
        f"malla tet P2: {field.n_nodos} nodos, {field.n_tets} tets, size {malla['size_mm']} mm",
        "sin contacto ni pandeo (el pandeo se verifica aparte con la regla de Euler)",
        "σ_vm en el empotramiento puede sobreestimarse (concentración numérica en esquinas)",
    ]

    detalle = (
        f"σ_vm máx = {field.vm_max:.1f} MPa en {field.vm_max_xyz}, "
        f"desplazamiento máx = {field.u_max_mm:.3f} mm, FS = {fs}"
    )
    if en_encastre:
        detalle += " (el máximo cae junto al empotramiento: probable concentración numérica)"

    resumen = {
        "pieza": pieza,
        "material": material,
        "sigma_vm_max_mpa": round(field.vm_max, 2),
        "ubicacion_mm": list(field.vm_max_xyz),
        "max_en_encastre": en_encastre,
        "desplazamiento_max_mm": round(field.u_max_mm, 4),
        "fs": fs,
        "fs_min": fs_min,
        "estado": estado,
        "detalle": detalle,
        "cargas": cargas_txt,
        "n_nodos": field.n_nodos,
        "n_tets": field.n_tets,
        "mesh_size_mm": malla["size_mm"],
        "tiempo_s": round(t_malla + t_solve, 1),
        "hipotesis": hipotesis,
        "calc": {
            "titulo": f"FEA estático lineal · {pieza}",
            "entradas": {
                "material": f"{material} (E={e_mpa:g} MPa, ν={nu:g}, σy={yield_mpa:g} MPa)",
                "cargas": "; ".join(cargas_txt),
                "malla": f"tet P2 · {field.n_tets} elementos · size {malla['size_mm']} mm",
                "sujecion": f"empotramiento en {len(fixed)} cara(s)",
            },
            "formula": "FS = σy / σ_vm,max (von Mises)",
            "sustitucion": f"FS = {yield_mpa:g} / {field.vm_max:.1f}",
            "resultado": (
                f"FS = {fs} · σ_vm,max = {field.vm_max:.1f} MPa · "
                f"δ_max = {field.u_max_mm:.3f} mm"
            ),
            "criterio": f"FS ≥ {fs_min:g} (estático); 1.2–{fs_min:g} justo; <1.2 sobrecargada",
            "fs": fs,
            "norma": "FEA estático lineal — criterio de diseño FS = σy/σ_vm (von Mises)",
        },
    }
    return resumen, field
