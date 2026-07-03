"""Spike V5.6 — FEA estático lineal: gmsh (malla tet) + scikit-fem (P2).

Criterios GO/NO-GO:
  S1  viga voladizo 100×10×10 acero, F=100 N punta: δ_punta = 0.2000 mm ±5 %
  S2  σ_vm a media luz = 30 MPa ±8 % (evita la singularidad del encastre)
  S3  tiempo total (malla+solve) < 30 s con ~50k dof
  S4  10 ciclos gmsh initialize/finalize en el MISMO proceso sin crash
  S5  un STEP real exportado por Apolo malla sin errores

Uso:  .venv\\Scripts\\python.exe scripts\\spike_fea.py
"""
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # consola Windows cp1252 vs δ/σ
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

import numpy as np

L, B, H = 100.0, 10.0, 10.0           # mm (largo X, ancho Y, alto Z)
E, NU = 200_000.0, 0.3                # MPa
F = 100.0                             # N, en -Z sobre la cara x=L
I = B * H**3 / 12.0                   # 833.33 mm4
DELTA_TEO = F * L**3 / (3 * E * I)    # 0.2000 mm
SIGMA_MID = 6 * F * (L / 2) / (B * H**2)  # 30 MPa


def build_step(path: str) -> None:
    from build123d import Box, Pos, export_step
    shape = Pos(L / 2, 0, 0) * Box(L, B, H)
    export_step(shape, path)


def mesh_with_gmsh(step_path: str, msh_path: str, size: float) -> dict:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("spike")
        gmsh.model.occ.importShapes(step_path)
        gmsh.model.occ.synchronize()

        # physical groups por match geométrico (centro de masa de superficies)
        fixed, load = [], []
        for dim, tag in gmsh.model.getEntities(2):
            cx, cy, cz = gmsh.model.occ.getCenterOfMass(dim, tag)
            if abs(cx - 0.0) < 1e-6:
                fixed.append(tag)
            elif abs(cx - L) < 1e-6:
                load.append(tag)
        assert fixed and load, f"caras no encontradas: fixed={fixed} load={load}"
        gmsh.model.addPhysicalGroup(2, fixed, name="fixed")
        gmsh.model.addPhysicalGroup(2, load, name="load")
        vols = [t for _, t in gmsh.model.getEntities(3)]
        gmsh.model.addPhysicalGroup(3, vols, name="body")

        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", size / 3)
        gmsh.model.mesh.generate(3)
        n_nodes = len(gmsh.model.mesh.getNodes()[0])
        _, tet_tags, _ = gmsh.model.mesh.getElements(3)
        n_tets = sum(len(t) for t in tet_tags)
        gmsh.write(msh_path)
        return {"n_nodes": n_nodes, "n_tets": n_tets}
    finally:
        gmsh.finalize()


def solve_cantilever(msh_path: str) -> dict:
    import skfem
    from skfem import (Basis, ElementTetP2, ElementVector, Functional, MeshTet,
                       asm, condense, solve)
    from skfem.helpers import ddot, eye, sym_grad, trace
    from skfem.models.elasticity import lame_parameters, linear_elasticity

    mesh = MeshTet.load(msh_path)
    print(f"    boundaries gmsh -> skfem: {sorted(mesh.boundaries)}")
    elem = ElementVector(ElementTetP2())
    basis = Basis(mesh, elem)
    lam, mu = lame_parameters(E, NU)
    K = asm(linear_elasticity(lam, mu), basis)

    # carga: tracción uniforme -Z sobre 'load' (F/área)
    fbasis = skfem.FacetBasis(mesh, elem, facets=mesh.boundaries["load"])
    area = Functional(lambda w: 1.0 + 0.0 * w.x[0]).assemble(fbasis)
    tz = -F / float(area)

    @skfem.LinearForm
    def traction(v, w):
        return tz * v[2]

    f = asm(traction, fbasis)
    D = basis.get_dofs(mesh.boundaries["fixed"])
    u = solve(*condense(K, f, D=D))

    # desplazamiento máximo (magnitud nodal)
    u3 = u[basis.nodal_dofs]          # (3, n_puntos)
    umag = np.sqrt((u3**2).sum(axis=0))
    u_max = float(umag.max())

    # von Mises evaluado en los puntos de cuadratura (sin proyección)
    uh = basis.interpolate(u)
    eps = sym_grad(uh)                              # (3,3,nel,nqp)
    sig = 2.0 * mu * eps + lam * eye(trace(eps), 3)
    dev = sig - eye(trace(sig) / 3.0, 3)
    vm = np.sqrt(1.5 * ddot(dev, dev))              # (nel, nqp)
    x = basis.global_coordinates().value            # (3, nel, nqp)

    mid = np.abs(x[0] - L / 2) < 2.5
    top = x[2] > H * 0.35  # fibra superior (tensión de flexión)
    sel = mid & top
    vm_mid = float(vm[sel].max()) if sel.any() else float("nan")
    return {"u_max": u_max, "vm_mid": vm_mid, "vm_max": float(vm.max()),
            "dof": K.shape[0]}


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="spike_fea_"))
    step = str(tmp / "viga.step")
    msh = str(tmp / "viga.msh")
    build_step(step)

    print("S1-S3: viga en voladizo (malla size=2.5 mm, P2)")
    t0 = time.perf_counter()
    m = mesh_with_gmsh(step, msh, size=2.5)
    t_mesh = time.perf_counter() - t0
    t0 = time.perf_counter()
    r = solve_cantilever(msh)
    t_solve = time.perf_counter() - t0
    err_d = abs(r["u_max"] - DELTA_TEO) / DELTA_TEO * 100
    err_s = abs(r["vm_mid"] - SIGMA_MID) / SIGMA_MID * 100
    print(f"    malla: {m['n_nodes']} nodos, {m['n_tets']} tets, {t_mesh:.1f}s"
          f" | solve: {r['dof']} dof, {t_solve:.1f}s")
    print(f"    δ = {r['u_max']:.4f} mm (teo {DELTA_TEO:.4f}, err {err_d:.1f}%)"
          f" -> {'GO' if err_d < 5 else 'NO-GO'}")
    print(f"    σ_vm media luz = {r['vm_mid']:.1f} MPa (teo {SIGMA_MID:.1f},"
          f" err {err_s:.1f}%) -> {'GO' if err_s < 8 else 'NO-GO'}")
    print(f"    σ_vm max = {r['vm_max']:.1f} MPa (raíz teo 60 + concentración)")
    print(f"    tiempo total {t_mesh + t_solve:.1f}s -> "
          f"{'GO' if t_mesh + t_solve < 30 else 'NO-GO'}")

    print("S4: 10 ciclos gmsh initialize/finalize en el mismo proceso")
    for i in range(10):
        mesh_with_gmsh(step, str(tmp / f"c{i}.msh"), size=4.0)
    print("    10 ciclos OK -> GO")

    print("S5: mallar un STEP real de Apolo (perfil HSS del catálogo)")
    from apolo.library.catalog import CATALOG, build_component
    from build123d import export_step
    ref = next(r for r in CATALOG if "hss" in r.lower() or "tubo" in r.lower())
    shape, _cut = build_component(ref, 500)  # devuelve (shape, longitud_cortada)
    real_step = str(tmp / "real.step")
    export_step(shape, real_step)
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("real")
        gmsh.model.occ.importShapes(real_step)
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.MeshSizeMax", 8.0)
        gmsh.model.mesh.generate(3)
        _, tet_tags, _ = gmsh.model.mesh.getElements(3)
        n = sum(len(t) for t in tet_tags)
        print(f"    {ref}: {n} tets -> GO")
    finally:
        gmsh.finalize()

    print("VEREDICTO: revisar GO/NO-GO arriba")


if __name__ == "__main__":
    main()
