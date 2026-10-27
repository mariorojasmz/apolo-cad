"""Chequeo eléctrico estático (ERC) del modelo evaluado (V8.1 D7).

`erc(modelo)` devuelve las reglas con la forma de siempre (`library/rules.py`):
`{regla, estado: ok|aviso|error, detalle, recomendacion?, norma, elementos}`. Una regla sin
hallazgos da UN «ok»; con hallazgos, un dict por hallazgo. Una regla que sólo aplica a un aparato
(«tipo de diferencial») no da fila sin él: el ERC de un tablero sin diferencial es el de siempre. Las redes y el peor caso salen de
`redes.analizar` (contactos y protecciones cerrados).

Las que miran el camino de la protección (PE en cadena, hilo PE de los cables, canales del STO) están en
`erc_seguridad.py`. Cada regla cita su norma o dice «criterio de diseño». Fuera de alcance
(V8.6): sección del conductor frente a la protección, caída de tensión, cortocircuito calculado.

Puro: recibe un `ModeloElectrico`, nunca un documento.
"""

from __future__ import annotations

from itertools import islice, product

from .erc_seguridad import canales_sto, pe_de_cables, pe_en_cadena
from .modelo import Carga, Dispositivo, ModeloElectrico
from .redes import Analisis, Llegada, Potencial, analizar, compatibles, nombre_conductor
from .referencias import ReferenciaError, parse_designacion
from .tension import admite, formato_valor, tension_entre

CRITERIO = "criterio de diseño"
NORMAS = {
    "referencias": CRITERIO,
    "designación duplicada": "IEC 81346-1 (designación de referencia unívoca)",
    "cortocircuito": CRITERIO,
    "tensión cruzada": "IEC 60204-1 §4.3 (tensión de régimen 0,9–1,1 de la nominal)",
    "protección del motor": "IEC 60204-1 §7.3 (obligatoria sobre 0,5 kW; por debajo, criterio de diseño)",
    "puesta a tierra": "IEC 60364-4-41 §411.3.1.1 · IEC 60364-5-54 · IEC 60204-1 §8.2",
    "borne suelto": CRITERIO,
    "color del conductor": "IEC 60204-1 §13.2",
    "parada de emergencia": "ISO 13850 · IEC 60204-1 §10.7",
    # la cita IEC 60364-5-53 §531.3.3 no se confirmó con el texto de la norma (plan
    # datos-de-corte-y-acometida, D10): queda como criterio de diseño
    "tipo de diferencial": CRITERIO,
}
_N_PE = "IEC 60204-1 §5.1 (el neutro no se une al circuito de protección dentro del equipo)"
_FASES = ("L1", "L2", "L3")
#: Combinaciones de llegadas que se revisan por carga (en el peor caso suelen ser 1–4).
TOPE_COMBINACIONES = 2000


def _r(regla: str, estado: str, detalle: str, recomendacion: str | None = None,
       elementos: list[str] | None = None, norma: str | None = None,
       conductores: list[int] | None = None) -> dict:
    """`conductores`: los números (1-based, orden de `modelo.conductores`) de los conductores del
    hallazgo; el texto los nombra por sus extremos (`redes.nombre_conductor`)."""
    out = {"regla": regla, "estado": estado, "detalle": detalle}
    if recomendacion:
        out["recomendacion"] = recomendacion
    out["norma"] = norma or NORMAS[regla]
    out["elementos"] = list(elementos or [])
    if conductores:
        out["conductores"] = list(conductores)
    return out


def _quien(d: Dispositivo) -> str:
    return f"{d.designacion} ({d.ref})"


def _lista(pts, n: int = 4) -> str:
    pts = list(pts)
    return ", ".join(pts[:n]) + (f" y {len(pts) - n} más" if len(pts) > n else "")


# ── reglas ────────────────────────────────────────────────────────────────────


def _referencias(a: Analisis) -> list[dict]:
    out = [_r("referencias", "error", p.detalle,
              "Corrige la referencia con la forma «-K1:A1» y un borne que exista en la ficha.",
              p.elementos, conductores=[p.conductor] if p.conductor else None) for p in a.problemas]
    for d in a.modelo.dispositivos:
        try:
            parse_designacion(d.designacion)
        except ReferenciaError as e:
            out.append(_r("referencias", "error", f"designación ilegible de {d.ref}: {e}",
                          "Una designación es «-K1» (o «=Faja1-K1»).", [d.designacion]))
    return out or [_r("referencias", "ok",
                      f"Las referencias de los {len(a.modelo.conductores)} conductores resuelven.")]


def _duplicadas(a: Analisis) -> list[dict]:
    out = []
    for des, n in a.duplicadas.items():
        refs = [d.ref for d in a.modelo.dispositivos if d.designacion == des]
        out.append(_r("designación duplicada", "error",
                      f"{des} está declarada {n} veces ({', '.join(refs)}): sus cables no sabrían a cuál van.",
                      "Dale a cada dispositivo una designación propia (-K1, -K2…).", [des]))
    return out or [_r("designación duplicada", "ok",
                      f"Las {len(a.modelo.dispositivos)} designaciones son únicas.")]


def _conflicto(p: Potencial, q: Potencial) -> bool:
    if p.etiqueta == q.etiqueta:
        return False
    if p.sistema == q.sistema:
        return p.polo != q.polo
    return not (p.referencia and q.referencia)


def _redundante(x: Potencial, y: Potencial, lls: list[Llegada]) -> bool:
    """¿El cruce entre sistemas es el MISMO corto que otro dentro de un sistema? (el PE contra
    el +24 cuando el 0 V de esa fuente está unido al PE: se reporta como +24 contra 0 V)."""
    for p, q in ((x, y), (y, x)):
        if p.referencia and any(ll.potencial.sistema == q.sistema and ll.potencial.referencia
                                and ll.potencial != q for ll in lls):
            return True
    return False


def _cortocircuitos(a: Analisis) -> list[dict]:
    out, vistos = [], set()
    for idx, lls in enumerate(a.llegadas):
        for x, y in ((x, y) for i, x in enumerate(lls) for y in lls[i + 1:]):
            par = frozenset((x.potencial.etiqueta, y.potencial.etiqueta))
            if par in vistos or not _conflicto(x.potencial, y.potencial) or not compatibles(x, y):
                continue
            if x.potencial.sistema != y.potencial.sistema and _redundante(x.potencial, y.potencial, lls):
                continue
            vistos.add(par)
            red = a.redes[idx]
            via = list(dict.fromkeys(x.via + y.via))
            como = "sin cerrar nada (cortocircuito directo)" if not via else f"al cerrar {_lista(via)}"
            polos = {x.potencial.polo, y.potencial.polo}
            norma = _N_PE if polos == {"N", "PE"} and x.potencial.sistema == y.potencial.sistema else None
            out.append(_r("cortocircuito", "error",
                          f"{x.potencial.etiqueta} y {y.potencial.etiqueta} llegan a la misma red "
                          f"({_lista(red.puntos)}) {como}, sin carga entre ellos.",
                          "Entre dos potenciales distintos tiene que haber una carga (bobina, motor, "
                          "piloto); revisa el conductor o el contacto que los une.",
                          list(red.puntos[:6]) + via, norma))
    return out or [_r("cortocircuito", "ok",
                      "Ninguna red recibe dos potenciales distintos, aun con todos los contactos cerrados.")]


def _ligados_dc(a: Analisis) -> dict[str, str]:
    """Fuentes DC cuyo «-» está unido (0 V común): sistema → representante del grupo."""
    grupo: dict[str, str] = {}

    def raiz(s: str) -> str:
        while grupo.setdefault(s, s) != s:
            s = grupo[s]
        return s

    for idx in range(len(a.redes)):
        menos = [p.sistema for p in a.directos(idx) if p.tension.tipo == "DC" and p.polo == "-"]
        for s in menos[1:]:
            grupo[raiz(s)] = raiz(menos[0])
    return {s: raiz(s) for s in list(grupo)}


def _voltaje(x: Potencial, y: Potencial, ligados: dict[str, str]) -> tuple[str, float | None, str | None]:
    """(tipo, V de x respecto de y, motivo si no se puede)."""
    if x == y:
        return x.tension.tipo, 0.0, None  # el mismo potencial en los dos bornes
    if "PE" in (x.polo, y.polo):
        return "", None, "uno de sus bornes está en el PE, que no es un conductor activo"
    if x.sistema == y.sistema:
        v = tension_entre(x.tension, x.polo, y.polo)
        return x.tension.tipo, v, None if v is not None else "la tensión entre esos polos no se infiere"
    if (x.tension.tipo == y.tension.tipo == "DC" and x.sistema in ligados
            and ligados.get(x.sistema) == ligados.get(y.sistema)):
        vx, vy = tension_entre(x.tension, x.polo, "-"), tension_entre(y.tension, y.polo, "-")
        return "DC", (vx or 0.0) - (vy or 0.0), None
    return "", None, f"mezcla dos fuentes sin referencia común ({x.etiqueta} y {y.etiqueta})"


def _preferida(d: Dispositivo, c: Carga) -> float | None:
    con = str(d.ajustes.get("conexion", "")).lower()
    if c.tipo != "motor" or len(c.tension.valores) != 2 or con not in ("triangulo", "estrella"):
        return None
    return min(c.tension.valores) if con == "triangulo" else max(c.tension.valores)


def _revisar_carga(a: Analisis, d: Dispositivo, c: Carga, ligados) -> str | None:
    """Motivo del primer cruce de tensión de la carga, o None si todo lo que recibe calza."""
    arr = [a.llegadas[a.red(d.designacion, b)] for b in c.bornes]
    if any(not lls for lls in arr):
        return None  # sin alimentar (o a medias): no hay tensión que comparar
    pref = _preferida(d, c)
    sistemas = [{ll.potencial.sistema for ll in lls} for lls in arr]
    en_cero = None  # una combinación con los dos bornes al mismo potencial (la carga apagada)
    alimentada = False  # al menos un estado la alimenta bien
    for combo in islice(product(*arr), TOPE_COMBINACIONES):
        if not compatibles(*combo):
            continue
        pots = [ll.potencial for ll in combo]
        if len(pots) == 2 and pots[0].sistema != pots[1].sistema and (
                pots[0].sistema in sistemas[1] or pots[1].sistema in sistemas[0]):
            continue  # el mismo nodo visto desde otra referencia (el 0 V unido al PE)
        recibe = " / ".join(f"{b}={p.etiqueta}" for b, p in zip(c.bornes, pots))
        if len(c.bornes) == 3:
            mismo = len({p.sistema for p in pots}) == 1
            fases = {p.polo for p in pots}
            if not (mismo and fases == set(_FASES) and pots[0].tension.fases == 3):
                return f"recibe {recibe}: una carga trifásica necesita las tres fases de una misma fuente"
            u = pots[0].tension.linea or 0.0
            if not admite(c.tension, "AC", u, preferida=pref):
                return f"recibe {formato_valor('AC', u)} 3F ({recibe}) y su nominal es {c.tension}"
            continue
        tipo, v, motivo = _voltaje(pots[0], pots[1], ligados)
        if motivo:
            return f"{motivo} ({recibe})"
        if abs(v) < 1e-9 and not admite(c.tension, tipo, v):
            en_cero = en_cero or recibe  # apagada en ese estado: no es un cruce por sí sola
            continue
        if not admite(c.tension, tipo, v, polar=c.polar, preferida=pref):
            extra = " (polaridad invertida)" if tipo == "DC" and c.polar and v < 0 else ""
            return f"recibe {formato_valor(tipo, v)}{extra} ({recibe}) y su nominal es {c.tension}"
        alimentada = True
    if en_cero and not alimentada:
        return f"sus bornes quedan siempre al mismo potencial ({en_cero}): nunca recibe tensión"
    return None


def _tensiones(a: Analisis) -> list[dict]:
    ligados = _ligados_dc(a)
    out, n = [], 0
    for d in a.dispositivos.values():
        for c in d.cargas:
            n += 1
            motivo = _revisar_carga(a, d, c, ligados)
            if motivo:
                out.append(_r("tensión cruzada", "error",
                              f"{_quien(d)}, carga {'–'.join(c.bornes)} ({c.tipo}): {motivo}.",
                              "Alimenta la carga desde una fuente de su tensión nominal (o cambia la ref "
                              "por la de la tensión que hay).",
                              [f"{d.designacion}:{b}" for b in c.bornes]))
    return out or [_r("tensión cruzada", "ok",
                      f"Las {n} cargas reciben su tensión nominal (o no están alimentadas).")]


def _motores(a: Analisis) -> list[tuple[Dispositivo, Carga]]:
    return [(d, c) for d in a.dispositivos.values() for c in d.cargas if c.tipo == "motor"]


def _proteccion_motor(a: Analisis) -> list[dict]:
    out = []
    motores = _motores(a)
    for d, c in motores:
        malas: list[Llegada] = [ll for b in c.bornes for ll in a.llegadas[a.red(d.designacion, b)]
                                if not ll.protegido and ll.potencial.polo in _FASES]
        if malas:
            ll = malas[0]
            camino = f" (camino: {_lista(ll.via)})" if ll.via else " (conexión directa)"
            out.append(_r("protección del motor", "error",
                          f"{_quien(d)} puede recibir {ll.potencial.etiqueta} sin pasar por un guardamotor, "
                          f"un relé térmico ni un variador con protección de motor{camino}.",
                          "Pon un guardamotor (o contactor + relé térmico, o un variador) en serie con el "
                          "motor, ajustado a su corriente nominal.",
                          [d.designacion] + list(ll.via)))
    return out or [_r("protección del motor", "ok",
                      f"{len(motores)} motor(es): todos alimentados a través de una protección de motor."
                      if motores else "No hay motores en el modelo.")]


def _tierra(a: Analisis) -> list[dict]:
    out, n = [], 0
    for d in a.dispositivos.values():
        for b in d.bornes:
            if b.rol != "tierra":
                continue
            n += 1
            idx = a.red(d.designacion, b.id)
            if not any(p.polo == "PE" for p in a.directos(idx)):
                out.append(_r("puesta a tierra", "error",
                              f"{_quien(d)}: el borne {b.id} no está unido a la red PE.",
                              "Lleva un conductor verde-amarillo desde ese borne hasta la barra o "
                              "bornera de tierra (unida al PE de la red).",
                              [f"{d.designacion}:{b.id}"]))
    return out or [_r("puesta a tierra", "ok", f"Los {n} bornes de tierra están unidos a la red PE.")]


def _sueltos(a: Analisis) -> list[dict]:
    out = []
    for d in a.dispositivos.values():
        usos: dict[str, int] = {}
        for c in d.cargas:
            for b in c.bornes:
                usos[b] = usos.get(b, 0) + 1
        for c in d.cargas:
            sueltos = [b for b in c.bornes if not a.conectado(d.designacion, b)]
            # una carga optativa (una entrada del PLC) sólo falla a medias: con su borne propio
            # cableado y algo suelto; el común compartido (1M, COM) cableado solo no cuenta
            propios = [b for b in c.bornes if usos[b] == 1 and b not in sueltos]
            if sueltos and (c.obligatoria or propios):
                out.append(_r("borne suelto", "error",
                              f"{_quien(d)}: la carga {'–'.join(c.bornes)} ({c.tipo}) tiene suelto "
                              f"{', '.join(sueltos)}.",
                              "Conecta el borne (o quita el dispositivo si no se usa).",
                              [f"{d.designacion}:{b}" for b in sueltos]))
        for b in d.bornes:
            if b.obligatorio and not a.conectado(d.designacion, b.id):
                out.append(_r("borne suelto", "error", f"{_quien(d)}: el borne obligatorio {b.id} está suelto.",
                              "Conéctalo según la ficha del aparato.", [f"{d.designacion}:{b.id}"]))
    return out or [_r("borne suelto", "ok", "Ninguna carga ni borne obligatorio queda suelto.")]


def _esperado(a: Analisis, idx: int, hay_neutro: bool) -> tuple[set[str], str] | None:
    pots = a.potenciales(idx)
    mando_dc = {"BU"} if hay_neutro else {"BU", "LBU"}
    if any(p.polo == "PE" for p in a.directos(idx)):
        otros = [p for p in pots if p.polo != "PE"]
        if otros and all(p.tension.tipo == "DC" and p.referencia for p in otros):
            return {"GNYE"} | mando_dc, "es el 0 V unido al PE: verde-amarillo el puente, azul el resto (§13.2)"
        return {"GNYE"}, "es del conductor de protección (PE): verde-amarillo (§13.2.2)"
    if any(p.polo == "N" for p in pots):
        return {"LBU"}, "lleva el neutro: azul claro (§13.2.3)"
    tipos = {p.tension.tipo for p in pots}
    if len(tipos) != 1:
        return None
    ac = tipos == {"AC"}
    roles: set[str] = set()
    for des, borne in a.miembros[idx]:
        d = a.dispositivos.get(des)
        if d is None or d.bornera:
            continue
        b = d.borne(borne)
        if b is not None and b.rol != "tierra":
            roles.add(b.rol)
    if not roles:
        return None
    mando = {"RD"} if ac else mando_dc
    if roles <= {"potencia"}:
        return {"BK", "OG"}, f"es de potencia {'AC' if ac else 'DC'}: negro (§13.2.4)"
    if "potencia" not in roles:
        color = "rojo" if ac else "azul"
        return mando | {"OG"}, f"es de mando en {'alterna' if ac else 'continua'}: {color} (§13.2.4)"
    return {"BK", "OG"} | mando, "mezcla potencia y mando (§13.2.4)"


def _colores(a: Analisis) -> list[dict]:
    out = []
    hay_neutro = any(p.polo == "N" for i in range(len(a.redes)) for p in a.potenciales(i))
    cables = {c.designacion: c for c in a.modelo.cables}
    for i, cond in enumerate(a.modelo.conductores):
        idx = a.conductor_red.get(i)
        if idx is None:
            continue
        color = cond.color
        en_cable = cond.cable is not None
        if en_cable and cond.cable in cables and cond.hilo is not None:
            hilo = cables[cond.cable].hilo(cond.hilo)
            color = hilo.color if hilo is not None and hilo.color else color
        if not color:
            continue
        esperado = _esperado(a, idx, hay_neutro)
        if esperado is None:
            continue
        colores, porque = esperado
        if color == "GNYE" and "GNYE" not in colores:
            motivo = "el verde-amarillo es EXCLUSIVO del conductor de protección (§13.2.2)"
        elif colores == {"GNYE"} and color != "GNYE":
            motivo = porque
        elif en_cable or color in colores:
            continue
        else:
            motivo = porque
        out.append(_r("color del conductor", "aviso",
                      f"conductor {nombre_conductor(cond)} es {color}: la red {motivo}.",
                      f"Usa {' o '.join(sorted(c for c in colores if c != 'OG'))} (naranja sólo en "
                      "circuitos que siguen energizados con el seccionador abierto).",
                      list(cond.puntos), conductores=[i + 1]))
    return out or [_r("color del conductor", "ok", "Los colores de los conductores siguen IEC 60204-1 §13.2.")]


def _parada_emergencia(a: Analisis) -> list[dict]:
    motores = _motores(a)
    setas = [d.designacion for d in a.dispositivos.values() if d.parada_emergencia]
    if motores and not setas:
        return [_r("parada de emergencia", "aviso",
                   f"Hay {len(motores)} motor(es) y ninguna parada de emergencia (seta).",
                   "Agrega una seta (p. ej. ESTOP-40) que corte el mando de los motores, salvo que la "
                   "evaluación de riesgos (ISO 12100) justifique no tenerla.",
                   [d.designacion for d, _ in motores])]
    det = f"Paradas de emergencia: {', '.join(setas)}." if setas else "No hay motores en el modelo."
    return [_r("parada de emergencia", "ok", det, elementos=setas)]


def _diferencial_de(a: Analisis, etiqueta: str) -> Dispositivo | None:
    """El diferencial del camino «-F1:1-2» de una llegada (None si es de otro aparato)."""
    d = a.dispositivos.get(etiqueta.rsplit(":", 1)[0])
    return d if d is not None and d.modelo.get("tipo") == "diferencial" else None


def _tipo_diferencial(a: Analisis) -> list[dict]:
    """Un variador alimentado a través de un diferencial que no ve la corriente de falla continua
    lisa de su rectificador: clase AC o A siempre; F con entrada trifásica (la F es de los
    variadores monofásicos). Sin diferenciales en el modelo, no aplica (sin fila)."""
    difs = [d for d in a.dispositivos.values() if d.modelo.get("tipo") == "diferencial"]
    if not difs:
        return []
    out, vistos = [], set()
    for v in (d for d in a.dispositivos.values() if d.modelo.get("tipo") == "variador"):
        for c in (c for c in v.cargas if c.tipo == "alimentacion"):
            malas = ("AC", "A", "F") if len(c.bornes) == 3 else ("AC", "A")
            for b in c.bornes:
                idx = a.red(v.designacion, b)
                for ll in a.llegadas[idx] if idx is not None else ():
                    for et in ll.via:
                        d = _diferencial_de(a, et)
                        clase = d.modelo.get("clase_residual") if d is not None else None
                        if d is None or clase not in malas or (v.designacion, d.designacion) in vistos:
                            continue
                        vistos.add((v.designacion, d.designacion))
                        out.append(_r("tipo de diferencial", "aviso",
                                      f"{_quien(v)} se alimenta a través de {_quien(d)}, clase {clase}: "
                                      "un variador puede dar una corriente de falla continua lisa que "
                                      f"un diferencial clase {clase} no ve (y lo ciega).",
                                      "Usa un diferencial clase B para el circuito del variador (o "
                                      "sepáralo del diferencial de clase A/AC de los demás circuitos).",
                                      [v.designacion, d.designacion]))
    return out or [_r("tipo de diferencial", "ok",
                      f"{len(difs)} diferencial(es): ningún variador se alimenta a través de uno que "
                      "no vea la corriente de falla continua lisa.", elementos=[d.designacion for d in difs])]


_REGLAS = (_referencias, _duplicadas, _cortocircuitos, _tensiones, _proteccion_motor, _tierra,
           pe_en_cadena, pe_de_cables, _sueltos, _colores, _parada_emergencia, canales_sto,
           _tipo_diferencial)


def erc(modelo: ModeloElectrico, analisis: Analisis | None = None) -> list[dict]:
    """Todas las reglas de D7 sobre el modelo (o sobre un análisis ya hecho)."""
    a = analisis or analizar(modelo)
    return [r for regla in _REGLAS for r in regla(a)]


def resumen(reglas: list[dict]) -> dict:
    """Estado global del ERC: error si alguna regla da error; aviso si alguna avisa."""
    errores = sum(r["estado"] == "error" for r in reglas)
    avisos = sum(r["estado"] == "aviso" for r in reglas)
    return {"estado": "error" if errores else ("aviso" if avisos else "ok"),
            "errores": errores, "avisos": avisos}
