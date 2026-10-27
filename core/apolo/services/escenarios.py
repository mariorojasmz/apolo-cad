"""Los escenarios de prueba de un documento (plan V8.3 D12, D14): metadato del manifest.

Un escenario es una PRUEBA, no diseño: vive en `doc.escenarios` (fuera del log y de los
checkpoints, como `motion` o `fea`) con la forma `{nombre: {"escenario": {...}, "resultado":
{...}?}}`. Aquí está lo que lo LEE y lo escribe (sin locks: el llamador sostiene STATE_LOCK):
  - `poner`/`quitar`: lo valida `cosim.escenario.leer_escenario` (con sus aserciones) y se
    guarda tal cual llegó (el JSON del agente); los dispositivos que nombra y no están en el
    tablero vuelven como `avisos` (el tablero puede declararse después);
  - `listar`: cada uno con su ESTADO: «sin_correr», «pasa», «falla», «sin_aserciones» o
    «vencido»;
  - vigencia (como las reglas del FEA): el resultado guarda la `firma_documento` (log sin los
    `create_group` + materiales + las fichas eléctricas del tablero: lo que decide la máquina;
    versión 2 desde V8.5 F5b, la 1 se sigue leyendo con `firmas_v1`), el
    `hash_escenario` y la versión del motor (`cosim.COSIM_EPOCH`, F6b) y, si el tablero usa
    modelos de una extensión, su versión (`extensiones`); si cualquiera cambió, «vencido»;
  - `resultado_compacto` + `guardar_resultado`: lo que queda del último run (veredicto y cada
    aserción, sin las trazas, que van a la memoria de la API; con cilindros, `aire`: sus carreras
    medidas, que lee la memoria de cálculo, `aire_resultado.py`, V8.9 F4; con motores o un disparo,
    `electrico`: la caída de tensión y los disparos medidos, `medidas_electricas.py`,
    pedidos-de-extensiones D7);
  - `reglas_escenarios`: la regla «escenarios» de la puerta de entrega (D14).
Los `ajustes` de PRUEBA de un escenario (cotizacion-identificada-y-ajustes-por-escenario D5–D6,
`escenario_ajustes.py`) viven en su dict: entran a SU `hash_escenario` (cambiar uno vence sólo
ese resultado), nunca a `firma_documento`, y sin ellos el dict y el hash son los de siempre.
`poner` los valida contra el tablero si ya existe (400); si no, se validan al correrlo.
"""

from __future__ import annotations

import hashlib
import json
import re
import time

from .errors import ServiceError

SIN_CORRER, VENCIDO = "sin_correr", "vencido"
_NOMBRE = re.compile(r"^[^/\\?#%]{1,60}$")


#: Un resultado guardado antes de que existiera la versión del motor (F6b) es de la versión 1.
EPOCH_SIN_DATO = 1


#: Campos de `Dispositivo` que NO entran a la firma (pedidos-de-extensiones D5): `simbolo` no es
#: física (el dibujo del esquema) y `acoplado_a` se deriva de lo que el log ya firma (la regla
#: de `library/electrico/acoples.py`). Un campo nuevo de `Dispositivo` va a la firma o aquí: lo
#: exige `tests/test_firma_dispositivo.py` (si entra, vence todo resultado con tablero).
FUERA_DE_FIRMA = ("simbolo", "acoplado_a")
#: Claves del `modelo` de la ficha que tampoco entran: las lee sólo el ERC (que no se guarda como
#: resultado), no la co-simulación. `STO_canales` (los bornes de cada canal del STO, regla «canales
#: del STO»): la co-simulación del variador lee S1 y S2 por su cuenta. Si un modelo de `cosim/`
#: pasa a leer una de éstas, sale de aquí (y vence lo guardado).
FUERA_DE_FIRMA_MODELO = ("STO_canales",)


def _fichas_electricas(doc) -> list:
    """El tablero ya ARMADO (dispositivos, conductores y cables con su ficha del catálogo y los
    ajustes deducidos): cambiar el `electrico.modelo` de una ref en el YAML cambia la máquina
    aunque el log sea el mismo (F6b). Los programas no: su fuente ya está en el log. De cada
    dispositivo sale lo de `FUERA_DE_FIRMA`."""
    from dataclasses import asdict, is_dataclass

    from .electrico import modelo

    def plano(x):
        return asdict(x) if is_dataclass(x) else x

    def dispositivo(d):
        out = plano(d)
        for campo in FUERA_DE_FIRMA:
            out.pop(campo, None)
        if any(k in out.get("modelo", {}) for k in FUERA_DE_FIRMA_MODELO):
            out["modelo"] = {k: v for k, v in out["modelo"].items() if k not in FUERA_DE_FIRMA_MODELO}
        return out

    m = modelo(doc)
    return [[dispositivo(d) for d in m.dispositivos], [plano(x) for x in m.conductores],
            [plano(x) for x in m.cables]]


#: Versión de la firma (V8.5 F5b). La 2 no firma los `create_group` (agrupar no cambia la física
#: ni la red) y se escribe «2:<hash>»; la 1 (un hash pelado) firmaba el log entero.
FIRMA_VERSION = 2
#: Los comandos que no cambian la máquina: sólo organizan. `create_group` sí cuenta si el log
#: tiene un `transform_group` (mueve lo que el grupo junta: la membresía es geometría).
SIN_FISICA = frozenset({"create_group"})


def _hash(comandos, doc, fichas) -> str:
    texto = json.dumps([comandos, doc.materials, fichas], sort_keys=True, default=str)
    return hashlib.sha256(texto.encode()).hexdigest()[:20]


def _que_cuenta(comandos: list) -> list:
    if any(c.get("type") == "transform_group" for c in comandos):
        return list(comandos)
    return [c for c in comandos if c.get("type") not in SIN_FISICA]


def firma_documento(doc) -> str:
    """Lo que decide la máquina: el log (escena, variables y carril eléctrico, programas
    incluidos) sin lo que sólo organiza (`SIN_FISICA`), los materiales (la masa) y las fichas
    eléctricas del tablero. Color, ocultos, grupos y metadatos no cuentan."""
    return f"{FIRMA_VERSION}:{_hash(_que_cuenta(doc.commands), doc, _fichas_electricas(doc))}"


def firmas_v1(doc) -> set[str]:
    """Las firmas de la versión 1 (log ENTERO) que un resultado viejo puede tener y siguen
    describiendo esta máquina: la del log de hoy y las del log sin los `create_group` que se
    agregaron AL FINAL después de correrlo (agrupar no cambia la física; F5b). Sin compatibilidad,
    todo resultado guardado antes de la versión 2 quedaba vencido."""
    fichas = _fichas_electricas(doc)
    cmds = list(doc.commands)
    out = {_hash(cmds, doc, fichas)}
    if any(c.get("type") == "transform_group" for c in cmds):
        return out
    while cmds and cmds[-1].get("type") in SIN_FISICA:
        cmds.pop()
        out.add(_hash(cmds, doc, fichas))
    return out


CAMBIO = "la máquina cambió desde que se corrió"


def _motivo_firma(doc, guardada, firma: str | None, cache: dict | None = None) -> str | None:
    """Por qué la firma guardada en un resultado ya no describe el documento, o None si sigue. Una
    de la versión 1 se compara con `firmas_v1` y, además, vence si la co-simulación de hoy toma
    largos calculados que la de entonces no tomaba (F5b: unión ideal → conductor ruteado)."""
    if guardada == (firma or firma_documento(doc)):
        return None
    if not isinstance(guardada, str) or ":" in guardada:  # de la versión de hoy (o una futura)
        return CAMBIO
    cache = cache if cache is not None else {}
    if "v1" not in cache:
        from .cosim_red import largos_calculados

        cache["v1"] = firmas_v1(doc)
        cache["largos"] = bool(largos_calculados(doc))
    if guardada not in cache["v1"]:
        return CAMBIO
    if cache["largos"]:
        return ("la co-simulación ahora toma los largos calculados (tablero armado, cables con por) "
                "donde antes suponía unión ideal")
    return None


def hash_escenario(esc: dict) -> str:
    return hashlib.sha256(json.dumps(esc, sort_keys=True, default=str).encode()).hexdigest()[:16]


def leer(esc: dict):
    """dict → `Escenario` validado, o `ServiceError(400)` con la corrección."""
    from apolo.cosim.escenario import EscenarioInvalido, leer_escenario

    try:
        return leer_escenario(esc)
    except EscenarioInvalido as exc:
        raise ServiceError(400, str(exc)) from exc


def _avisos_tablero(doc, e) -> list[str]:
    """Los dispositivos que el escenario nombra y el tablero no tiene (todavía)."""
    from .electrico import modelo

    me = modelo(doc)
    des = {d.designacion for d in me.dispositivos}
    if not des:
        return ["el documento todavía no declara tablero (add_device): el escenario se valida "
                "contra él al correrlo"]
    nombrados = {a.dispositivo for a in e.acciones} | set(e.selectores) | set(e.setas_retenidas)
    nombrados |= set(e.motores) | set(e.sensores) | set(e.cilindros)
    nombrados |= {a["senal"].split(".")[0] for a in e.aserciones if a["senal"][:1] in "-="}
    des |= {c.designacion for c in me.cables}  # «-W1.1.I_A»: la corriente de un hilo del cable
    faltan = sorted(n for n in nombrados if n not in des)
    return [f"el tablero no tiene {n}" for n in faltan]


def _revisar_tipos(doc, e) -> tuple[list[str], list[str]]:
    """Las aserciones contra los tipos de las señales del tablero, SIN simular (F6b)."""
    from apolo.cosim.tipos import revisar, valores_iniciales

    from .cosim_aire import dispositivos
    from .electrico import modelo

    me = modelo(doc)
    if not me.dispositivos:
        return [], []
    return revisar(e.aserciones, valores_iniciales(dispositivos(doc, me, e.cilindros), me.programas))


def validar_nombre(nombre) -> str:
    """El nombre de un escenario, sin espacios a los lados, o `ServiceError(400)`."""
    nombre = str(nombre or "").strip()
    if not _NOMBRE.match(nombre):
        raise ServiceError(400, "el escenario necesita un nombre de 1 a 60 caracteres, sin «/», "
                                "«\\», «?», «#» ni «%» (p. ej. «marcha», «seta», «atasco»)")
    return nombre


def poner(doc, nombre: str, esc: dict) -> dict:
    """Guarda (o reemplaza) el escenario `nombre`. El resultado anterior se conserva: si el
    escenario cambió, queda «vencido» por su hash. Una aserción cuyo tipo no casa con su señal
    es 400 AL DECLARAR (F6b); una señal que el tablero no da, aviso."""
    nombre = validar_nombre(nombre)
    if not isinstance(esc, dict):
        raise ServiceError(400, "el escenario es un objeto {duracion_s, acciones, eventos, "
                                "aserciones, acoples, …}")
    from .flujo_producto import resolver_ritmo

    esc = resolver_ritmo(doc, esc)  # balance-de-producto D7: se GUARDA el número, no «nominal»
    e = leer(esc)
    from .cosim_inicial import validar as validar_iniciales

    validar_iniciales(doc, e)  # motor-a-eje-lineal F4: los límites de la junta, AL DECLARAR
    if e.ajustes:  # D5: contra el tablero si ya está (si no, al correrlo: como los dispositivos)
        from .electrico import modelo
        from .escenario_ajustes import validar as validar_ajustes

        me = modelo(doc)
        if me.dispositivos:
            validar_ajustes(me, e.ajustes)
    errores, avisos_tipos = _revisar_tipos(doc, e)
    if errores:
        raise ServiceError(400, "aserciones: " + " | ".join(errores))
    plano = json.loads(json.dumps(esc))
    previo = doc.escenarios.get(nombre) or {}
    doc.escenarios[nombre] = {"escenario": plano,
                              **({"resultado": previo["resultado"]} if previo.get("resultado") else {})}
    return {"nombre": nombre, "estado": estado(doc, nombre)["estado"],
            "n_aserciones": len(e.aserciones), "aserciones": [a["texto"] for a in e.aserciones],
            **({"flujo": {"ritmo_por_min": e.flujo["ritmo_por_min"], "sumideros": e.flujo["sumideros"]}}
               if e.flujo else {}),
            "avisos": _avisos_tablero(doc, e) + avisos_tipos}


def quitar(doc, nombre: str) -> None:
    if nombre not in doc.escenarios:
        raise ServiceError(404, no_existe(doc, nombre))
    del doc.escenarios[nombre]


def no_existe(doc, nombre: str) -> str:
    from apolo.library.electrico.referencias import sufijo_sugerencia

    return (f"No existe el escenario «{nombre}». Escenarios: "
            f"{', '.join(doc.escenarios) or 'ninguno (declara uno con set_scenario)'}."
            f"{sufijo_sugerencia(nombre, list(doc.escenarios))}")


def resolver(doc, escenario) -> tuple[str | None, dict]:
    """`escenario` = nombre guardado o dict inline → (nombre o None, dict del escenario)."""
    if isinstance(escenario, str):
        ent = doc.escenarios.get(escenario.strip())
        if ent is None:
            raise ServiceError(404, no_existe(doc, escenario))
        return escenario.strip(), ent["escenario"]
    if isinstance(escenario, dict):
        return None, escenario
    raise ServiceError(400, "`escenario` es el nombre de uno guardado (set_scenario) o el objeto "
                            "del escenario")


def estado(doc, nombre: str, firma: str | None = None, cache: dict | None = None) -> dict:
    """El estado del escenario guardado `nombre`, con su vigencia (`cache`: lo de la firma v1, una
    vez por listado)."""
    ent = doc.escenarios[nombre]
    res = ent.get("resultado")
    if not res:
        return {"estado": SIN_CORRER}
    from apolo.cosim import COSIM_EPOCH

    motivos = []
    epoch = res.get("cosim_epoch", EPOCH_SIN_DATO)
    if epoch != COSIM_EPOCH:
        motivos.append(f"el motor de la co-simulación cambió (versión {epoch} → {COSIM_EPOCH}) "
                       "desde que se corrió")
    motivo = _motivo_firma(doc, res.get("firma_documento"), firma, cache)
    if motivo:
        motivos.append(motivo)
    if res.get("hash_escenario") != hash_escenario(ent["escenario"]):
        motivos.append("el escenario cambió desde que se corrió")
    ext = res.get("extensiones") or {}
    hoy = extensiones_usadas(doc, ext)  # A4: como el epoch, pero de la extensión
    if ext != hoy:
        motivos.append(f"cambió una extensión cuyos modelos usa el tablero (era {ext or 'ninguna'}, "
                       f"hoy {hoy or 'ninguna'})")
    if motivos:
        return {"estado": VENCIDO, "motivo": "; ".join(motivos), "ultimo": res.get("veredicto")}
    return {"estado": res.get("veredicto")}


def listar(doc, nombre: str | None = None) -> dict:
    """Todos los escenarios con su estado; con `nombre`, ése entero (definición + resultado)."""
    firma = firma_documento(doc)
    if nombre is not None:
        if nombre not in doc.escenarios:
            raise ServiceError(404, no_existe(doc, nombre))
        ent = doc.escenarios[nombre]
        return {"nombre": nombre, **estado(doc, nombre, firma), "escenario": ent["escenario"],
                **({"resultado": ent["resultado"]} if ent.get("resultado") else {})}
    filas, cache = [], {}
    for n, ent in doc.escenarios.items():
        esc, res = ent["escenario"], ent.get("resultado") or {}
        fila = {"nombre": n, **estado(doc, n, firma, cache),
                **({"descripcion": esc["descripcion"]} if esc.get("descripcion") else {}),
                "duracion_s": esc.get("duracion_s"), "n_aserciones": len(esc.get("aserciones") or [])}
        if res:
            fila["corrido"] = res.get("fecha")
            fallidas = [a["asercion"] for a in res.get("aserciones", []) if not a.get("pasa")]
            if fallidas:
                fila["fallidas"] = fallidas
            if (res.get("flujo") or {}).get("balance"):  # balance-de-producto D11
                fila["balance"] = res["flujo"]["balance"]
        filas.append(fila)
    return {"escenarios": filas, "firma_documento": firma}


def extensiones_usadas(doc, previas: dict | None = None) -> dict:
    """{extensión: versión} de las extensiones cuyos modelos de co-simulación usa el tablero
    (plan nucleo-abierto-extensiones-privadas, A4: `COSIM_EPOCH` es sólo del núcleo). Sin
    extensiones cargadas ni `previas` guardadas, `{}` sin armar el tablero."""
    from apolo.cosim.modelos import DE_EXTENSION, de_extension

    if not DE_EXTENSION and not previas:
        return {}
    from .electrico import modelo

    return de_extension((d.modelo or {}).get("tipo") for d in modelo(doc).dispositivos)[1]


def resultado_compacto(veredicto: dict, res: dict, *, firma: str, hash_esc: str,
                       simulacion: str | None, extensiones: dict | None = None,
                       referencias_electricas: dict | None = None,
                       ajustes: list | None = None) -> dict:
    """Lo que se guarda en el manifest del último run: sin trazas (pesan cientos de KB). Con la
    versión del motor que lo produjo (`cosim_epoch`, F6b) y, sólo si el tablero usó modelos de
    una extensión, sus versiones (`extensiones`, A4). `referencias_electricas` (las arma la API
    del documento: `medidas_electricas.referencias`) dice qué es motor y contra qué se mide su
    caída; sin motores ni disparos no hay `electrico` (D7). `ajustes` (los de PRUEBA del
    escenario, `CosimSnapshot.ajustes`) va como `ajustes_de_prueba` sólo si hubo: quien lee las
    cifras de este resultado sabe que no son las del proyecto."""
    from apolo.cosim import COSIM_EPOCH

    from apolo.cosim.flujo import resumen as resumen_flujo

    from .aire_resultado import resumen_aire
    from .medidas_electricas import resumen_electrico

    r = res.get("resumen") or {}
    flujo = resumen_flujo((res.get("mecanica") or {}).get("flujo"))  # balance-de-producto D11
    aire = resumen_aire(res)  # V8.9 F4: carreras y consumo del aire para la memoria (sin aire, nada)
    electrico = resumen_electrico(res, referencias_electricas)  # D7: sin motores ni disparos, nada
    return {"veredicto": veredicto["veredicto"], "aserciones": veredicto["aserciones"],
            "firma_documento": firma, "hash_escenario": hash_esc, "cosim_epoch": COSIM_EPOCH,
            "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), "huella": r.get("huella"),
            "duracion_s": r.get("duracion_s"), "factor_tiempo_real": r.get("factor_tiempo_real"),
            **({"simulacion": simulacion} if simulacion else {}),
            **({"extensiones": dict(extensiones)} if extensiones else {}),
            **({"aire": aire} if aire else {}),
            **({"electrico": electrico} if electrico else {}),
            **({"ajustes_de_prueba": [dict(a) for a in ajustes]} if ajustes else {}),
            **({"flujo": flujo} if flujo else {})}


def guardar_resultado(doc, nombre: str, compacto: dict) -> bool:
    """Guarda el resultado si el escenario sigue existiendo (lo pudieron borrar mientras corría)."""
    ent = doc.escenarios.get(nombre)
    if ent is None:
        return False
    ent["resultado"] = compacto
    return True


def reglas_escenarios(doc) -> list[dict] | None:
    """La regla «escenarios» de la puerta (D14), una fila por escenario: `error` si el último
    run vigente falla, `aviso` si no se corrió, está vencido o no tiene aserciones, `ok` si pasa
    vigente. None sin escenarios: la puerta da lo de siempre."""
    if not doc.escenarios:
        return None
    firma = firma_documento(doc)
    filas, cache = [], {}
    for n in doc.escenarios:
        st = estado(doc, n, firma, cache)
        e = st["estado"]
        res = doc.escenarios[n].get("resultado") or {}
        if e == "falla":
            fallidas = [f"{a['asercion']} ({a.get('detalle', '')})"
                        for a in res.get("aserciones", []) if not a.get("pasa")]
            filas.append({"escenario": n, "estado": "error",
                          "detalle": f"falla: {'; '.join(fallidas[:3])}"
                                     + ("…" if len(fallidas) > 3 else "")})
        elif e == "pasa":
            filas.append({"escenario": n, "estado": "ok", "detalle": "pasa y está vigente"})
        else:
            detalle = {SIN_CORRER: "sin correr: córrelo con simulate(escenario=…)",
                       VENCIDO: f"vencido ({st.get('motivo')}; el último dio «{st.get('ultimo')}»): "
                                "vuelve a correrlo",
                       "sin_aserciones": "no tiene aserciones: no prueba nada"}.get(e, e)
            filas.append({"escenario": n, "estado": "aviso", "detalle": detalle})
    return filas
