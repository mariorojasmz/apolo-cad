"""El video de la tienda en modo MONTAJE (plan video-tienda-pulido, F1b · D8): las etapas siguen
la secuencia de `montaje.py` (cómo se arma en el taller), no el log (cómo se diseñó).

Cada paso de montaje se vuelve un `construccion.Paso` SINTÉTICO, con `k` = su número en la
secuencia, las piezas de la escena FINAL como agregados y el grupo de su primera pieza (un
conjunto soldado trae piezas de varios grupos y entra entero: el bastidor con su base del motor). Así el compactado, las etapas, sus títulos, duraciones
y rótulos con datos (D1 y D2) son los mismos del modo diseño. En el guion, cada paso de una etapa
es la LISTA de piezas que entra (en diseño, el `k` del log): el video las va sumando a la escena
terminada, sin regenerar prefijos.
"""

from __future__ import annotations

from dataclasses import replace

from apolo.services.construccion import (
    TIEMPOS,
    Etapa,
    Paso,
    Tiempos,
    _ruta_por_comando,
    etapas,
    pasos_visuales,
    revelado,
)
from apolo.services.guion_video import MODO_DISENO, MODO_MONTAJE, MODOS
from apolo.services.montaje import PasoMontaje, secuencia


def _ruta(rutas: dict, cid: str) -> tuple[str, ...]:
    # insert_project emite command_ids sintéticos «{cmd}_{orig}» (como `pasos_visuales`)
    return rutas.get(cid) or rutas.get(cid.split("_", 1)[0]) or ()


def pasos_montaje(doc, secuencia_: list[PasoMontaje] | None = None) -> list[Paso]:
    """Los pasos del video en orden de montaje (`k` = 1, 2, …: su lugar en la secuencia)."""
    escena = doc.scene
    rutas = _ruta_por_comando(doc.groups)
    out: list[Paso] = []
    for pm in secuencia(doc) if secuencia_ is None else secuencia_:
        nombres = {f: escena[f].name for f in pm.ids}
        roles, listas = revelado(escena, pm.ids, nombres)
        out.append(Paso(k=len(out) + 1, cmd_id="", tipo="montaje", titulo=pm.titulo,
                        etiqueta=pm.titulo, agregados=pm.ids, quitados=(), reemplazados=(),
                        revelado=listas, roles=roles, nombres=nombres,
                        grupos=_ruta(rutas, escena[pm.ids[0]].command_id)))
    return out


def etapas_montaje(doc, duracion_objetivo_s: float = 75.0, *, tiempos: Tiempos = TIEMPOS,
                   datos=None) -> list[Etapa]:
    """Las etapas del video de montaje; `Etapa.pasos` = tupla de tuplas de piezas."""
    pasos = pasos_montaje(doc)
    ids_de = {p.k: p.agregados for p in pasos}
    out, previo = [], 0
    for e in etapas(pasos, duracion_objetivo_s, tiempos=tiempos, datos=datos):
        tandas = []
        for k in e.pasos:  # el último k de cada paso compacto: lo que entró desde el anterior
            tandas.append(tuple(f for j in range(previo + 1, k + 1) for f in ids_de[j]))
            previo = k
        out.append(replace(e, pasos=tuple(tandas)))
    return out


def etapas_del_modo(doc, duracion_objetivo_s: float, modo: str = MODO_MONTAJE, *,
                    datos=None) -> list[Etapa]:
    """Las etapas del guion según `modo`: «montaje» (D8, el de la tienda) o «diseño» (el log)."""
    if modo not in MODOS:
        raise ValueError(f"Modo de video desconocido: {modo!r} (válidos: {', '.join(MODOS)})")
    if modo == MODO_DISENO:
        return etapas(pasos_visuales(doc), duracion_objetivo_s, datos=datos)
    return etapas_montaje(doc, duracion_objetivo_s, datos=datos)
