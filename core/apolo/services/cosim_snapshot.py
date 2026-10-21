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
Por último corre la agenda del escenario en seco sobre un tablero desechable: un dispositivo,
una acción o una rama que no existen salen aquí, con su corrección.

Todo error es `ServiceError(400, texto)`. Sin locks: el llamador sostiene STATE_LOCK. Los
programas salen del carril (`add_program`, F5, ya compilados en el regenerate); `programas=`
pone otros ENCIMA, por PLC, sin guardarlos (`test_plc`).
"""

from __future__ import annotations

import json
import math
import re

from .errors import ServiceError


def _plano(x):
    """Una copia JSON pura (dicts y listas): lo que viaja al worker no arrastra tipos del catálogo."""
    return json.loads(json.dumps(x, default=str))


def _nombre_rayo(des: str) -> str:
    return "sensor_" + re.sub(r"[^A-Za-z0-9_]", "_", des)


def _motores(esc, me, modelos: dict) -> list[dict]:
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
                            if a.get("direccion_transporte") else {})})
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


def snapshot_cosim(doc, escenario, *, programas: list[dict] | None = None):
    """El `CosimSnapshot` del documento para `escenario` (dict de D12). `ServiceError(400)`."""
    from apolo.cosim.agenda import validar
    from apolo.cosim.datos import AcopleMotor, AcopleSensor, CosimSnapshot, DispositivoCosim
    from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
    from apolo.cosim.modelos import ModeloIncompleto
    from apolo.cosim.red import EntradaInvalida
    from apolo.cosim.tablero import Tablero
    from apolo.physics.dinamica import prepare_dynamics
    from apolo.physics.sim import PhysicsError

    from .cosim_red import entrada_red
    from .electrico import modelo

    try:
        esc = leer_escenario(escenario)
    except EscenarioInvalido as exc:
        raise ServiceError(400, str(exc)) from exc
    me = modelo(doc)
    if not me.dispositivos:
        raise ServiceError(400, "el documento no tiene tablero (add_device): no hay nada que co-simular; "
                                "para la mecánica sola usa simulate")
    dispositivos = [DispositivoCosim(d.designacion, d.ref, _plano(d.modelo or {}), _plano(d.ajustes or {}),
                                     int(d.cantidad or 1)) for d in me.dispositivos]
    red = _plano(entrada_red(me))
    try:
        tab = Tablero(red, dispositivos)
    except (ModeloIncompleto, EntradaInvalida) as exc:
        raise ServiceError(400, str(exc)) from exc
    por_des = {d.designacion: d for d in me.dispositivos}
    sensores, avisos = _sensores(esc, tab.modelos, por_des)
    peticion = {**esc.mecanica, "duracion_s": esc.duracion_s, "fps": esc.mecanica.get("fps", 10),
                "motores": _motores(esc, me, tab.modelos), "sensores": sensores,
                "productos": [dict(p) for p in esc.productos]}
    try:
        dyn = prepare_dynamics(doc.scene, doc.joints, doc.fasteners, doc.grounds, peticion, mates=doc.mates)
    except PhysicsError as exc:
        raise ServiceError(400, f"mecánica: {exc}") from exc
    if dyn.early is not None:
        raise ServiceError(400, f"mecánica: {dyn.early.get('mensaje')}")
    motores = [AcopleMotor(des, a["junta"], md.nombre, math.copysign(1.0, md.consigna))
               for (des, a), md in zip(esc.motores.items(), dyn.motores)]
    acoples_s = [AcopleSensor(des, _nombre_rayo(des)) for des in esc.sensores]
    progs = _programas(programas, me)
    try:
        validar(esc, tab, set(dyn.juntas))
    except EscenarioInvalido as exc:
        raise ServiceError(400, str(exc)) from exc
    return CosimSnapshot(dinamica=dyn, red=red, dispositivos=dispositivos, programas=progs,
                         motores=motores, sensores=acoples_s, escenario=esc,
                         hipotesis=[], avisos=avisos)  # los de la mecánica van en su salida
