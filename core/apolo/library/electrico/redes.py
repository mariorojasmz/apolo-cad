"""Redes del modelo eléctrico: union-find de puntos y propagación de fuentes (V8.1 D7).

1. **Puntos** = (designación del dispositivo, borne). Se UNEN por los conductores (todos los
   puntos de un `add_wire`), por los caminos `fijo` y por los bornes de una misma fuente que
   imponen el mismo polo. Cada componente es una `Red`.
2. **Peor caso**: los caminos NA, NC y de protección se suponen CERRADOS. Cada potencial de
   fuente se propaga por ellos de red en red (nunca a través de una carga: la carga separa).
   Excepción honesta: un NA y un NC del MISMO actuador (la bobina de un contactor, un relé
   conmutado) no cierran a la vez, así que una propagación que ya pasó por uno no pasa por el
   otro (`compromisos`). Los enclavamientos entre aparatos distintos (inversor de giro) no se
   ven: los marca el ERC como cortocircuito.
3. Cada llegada recuerda si pasó por una protección de MOTOR (guardamotor, relé térmico) o si
   nació en una fuente que protege al motor (variador): la regla «motor sin protección».

Puro: recibe un `ModeloElectrico`, nunca un documento.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .modelo import Dispositivo, ModeloElectrico, Red
from .referencias import ReferenciaError, parse_referencia, sufijo_sugerencia
from .tension import Tension, es_referencia

#: Tope de llegadas distintas por (red, potencial, protegido): acota la explosión de
#: combinaciones de compromisos en tableros grandes (rara vez pasa de 2).
TOPE_LLEGADAS = 8


@dataclass(frozen=True)
class Potencial:
    """Un polo de una fuente: `sistema` identifica la fuente («-G1», «-T2.2» si el aparato
    tiene varias)."""

    sistema: str
    polo: str
    tension: Tension
    designacion: str

    @property
    def etiqueta(self) -> str:
        return f"{self.sistema}:{self.polo}"

    @property
    def referencia(self) -> bool:
        return es_referencia(self.polo)


@dataclass(frozen=True)
class Llegada:
    potencial: Potencial
    protegido: bool
    compromisos: frozenset  # {((designacion, actuador), "NA"|"NC")}
    via: tuple[str, ...]  # caminos conmutados atravesados («-Q1:1-2»)


@dataclass
class Problema:
    """Una referencia que no resuelve (lo reporta el ERC como «referencias»). `conductor`: el
    número (1-based, el orden de `modelo.conductores`) del conductor que la tiene, si es de uno:
    el texto lo nombra por sus extremos (`nombre_conductor`), la clave queda aquí."""

    detalle: str
    elementos: list[str] = field(default_factory=list)
    conductor: int | None = None


def nombre_conductor(cond) -> str:
    """Cómo se lee un conductor en el esquema: sus puntos en el orden de cableado («-T2:V →
    -M1:V1») y, si la tiene, su etiqueta entre corchetes: el hilo del cable («-W1.3») y el nombre
    de su red («L1»): «-T2:V → -M1:V1 [-W1.2]». Nunca su índice en el modelo (va en un campo
    aparte: `Problema.conductor`, la clave `conductores` de una fila del ERC)."""
    extras = [f"{cond.cable}.{cond.hilo}" if cond.hilo else cond.cable] if cond.cable else []
    if cond.potencial:
        extras.append(cond.potencial)
    base = cond.etiqueta or "sin puntos"
    return f"{base} [{', '.join(extras)}]" if extras else base


@dataclass
class Analisis:
    modelo: ModeloElectrico
    dispositivos: dict[str, Dispositivo]
    redes: list[Red]
    red_de: dict[tuple[str, str], int]  # punto → índice de red
    llegadas: list[list[Llegada]]  # por red
    conectados: set[int]  # redes con al menos un extremo de conductor
    conductor_red: dict[int, int]  # índice de conductor → red
    problemas: list[Problema]
    duplicadas: dict[str, int]  # designación → cuántas veces
    miembros: list[list[tuple[str, str]]] = field(default_factory=list)  # por red: sus puntos

    def red(self, designacion: str, borne: str) -> int | None:
        return self.red_de.get((designacion, borne))

    def conectado(self, designacion: str, borne: str) -> bool:
        """¿Llega al menos un conductor a la red del borne?"""
        return self.red(designacion, borne) in self.conectados

    def potenciales(self, idx: int) -> list[Potencial]:
        vistos: dict[str, Potencial] = {}
        for ll in self.llegadas[idx]:
            vistos.setdefault(ll.potencial.etiqueta, ll.potencial)
        return list(vistos.values())

    def directos(self, idx: int) -> list[Potencial]:
        vistos: dict[str, Potencial] = {}
        for ll in self.llegadas[idx]:
            if not ll.via:
                vistos.setdefault(ll.potencial.etiqueta, ll.potencial)
        return list(vistos.values())


class _UF:
    def __init__(self):
        self.padre: dict = {}

    def add(self, x):
        self.padre.setdefault(x, x)

    def find(self, x):
        self.add(x)
        while self.padre[x] != x:
            self.padre[x] = self.padre[self.padre[x]]
            x = self.padre[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.padre[rb] = ra


def resolver(punto: str, dispositivos: dict[str, Dispositivo]) -> tuple[tuple[str, str] | None, str | None]:
    """Referencia «-K1:A1» → ((designación, borne), None) o (None, motivo con sugerencias)."""
    try:
        ref = parse_referencia(punto, exige_borne=True)
    except ReferenciaError as e:
        return None, str(e)
    disp = dispositivos.get(ref.designacion)
    if disp is None and not ref.funcion:
        # «-K1» basta dentro de una máquina: vale si un solo dispositivo tiene ese producto
        cand = [d for d in dispositivos.values() if d.designacion.endswith(ref.producto)
                and d.designacion[: -len(ref.producto)].count("-") == 0]
        if len(cand) == 1:
            disp = cand[0]
        elif len(cand) > 1:
            nombres = ", ".join(d.designacion for d in cand)
            return None, (f"«{punto}» es ambiguo: {ref.producto} existe como {nombres}; antepón el "
                          f"aspecto de función, p. ej. «{cand[0].designacion}:{ref.borne}»")
    if disp is None:
        pista = sufijo_sugerencia(ref.designacion, dispositivos)
        return None, f"«{punto}»: el dispositivo {ref.designacion} no existe.{pista}"
    if ref.ubicacion and disp.ubicacion and disp.ubicacion.lstrip("+") != ref.ubicacion:
        return None, f"«{punto}»: {disp.designacion} está en {disp.ubicacion}, no en +{ref.ubicacion}"
    if disp.borne(ref.borne) is None and disp.puerto(ref.borne) is not None:  # V8.9 D1
        return None, (f"«{punto}»: {ref.borne} es un PUERTO de aire de {disp.designacion} ({disp.ref}), "
                      "no un borne: un puerto se une con add_tubo; un conductor va a un borne"
                      + (f" ({', '.join(disp.ids_bornes)})" if disp.bornes else ""))
    if disp.borne(ref.borne) is None:
        return None, (f"«{punto}»: {disp.designacion} ({disp.ref}) no tiene el borne {ref.borne}; "
                      f"bornes: {', '.join(disp.ids_bornes)}.{sufijo_sugerencia(ref.borne, disp.ids_bornes)}")
    return (disp.designacion, ref.borne), None


def _sistemas(disp: Dispositivo) -> list[str]:
    if len(disp.fuentes) == 1:
        return [disp.designacion]
    return [f"{disp.designacion}.{i + 1}" for i in range(len(disp.fuentes))]


def _resolver_conductores(modelo, dispositivos, cables_por_nombre, problemas):
    """Puntos resueltos de cada conductor (o problemas si no resuelven)."""
    resueltos: dict[int, list[tuple[str, str]]] = {}
    for i, cond in enumerate(modelo.conductores):
        nombre, n = nombre_conductor(cond), i + 1
        if len(cond.puntos) < 2:
            problemas.append(Problema(f"el conductor {nombre} une menos de dos puntos", list(cond.puntos), n))
        pts: list[tuple[str, str]] = []
        for p in cond.puntos:
            r, motivo = resolver(p, dispositivos)
            if r is None:
                problemas.append(Problema(f"conductor {nombre}: {motivo}", [p], n))
            else:
                pts.append(r)
        if cond.cable:
            cable = cables_por_nombre.get(cond.cable)
            if cable is None:
                problemas.append(Problema(
                    f"conductor {nombre}: el cable {cond.cable} no existe."
                    f"{sufijo_sugerencia(cond.cable, cables_por_nombre)}", [cond.cable], n))
            elif cond.hilo is None or cable.hilo(cond.hilo) is None:
                ids = [h.id for h in cable.hilos]
                problemas.append(Problema(
                    f"conductor {nombre}: el cable {cond.cable} ({cable.ref}) no tiene el hilo "
                    f"{cond.hilo}; hilos: {', '.join(ids)}.{sufijo_sugerencia(str(cond.hilo), ids)}", [cond.cable], n))
        resueltos[i] = pts
    return resueltos


def _armar_redes(dispositivos, resueltos):
    uf = _UF()
    for d in dispositivos.values():
        for b in d.bornes:
            uf.add((d.designacion, b.id))
        for c in d.caminos:
            if c.tipo == "fijo":
                uf.union((d.designacion, c.de), (d.designacion, c.a))
        for f in d.fuentes:
            por_polo: dict[str, str] = {}
            for borne, polo in f.polos:
                if polo in por_polo:
                    uf.union((d.designacion, por_polo[polo]), (d.designacion, borne))
                por_polo.setdefault(polo, borne)
    for pts in resueltos.values():
        for a, b in zip(pts, pts[1:]):
            uf.union(a, b)
    # índices deterministas: en el orden de dispositivos y bornes del modelo
    raices: dict = {}
    red_de: dict[tuple[str, str], int] = {}
    for d in dispositivos.values():
        for b in d.bornes:
            punto = (d.designacion, b.id)
            red_de[punto] = raices.setdefault(uf.find(punto), len(raices))
    return red_de, len(raices)


def _aristas(dispositivos, red_de, n):
    """Caminos conmutados (NA/NC/protección) entre redes distintas."""
    ady: list[list[tuple]] = [[] for _ in range(n)]
    for d in dispositivos.values():
        tipos_por_act: dict[str, set] = {}
        for c in d.caminos:
            if c.tipo in ("NA", "NC"):
                tipos_por_act.setdefault(c.actuador, set()).add(c.tipo)
        exclusivos = {a for a, ts in tipos_por_act.items() if ts == {"NA", "NC"}}
        for c in d.caminos:
            if c.tipo == "fijo":
                continue
            ra, rb = red_de[(d.designacion, c.de)], red_de[(d.designacion, c.a)]
            if ra == rb:
                continue
            excl = (d.designacion, c.actuador) if c.tipo in ("NA", "NC") and c.actuador in exclusivos else None
            protege = c.tipo == "proteccion" and d.protege_motor
            etiqueta = f"{d.designacion}:{c.de}-{c.a}"
            ady[ra].append((rb, excl, c.tipo, protege, etiqueta))
            ady[rb].append((ra, excl, c.tipo, protege, etiqueta))
    return ady


def _propagar(dispositivos, red_de, ady, n) -> list[list[Llegada]]:
    llegadas: list[list[Llegada]] = [[] for _ in range(n)]
    cola: deque = deque()
    for d in dispositivos.values():
        for sistema, f in zip(_sistemas(d), d.fuentes):
            for borne, polo in f.polos:
                pot = Potencial(sistema, polo, f.tension, d.designacion)
                cola.append((red_de[(d.designacion, borne)], pot, d.protege_motor, frozenset(), ()))
    while cola:
        red, pot, prot, comp, via = cola.popleft()
        lst = llegadas[red]
        mismas = [ll for ll in lst if ll.potencial == pot and ll.protegido == prot]
        if any(ll.compromisos <= comp for ll in mismas) or len(mismas) >= TOPE_LLEGADAS:
            continue
        lst.append(Llegada(pot, prot, comp, via))
        for otra, excl, tipo, protege, etiqueta in ady[red]:
            comp2 = comp
            if excl is not None:
                opuesto = (excl, "NC" if tipo == "NA" else "NA")
                if opuesto in comp:
                    continue
                comp2 = comp | {(excl, tipo)}
            cola.append((otra, pot, prot or protege, comp2, via + (etiqueta,)))
    return llegadas


def compatibles(*llegadas: Llegada) -> bool:
    """¿Pueden darse a la vez? (ningún actuador comprometido como NA en una y NC en otra)."""
    estado: dict = {}
    for ll in llegadas:
        for act, tipo in ll.compromisos:
            if estado.setdefault(act, tipo) != tipo:
                return False
    return True


def _tension_legible(pots: list[Potencial]) -> str | None:
    if not pots:
        return None
    return " / ".join(f"{p.etiqueta} · {p.tension}" for p in pots)


def analizar(modelo: ModeloElectrico) -> Analisis:
    """Redes, llegadas de potencial en el peor caso y problemas de referencias."""
    dispositivos: dict[str, Dispositivo] = {}
    duplicadas: dict[str, int] = {}
    for d in modelo.dispositivos:
        duplicadas[d.designacion] = duplicadas.get(d.designacion, 0) + 1
        dispositivos.setdefault(d.designacion, d)
    duplicadas = {k: v for k, v in duplicadas.items() if v > 1}
    problemas: list[Problema] = []
    cables = {c.designacion: c for c in modelo.cables}
    resueltos = _resolver_conductores(modelo, dispositivos, cables, problemas)
    red_de, n = _armar_redes(dispositivos, resueltos)
    ady = _aristas(dispositivos, red_de, n)
    llegadas = _propagar(dispositivos, red_de, ady, n)
    conductor_red = {i: red_de[pts[0]] for i, pts in resueltos.items() if pts}
    conectados = set(conductor_red.values())

    miembros: list[list[tuple[str, str]]] = [[] for _ in range(n)]
    for punto, idx in red_de.items():
        miembros[idx].append(punto)
    conds: list[list[int]] = [[] for _ in range(n)]
    for i, idx in conductor_red.items():
        conds[idx].append(i)
    analisis = Analisis(modelo, dispositivos, [], red_de, llegadas, conectados, conductor_red,
                        problemas, duplicadas, miembros)
    for idx in range(n):
        pots = analisis.potenciales(idx)
        nombres = [modelo.conductores[i].potencial for i in conds[idx] if modelo.conductores[i].potencial]
        analisis.redes.append(Red(
            id=f"N{idx + 1}", puntos=tuple(f"{des}:{borne}" for des, borne in miembros[idx]),
            potenciales=tuple(p.etiqueta for p in pots),
            directos=tuple(p.etiqueta for p in analisis.directos(idx)),
            tension=_tension_legible(pots), nombre=nombres[0] if nombres else None,
            conductores=tuple(conds[idx]),
        ))
    return analisis
