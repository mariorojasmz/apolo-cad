"""Las cadenas de rodillos del modelo y de qué comando sale cada una (plan lo-que-se-mueve, D1):
el insumo de `transmision_flexible.de_su_comando` (`library/calidad/cadenas.py`) y su detector en
`puerta_hechos`. El llamador sostiene STATE_LOCK.

Una cadena es una pieza con ref `CADENA-*`. Sale de su comando si el comando que la creó (por
`command_id` en `doc.commands`) es `create_chain` o `create_hoist_chain`, o si su `mesh_key` es el
de esos executors («cadena|…», «izaje|…»): así se reconoce también la que corrió dentro de un
compuesto (`create_roller_conveyor`) o llegó por `insert_project`, con command_id sintético.
"""

from __future__ import annotations

from apolo.library.calidad.cadenas import COMANDOS

#: El prefijo del `mesh_key` de cada executor de cadena (`exec_transmision.Transmision.clave`,
#: `library/izaje_geom.py`).
PREFIJOS_MESH = ("cadena|", "izaje|")


def _comando_de(cid: str, tipo: dict) -> tuple[str, str | None]:
    """(command_id del comando del log que la creó, su tipo): el exacto o, con un command_id
    sintético `{cmd}_…`, el prefijo más largo que es un comando del log."""
    if cid in tipo:
        return cid, tipo[cid]
    padres = [c for c in tipo if cid.startswith(f"{c}_")]
    if padres:
        c = max(padres, key=len)
        return c, tipo[c]
    return cid, None


def cadenas_de_rodillos(doc) -> list[dict]:
    """[{id, nombre, ref, comando, tipo, de_su_comando}] de cada pieza `CADENA-*` (no guía)."""
    tipo = {c["id"]: c.get("type") for c in doc.commands}
    out = []
    for fid in sorted(doc.scene):
        f = doc.scene[fid]
        ref = str(getattr(f, "component", None) or "")
        if not ref.startswith("CADENA-") or getattr(f, "is_guide", False):
            continue
        cmd, t = _comando_de(str(getattr(f, "command_id", None) or ""), tipo)
        mesh = str(getattr(f, "mesh_key", None) or "")
        out.append({"id": fid, "nombre": getattr(f, "name", None) or fid, "ref": ref,
                    "comando": cmd, "tipo": t,
                    "de_su_comando": t in COMANDOS or mesh.startswith(PREFIJOS_MESH)})
    return out


def elementos(cadenas: list[dict]) -> dict:
    """{de_su_comando: n, a_mano: n} sin los ceros (el detector de `puerta_hechos`)."""
    n = sum(1 for c in cadenas if c["de_su_comando"])
    return {k: v for k, v in {"de_su_comando": n, "a_mano": len(cadenas) - n}.items() if v}
