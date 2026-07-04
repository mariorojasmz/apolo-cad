"""Esqueleto de bastidor a partir de aristas ARBITRARIAS (G3).

Generaliza el weldment rectangular: nodos 3D + aristas (pares de índices) → un
miembro de perfil del catálogo a lo largo de CADA arista (en cualquier dirección),
recortado a tope, con lista de corte (BOM) y cordones de soldadura en los nodos.
Reutiliza WeldmentPart/_section del weldment y la orientación Z→dirección de
kernel.matrix. Sirve para A-frames, trípodes, bastidores inclinados, cerchas.
"""

from __future__ import annotations

import math

from apolo.kernel.matrix import direction_to_euler
from apolo.kernel.shapes import place

from .catalog import build_component
from .weldment import WeldmentPart, _section


def frame_from_edges(nodes, edges, perfil_ref: str, cordones: bool = True,
                     esquinas: str = "tope") -> list[WeldmentPart]:
    pts = [tuple(float(c) for c in n) for n in (nodes or [])]
    if len(pts) < 2:
        raise ValueError("El esqueleto necesita al menos 2 nodos")
    if any(len(n) != 3 for n in pts):
        raise ValueError("Cada nodo es [x, y, z]")
    if not edges:
        raise ValueError("El esqueleto necesita al menos 1 arista")
    if esquinas not in ("tope", "inglete"):
        raise ValueError("esquinas debe ser 'tope' o 'inglete'")

    sec = _section(perfil_ref)
    parts: list[WeldmentPart] = []
    degree = [0] * len(pts)

    pairs: list[tuple[int, int]] = []
    for e in edges:
        if len(e) != 2:
            raise ValueError("Cada arista es [i, j] (índices de nodo)")
        i, j = int(e[0]), int(e[1])
        if not (0 <= i < len(pts)) or not (0 <= j < len(pts)):
            raise ValueError(f"Arista ({i}, {j}): índice de nodo fuera de rango")
        if i == j:
            raise ValueError(f"Arista ({i}, {j}): los dos nodos son el mismo")
        pairs.append((i, j))
        degree[i] += 1
        degree[j] += 1

    # adyacencia nodo → nodos vecinos (para el inglete en nodos de grado 2)
    adj: dict[int, list[int]] = {}
    for i, j in pairs:
        adj.setdefault(i, []).append(j)
        adj.setdefault(j, []).append(i)

    def _neighbor_out(node: int, other: int):
        """Dirección SALIENTE del vecino en `node` (None si no aplica inglete):
        solo nodos de grado 2 — el vecino es la OTRA arista del nodo."""
        if esquinas != "inglete" or degree[node] != 2:
            return None
        vecino = next((v for v in adj[node] if v != other), None)
        if vecino is None:  # dos aristas al MISMO otro nodo (degenerado)
            return None
        return tuple(pts[vecino][c] - pts[node][c] for c in range(3))

    for k, (i, j) in enumerate(pairs, start=1):
        a, b = pts[i], pts[j]
        d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        length = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
        if length <= 2.0 * sec:
            raise ValueError(
                f"La arista ({i}, {j}) mide {length:.0f} mm: demasiado corta para el "
                f"perfil {perfil_ref} (necesita > {2 * sec:.0f} mm)"
            )
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)
        rot = direction_to_euler(d)
        end1 = end2 = None
        if esquinas == "inglete":
            from .miter import member_ends

            end1, end2 = member_ends(a, b, _neighbor_out(i, j), _neighbor_out(j, i))
        if end1 is None and end2 is None:
            # a tope (histórico, y fallback de grado≠2 / α>75°): mismo base_key de siempre
            cut = length - 2.0 * sec
            shape, _ = build_component(perfil_ref, cut)
            base_key = f"comp|{perfil_ref}|{round(cut, 2)}"
            miter = None
        else:
            from .miter import mitered_profile

            shape, base_key, cut, miter = mitered_profile(perfil_ref, length, sec, end1, end2)
        parts.append(
            WeldmentPart(
                suffix=f"m{k}", name=f"Miembro ({i}-{j})", shape=place(shape, mid, rot),
                component=perfil_ref, cut_length=cut, base_key=base_key, base_shape=shape,
                position=mid, rotation=rot, miter=miter,
            )
        )

    if cordones:
        from build123d import Sphere

        r = sec * 0.6
        bead = Sphere(r)
        bead_key = f"weldbead|{round(r, 2)}"
        for n, node in enumerate(pts):
            if degree[n] == 0:
                continue  # nodo suelto: sin cordón
            parts.append(
                WeldmentPart(
                    suffix=f"bead{n + 1}", name="Cordón", shape=place(bead, node, (0.0, 0.0, 0.0)),
                    component=None, cut_length=None, base_key=bead_key, base_shape=bead,
                    position=node, rotation=(0.0, 0.0, 0.0),
                )
            )

    return parts
