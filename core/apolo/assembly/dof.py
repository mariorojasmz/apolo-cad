"""Reporte de GRADOS DE LIBERTAD del ensamblaje (V6.3c) — el análogo 3D del
`dof/redundantes/conflictivas` del croquis 2D (PlaneGCS).

Responde «¿qué puede moverse y qué está sobre-restringido?» por conteo clásico (Grübler):
cada sólido parte de 6 GDL (cuerpo libre) y ground/junta/mates se los restan. Es
DETERMINISTA y BARATO (puro conteo, sin OCCT).

SEMÁNTICA de las juntas: en el resto de Apolo las juntas son cinemática de VISUALIZACIÓN
(pose preview), no restan GDL en ningún cómputo. Aquí SÍ cuentan como restricción — es la
lectura útil para el usuario: el hijo de una junta giratoria tiene 1 GDL (gira), no 6.

HONESTIDAD del conteo: Grübler NO detecta redundancia geométrica — un sólido con
coincidente (−3) + concéntrico (−4) suma 7 «removidos» y se marca `sobre_restringido`
aunque sea perfectamente válido (las restricciones son consistentes y el solver las
satisface). Los conflictos REALES (restricciones que no se pueden cumplir a la vez) los
detecta el solver de mates en la mutación (MateError + rollback), no este conteo — por eso
un doc que regeneró bien nunca trae `overconstrained` del solver. El payload lo declara.
"""

from __future__ import annotations

# GDL que RESTA cada entidad a los 6 de un cuerpo libre.
_JOINT_REMOVE = {"fija": 6, "giratoria": 5, "continua": 5, "prismatica": 5}
_MATE_REMOVE = {"coincidente": 3, "distancia": 3, "concentrico": 4, "paralelo": 2, "angulo": 1}


def dof_report(
    scene: dict,
    joints: dict,
    mates: dict,
    grounds: dict,
    overconstrained: set | None = None,
) -> dict:
    """Grados de libertad por sólido (conteo Grübler). `scene` = dict fid→Feature; `joints`/
    `mates`/`grounds` = registros del documento. `overconstrained` = ids que el solver de mates
    marcó con residuo (un doc regenerado no trae ninguno: el solver rechaza conflictos en la
    mutación) — se fusiona con el conteo. Devuelve un dict serializable, determinista."""
    over = set(overconstrained or ())

    grounded: dict[str, list[str]] = {}
    for name, g in grounds.items():
        grounded.setdefault(g["feature"], []).append(name)
    joint_of: dict[str, dict] = {j["child"]: {**j, "name": name} for name, j in joints.items()}
    mates_of: dict[str, list[str]] = {}
    for name, m in mates.items():
        mates_of.setdefault(m["feature_b"], []).append(name)

    features: list[dict] = []
    total_dof = 0
    libres = 0
    sobre = 0
    for fid in sorted(scene):
        feat = scene[fid]
        if getattr(feat, "is_guide", False):
            continue  # los bocetos-guía no son piezas del ensamblaje
        removed = 0
        restringido_por: list[str] = []
        if fid in grounded:
            removed += 6
            restringido_por.extend(f"tierra:{n}" for n in grounded[fid])
        j = joint_of.get(fid)
        if j is not None:
            removed += _JOINT_REMOVE.get(j.get("type", "fija"), 6)
            restringido_por.append(f"junta:{j['name']}")
        for mname in mates_of.get(fid, ()):  # noqa: SIM118
            m = mates[mname]
            removed += _MATE_REMOVE.get(m.get("type", "coincidente"), 3)
            restringido_por.append(f"mate:{mname}")

        dof = max(0, 6 - removed)
        if removed > 6 or fid in over:
            estado, dof = "sobre_restringido", 0
            sobre += 1
        elif removed == 0:
            estado = "libre"
            libres += 1
        elif dof == 0:
            estado = "fijo"
        else:
            estado = "parcial"
        total_dof += dof
        features.append({
            "id": fid,
            "name": feat.name,
            "dof": dof,
            "estado": estado,
            "restringido_por": restringido_por,
        })

    resumen = _resumen(len(features), libres, sobre, total_dof)
    return {
        "features": features,
        "total_dof": total_dof,
        "libres": libres,
        "sobre_restringidos": sobre,
        "resumen": resumen,
        "nota": (
            "Conteo heurístico (Grübler): no detecta redundancia geométrica; un "
            "'sobre_restringido' por conteo puede ser redundancia benigna. Los conflictos "
            "REALES los rechaza el solver de mates en la edición."
        ),
    }


def _resumen(n: int, libres: int, sobre: int, total_dof: int) -> str:
    if n == 0:
        return "Sin piezas."
    partes = [f"{n} pieza{'s' if n != 1 else ''}", f"{total_dof} GDL"]
    if libres:
        partes.append(f"{libres} libre{'s' if libres != 1 else ''}")
    if sobre:
        partes.append(f"{sobre} sobre-restringida{'s' if sobre != 1 else ''}")
    return " · ".join(partes)
