"""Las líneas del circuito de aire (plan V8.9 D1, D9; F1b): qué puertos une cada tubo y qué queda
aguas abajo de qué.

1. **Línea** = puertos unidos por tubos (union-find de (designación, puerto)), como la red
   eléctrica son bornes unidos por conductores. Un puerto sin tubo es una línea de un puerto.
2. **Paso interno** de un componente (lo que conecta en ALGUNA posición: el peor caso, como los
   contactos cerrados de la red eléctrica): FRL 1→2, válvula de corte 1→2, válvula 1→2 y 1→4
   (ISO 5599-3), regulador de caudal 1↔2. El cilindro, el silenciador y el presostato no pasan
   aire. `aguas_abajo` recorre líneas y pasos desde unas líneas de inicio.
3. **Presión de cada línea**: la regulada de cada FRL (`ajustes.p_regulada_bar`) aguas abajo de
   su puerto 2. Con varios FRL que llegan a la misma línea, la más alta y la más baja.

Puro (biblioteca estándar): recibe el modelo del carril por sus atributos (`dispositivos` con
`puertos`, `neumatico`, `ajustes`; `tubos` con `desde`/`hasta` canónicos «-QM1:4»).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

#: Paso interno por `modelo.tipo` (y vías, en la válvula): (de, a) dirigidos.
PASOS = {
    "frl": (("1", "2"),),
    "valvula_corte": (("1", "2"),),
    "regulador_caudal": (("1", "2"), ("2", "1")),
}
PASOS_VALVULA = {5: (("1", "2"), ("1", "4")), 3: (("1", "2"),), 2: (("1", "2"),)}


def tipo(d) -> str | None:
    return getattr(getattr(d, "neumatico", None), "tipo", None)


def pasos(d) -> tuple[tuple[str, str], ...]:
    t = tipo(d)
    if t == "valvula":
        return PASOS_VALVULA.get(d.neumatico.modelo.get("vias"), ())
    return PASOS.get(t or "", ())


@dataclass
class Circuito:
    """El circuito de aire analizado. `problemas`: (tubo, motivo) de los extremos que no son un
    puerto de aire (el ERC los da como «tubo sin puerto»)."""

    dispositivos: dict  # designación → dispositivo con ficha neumática
    tubos: list
    linea_de: dict = field(default_factory=dict)  # (designación, puerto) → índice de línea
    miembros: list = field(default_factory=list)  # por línea: sus puertos
    conectados: set = field(default_factory=set)  # puertos con al menos un tubo
    problemas: list = field(default_factory=list)
    presion: dict = field(default_factory=dict)  # línea → (p_min, p_max, [FRL])

    def linea(self, designacion: str, puerto: str) -> int | None:
        return self.linea_de.get((designacion, puerto))

    def presion_de(self, d) -> tuple[float, float, list] | None:
        """La presión que llega a un dispositivo por cualquiera de sus puertos (None si ninguna)."""
        lo = hi = None
        frls: list = []
        for p in d.puertos:
            x = self.presion.get(self.linea(d.designacion, p.id))
            if x is None:
                continue
            lo = x[0] if lo is None else min(lo, x[0])
            hi = x[1] if hi is None else max(hi, x[1])
            frls += [f for f in x[2] if f not in frls]
        return None if lo is None else (lo, hi, frls)


def punto(texto: str) -> tuple[str, str] | None:
    des, sep, puerto = str(texto or "").rpartition(":")
    return (des, puerto) if sep and des and puerto else None


def _motivo(texto: str, todos: dict) -> str | None:
    """Por qué un extremo de tubo no es un puerto de aire (None si lo es)."""
    pt = punto(texto)
    if pt is None:
        return f"«{texto}» no es un puerto «-QM1:4»"
    d = todos.get(pt[0])
    if d is None:
        return f"«{texto}»: el dispositivo {pt[0]} no existe"
    if d.puerto(pt[1]) is not None:
        return None
    if d.borne(pt[1]) is not None:
        return f"«{texto}»: {pt[1]} es un borne eléctrico de {pt[0]}, no un puerto de aire (medio distinto)"
    ids = ", ".join(p.id for p in d.puertos) or "ninguno: es eléctrico"
    return f"«{texto}»: {pt[0]} ({d.ref}) no tiene el puerto {pt[1]} (puertos: {ids})"


def analizar(modelo) -> Circuito:
    todos = {d.designacion: d for d in modelo.dispositivos}
    aire = {k: d for k, d in todos.items() if getattr(d, "neumatico", None) is not None}
    c = Circuito(aire, list(getattr(modelo, "tubos", ()) or ()))
    padre: dict = {}

    def find(x):
        padre.setdefault(x, x)
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for d in aire.values():
        for p in d.puertos:
            find((d.designacion, p.id))
    for t in c.tubos:
        malos = [m for m in (_motivo(t.desde, todos), _motivo(t.hasta, todos)) if m]
        if malos:
            c.problemas.append((t, "; ".join(malos)))
            continue
        a, b = punto(t.desde), punto(t.hasta)
        c.conectados |= {a, b}
        ra, rb = find(a), find(b)
        if ra != rb:
            padre[rb] = ra
    raices: dict = {}
    for d in aire.values():  # índices deterministas: en el orden de dispositivos y puertos
        for p in d.puertos:
            k = (d.designacion, p.id)
            c.linea_de[k] = raices.setdefault(find(k), len(raices))
    c.miembros = [[] for _ in raices]
    for k, i in c.linea_de.items():
        c.miembros[i].append(k)
    _presiones(c)
    return c


def aguas_abajo(c: Circuito, inicios) -> set[int]:
    """Las líneas a las que llega el aire desde las líneas `inicios` (incluidas) por los pasos
    internos de los componentes."""
    vistas = set(inicios)
    cola = deque(vistas)
    while cola:
        i = cola.popleft()
        for des, puerto in c.miembros[i]:
            d = c.dispositivos[des]
            for de, a in pasos(d):
                if de == puerto:
                    j = c.linea(des, a)
                    if j is not None and j not in vistas:
                        vistas.add(j)
                        cola.append(j)
    return vistas


def _presiones(c: Circuito) -> None:
    for d in c.dispositivos.values():
        p = d.ajustes.get("p_regulada_bar") if tipo(d) == "frl" else None
        salida = c.linea(d.designacion, "2")
        if p is None or salida is None:
            continue
        for i in aguas_abajo(c, {salida}):
            lo, hi, frls = c.presion.get(i, (p, p, []))
            c.presion[i] = (min(lo, p), max(hi, p), frls + [d.designacion])
