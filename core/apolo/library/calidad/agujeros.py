"""Control de AGUJEROS de una unión atornillada DECLARADA (F3c de puerta-sin-sobrediseno). Puro:
recibe lo que mide `services/calidad_agujeros.py` y devuelve ítems de la ficha de calidad.

El modo de falla: un `fasten kind=perno` (o un anclaje con sus pernos de expansión) declara pernos
entre dos piezas, pero ninguna tiene el patrón de agujeros en la geometría. La puerta de entrega lo
da por sujeto (la sujeción es la DECLARADA) y `union.agarre` sólo mide la tornillería MODELADA:
pasaba las dos puertas y lo encontró un revisor de taller a ciegas (la chumacera sobre el puente
del tanque, el portasello, las placas de piso de la mezcladora y del tanque). Al taller llega una
unión que no se puede armar.

El insumo de una unión (dict):

    {"union", "tipo": "fasten" | "anclaje", "d" (Ø nominal del perno o None), "pide" (agujeros
     por pieza: la `qty` declarada, o los pernos que dice la nota del anclaje; ≥ 1),
     "basta_una": bool,  # la nota dice «punta roscada»: una pieza lleva la rosca macho y la
                         # OTRA el agujero (no se sabe cuál: basta uno)
     "piezas": [{"fid", "nombre", "juzgada": bool, "motivo" (si no se juzga), "agujeros": n}]}

Cada pieza que se juzga debe tener ≥ `pide` agujeros compatibles con el perno —pasantes o
roscados: Ø entre 0,75·d (broca de machuelo) y 1,6·d + 2 mm (paso holgado o ranura)— en la zona
de la unión; con `basta_una`, una sola de ellas. Un COLISO (ranura alargada de extremos redondos
o rectos, `services/calidad_colisos.py`) es agujero si su ANCHO cumple ese rango, y recibe los
pernos que caben a lo largo (`pernos_en_coliso`, F3e). No se juzga (lo decide `services`, con su
motivo) lo de catálogo y lo declarado «(compra…)» (sus agujeros son del fabricante: el builder o el
bloque a mano no siempre los modelan), la tornillería y los pasadores, una cadena o una banda, una
chapa perforada (la perforación no se modela), el eje que aprieta un prisionero ni la base sobre
la que va soldado un espárrago (no la atraviesa). Una unión sin piezas que juzgar no cuenta; una
con «sin perno» en la nota (un cierre de palanca) no llega. Las uniones internas de una plantilla
(`create_belt_conveyor`, `layout_tablero`…) las responde su plantilla y no llegan aquí.
"""

from __future__ import annotations

import math

from .item import FALLA, NO_APLICA, OK, Item, recortar

#: El Ø de un agujero «del perno» M d: desde la broca de machuelo (M10 → 8,5 = 0,85·d; 0,75·d da
#: margen a la rosca fina y al piloto de un autorroscante) hasta un paso holgado o una ranura
#: (ISO 273 serie gruesa M10 → 12; una placa de anclaje lleva a veces 1,5·d). Criterio de diseño.
D_MIN_FRACCION = 0.75
D_MAX_FRACCION, D_MAX_EXTRA_MM = 1.6, 2.0
#: Sin métrica declarada: cualquier agujero de perno razonable.
D_SIN_METRICA_MM = (3.0, 50.0)


def compatible(diametro_mm: float, d: float | None) -> bool:
    """¿Un agujero de `diametro_mm` sirve para un perno M`d` (pasante o roscado)? De un COLISO se
    pasa su ANCHO: el mismo rango."""
    if d is None:
        return D_SIN_METRICA_MM[0] <= diametro_mm <= D_SIN_METRICA_MM[1]
    return D_MIN_FRACCION * d - 1e-6 <= diametro_mm <= D_MAX_FRACCION * d + D_MAX_EXTRA_MM + 1e-6


def pernos_en_coliso(ancho: float, largo: float) -> int:
    """Cuántos pernos caben en un coliso (F3e): uno, y otro más por cada paso p1 ≥ 2,2·d0 de
    EN 1993-1-8 tabla 3.3 (`borde_agujero.P_MIN`, d0 = el ancho) entre los centros de sus
    extremos. Un coliso corto es UN agujero (antes sus dos medios cilindros contaban dos)."""
    from ..borde_agujero import P_MIN

    if ancho <= 0:
        return 1
    return 1 + int(max(largo - ancho, 0.0) / (P_MIN * ancho) + 1e-6)


def cuenta(agujero: dict) -> int:
    """Los pernos que recibe un agujero medido: 1, o los de su coliso."""
    if agujero.get("tipo") == "coliso":
        return pernos_en_coliso(agujero["d"], agujero.get("largo", agujero["d"]))
    return 1


def distancia_a_tramo(q, p0, p1, eje) -> float:
    """Distancia de la recta (`q`, `eje` unitario) al tramo p0–p1, medida en el plano ⊥ al eje:
    0 si la recta pasa por el coliso cuyos extremos tienen sus centros en p0 y p1."""
    def plano(x):
        w = tuple(x[i] - q[i] for i in range(3))
        k = sum(w[i] * eje[i] for i in range(3))
        return tuple(w[i] - k * eje[i] for i in range(3))

    a, b = plano(p0), plano(p1)
    ab = tuple(b[i] - a[i] for i in range(3))
    den = sum(x * x for x in ab)
    s = 0.0 if den < 1e-12 else max(0.0, min(1.0, -sum(a[i] * ab[i] for i in range(3)) / den))
    return math.sqrt(sum((a[i] + s * ab[i]) ** 2 for i in range(3)))


def juzgar(u: dict) -> tuple[str, str, dict] | None:
    """(estado, texto, números) de UNA unión; None si no tiene piezas que juzgar."""
    piezas = [p for p in u.get("piezas", []) if p.get("juzgada")]
    if not piezas:
        return None
    pide = max(1, int(u.get("pide") or 1))
    metrica = f"M{u['d']:g}" if u.get("d") else "de perno"
    faltan = [p for p in piezas if p.get("agujeros", 0) < pide]
    nums = {"pide": pide, "d": u.get("d"),
            "piezas": [{"fid": p["fid"], "agujeros": p.get("agujeros", 0)} for p in piezas]}
    if u.get("basta_una") and len(faltan) < len(piezas):
        return OK, f"{len(piezas) - len(faltan)} pieza(s) con sus agujeros {metrica}", nums
    if not faltan:
        return OK, f"{len(piezas)} pieza(s) con sus agujeros {metrica}", nums
    p = faltan[0]
    que = "la unión" if u.get("tipo") == "fasten" else "el anclaje"
    texto = (f"{p['nombre']} no tiene los agujeros {metrica} de {que} «{u['union']}» en la zona "
             f"donde se une: declara {pide} perno(s) y tiene {p.get('agujeros', 0)}")
    if u.get("basta_una"):
        texto += " (ninguna de sus piezas los tiene)"
    return FALLA, texto + ": taládralos (join_bolted taladra y declara en una operación)", nums


_CONTROLES = {
    "fasten": ("agujeros.union", "Cada unión atornillada declarada tiene sus agujeros",
               "una unión con pernos declarados y sin agujeros en las piezas: el taller no la puede "
               "armar, aunque la puerta de entrega la dé por sujeta",
               "criterio de taller (la unión declarada se fabrica: ISO 273 para el paso)"),
    "anclaje": ("agujeros.anclaje", "Cada anclaje con pernos declarados tiene sus taladros",
                "una placa de piso con pernos de expansión declarados y sin taladros: no se puede "
                "anclar", "criterio de taller (la placa de anclaje lleva sus taladros)"),
}


def controlar_agujeros(uniones: list[dict]) -> list[Item]:
    """Un ítem por clase (uniones declaradas y anclajes) sobre todas las uniones medidas."""
    items = []
    for tipo, (iid, titulo, modo, norma) in _CONTROLES.items():
        suyas = [u for u in uniones if u.get("tipo") == tipo]
        juicios = [(u, j) for u in suyas if (j := juzgar(u)) is not None]
        no_juzgadas = len(suyas) - len(juicios)
        if not juicios:
            items.append(Item(iid, titulo, NO_APLICA, modo, norma,
                              evidencia={"uniones": len(suyas), "no_juzgadas": no_juzgadas},
                              detalle=("ninguna con piezas a medida que taladrar" if suyas else
                                       "no hay " + ("uniones atornilladas declaradas" if
                                                    tipo == "fasten" else
                                                    "anclajes con pernos declarados"))))
            continue
        malas = [(u, j) for u, j in juicios if j[0] == FALLA]
        casos = [{"union": u["union"], "estado": e, "detalle": txt, **n} for u, (e, txt, n) in malas]
        items.append(Item(
            iid, titulo, FALLA if malas else OK, modo, norma,
            evidencia={"evaluadas": len(juicios), "fallan": len(malas), "no_juzgadas": no_juzgadas,
                       **recortar(casos)},
            piezas=list(dict.fromkeys(p["fid"] for u, (_e, _t, n) in malas for p in n["piezas"]
                                      if p["agujeros"] < n["pide"])),
            detalle=(malas[0][1][1] + (f" (y {len(malas) - 1} más)" if len(malas) > 1 else "")
                     if malas else f"{len(juicios)} de {len(juicios)} con sus agujeros")))
    return items
