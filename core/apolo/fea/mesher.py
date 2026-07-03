"""Mallado tetraédrico con gmsh a partir de un STEP, con physical groups nombrados.

gmsh es single-instance GLOBAL (estado C compartido): todo acceso pasa por
``FEA_LOCK`` con ``initialize()``/``finalize()`` por análisis (el spike verificó 10
ciclos estables en el mismo proceso). El puente con OCP es SIEMPRE por archivo STEP
— nunca punteros nativos: el OCCT embebido de gmsh es otro build y la ABI no está
garantizada.

Las caras se identifican por MATCH GEOMÉTRICO (centro de masa + área) contra
descriptores extraídos de las caras OCCT bajo STATE_LOCK — el mismo espíritu que los
selectores declarativos: nada de índices frágiles entre kernels.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass

from . import FeaError, _require_fea

FEA_LOCK = threading.Lock()

MAX_TETS = 150_000  # ~600k dof P2; más allá spsolve/ensamblado no responde en tiempos MCP


@dataclass(frozen=True)
class FaceDesc:
    """Descriptor puro de una cara OCCT (extraído bajo STATE_LOCK, floats sin refs)."""

    center: tuple[float, float, float]
    area_mm2: float

    @classmethod
    def from_face(cls, face) -> "FaceDesc":
        c = face.center()
        return cls((float(c.X), float(c.Y), float(c.Z)), float(face.area))


def _match_surfaces(gmsh, descs: list[FaceDesc], surfaces: list[dict],
                    tol_center: float) -> list[int]:
    """Superficies gmsh que casan con los descriptores (centro tol + área ±1 %)."""
    tags = []
    for d in descs:
        best = None
        for s in surfaces:
            dc = math.dist(d.center, s["center"])
            if dc > tol_center:
                continue
            if d.area_mm2 > 0 and abs(s["area"] - d.area_mm2) > 0.01 * d.area_mm2 + 1e-6:
                continue
            if best is None or dc < best[0]:
                best = (dc, s["tag"])
        if best is None:
            raise FeaError(
                f"No encontré en la malla la cara con centro {tuple(round(c, 2) for c in d.center)} "
                f"y área {d.area_mm2:.1f} mm² — usa get_topology para elegir el selector "
                f"(candidatas: {[(tuple(round(c, 1) for c in s['center']), round(s['area'], 1)) for s in surfaces[:8]]})"
            )
        tags.append(best[1])
    return tags


def mesh_step(step_path: str, groups: dict[str, list[FaceDesc]], msh_path: str,
              mesh_size_mm: float | None = None) -> dict:
    """Malla el STEP en tets con un physical group de superficie por entrada de
    `groups` (mismo nombre) + el grupo de volumen "body". Devuelve
    {n_nodos, n_tets, size_mm}. Serializado por FEA_LOCK."""
    _require_fea()
    import gmsh

    with FEA_LOCK:
        # interruptible=False: NO instala el handler de SIGINT — obligatorio porque
        # los endpoints sync de FastAPI corren en un threadpool (signal solo funciona
        # en el hilo principal; sin esto el primer análisis da 500).
        gmsh.initialize(interruptible=False)
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("apolo_fea")
            gmsh.model.occ.importShapes(step_path)
            gmsh.model.occ.synchronize()

            x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(-1, -1)
            diag = math.dist((x0, y0, z0), (x1, y1, z1))
            size = float(mesh_size_mm) if mesh_size_mm else max(diag / 15.0, 1.0)

            surfaces = []
            for dim, tag in gmsh.model.getEntities(2):
                surfaces.append({
                    "tag": tag,
                    "center": gmsh.model.occ.getCenterOfMass(dim, tag),
                    "area": gmsh.model.occ.getMass(dim, tag),
                })
            tol_center = max(1e-3 * diag, 1e-3)
            for name, descs in groups.items():
                if not descs:
                    raise FeaError(f"El grupo '{name}' no tiene caras")
                tags = _match_surfaces(gmsh, descs, surfaces, tol_center)
                gmsh.model.addPhysicalGroup(2, tags, name=name)
            vols = [t for _, t in gmsh.model.getEntities(3)]
            if not vols:
                raise FeaError("El STEP no contiene ningún sólido (volumen) que mallar")
            gmsh.model.addPhysicalGroup(3, vols, name="body")

            gmsh.option.setNumber("Mesh.MeshSizeMax", size)
            gmsh.option.setNumber("Mesh.MeshSizeMin", size / 3.0)
            gmsh.model.mesh.generate(3)

            n_nodos = len(gmsh.model.mesh.getNodes()[0])
            _, tet_tags, _ = gmsh.model.mesh.getElements(3)
            n_tets = int(sum(len(t) for t in tet_tags))
            if n_tets == 0:
                raise FeaError("gmsh no generó tetraedros (¿sólido degenerado?)")
            if n_tets > MAX_TETS:
                raise FeaError(
                    f"Malla demasiado fina: {n_tets} tets (cap {MAX_TETS}). "
                    f"Sube mesh_size_mm (usado: {size:.1f} mm)"
                )
            gmsh.write(msh_path)
            return {"n_nodos": n_nodos, "n_tets": n_tets, "size_mm": round(size, 2)}
        finally:
            gmsh.finalize()
