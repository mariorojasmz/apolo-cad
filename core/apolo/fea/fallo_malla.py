"""Un fallo de ``gmsh.model.mesh.generate`` → ``FeaError`` (400) que nombra las piezas.

gmsh lanza un ``Exception`` crudo («Invalid boundary mesh (overlapping facets) on surface
730 surface 737») que subía como 500 y no decía de qué pieza era ni qué hacer. Aquí, ANTES
de ``gmsh.finalize()`` (el modelo vivo es la única fuente de esos tags), se leen las
superficies que nombra el texto: su tipo, su área, su radio si es curva y los volúmenes que
bordean → la pieza dueña. Todo best-effort: lo que gmsh no deje leer se omite y, sin
superficies identificables, el error lleva el texto de gmsh con las mismas salidas.
Plan ``docs/plans/fea-chapa-empernada.md`` (D3). Sin imports pesados: gmsh llega como
argumento.
"""

from __future__ import annotations

import re

from . import FeaError

_SUPERFICIE_RE = re.compile(r"\bsurface\s+(\d+)", re.IGNORECASE)
_MAX_SUPERFICIES = 6  # el mensaje es para leerlo, no un volcado

# tipos de superficie de gmsh («Cylinder», «BSpline surface») y de build123d
# («GeomType.CYLINDER») → el nombre que lee un ingeniero hispanohablante
_TIPOS = {
    "plane": "plano", "cylinder": "cilindro", "cone": "cono", "sphere": "esfera",
    "torus": "toro", "bspline": "B-spline", "bspline surface": "B-spline",
    "bezier": "Bézier", "bezier surface": "Bézier", "revolution": "revolución",
    "surface of revolution": "revolución", "extrusion": "extrusión",
    "surface of extrusion": "extrusión", "offset": "offset", "offset surface": "offset",
}


def tipo_es(nombre) -> str:
    """Tipo de superficie en español; lo desconocido pasa en minúsculas («» si no hay)."""
    clave = str(nombre or "").rsplit(".", 1)[-1].strip().lower()
    return _TIPOS.get(clave, clave)


def etiqueta_pieza(nombre: str | None, clave: str | None = None) -> str:
    """«nombre» (id); sin nombre, la clave; sin ninguno, «la pieza»."""
    if nombre and clave:
        return f"«{nombre}» ({clave})"
    if nombre or clave:
        return f"«{nombre or clave}»"
    return "la pieza"


def generar_3d(gmsh, *, size_mm: float, duenos: dict[int, str], objetivo: str,
               ensamblaje: bool) -> None:
    """``gmsh.model.mesh.generate(3)`` con su fallo traducido a ``FeaError``. `duenos`: tag de
    volumen → etiqueta de su pieza; `objetivo`: qué se mallaba («el ensamblaje», «la pieza»),
    para cuando el texto de gmsh no nombra superficies. Llamar con gmsh inicializado."""
    try:
        gmsh.model.mesh.generate(3)
    except Exception as exc:
        raise _explicar(gmsh, exc, size_mm=size_mm, duenos=duenos, objetivo=objetivo,
                        ensamblaje=ensamblaje) from exc


def _radio(gmsh, tag: int) -> float | None:
    """Radio de curvatura (1/κ máx) en el centro del dominio paramétrico; None si es plana o
    si gmsh no la deja evaluar."""
    try:
        bmin, bmax = gmsh.model.getParametrizationBounds(2, tag)
        uv = [(bmin[0] + bmax[0]) / 2.0, (bmin[1] + bmax[1]) / 2.0]
        k_max, k_min, _, _ = gmsh.model.getPrincipalCurvatures(tag, uv)
        k = max(abs(float(k_max[0])), abs(float(k_min[0])))
    except Exception:  # noqa: BLE001 — best-effort: el mensaje sale sin radio
        return None
    return 1.0 / k if k > 1e-9 else None


def _superficie(gmsh, tag: int, duenos: dict[int, str]) -> dict | None:
    """Tipo, área, radio y piezas dueñas de una superficie del modelo vivo (None si gmsh no
    la conoce: el texto pudo nombrar una entidad que ya no existe)."""
    try:
        tipo = tipo_es(gmsh.model.getType(2, tag))
        area = float(gmsh.model.occ.getMass(2, tag))
        vols, _ = gmsh.model.getAdjacencies(2, tag)
    except Exception:  # noqa: BLE001
        return None
    piezas = list(dict.fromkeys(duenos[int(v)] for v in vols if int(v) in duenos))
    return {"tag": tag, "tipo": tipo, "area": area, "radio": _radio(gmsh, tag),
            "piezas": piezas}


def _num(x: float) -> str:
    return f"{round(x, 1):g}"


def _explicar(gmsh, exc: Exception, *, size_mm: float, duenos: dict[int, str],
              objetivo: str, ensamblaje: bool) -> FeaError:
    texto = " ".join(str(exc).split()) or type(exc).__name__
    tags = list(dict.fromkeys(int(t) for t in _SUPERFICIE_RE.findall(texto)))
    sups = [s for s in (_superficie(gmsh, t, duenos) for t in tags[:_MAX_SUPERFICIES]) if s]
    piezas = list(dict.fromkeys(p for s in sups for p in s["piezas"]))
    malla = f"{_num(size_mm)} mm"

    if piezas:
        msg = f"gmsh no pudo mallar {' y '.join(piezas)} con malla de {malla} («{texto}»)."
        partes = []
        for s in sups:
            desc = f"{s['tag']} {s['tipo'] or 'superficie'}"
            if s["radio"] is not None:
                desc += f" r ≈ {_num(s['radio'])} mm"
            desc += f", {s['area']:.0f} mm²"
            if len(piezas) > 1 and s["piezas"]:
                desc += f" de {' y '.join(s['piezas'])}"
            partes.append(desc)
        msg += f" Superficies que nombra gmsh: {'; '.join(partes)}."
        radios = [s["radio"] for s in sups if s["radio"] is not None]
        if radios and min(radios) < size_mm / 4.0:
            msg += (f" Un radio de {_num(min(radios))} mm frente a una malla de {malla} queda "
                    f"con una o dos cuerdas y sus facetas pueden cruzarse.")
        quien = "esa pieza" if len(piezas) == 1 else "esas piezas"
    else:
        msg = f"gmsh no pudo mallar {objetivo} con malla de {malla}: «{texto}»."
        if ensamblaje:
            msg += " No identifiqué a qué pieza pertenecen las superficies del error."
        quien = "la pieza sospechosa (p. ej. chapa plegada con radios chicos)"

    if ensamblaje:
        msg += (f" Qué hacer: 1) excluye {quien} del grupo (fea_assembly con `ids` sin ella); "
                f"2) analízala sola con fea_static a una malla del orden de unos pocos "
                f"espesores; 3) cambia mesh_size_mm: otro tamaño puede mallar.")
    else:
        msg += (" Qué hacer: 1) baja mesh_size_mm al orden de unos pocos espesores de la "
                "pieza; 2) prueba otro mesh_size_mm: otro tamaño puede mallar; 3) si viene "
                "de un ensamblaje, déjala fuera del grupo de fea_assembly.")
    return FeaError(msg)
