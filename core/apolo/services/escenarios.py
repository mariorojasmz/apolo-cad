"""Los escenarios de prueba de un documento (plan V8.3 D12, D14): metadato del manifest.

Un escenario es una PRUEBA, no diseño: vive en `doc.escenarios` (fuera del log y de los
checkpoints, como `motion` o `fea`) con la forma `{nombre: {"escenario": {...}, "resultado":
{...}?}}`. Aquí está lo que lo LEE y lo escribe (sin locks: el llamador sostiene STATE_LOCK):
  - `poner`/`quitar`: lo valida `cosim.escenario.leer_escenario` (con sus aserciones) y se
    guarda tal cual llegó (el JSON del agente); los dispositivos que nombra y no están en el
    tablero vuelven como `avisos` (el tablero puede declararse después);
  - `listar`: cada uno con su ESTADO: «sin_correr», «pasa», «falla», «sin_aserciones» o
    «vencido»;
  - vigencia (como las reglas del FEA): el resultado guarda la `firma_documento` (log +
    materiales + las fichas eléctricas del tablero: lo que decide la máquina), el
    `hash_escenario` y la versión del motor (`cosim.COSIM_EPOCH`, F6b); si cualquiera cambió,
    «vencido»;
  - `resultado_compacto` + `guardar_resultado`: lo que queda del último run (veredicto y cada
    aserción, sin las trazas, que van a la memoria de la API);
  - `reglas_escenarios`: la regla «escenarios» de la puerta de entrega (D14).
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


def _fichas_electricas(doc) -> list:
    """El tablero ya ARMADO (dispositivos, conductores y cables con su ficha del catálogo y los
    ajustes deducidos): cambiar el `electrico.modelo` de una ref en el YAML cambia la máquina
    aunque el log sea el mismo (F6b). Los programas no: su fuente ya está en el log."""
    from dataclasses import asdict, is_dataclass

    from .electrico import modelo

    m = modelo(doc)
    return [[asdict(x) if is_dataclass(x) else x for x in grupo]
            for grupo in (m.dispositivos, m.conductores, m.cables)]


def firma_documento(doc) -> str:
    """Lo que decide la máquina: el log entero (escena, variables y carril eléctrico, programas
    incluidos), los materiales (la masa) y las fichas eléctricas del tablero. Color, ocultos y
    metadatos no cuentan."""
    texto = json.dumps([doc.commands, doc.materials, _fichas_electricas(doc)], sort_keys=True,
                       default=str)
    return hashlib.sha256(texto.encode()).hexdigest()[:20]


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
    nombrados |= set(e.motores) | set(e.sensores)
    nombrados |= {a["senal"].split(".")[0] for a in e.aserciones if a["senal"][:1] in "-="}
    des |= {c.designacion for c in me.cables}  # «-W1.1.I_A»: la corriente de un hilo del cable
    faltan = sorted(n for n in nombrados if n not in des)
    return [f"el tablero no tiene {n}" for n in faltan]


def _revisar_tipos(doc, e) -> tuple[list[str], list[str]]:
    """Las aserciones contra los tipos de las señales del tablero, SIN simular (F6b)."""
    from apolo.cosim.tipos import revisar, valores_iniciales

    from .electrico import modelo

    me = modelo(doc)
    if not me.dispositivos:
        return [], []
    return revisar(e.aserciones, valores_iniciales(me.dispositivos, me.programas))


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
    e = leer(esc)
    errores, avisos_tipos = _revisar_tipos(doc, e)
    if errores:
        raise ServiceError(400, "aserciones: " + " | ".join(errores))
    plano = json.loads(json.dumps(esc))
    previo = doc.escenarios.get(nombre) or {}
    doc.escenarios[nombre] = {"escenario": plano,
                              **({"resultado": previo["resultado"]} if previo.get("resultado") else {})}
    return {"nombre": nombre, "estado": estado(doc, nombre)["estado"],
            "n_aserciones": len(e.aserciones), "aserciones": [a["texto"] for a in e.aserciones],
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


def estado(doc, nombre: str, firma: str | None = None) -> dict:
    """El estado del escenario guardado `nombre`, con su vigencia."""
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
    if res.get("firma_documento") != (firma or firma_documento(doc)):
        motivos.append("la máquina cambió desde que se corrió")
    if res.get("hash_escenario") != hash_escenario(ent["escenario"]):
        motivos.append("el escenario cambió desde que se corrió")
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
    filas = []
    for n, ent in doc.escenarios.items():
        esc, res = ent["escenario"], ent.get("resultado") or {}
        fila = {"nombre": n, **estado(doc, n, firma),
                **({"descripcion": esc["descripcion"]} if esc.get("descripcion") else {}),
                "duracion_s": esc.get("duracion_s"), "n_aserciones": len(esc.get("aserciones") or [])}
        if res:
            fila["corrido"] = res.get("fecha")
            fallidas = [a["asercion"] for a in res.get("aserciones", []) if not a.get("pasa")]
            if fallidas:
                fila["fallidas"] = fallidas
        filas.append(fila)
    return {"escenarios": filas, "firma_documento": firma}


def resultado_compacto(veredicto: dict, res: dict, *, firma: str, hash_esc: str,
                       simulacion: str | None) -> dict:
    """Lo que se guarda en el manifest del último run: sin trazas (pesan cientos de KB). Con la
    versión del motor que lo produjo (`cosim_epoch`, F6b)."""
    from apolo.cosim import COSIM_EPOCH

    r = res.get("resumen") or {}
    return {"veredicto": veredicto["veredicto"], "aserciones": veredicto["aserciones"],
            "firma_documento": firma, "hash_escenario": hash_esc, "cosim_epoch": COSIM_EPOCH,
            "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), "huella": r.get("huella"),
            "duracion_s": r.get("duracion_s"), "factor_tiempo_real": r.get("factor_tiempo_real"),
            **({"simulacion": simulacion} if simulacion else {})}


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
    filas = []
    for n in doc.escenarios:
        st = estado(doc, n, firma)
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
