"""La guarda fija se quita SÓLO con herramienta (ISO 14120 §3.2 y 7.1; ISO 12100 6.3.3.2.2).

Sobre el grafo de uniones DECLARADAS (`fasten`), por cada guarda (rol «guarda» de
`roles.rol_union`) que no gira:

- su CUERPO = la guarda + lo soldado/pegado a ella que no es estructura ni gira (orejas,
  faldones, fondo: piezas de la misma guarda);
- lo une a la máquina al menos un **perno** declarado (`fasten kind=perno` o `join_bolted`);
- **no** está soldada ni pegada a la estructura (no se podría quitar);
- **no** se une (de ningún modo) a una pieza que gira o se mueve;
- «sólo contacto» = apoyada: FALLA (se quita sin herramienta, o se cae).

Las uniones con tornillería (perno, tuerca, arandela) son ruido del herraje y no cuentan. Una
«guarda» que gira con su cuerpo (la tapa-cubo de un tambor) no es guarda: es parte del peligro, y
se lista aparte.
"""

from __future__ import annotations

from .modelo import SOLDADAS, Pieza, es_tornilleria

NORMA = "ISO 14120:2015 §3.2/7.1 (guarda fija: sólo con herramienta) + ISO 12100 6.3.3.2.2"
_NO_ENTRA = {"estructura", "eje", "chumacera", "equipo", "gira", "flexible", "pie"}


def cuerpo_guarda(g: str, piezas: dict[str, Pieza], uniones: list[dict], moviles: set) -> set:
    cuerpo, pila = set(), [g]
    while pila:
        n = pila.pop()
        if n in cuerpo:
            continue
        cuerpo.add(n)
        for u in uniones:
            if u.get("kind") not in SOLDADAS or n not in (u["a"], u["b"]):
                continue
            m = u["b"] if u["a"] == n else u["a"]
            p = piezas.get(m)
            if (p is None or m in cuerpo or m in moviles or p.anclada or p.rol in _NO_ENTRA
                    or es_tornilleria(p)):
                continue
            pila.append(m)
    return cuerpo


def revisar_guardas(piezas: dict[str, Pieza], uniones: list[dict], moviles: set) -> dict:
    """→ {guardas: [{ids, nombre, estado, motivo, pernos, soldadas, contactos, moviles}],
    excluidas_por_girar: [ids]}."""
    guardas = sorted(i for i, p in piezas.items() if p.rol == "guarda")
    excluidas = [i for i in guardas if i in moviles]
    vistos: set[str] = set()
    out = []
    for g in guardas:
        if g in moviles or g in vistos:
            continue
        cuerpo = cuerpo_guarda(g, piezas, uniones, moviles)
        vistos |= cuerpo
        pernos, soldadas, contactos, a_moviles = set(), set(), set(), set()
        for u in uniones:
            dentro_a, dentro_b = u["a"] in cuerpo, u["b"] in cuerpo
            if dentro_a == dentro_b:
                continue
            otra = u["b"] if dentro_a else u["a"]
            p = piezas.get(otra)
            if p is None or es_tornilleria(p):
                continue
            if otra in moviles:
                a_moviles.add(otra)
            elif u.get("kind") == "perno":
                pernos.add(otra)
            elif u.get("kind") in SOLDADAS:
                soldadas.add(otra)
            else:
                contactos.add(otra)
        if a_moviles:
            estado, motivo = "FALLA", "unida a una pieza que se mueve"
        elif soldadas:
            estado, motivo = "FALLA", "soldada o pegada a la máquina: no se quita"
        elif not pernos:
            estado = "FALLA"
            motivo = ("sólo apoyada (contacto): se quita sin herramienta" if contactos
                      else "sin unión declarada a la máquina")
        else:
            estado, motivo = "OK", "atornillada"
        out.append({"ids": sorted(cuerpo), "nombre": piezas[g].nombre, "estado": estado,
                    "motivo": motivo, "pernos": sorted(pernos), "soldadas": sorted(soldadas),
                    "contactos": sorted(contactos), "moviles": sorted(a_moviles)})
    return {"guardas": out, "excluidas_por_girar": excluidas}
