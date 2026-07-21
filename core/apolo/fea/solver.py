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


@dataclass
class PieceResult:
    """von Mises máx y su ubicación DENTRO de una pieza del ensamblaje."""

    key: str
    vm_max: float
    vm_max_xyz: tuple[float, float, float]
    u_max_mm: float
    n_tets: int


def solve_assembly_elasticity(msh_path: str, *, pieces: list[dict],
                              loads: list[dict],
                              gravity: tuple[float, float, float] | None = None,
                              ) -> tuple[FeaField, list[PieceResult]]:
    """Estático lineal de un ENSAMBLAJE BONDED multi-material. La malla trae un
    subdominio ``piece_<idx>`` por pieza (nodos de interfaz COMPARTIDOS = pegado);
    la rigidez toma E/ν POR ELEMENTO según su pieza. `pieces`:
    [{name (physical group), key, e_mpa, nu, density_kg_mm3}]. `gravity` != None
    añade peso propio con la densidad de CADA pieza. Devuelve (campo global para el
    fringe, resultados POR PIEZA con σ_vm y FS listos para la tabla)."""
    import numpy as np
    import skfem
    from skfem import (Basis, BilinearForm, ElementTetP0, ElementTetP2,
                       ElementVector, Functional, LinearForm, MeshTet, asm,
                       condense, solve)
    from skfem.helpers import ddot, eye, sym_grad, trace

    from . import FeaError

    mesh = MeshTet.load(msh_path)
    if "fixed" not in (mesh.boundaries or {}):
        raise FeaError("La malla no trae el grupo 'fixed' (caras de empotramiento)")
    subs = mesh.subdomains or {}
    elem = ElementVector(ElementTetP2())
    basis = Basis(mesh, elem)
    basis0 = basis.with_element(ElementTetP0())

    nelem = mesh.t.shape[1]
    E_el = np.zeros(nelem)
    nu_el = np.zeros(nelem)
    rho_el = np.zeros(nelem)
    piece_of = np.full(nelem, -1, dtype=int)
    for i, p in enumerate(pieces):
        idx = subs.get(p["name"])
        if idx is None:
            raise FeaError(f"La malla no trae el subdominio '{p['name']}' de la pieza {p['key']}")
        E_el[idx] = float(p["e_mpa"])
        nu_el[idx] = float(p["nu"])
        rho_el[idx] = float(p["density_kg_mm3"])
        piece_of[idx] = i
    if (piece_of < 0).any():
        # elementos sin pieza: no debería pasar (todo volumen tiene grupo) → error honesto
        raise FeaError(
            f"{int((piece_of < 0).sum())} elementos de la malla no quedaron asignados a "
            f"ninguna pieza (fragmentación incoherente)"
        )
    lam_el = E_el * nu_el / ((1.0 + nu_el) * (1.0 - 2.0 * nu_el))
    mu_el = E_el / (2.0 * (1.0 + nu_el))

    lam_dg = basis0.zeros(); lam_dg[:] = lam_el
    mu_dg = basis0.zeros(); mu_dg[:] = mu_el
    lam_q = basis0.interpolate(lam_dg)
    mu_q = basis0.interpolate(mu_dg)

    @BilinearForm
    def elasticity(u, v, w):
        eps_u = sym_grad(u)
        sig = 2.0 * w["mu"] * eps_u + eye(w["lam"] * trace(eps_u), 3)
        return ddot(sig, sym_grad(v))

    K = asm(elasticity, basis, lam=lam_q, mu=mu_q)

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
                return -p * (w.n[0] * v[0] + w.n[1] * v[1] + w.n[2] * v[2])

            f = f + asm(pressure, fbasis)
        else:
            raise FeaError(f"Carga sin force_n ni pressure_mpa: {load}")

    if gravity is not None:
        gx, gy, gz = (float(c) for c in gravity)
        # peso propio con densidad POR ELEMENTO: b = ρ·g (N/mm³)
        bx_dg = basis0.zeros(); bx_dg[:] = rho_el * gx
        by_dg = basis0.zeros(); by_dg[:] = rho_el * gy
        bz_dg = basis0.zeros(); bz_dg[:] = rho_el * gz
        bx_q, by_q, bz_q = (basis0.interpolate(a) for a in (bx_dg, by_dg, bz_dg))

        @LinearForm
        def body(v, w):
            return w["bx"] * v[0] + w["by"] * v[1] + w["bz"] * v[2]

        f = f + asm(body, basis, bx=bx_q, by=by_q, bz=bz_q)

    D = basis.get_dofs(mesh.boundaries["fixed"])
    u = solve(*condense(K, f, D=D))

    u3 = u[basis.nodal_dofs]
    u_mag = np.sqrt((u3 ** 2).sum(axis=0))
    # backstop: un desplazamiento no físico delata un mecanismo/pieza suelta que la guarda
    # topológica no cazó (contacto por arista/punto). 1e5 mm = 100 m: absurdo para máquinas.
    u_peak = float(u_mag.max()) if u_mag.size else 0.0
    if not np.isfinite(u_peak) or u_peak > 1e5:
        raise FeaError(
            f"Desplazamiento no físico ({u_peak:.3g} mm): el ensamblaje tiene un modo de "
            f"cuerpo rígido (pieza suelta o unida solo por arista/punto). Revisa que cada "
            f"pieza comparta una CARA de contacto con el bastidor anclado."
        )

    uh = basis.interpolate(u)
    eps = sym_grad(uh)
    # esfuerzo con λ, μ POR ELEMENTO (broadcast a los puntos de cuadratura)
    lam_b = lam_el[:, None]
    mu_b = mu_el[:, None]
    tr = eps[0, 0] + eps[1, 1] + eps[2, 2]
    sig = [[2.0 * mu_b * eps[a, b] + (lam_b * tr if a == b else 0.0)
            for b in range(3)] for a in range(3)]
    tr_s = sig[0][0] + sig[1][1] + sig[2][2]
    dev = [[sig[a][b] - (tr_s / 3.0 if a == b else 0.0) for b in range(3)] for a in range(3)]
    vm = np.sqrt(1.5 * sum(dev[a][b] ** 2 for a in range(3) for b in range(3)))  # (nelem, nqp)
    x = basis.global_coordinates().value

    # global (para el fringe + escalar)
    flat = int(np.argmax(vm))
    iel, iqp = np.unravel_index(flat, vm.shape)
    vm_max_xyz = tuple(round(float(x[k][iel, iqp]), 2) for k in range(3))

    vm_elem = vm.mean(axis=1)
    vm_nodal = np.zeros(mesh.p.shape[1])
    counts = np.zeros(mesh.p.shape[1])
    for k in range(4):
        np.add.at(vm_nodal, mesh.t[k], vm_elem)
        np.add.at(counts, mesh.t[k], 1.0)
    vm_nodal /= np.maximum(counts, 1.0)

    field = FeaField(
        coords=mesh.p, tets=mesh.t, vm_nodal=vm_nodal, u_mag_nodal=u_mag,
        vm_max=float(vm.max()), vm_max_xyz=vm_max_xyz,
        u_max_mm=float(u_mag.max()), n_nodos=int(mesh.p.shape[1]),
        n_tets=int(mesh.t.shape[1]),
    )

    # von Mises máx POR PIEZA (máximo sobre los elementos de su subdominio)
    vm_elem_max = vm.max(axis=1)                     # (nelem,)
    # desplazamiento por pieza: nodos tocados por sus elementos (vértices P1)
    results: list[PieceResult] = []
    for i, p in enumerate(pieces):
        emask = piece_of == i
        if not emask.any():
            continue
        ki = int(np.argmax(np.where(emask, vm_elem_max, -1.0)))
        qi = int(np.argmax(vm[ki]))
        xyz = tuple(round(float(x[k][ki, qi]), 2) for k in range(3))
        verts = np.unique(mesh.t[:, emask].ravel())
        results.append(PieceResult(
            key=p["key"], vm_max=float(vm_elem_max[emask].max()),
            vm_max_xyz=xyz, u_max_mm=float(u_mag[verts].max()),
            n_tets=int(emask.sum()),
        ))
    return field, results
