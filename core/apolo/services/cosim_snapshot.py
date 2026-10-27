"""El snapshot de una co-simulación desde el documento (plan V8.3 D11.1): se toma bajo STATE_LOCK.

`snapshot_cosim(doc, escenario, programas=…)` hornea TODO lo que el worker necesita en datos puros
(`cosim/datos.CosimSnapshot`), así la co-simulación corre después en otro proceso sin
`STATE_LOCK` ni `PHYSICS_LOCK`:
  - la dinámica de V8.2 (`prepare_dynamics`) con un motor POR PLACA por cada motor del tablero
    acoplado a su junta (`acoples.motores`; D8: la fuente ideal no deja escribir el tope), la
    placa por el adaptador `placa_v82` y la relación y el rendimiento del reductor de su modelo;
  - una fotocelda por cada sensor del tablero acoplado a su rayo (`acoples.sensores`; sin
    alcance, el de su ficha: `alcance_mm` o `Sn_mm`, el inductivo como rayo corto, D1);
  - los productos del escenario y su `mecanica`;
  - el formato plano de las redes (`cosim_red.entrada_red`) y los dispositivos con su `modelo` y
    sus `ajustes` (un `modelo` incompleto es error ANTES de simular, D7);
  - el ST de cada PLC compilado contra los bornes de SU ficha (D4).
Por último corre la agenda del escenario en seco sobre un tablero y unos PLC desechables: un
dispositivo, una acción, una rama o una variable a `escribir` que no existen (o no se escriben)
salen aquí, con su corrección.

F6: los ajustes obligatorios que faltan salen TODOS juntos (`electrico.ajustes_faltantes`), una
banda que no avanza con cajas encima o con aserciones es error (`cosim_bandas.bandas_quietas`),
los avisos de la preparación de la dinámica van, con «mecánica: », a los avisos del resultado y
los ajustes deducidos de la pieza ligada (`Dispositivo.deducidos`), a las hipótesis.

F6b: lo barato va ANTES de preparar la dinámica (cascos e inercias: ~20 s en la faja 73): los
tipos de las aserciones contra el tablero (`cosim/tipos.py`) y la banda que no avanza, con la
PREVISIÓN de las bandas (`cosim_bandas.prever`, sin OCCT pesado); el chequeo de bandas se repite
después sobre la dinámica real, que manda.

Todo error es `ServiceError(400, texto)`. Sin locks: el llamador sostiene STATE_LOCK. Los
programas salen del carril (`add_program`, F5, ya compilados en el regenerate); `programas=`
pone otros ENCIMA, por PLC, sin guardarlos (`test_plc`). `plc_externo=` (el PEDIDO de la corrida,
plan plc-en-el-lazo D6) cambia el PLC de esas designaciones por el conector de una extensión
(`services/cosim_externo.py` lo valida; sin él, `externos` vacío y el snapshot de siempre).
"""

from __future__ import annotations

import json
import math
import re

from .errors import ServiceError


def _plano(x):
    """Una copia JSON pura (dicts y listas): lo que viaja al worker no arrastra tipos del catálogo."""
    return json.loads(json.dumps(x, default=str))


def _color(ref: str) -> str | None:
    """El color físico de la ficha (`specs.color`: verde, rojo, azul, ámbar…), o None. Viaja al
    worker para la tabla de mandos y pilotos de la sesión en vivo (V8.4 D4, D5)."""
    from apolo.library.catalog import CATALOG

    c = CATALOG.get(ref)
    color = (getattr(c, "specs", None) or {}).get("color") if c is not None else None
    return str(color) if color else None


def _nombre_rayo(des: str) -> str:
    return "sensor_" + re.sub(r"[^A-Za-z0-9_]", "_", des)


def _motores(esc, me, modelos: dict, transmisiones: dict) -> list[dict]:
    from apolo.cosim.modelos import Motor
    from apolo.cosim.modelos.motor import placa_v82

    por_des = {d.designacion: d for d in me.dispositivos}
    peticion = []
    for des, m in modelos.items():
        if isinstance(m, Motor) and des not in esc.motores:
            raise ServiceError(400, f"el motor {des} no está acoplado a una junta: declara "
                                    f'acoples.motores = {{"{des}": {{"junta": "<junta que mueve>", '
                                    '"direccion_transporte": [1, 0, 0]}} en el escenario')
    for des, a in esc.motores.items():
        m = modelos.get(des)
        if not isinstance(m, Motor):
            raise ServiceError(400, f"acoples.motores: «{des}» no es un motor del tablero; motores: "
                                    f"{', '.join(d for d, x in modelos.items() if isinstance(x, Motor)) or 'ninguno'}")
        d = por_des[des]
        placa = placa_v82({**d.modelo, **d.ajustes})
        peticion.append({"junta": a["junta"], "modo": "velocidad", "placa": placa, "reduccion": m.i,
                         "eta": m.eta_red, "frecuencia_hz": m.fn,
                         **({"direccion_transporte": a["direccion_transporte"]}
                            if a.get("direccion_transporte") else {}),
                         # plan motor-a-eje-lineal D2: el motor rotativo a una junta prismática
                         **({"radio_transmision_mm": transmisiones[des][0]} if des in transmisiones else {})})
    return peticion


def _sensores(esc, modelos: dict, por_des: dict) -> tuple[list[dict], list[str]]:
    from apolo.cosim.modelos import Sensor

    avisos, out = [], []
    for des, m in modelos.items():
        if isinstance(m, Sensor) and des not in esc.sensores:
            avisos.append(f"el sensor {des} no tiene rayo (acoples.sensores): no detecta nada")
    for des, s in esc.sensores.items():
        if not isinstance(modelos.get(des), Sensor):
            raise ServiceError(400, f"acoples.sensores: «{des}» no es un sensor del tablero")
        if "junta" in s:  # V8.9 D8: el detector de un cilindro lee su junta, no un rayo
            continue
        alcance = s.get("alcance_mm")
        if alcance is None:
            ficha = por_des[des].modelo
            alcance = ficha.get("alcance_mm") or ficha.get("Sn_mm")
        if not alcance:
            raise ServiceError(400, f"acoples.sensores.{des}: falta «alcance_mm» (su ficha no lo trae)")
        out.append({"nombre": _nombre_rayo(des), "tipo": "rayo", "origen": s["origen"],
                    "direccion": s["direccion"], "alcance_mm": float(alcance)})
    return out, avisos


def _programas(programas, me) -> list:
    """Los programas del carril (`add_program`, ya compilados) con los de `programas`
    ENCIMA: uno de la lista reemplaza al del carril de su PLC (así prueba `test_plc` un ST sin
    guardarlo)."""
    from apolo.cosim.datos import ProgramaCosim

    del_carril = {p.plc: ProgramaCosim(p.plc, p.nombre, p.compilado, p.ciclo_ms, dict(p.ciclos))
                  for p in me.programas}
    encima = _compilar_programas(programas, me)
    return list({**del_carril, **{p.plc: p for p in encima}}.values())


def _compilar_programas(programas, me) -> list:
    from apolo.cosim.datos import ProgramaCosim
    from apolo.plc import ErrorCompilacion, compilar

    por_des = {d.designacion: d for d in me.dispositivos}
    out = []
    for k, p in enumerate(programas or []):
        des = p.get("plc")
        d = por_des.get(des)
        if d is None or (d.modelo or {}).get("tipo") != "plc":
            raise ServiceError(400, f"programas[{k}]: «{des}» no es un PLC del tablero; PLC: "
                                    f"{', '.join(x.designacion for x in me.dispositivos if (x.modelo or {}).get('tipo') == 'plc') or 'ninguno'}")
        try:
            comp = compilar(str(p.get("fuente") or ""), bornes={b.id for b in d.bornes})
        except ErrorCompilacion as exc:
            raise ServiceError(400, f"programas[{k}] ({des}): {exc}") from exc
        ciclo = p.get("ciclo_ms", 10)
        if not isinstance(ciclo, int) or isinstance(ciclo, bool) or ciclo < 1:
            raise ServiceError(400, f"programas[{k}]: «ciclo_ms» es un entero ≥ 1 (ms)")
        out.append(ProgramaCosim(des, str(p.get("nombre") or f"programa{k}"), comp, ciclo,
                                 dict(p.get("ciclos") or {})))
    if len({p.plc for p in out}) != len(out):
        raise ServiceError(400, "programas: un PLC lleva UN programa fuente (varias tareas = varios "
                                "PROGRAM en la misma fuente, con «ciclos»)")
    return out


def snapshot_cosim(doc, escenario, *, programas: list[dict] | None = None, plc_externo: dict | None = None):
    """El `CosimSnapshot` del documento para `escenario` (dict de D12). `ServiceError(400)`."""
    from apolo.cosim.agenda import plcs_de_prueba, validar
    from apolo.cosim.datos import AcopleMotor, AcopleSensor, CosimSnapshot
    from apolo.cosim.escenario import DURACION_MAX_S as DURACION_ESCENARIO_MAX_S
    from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
    from apolo.cosim.modelos import ModeloIncompleto, de_extension
    from apolo.cosim.red import EntradaInvalida
    from apolo.cosim.tablero import Tablero
    from apolo.physics.dinamica import prepare_dynamics
    from apolo.physics.sim import PhysicsError

    from apolo.cosim.tipos import revisar, valores_iniciales

    from . import cosim_aire, cosim_externo, cosim_transmision, escenario_ajustes
    from .cosim_bandas import bandas_quietas, prever
    from .cosim_red import entrada_red, largos_calculados
    from .delivery_inputs import tornilleria_join_bolted
    from .electrico import ajustes_faltantes, modelo, texto_ajustes_faltantes
    from .flujo_producto import resolver_ritmo

    try:
        esc = leer_escenario(resolver_ritmo(doc, escenario))  # balance-de-producto D7: «nominal»
    except EscenarioInvalido as exc:
        raise ServiceError(400, str(exc)) from exc
    me = modelo(doc)
    if not me.dispositivos:
        raise ServiceError(400, "el documento no tiene tablero (add_device): no hay nada que co-simular; "
                                "para la mecánica sola usa simulate")
    faltan = ajustes_faltantes(me)  # F6: todos juntos, no el primero de uno solo
    if faltan:
        raise ServiceError(400, " | ".join(texto_ajustes_faltantes(d, f) for d, f in faltan))
    # D5 (cotizacion-identificada-y-ajustes-por-escenario): los ajustes de PRUEBA del escenario,
    # encima de los del proyecto en una COPIA del modelo (el del documento no cambia); sin ellos,
    # el mismo `me`
    me, usados = escenario_ajustes.aplicar(me, esc.ajustes)
    hipotesis = [f"{d.designacion}: {k} = {d.ajustes[k]:g}, {origen}"
                 for d in me.dispositivos for k, origen in d.deducidos.items()]
    hipotesis += escenario_ajustes.hipotesis(usados)
    cosim_aire.exigir_acoples(doc, me, esc)  # V8.9 D8: antes de armar los modelos
    aire = cosim_aire.red_aire(me, esc)
    dispositivos = cosim_aire.dispositivos(doc, me, esc.cilindros)
    red = _plano(entrada_red(me, largos=largos_calculados(doc, me)))  # V8.5 F5b: los calculados
    try:
        tab = Tablero(red, dispositivos, aire or None)
    except (ModeloIncompleto, EntradaInvalida) as exc:
        raise ServiceError(400, str(exc)) from exc
    por_des = {d.designacion: d for d in me.dispositivos}
    sensores, avisos = _sensores(esc, tab.modelos, por_des)
    transmisiones, hip_tr = cosim_transmision.resolver(doc, esc)  # motor-a-eje-lineal: {} sin ellas
    hipotesis += hip_tr
    peticion = {**esc.mecanica, "duracion_s": esc.duracion_s, "fps": esc.mecanica.get("fps", 10),
                "motores": _motores(esc, me, tab.modelos, transmisiones), "sensores": sensores,
                "productos": [dict(p) for p in esc.productos]}
    if esc.flujo is not None:  # balance-de-producto D5: el rastreo, sólo con el bloque
        peticion["flujo"] = {k: esc.flujo[k] for k in ("plazo_s", "quieto_s", "zonas_espera")}
    if aire:  # V8.9 D4: el <motor> de fuerza de cada cilindro y su fricción y masa en la junta
        mot_aire, juntas_aire = cosim_aire.peticion(doc, me, esc, tab)
        peticion["motores"] = peticion["motores"] + mot_aire
        peticion["juntas"] = {**(esc.mecanica.get("juntas") or {}), **juntas_aire}
    progs = _programas(programas, me)
    externos = cosim_externo.leer(plc_externo, me, progs)  # plc-en-el-lazo D6: antes de la dinámica
    errores, _ = revisar(esc.aserciones, valores_iniciales(dispositivos, progs))
    if errores:  # F6b: antes de simular, no tras el veredicto
        raise ServiceError(400, "aserciones: " + " | ".join(errores))
    # el tope de la duración es el del ESCENARIO (corre en su proceso, sin PHYSICS_LOCK), no el de
    # la dinámica suelta: lo que `set_scenario` acepta, corre (balance-de-producto, trabas de flujo)
    sujetas = tornilleria_join_bolted(doc)  # trabas-de-modelado D2b: la tornillería con su unión
    prevision = prever(doc.scene, doc.joints, doc.fasteners, doc.grounds, peticion, mates=doc.mates,
                       duracion_max_s=DURACION_ESCENARIO_MAX_S, sujetas=sujetas)
    error = bandas_quietas(doc.scene, esc, prevision) if prevision is not None else None
    if error:  # F6b: el rechazo no espera los cascos
        raise ServiceError(400, error)
    try:
        dyn = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, peticion, mates=doc.mates,
                               duracion_max_s=DURACION_ESCENARIO_MAX_S, sujetas=sujetas)
    except PhysicsError as exc:
        raise ServiceError(400, f"mecánica: {exc}") from exc
    if dyn.early is not None:
        raise ServiceError(400, f"mecánica: {dyn.early.get('mensaje')}")
    error = bandas_quietas(doc.scene, esc, dyn)  # F6: una banda que no avanza da verdes triviales
    if error:
        raise ServiceError(400, error)
    avisos += [f"mecánica: {a}" for a in dyn.avisos]  # F6: los de la dinámica, todos
    motores = [AcopleMotor(des, a["junta"], md.nombre, math.copysign(1.0, md.consigna),
                           **({"irreversible": True} if transmisiones.get(des, (0, False))[1] else {}))
               for (des, a), md in zip(esc.motores.items(), dyn.motores)]
    acoples_s = [AcopleSensor(des, _nombre_rayo(des)) for des, s in esc.sensores.items() if "junta" not in s]
    cilindros, reeds = cosim_aire.acoples(esc, dyn, len(esc.motores))
    try:
        validar(esc, tab, set(dyn.juntas), plcs_de_prueba(progs, externos))
    except EscenarioInvalido as exc:
        raise ServiceError(400, str(exc)) from exc
    clases, extensiones = de_extension((d.modelo or {}).get("tipo") for d in dispositivos)
    return CosimSnapshot(dinamica=dyn, red=red, dispositivos=dispositivos, programas=progs,
                         motores=motores, sensores=acoples_s, escenario=esc,
                         hipotesis=hipotesis, avisos=avisos,
                         modelos_extension=clases, extensiones=extensiones,
                         aire=aire, cilindros=cilindros, reeds=reeds, externos=externos,
                         ajustes=usados)
