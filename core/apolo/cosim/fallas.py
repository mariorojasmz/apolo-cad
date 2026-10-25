"""Las fallas a propósito sobre un tablero armado (plan cosim-fallas D2–D4, D6).

Un evento `falla` del escenario (o de la sesión en vivo) cae en una de tres formas, ya validadas
en sus claves por `escenario.py`:
  - de un APARATO: {"dispositivo": "-K1", "falla": "soldado", "valor"?} → `Modelo.fallar`; el
    modelo dice qué fallas toma (`Modelo.FALLAS`) y el error, cuáles sí;
  - de una RAMA de la red: {"rama": "-K1:13-14", "falla": "pegado", "valor": true} (UN contacto
    queda como se dice: `RedNodal.pegar`) o {"rama": "-W1", "falla": "abierto"} (= el
    `cable_cortado`: `RedNodal.cortar`);
  - un CORTO entre dos puntos: {"falla": "corto", "a": "-X1:1", "b": "-X1:PE", "R_ohm"?} sobre
    `RedNodal.cortocircuito` (los dos puntos en la MISMA red; el PE sólo está en la potencia de
    un esquema TN, de un TT con `RA_ohm`, o en el mando unido a su 0 V: el rechazo de un corto a
    PE en TT sin RA o en IT dice por qué, plan datos-de-corte-y-acometida D7).
`aplicar(tab, datos, reparar)` la pone o la quita; `catalogo(tab)` es lo que el `inicio` de la
sesión en vivo ofrece (D6): las fallas de cada aparato y las ramas que se pueden pegar o cortar.
Puro: sólo `cosim`. Determinista: sin azar ni reloj (D10).
"""

from __future__ import annotations

import difflib

from .red.nodal import R_CORTO

#: Fallas que no son de un aparato sino de la red (D3).
FALLAS_RAMA = ("abierto", "pegado")
FALLA_CORTO = "corto"


def _pista(x: str, opciones) -> str:
    parecida = difflib.get_close_matches(x, sorted(opciones), n=1)
    return f" ¿Quisiste decir «{parecida[0]}»?" if parecida else ""


def _modelo(tab, des: str):
    m = tab.modelos.get(des)
    if m is None:
        raise ValueError(f"falla: el tablero no tiene el dispositivo «{des}» (o es pasivo).{_pista(des, tab.modelos)}")
    return m


def contactos(tab) -> list[tuple]:
    """(red, id) de cada contacto de las dos redes, en el orden de la entrada."""
    out = []
    for red in (tab.mando_red, tab.pot_red):
        if red is not None:
            out += [(red, rid) for rid in red._pos_contacto]
    return out


def _contacto(tab, rama: str) -> list[tuple]:
    hallados = [(red, rid) for red, rid in contactos(tab) if rid == rama]
    if not hallados:
        ids = [rid for _, rid in contactos(tab)]
        raise ValueError(f"falla: «{rama}» no es un contacto de las redes.{_pista(rama, ids)} Un contacto "
                         "es «<designación>:<borne>-<borne>» (p. ej. «-K1:13-14»)")
    return hallados


def _red_de_puntos(tab, a: str, b: str):
    for red in (tab.mando_red, tab.pot_red):
        if red is not None and a in red.dom.puntos and b in red.dom.puntos:
            return red
    sueltos = [p for p in (a, b) if not any(red is not None and p in red.dom.puntos
                                            for red in (tab.mando_red, tab.pot_red))]
    if sueltos:
        raise ValueError(f"falla corto: «{sueltos[0]}» no es un punto de las redes"
                         f"{_por_que_fuera(tab, sueltos[0])}")
    raise ValueError(f"falla corto: «{a}» y «{b}» están en redes distintas (mando y potencia): un corto "
                     "va entre dos puntos de la misma red")


#: Por qué el PE de una red con este esquema no está en la potencia (plan
#: datos-de-corte-y-acometida, D7).
_PE_FUERA = {
    "TT": ": el PE de una red TT entra a la potencia sólo con su lazo de tierra; en TT declara "
          "RA_ohm (add_device.ajustes de la red, p. ej. {\"RA_ohm\": 100})",
    "IT": ": en IT el primer defecto a masa no da corriente de falla (la estrella de la red está "
          "aislada): el PE queda fuera de la potencia y no hay corto que simular",
}
_GENERICO = (" (un PE sólo entra en la potencia de un esquema TN, o TT con RA_ohm, o en el mando "
             "unido a su 0 V)")


def _por_que_fuera(tab, punto: str) -> str:
    """El motivo de que `punto` no esté en ninguna red: si está unido (todo cerrado) al PE de una
    red TT sin RA o IT, el de su esquema; si no, el genérico."""
    fuentes = [f for f in tab.entrada.get("fuentes", ())
               if f.get("esquema") in _PE_FUERA and f.get("R_tierra_ohm") is None]
    if not fuentes:
        return _GENERICO
    from .red.entrada import leer_entrada
    from .red.topologia import Topologia

    topo = Topologia(leer_entrada(tab.entrada))
    if punto not in topo.nodo_de:
        return _GENERICO
    for f in fuentes:
        pe = next((p for p, q in f["polos"].items() if q == "PE"), None)
        if pe is not None and topo.nodo_de[punto] in topo._alcanza([topo.nodo_de[pe]]):
            return _PE_FUERA[f["esquema"]]
    return _GENERICO


def id_corto(a: str, b: str) -> str:
    return f"falla:{a}~{b}"


def aplicar(tab, d: dict, reparar: bool = False) -> list[str]:
    """Pone (o quita) la falla `d` sobre el tablero. Devuelve las hipótesis NUEVAS que dejó
    (el límite de un modelo, D10) con la designación delante."""
    falla = d["falla"]
    if "dispositivo" in d:
        des = d["dispositivo"]
        m = _modelo(tab, des)
        antes = len(m.hipotesis)
        if reparar:
            m.reparar(falla, d.get("valor"))
        else:
            m.fallar(falla, d.get("valor"))
        return [f"{des}: {h}" for h in m.hipotesis[antes:]]
    if falla == FALLA_CORTO:
        a, b = d["a"], d["b"]
        red = _red_de_puntos(tab, a, b)
        if reparar:
            red.quitar_falla(id_corto(a, b))
        else:
            red.cortocircuito(id_corto(a, b), a, b, float(d.get("R_ohm") or R_CORTO))
        return []
    rama = d["rama"]
    if falla == "abierto":
        ramas = tab.ramas_de(rama)
        if not ramas:
            raise ValueError(f"falla abierto: «{rama}» no es una rama de las redes (un conductor sin largo ni "
                             "sección es una unión ideal y no se puede cortar: declara largo_m en add_wire o "
                             "add_cable)")
        for red, rid in ramas:
            (red.reponer if reparar else red.cortar)(rid)
        return []
    for red, rid in _contacto(tab, rama):
        if reparar:
            red.despegar(rid)
        else:
            red.pegar(rid, d.get("valor", True))
    return []


def _opciones(m) -> dict:
    """Las opciones del valor de cada falla que las tiene (lo que la UI ofrece para elegir)."""
    out: dict = {}
    if m.tipo == "selector":
        out["trabado"] = [str(p) for p in m.posiciones]
    elif m.tipo == "plc":
        out["entrada_pegada"] = list(m.DI) + list(m.AI)
        out["salida_pegada"] = list(m.DO)
    elif m.tipo == "variador" and m.tiene_sto:
        out["canal_sto_pegado"] = ["S1", "S2"]
    elif m.tipo == "rele_seguridad":
        out["salida_pegada"] = list(m.ids_salida)
    elif m.tipo == "fusible" and m.unidades > 1:
        out["abierto"] = list(range(1, m.unidades + 1))
    elif m.tipo == "electrovalvula":  # V8.9 D8: dónde queda el carrete y qué bobina se corta
        out["pegada"] = list(m.posiciones)
        if len(m.lados) > 1:
            out["bobina_cortada"] = list(m.lados)
    return out


def catalogo(tab) -> dict:
    """{"fallas": [{designacion, tipo, fallas: [{falla, pide, opciones?}]}], "ramas": [{id, tipo:
    contacto | conductor, red, dispositivo?}]} para el `inicio` de la sesión en vivo (D6)."""
    fallas = []
    for des, m in tab.modelos.items():
        if not m.FALLAS:
            continue
        if m.tipo == "variador" and not m.tiene_sto:
            lista = {k: v for k, v in m.FALLAS.items() if k != "canal_sto_pegado"}
        else:
            lista = m.FALLAS
        ops = _opciones(m)
        fallas.append({"designacion": des, "tipo": m.tipo, "fallas": [
            {"falla": f, "pide": pide, **({"opciones": ops[f]} if f in ops else {})} for f, pide in lista.items()]})
    ramas = []
    for red in (tab.mando_red, tab.pot_red):
        if red is None:
            continue
        for r in red.dom.ramas:
            if r.tipo in ("contacto", "conductor"):
                ramas.append({"id": r.id, "tipo": r.tipo, "red": red.nombre,
                              **({"dispositivo": r.dispositivo} if r.dispositivo else {})})
    return {"fallas": fallas, "ramas": ramas}
