"""Reparable: las piezas de desgaste se cambian sin cortar ni soldar (plan puerta-de-publicacion,
D5; MIL-HDBK-470A cap. 4 y DFMA, Boothroyd-Dewhurst: la pieza que se gasta se desmonta).

Puro (sin OCCT ni `Document`): los barridos los mide `services/calidad_reparabilidad.py`.

- **Pieza de desgaste** (`desgaste`): banda, cadena, rodamiento, chumacera, piñón, rodillo y
  motorreductor, por catálogo y rol (`roles.rol_union`).
- **Marco soldado** (`marco_soldado`): cada grupo de piezas unidas por soldadura/pegado que
  contiene estructura o una pieza anclada: no se desarma sin cortar.
- **Sin soldadura** (`soldada_al_marco`): la UNIDAD de la pieza (lo soldado/pegado a ella) no
  toca el marco. Un piñón soldado a su rodillo es una unidad (se cambia el rodillo con su piñón),
  un rodamiento soldado al bastidor no.
- **Camino de salida** (`camino_libre`): en alguna de las 6 direcciones de los ejes, lo que la
  caja de la unidad barre hasta salir de la máquina no es marco soldado (todo lo demás se
  desatornilla o se aparta). La cadena se abre por su eslabón de unión (ISO 606) y la banda tiene
  su propio control: no se barren.
- **Banda montable** (`banda_montable`): el lazo sale de costado (a lo largo del eje de los
  tambores) si en ese lado nada de lo que su propio sólido barre pertenece a un grupo soldado que
  además pasa POR DENTRO del lazo (la estructura soldada que lo abraza). Un empalme mecánico
  declarado en el nombre (grapas, empalme mecánico) la deja montar abierta.
"""

from __future__ import annotations

import re

from .seguridad.modelo import SOLDADAS, Pieza, clase_flexible, componentes, item, vecinos

NORMA = "MIL-HDBK-470A cap. 4 + DFMA (Boothroyd-Dewhurst): desgaste desmontable sin cortar"
_RODAMIENTO_RE = re.compile(r"^\s*(rodamientos?|bearings?)\b", re.I)
_PINON_RE = re.compile(r"\b(pi[ñn][oó]n(es)?|catarinas?|sprockets?|poleas?)\b", re.I)
_RODILLO_RE = re.compile(r"\brodillos?\b", re.I)
_MOTOR_RE = re.compile(r"\b(moto-?reductor(es)?|reductor(es)?|gear-?motor)\b", re.I)
_EMPALME_RE = re.compile(r"\b(grapas?|empalme\s+mec[aá]nico|clipper|lacing|abierta)\b", re.I)
DIRECCIONES = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def desgaste(p: Pieza) -> str | None:
    """La clase de desgaste de una pieza, o None."""
    flex = clase_flexible(p)
    if flex == "banda":
        return "banda"
    if flex == "transmision":
        return "cadena"
    ultimo = p.nombre.split("·")[-1]
    if p.categoria == "rodamientos" or _RODAMIENTO_RE.match(ultimo):
        return "rodamiento"
    if p.rol == "chumacera" or p.categoria == "chumaceras":
        return "chumacera"
    if p.rol == "equipo" and (p.categoria in ("motorreductores", "motorreductores_sinfin")
                              or _MOTOR_RE.search(p.nombre)):
        return "motorreductor"
    if p.rol == "gira" and (p.categoria == "transmision" or _PINON_RE.search(ultimo)):
        return "piñón"
    if p.categoria == "rodillos" or (p.rol == "gira" and _RODILLO_RE.search(ultimo)):
        return "rodillo"
    return None


def marco_soldado(piezas: dict[str, Pieza], uniones: list[dict]) -> set[str]:
    adj = vecinos(uniones, SOLDADAS)
    marco: set[str] = set()
    for comp in componentes(set(adj) & set(piezas), adj):
        if len(comp) >= 2 and any(piezas[i].rol == "estructura" or piezas[i].anclada
                                  for i in comp):
            marco |= comp
    return marco


def unidad(fid: str, uniones: list[dict]) -> set[str]:
    """La pieza y todo lo soldado/pegado a ella (lo que sale junto)."""
    adj = vecinos(uniones, SOLDADAS)
    return next((c for c in componentes(set(adj) | {fid}, adj) if fid in c), {fid})


def camino_soldadura(fid: str, piezas: dict[str, Pieza], uniones: list[dict]) -> list[str]:
    """La cadena de soldaduras más corta de la pieza a la estructura (o a lo anclado)."""
    adj = vecinos(uniones, SOLDADAS)
    previo, cola = {fid: None}, [fid]
    while cola:
        n = cola.pop(0)
        p = piezas.get(n)
        if n != fid and p is not None and (p.rol == "estructura" or p.anclada):
            camino = [n]
            while previo[camino[-1]] is not None:
                camino.append(previo[camino[-1]])
            return camino[::-1]
        for m in sorted(adj.get(n, ())):
            if m not in previo:
                previo[m] = n
                cola.append(m)
    return []


def piezas_de_desgaste(piezas: dict[str, Pieza]) -> dict[str, str]:
    return {i: c for i, p in sorted(piezas.items()) if (c := desgaste(p))}


def item_sin_soldadura(piezas, uniones, id_: str) -> dict:
    marco = marco_soldado(piezas, uniones)
    desg = piezas_de_desgaste(piezas)
    titulo = "Las piezas de desgaste no están soldadas a la estructura"
    modo = "una pieza de desgaste soldada obliga a cortar y soldar para cambiarla"
    if not desg:
        return item(id_, titulo, "NO_APLICA", modo, NORMA, {"motivo": "sin piezas de desgaste"})
    fallas = []
    for i, clase in desg.items():
        if i in marco:
            fallas.append({"id": i, "nombre": piezas[i].nombre, "clase": clase,
                           "soldadura": camino_soldadura(i, piezas, uniones)})
    ev = {"piezas_de_desgaste": len(desg),
          "por_clase": {c: sum(1 for v in desg.values() if v == c) for c in sorted(set(desg.values()))},
          "soldadas": fallas}
    if fallas:
        return item(id_, titulo, "FALLA", modo, NORMA, ev, [f["id"] for f in fallas],
                    "; ".join(f"{f['nombre']} soldada vía {' → '.join(f['soldadura'])}"
                              for f in fallas[:5]))
    return item(id_, titulo, "OK", modo, NORMA, ev, detalle=f"{len(desg)} piezas de desgaste")


def camino_libre(barridos: dict[tuple, list[str]], propia: set[str], marco: set[str]) -> dict:
    """`barridos`: {dirección: [ids que la caja de la unidad corta al salir]}. Libre = ninguno
    es marco soldado (fuera de la propia unidad). → {libre, direccion, bloqueos}."""
    bloqueos = {}
    for d in DIRECCIONES:
        if d not in barridos:
            continue
        duros = sorted(i for i in barridos[d] if i in marco and i not in propia)
        if not duros:
            return {"libre": True, "direccion": list(d), "aparta": sorted(barridos[d])[:10]}
        bloqueos[str(list(d))] = duros[:6]
    return {"libre": False, "direccion": None, "bloqueos": bloqueos}


def empalme_mecanico(p: Pieza) -> bool:
    return bool(_EMPALME_RE.search(p.nombre))


def banda_montable(lados: dict[str, list[str]]) -> dict:
    """`lados`: {«+Y»/«−Y»…: [ids soldados que abrazan el lazo en ese lado]}."""
    libres = [k for k, v in lados.items() if not v]
    return {"montable": bool(libres), "lado": libres[0] if libres else None,
            "bloqueos": {k: v[:8] for k, v in lados.items() if v}}
