"""Solver de elasticidad lineal con scikit-fem sobre la malla .msh de gmsh.

Elementos: tets lineales de gmsh + campo P2 (``ElementTetP2``) — los P1 son
demasiado rígidos a flexión (shear locking numérico); con P2 el spike clavó la viga
en voladizo con 0.3 % de error. ``MeshTet.load`` lee los physical groups de gmsh
como ``mesh.boundaries`` nombrados (meshio por debajo).

El von Mises se evalúa en los puntos de cuadratura (sin proyección global) y se
promedia a nodos SOLO para el fringe. σ_vm máx se reporta desde cuadratura, con su
ubicación — si cae en la cara fija es la concentración numérica del empotramiento
ideal (hipótesis declarada aguas arriba).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FeaField:
    """Resultado de campo para posproceso (fringe) + escalares del resumen."""

    coords: np.ndarray        # (3, n_puntos) vértices de la malla
    tets: np.ndarray          # (4, n_tets)
    vm_nodal: np.ndarray      # (n_puntos,) von Mises promediado a nodos (fringe)
    u_mag_nodal: np.ndarray   # (n_puntos,) |u| en vértices
    vm_max: float             # MPa, máximo en cuadratura
    vm_max_xyz: tuple[float, float, float]
    u_max_mm: float
    n_nodos: int
    n_tets: int


def solve_linear_elasticity(msh_path: str, *, e_mpa: float, nu: float,
                            loads: list[dict],
                            body_force: tuple[float, float, float] | None = None,
                            ) -> FeaField:
    """Resuelve el estático lineal. `loads`: [{group, force_n:[x,y,z]}] (fuerza TOTAL
    repartida como tracción uniforme F/área) o [{group, pressure_mpa}] (presión
    normal ENTRANTE a la cara). Encastre total en el grupo 'fixed'.
    `body_force` en N/mm³ (peso propio)."""
    import skfem
    from skfem import (Basis, ElementTetP2, ElementVector, Functional, MeshTet,
                       asm, condense, solve)
    from skfem.helpers import ddot, eye, sym_grad, trace
    from skfem.models.elasticity import lame_parameters, linear_elasticity

    from . import FeaError

    mesh = MeshTet.load(msh_path)
    if "fixed" not in (mesh.boundaries or {}):
        raise FeaError("La malla no trae el grupo 'fixed' (caras de empotramiento)")
    elem = ElementVector(ElementTetP2())
    basis = Basis(mesh, elem)
    lam, mu = lame_parameters(e_mpa, nu)
    K = asm(linear_elasticity(lam, mu), basis)

    f = np.zeros(K.shape[0])
    for load in loads:
        group = load["group"]
        if group not in mesh.boundaries:
            raise FeaError(f"La malla no trae el grupo de carga '{group}'")
        fbasis = skfem.FacetBasis(mesh, elem, facets=mesh.boundaries[group])
        if load.get("force_n") is not None:
            fx, fy, fz = (float(c) for c in load["force_n"])
            area = float(Functional(lambda w: 1.0 + 0.0 * w.x[0]).assemble(fbasis))
            tx, ty, tz = fx / area, fy / area, fz / area

            @skfem.LinearForm
            def traction(v, w, tx=tx, ty=ty, tz=tz):
                return tx * v[0] + ty * v[1] + tz * v[2]

            f = f + asm(traction, fbasis)
        elif load.get("pressure_mpa") is not None:
            p = float(load["pressure_mpa"])

            @skfem.LinearForm
            def pressure(v, w, p=p):
                # presión entrante: tracción -p·n (n = normal exterior del sólido)
                return -p * (w.n[0] * v[0] + w.n[1] * v[1] + w.n[2] * v[2])

            f = f + asm(pressure, fbasis)
        else:
            raise FeaError(f"Carga sin force_n ni pressure_mpa: {load}")

    if body_force is not None:
        bx, by, bz = (float(c) for c in body_force)

        @skfem.LinearForm
        def body(v, w, bx=bx, by=by, bz=bz):
            return bx * v[0] + by * v[1] + bz * v[2]

        f = f + asm(body, basis)

    D = basis.get_dofs(mesh.boundaries["fixed"])
    u = solve(*condense(K, f, D=D))

    # desplazamiento en vértices
    u3 = u[basis.nodal_dofs]                       # (3, n_puntos)
    u_mag = np.sqrt((u3**2).sum(axis=0))

    # von Mises en cuadratura
    uh = basis.interpolate(u)
    eps = sym_grad(uh)
    sig = 2.0 * mu * eps + lam * eye(trace(eps), 3)
    dev = sig - eye(trace(sig) / 3.0, 3)
    vm = np.sqrt(1.5 * ddot(dev, dev))             # (n_elems, n_qp)
    x = basis.global_coordinates().value           # (3, n_elems, n_qp)
    flat = int(np.argmax(vm))
    iel, iqp = np.unravel_index(flat, vm.shape)
    vm_max_xyz = tuple(round(float(x[k][iel, iqp]), 2) for k in range(3))

    # promedio del vm por elemento acumulado a los 4 vértices del tet (fringe)
    vm_elem = vm.mean(axis=1)                      # (n_elems,)
    vm_nodal = np.zeros(mesh.p.shape[1])
    counts = np.zeros(mesh.p.shape[1])
    for k in range(4):
        np.add.at(vm_nodal, mesh.t[k], vm_elem)
        np.add.at(counts, mesh.t[k], 1.0)
    vm_nodal /= np.maximum(counts, 1.0)

    return FeaField(
        coords=mesh.p, tets=mesh.t, vm_nodal=vm_nodal, u_mag_nodal=u_mag,
        vm_max=float(vm.max()), vm_max_xyz=vm_max_xyz,
        u_max_mm=float(u_mag.max()), n_nodos=int(mesh.p.shape[1]),
        n_tets=int(mesh.t.shape[1]),
    )
