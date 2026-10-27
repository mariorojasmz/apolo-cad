"""¿La corta la seta? La cadena CABLEADA de la parada de emergencia hasta una carga (plan
bloqueo-de-vastago D6).

Sobre el `Analisis` de `redes.py`: cada `Llegada` dice por qué contactos (`via`) llega un
potencial a un borne. Un contacto está «en la cadena de la seta» si es:
  - el NC de un aparato con `parada_emergencia` (la seta);
  - el NA de un aparato que SÓLO se energiza a través de la cadena: toda llegada ACTIVA (no de
    referencia) a cada una de sus cargas que lo mueven (`bobina` de un contactor o relé, `entrada`
    de un relé de seguridad) pasa por un contacto de la cadena. Se itera hasta que no cambia.
Una carga la corta la seta si toda llegada activa a sus bornes pasa por un contacto de la cadena.
Si alguna llega sin pasar (directo de la fuente, por un pulsador, por una salida del PLC), NO: lo
que la corta es el programa o la mano, no la cadena cableada (lo que pide la categoría 1 de EN ISO
13849-1). Es el peor caso de las llegadas, como el resto del ERC: nunca un «sí» inventado.

Puro: sobre el análisis de `redes.analizar`.
"""

from __future__ import annotations

from .redes import Analisis

#: Cargas que MUEVEN los contactos de su aparato (una bobina, la entrada de un relé de seguridad).
ACTUAN = ("bobina", "entrada")


def _activas(a: Analisis, des: str, bornes) -> list:
    out = []
    for b in bornes:
        idx = a.red(des, b)
        out += [ll for ll in (a.llegadas[idx] if idx is not None else ()) if not ll.potencial.referencia]
    return out


def contactos_de_la_cadena(a: Analisis) -> set[str]:
    """Las etiquetas «-S0:11-12» de los contactos de la cadena de la seta (ver el módulo)."""
    cadena = {f"{d.designacion}:{c.de}-{c.a}" for d in a.dispositivos.values() if d.parada_emergencia
              for c in d.caminos if c.tipo == "NC"}
    if not cadena:
        return cadena
    hechos: set[str] = set()
    cambio = True
    while cambio:
        cambio = False
        for d in a.dispositivos.values():
            if d.parada_emergencia or d.designacion in hechos:
                continue
            cargas = [c for c in d.cargas if c.tipo in ACTUAN]
            nas = [c for c in d.caminos if c.tipo == "NA"]
            if not cargas or not nas:
                continue
            llegadas = [ll for c in cargas for ll in _activas(a, d.designacion, c.bornes)]
            if llegadas and all(cadena & set(ll.via) for ll in llegadas):
                hechos.add(d.designacion)
                cadena |= {f"{d.designacion}:{c.de}-{c.a}" for c in nas}
                cambio = True
    return cadena


def cortada_por_seta(a: Analisis, des: str, bornes) -> tuple[bool, str]:
    """(¿toda la tensión que llega a los `bornes` de `des` pasa por la cadena de la seta?, por qué)."""
    if not any(d.parada_emergencia for d in a.dispositivos.values()):
        return False, "no hay parada de emergencia (seta) en el circuito"
    llegadas = _activas(a, des, bornes)
    if not llegadas:
        return False, f"no llega tensión a {des} ({'/'.join(bornes)}): la bobina no está cableada"
    cadena = contactos_de_la_cadena(a)
    for ll in llegadas:
        if not cadena & set(ll.via):
            camino = " → ".join(ll.via) if ll.via else "directo"
            return False, (f"llega {ll.potencial.etiqueta} a {des} sin pasar por la seta ({camino}): la corta "
                           "el programa o un mando, no la cadena cableada")
    pasa = sorted({v for ll in llegadas for v in ll.via if v in cadena})
    return True, f"toda la tensión de {des} pasa por la cadena de la seta ({', '.join(pasa)})"
