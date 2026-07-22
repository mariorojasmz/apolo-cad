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
MAX_PIECES = 25     # tope de sólidos por ensamblaje (el solve del bastidor ya tarda minutos)


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


@dataclass(frozen=True)
class PieceMesh:
    """Un sólido del ensamblaje a mallar: su STEP propio + una CLAVE estable con la
    que la capa API vuelve a atar el resultado a la Feature (material/σy)."""

    key: str          # clave estable (feature_id) — nombre del physical group será piece_<idx>
    step_path: str    # STEP de UN sólido (o compound de una pieza), exportado bajo STATE_LOCK


def _assert_bonded_to_ground(gmsh, assigned: dict[int, int], fixed_tags: list[int],
                             pieces: list["PieceMesh"], piece_groups: list[dict]) -> None:
    """Verifica que TODA pieza esté pegada (por interfaz compartida) a la componente que
    toca el empotramiento. Una pieza suelta introduce un modo de cuerpo rígido → la
    rigidez es singular y el solve devuelve un desplazamiento sin sentido; mejor errar
    aquí nombrando la(s) pieza(s) que flotan. `assigned`: tag de volumen → índice de
    pieza. Debe llamarse tras synchronize (la topología ya existe)."""
    from collections import deque

    # aristas de adyacencia: dos piezas comparten una SUPERFICIE que bordea volúmenes de ambas
    adj: dict[int, set[int]] = {g["idx"]: set() for g in piece_groups}
    for _, stag in gmsh.model.getEntities(2):
        ups, _ = gmsh.model.getAdjacencies(2, stag)
        ps = {assigned[v] for v in ups if v in assigned}
        for a in ps:
            for b in ps:
                if a != b and a in adj:
                    adj[a].add(b)
    # piezas ancladas: las que bordean una cara fija
    anchored: set[int] = set()
    for ftag in fixed_tags:
        ups, _ = gmsh.model.getAdjacencies(2, ftag)
        anchored |= {assigned[v] for v in ups if v in assigned}
    if not anchored:
        raise FeaError("El empotramiento no toca ninguna pieza mallada (revisa las caras fijas)")
    # BFS desde las ancladas por el grafo de interfaces
    reach = set(anchored)
    dq = deque(anchored)
    while dq:
        p = dq.popleft()
        for q in adj.get(p, ()):
            if q not in reach:
                reach.add(q)
                dq.append(q)
    present = {g["idx"] for g in piece_groups}
    floating = sorted(present - reach)
    if floating:
        names = [pieces[i].key for i in floating]
        raise FeaError(
            f"Pieza(s) SUELTA(S) no pegada(s) al bastidor anclado: {names}. No comparten "
            f"interfaz de contacto con la estructura fija → el análisis sería un mecanismo "
            f"(matriz singular, desplazamiento sin sentido). Verifica la soldadura/contacto "
            f"o quítalas del grupo (p. ej. un soporte que solo toca el motor excluido)."
        )


def mesh_assembly(pieces: list[PieceMesh], fixed: list[FaceDesc],
                  loads: dict[str, list[FaceDesc]], msh_path: str,
                  mesh_size_mm: float | None = None) -> dict:
    """Malla BONDED de N sólidos: importa cada STEP, los FRAGMENTA juntos (interfaces
    compartidas → nodos compartidos = pegado, sin pares de contacto) y crea un
    physical group de VOLUMEN por pieza (``piece_<idx>``) + los de superficie
    (``fixed`` + claves de ``loads``). Devuelve
    ``{n_nodos, n_tets, size_mm, piece_groups, shared_volumes, absorbidas}``:
    ``piece_groups`` = [{idx, key, name, n_vols}] mapea cada pieza a su grupo.
    Serializado por FEA_LOCK (gmsh es global). Bonded lineal es la hipótesis CORRECTA
    para un bastidor SOLDADO — no un atajo."""
    # topes de entrada ANTES de exigir el extra [fea] o tocar gmsh (baratos y puros)
    if not pieces:
        raise FeaError("El ensamblaje no tiene piezas que mallar")
    if len(pieces) > MAX_PIECES:
        raise FeaError(
            f"El ensamblaje tiene {len(pieces)} sólidos (tope {MAX_PIECES}): acota el grupo "
            f"o excluye el herraje. El bonded de tantas piezas no resuelve en tiempo útil."
        )
    _require_fea()
    import gmsh

    with FEA_LOCK:
        gmsh.initialize(interruptible=False)
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("apolo_fea_asm")

            # 1) importar cada STEP y recordar de qué PIEZA vino cada volumen importado
            all_vols: list[tuple[int, int]] = []
            vol_piece: list[int] = []   # paralelo a all_vols: índice de pieza
            for i, p in enumerate(pieces):
                imported = gmsh.model.occ.importShapes(p.step_path)
                vols = [(d, t) for (d, t) in imported if d == 3]
                if not vols:
                    raise FeaError(
                        f"La pieza '{p.key}' no aportó ningún sólido al ensamblaje "
                        f"(¿es una superficie? el FEA necesita volumen)"
                    )
                all_vols.extend(vols)
                vol_piece.extend([i] * len(vols))
            gmsh.model.occ.synchronize()

            # estimación de tets ANTES de fragmentar/mallar (bbox × 6 / size³). La
            # estimación por BBOX es CONSERVADORA en bastidores dispersos (medido ~7×
            # sobre el real en la faja 38) → solo pre-bloquea si supera 4× el cap; el
            # cap DURO post-malla (1×) queda de red.
            x0, y0, z0, x1, y1, z1 = gmsh.model.getBoundingBox(-1, -1)
            diag = math.dist((x0, y0, z0), (x1, y1, z1))
            size = float(mesh_size_mm) if mesh_size_mm else max(diag / 15.0, 1.0)
            bbox_vol = max((x1 - x0) * (y1 - y0) * (z1 - z0), 0.0)
            n_est = 6.0 * bbox_vol / (size ** 3) if size > 0 else 0.0
            if n_est > 4 * MAX_TETS:
                raise FeaError(
                    f"Malla estimada ~{n_est:.0f} tets (estimación por bbox, conservadora; "
                    f"pre-bloqueo a {4 * MAX_TETS}, cap real {MAX_TETS}) con size {size:.1f} mm. "
                    f"Sube mesh_size_mm (p. ej. {size * (n_est / (4 * MAX_TETS)) ** (1 / 3):.0f}) "
                    f"o acota el grupo a menos piezas."
                )

            # 2) FRAGMENTAR todos los volúmenes juntos → interfaces coherentes (bonded)
            try:
                out, outmap = gmsh.model.occ.fragment(all_vols, [])
                gmsh.model.occ.removeAllDuplicates()
                gmsh.model.occ.synchronize()
            except Exception as exc:
                raise FeaError(
                    f"La fragmentación bonded falló (geometría sucia o solape degenerado): "
                    f"{exc}. Corre check_interference sobre el grupo para localizar el par "
                    f"problemático, o excluye la pieza sospechosa."
                ) from exc

            # 3) asignar cada volumen resultante a la PRIMERA pieza que lo reclama
            #    (un volumen de SOLAPE aparece en varios inputs → gana el declarado antes;
            #     se cuenta como compartido y se declara en el reporte)
            assigned: dict[int, int] = {}      # tag de volumen → índice de pieza
            shared = 0
            for j, outs in enumerate(outmap):
                pi = vol_piece[j]
                for (d, t) in outs:
                    if d != 3:
                        continue
                    if t in assigned:
                        if assigned[t] != pi:
                            shared += 1
                        continue
                    assigned[t] = pi

            piece_vols: dict[int, list[int]] = {i: [] for i in range(len(pieces))}
            for t, pi in assigned.items():
                piece_vols[pi].append(t)

            piece_groups = []
            absorbidas = []
            for i, p in enumerate(pieces):
                vols = sorted(piece_vols[i])
                if not vols:
                    absorbidas.append(p.key)   # pieza tragada por el solape de otra
                    continue
                name = f"piece_{i}"
                gmsh.model.addPhysicalGroup(3, vols, name=name)
                piece_groups.append({"idx": i, "key": p.key, "name": name, "n_vols": len(vols)})
            if not piece_groups:
                raise FeaError("Ninguna pieza sobrevivió a la fragmentación (¿solapes totales?)")

            # 4) superficies de frontera (empotramiento + cargas) por MATCH geométrico
            surfaces = []
            for dim, tag in gmsh.model.getEntities(2):
                surfaces.append({
                    "tag": tag,
                    "center": gmsh.model.occ.getCenterOfMass(dim, tag),
                    "area": gmsh.model.occ.getMass(dim, tag),
                })
            tol_center = max(1e-3 * diag, 1e-3)
            if not fixed:
                raise FeaError("Falta el grupo de caras fijas (empotramiento) del ensamblaje")
            fixed_tags = _match_surfaces(gmsh, fixed, surfaces, tol_center)
            gmsh.model.addPhysicalGroup(2, fixed_tags, name="fixed")
            for gname, descs in loads.items():
                if not descs:
                    raise FeaError(f"El grupo de carga '{gname}' no tiene caras")
                gmsh.model.addPhysicalGroup(2, _match_surfaces(gmsh, descs, surfaces, tol_center),
                                            name=gname)

            # 5) GUARDA de cuerpo rígido: toda pieza debe estar PEGADA (interfaz compartida)
            #    a la componente que toca el empotramiento. Una pieza suelta = modo de cuerpo
            #    rígido → matriz singular → desplazamiento basura; se ataja nombrándola.
            _assert_bonded_to_ground(gmsh, assigned, fixed_tags, pieces, piece_groups)

            gmsh.option.setNumber("Mesh.MeshSizeMax", size)
            gmsh.option.setNumber("Mesh.MeshSizeMin", size / 3.0)
            gmsh.model.mesh.generate(3)

            n_nodos = len(gmsh.model.mesh.getNodes()[0])
            _, tet_tags, _ = gmsh.model.mesh.getElements(3)
            n_tets = int(sum(len(t) for t in tet_tags))
            if n_tets == 0:
                raise FeaError("gmsh no generó tetraedros (¿geometría degenerada?)")
            if n_tets > MAX_TETS:
                raise FeaError(
                    f"Malla demasiado fina: {n_tets} tets (cap {MAX_TETS}). "
                    f"Sube mesh_size_mm (usado: {size:.1f} mm)"
                )
            gmsh.write(msh_path)
            return {
                "n_nodos": n_nodos, "n_tets": n_tets, "size_mm": round(size, 2),
                "piece_groups": piece_groups, "shared_volumes": shared,
                "absorbidas": absorbidas,
            }
        finally:
            gmsh.finalize()
