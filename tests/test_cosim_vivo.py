"""La sesión en vivo de la co-simulación, sin proceso ni WebSocket (plan V8.4 F1, D1).

  - el paso compartido (`corrida.Corrida`) deja el lote IGUAL: la huella de `planificador.correr`
    es la del bucle de V8.3, copiado aquí tal cual estaba;
  - determinismo: las acciones inyectadas SIN hora en la sesión dan la misma huella que el
    escenario por lote con esas acciones agendadas, y la GRABACIÓN vuelta escenario también;
  - `Agenda.inyectar`: una acción que el modelo no admite vuelve como rechazo de ESA acción y la
    corrida sigue; un mensaje que no se lee, rechazo inmediato;
  - sin historia: tras `podar` el integrador no acumula fotogramas ni trazas;
  - la tabla y el fotograma binario (formato de `vivo_fotograma.py`).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("mujoco")

from apolo.cosim.acople import AcopleMecanico  # noqa: E402
from apolo.cosim.agenda import Agenda  # noqa: E402
from apolo.cosim.corrida import _fuentes_plc, _mecanica, _paso_ms, _plc, _signos_banda  # noqa: E402
from apolo.cosim.escenario import EscenarioInvalido, leer_escenario  # noqa: E402
from apolo.cosim.planificador import correr  # noqa: E402
from apolo.cosim.tablero import Tablero  # noqa: E402
from apolo.cosim.trazas import Trazas, huella  # noqa: E402
from apolo.cosim.vivo import Vivo, escenario_grabado, escenario_vivo, leer_mensaje  # noqa: E402
from apolo.cosim.vivo_fotograma import CABECERA, FORMATO, leer_fotograma  # noqa: E402
from apolo.physics.dinamica_integrador import Integrador  # noqa: E402
from apolo.plc import PLC  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from cosim_lazo_banco import PROGRAMAS, escenario_variador, faja_variador  # noqa: E402

DUR = 2.5
SETA = {"t": 2.0, "accion": "presionar", "dispositivo": "-S0"}


def _correr_v83(snap) -> str:
    """El bucle de `planificador.correr` ANTES de V8.4 F1, copiado tal cual: sólo la huella."""
    esc = snap.escenario
    integ = Integrador(snap.dinamica)
    tab = Tablero(snap.red, snap.dispositivos)
    plcs = {}
    for p in snap.programas:
        plc = PLC(p.compilado, ciclo_ms=p.ciclo_ms, ciclos=p.ciclos or None)
        plc.cortar()
        plcs[p.plc] = plc
    acople = AcopleMecanico(integ, snap.motores, snap.sensores)
    agenda = Agenda(esc, tab, acople)
    dt = integ.dt_int
    paso_ms = _paso_ms(dt)
    trazas = Trazas(esc.analogicas_hz, dt)
    extra = set(esc.senales_extra)
    signos = _signos_banda(snap)
    n = integ.n_int
    for k in range(n + 1):
        t = k * dt
        agenda.aplicar(t)
        tab.mec, tab.detecta = acople.leer()
        tab.paso(dt)
        for des, plc in plcs.items():
            _plc(des, plc, tab, k * paso_ms, esc.plc_run)
        trazas.registrar(k, t, tab.salidas_por_prefijo() + _fuentes_plc(plcs),
                         lambda: {**tab.senales_red(extra), **_mecanica(integ, signos)}, forzar=k == n)
        if k == n:
            break
        integ.intercambio(control=acople.control(tab.comandos))
    final = trazas.cerrar()
    return huella(trazas.salida(), agenda.eventos, final)


@pytest.fixture(scope="module")
def doc():
    return faja_variador()


@pytest.fixture(scope="module")
def base():
    return escenario_variador(DUR, cajas=True, acciones=[SETA])


@pytest.fixture(scope="module")
def lote(doc, base):
    return correr(snapshot_cosim(doc, base, programas=PROGRAMAS))


@pytest.fixture(scope="module")
def snap_vivo(doc, base):
    return snapshot_cosim(doc, escenario_vivo(base), programas=PROGRAMAS)


def test_el_paso_compartido_deja_el_lote_igual_al_de_v83(doc, base, lote):
    assert lote["resumen"]["huella"] == _correr_v83(snapshot_cosim(doc, base, programas=PROGRAMAS))
    assert lote["final"]["-K1.Main.cuenta"] >= 1  # pasó de todo: cajas, fotocelda, PLC, seta


def test_el_escenario_vivo_quita_lo_que_da_la_persona(base):
    esc = escenario_vivo({**base, "aserciones": ["-M1.rpm >= 1 al_final"],
                          "eventos": base["eventos"] + [{"t": 1, "tipo": "atasco", "junta": "j", "par_Nm": 5}]})
    assert esc["acciones"] == [] and "aserciones" not in esc
    assert [e["tipo"] for e in esc["eventos"]] == ["producto"]  # la cola de cajas se queda
    assert esc["acoples"] == base["acoples"] and esc["duracion_s"] == DUR
    leer_escenario(esc)


def _sesion(snap, plan: dict, *, trazas=True, n=None) -> tuple[Vivo, list]:
    """Corre una sesión «de golpe»: en cada k de `plan` entra ese mensaje sin hora."""
    v = Vivo(snap, trazas=trazas)
    n = n if n is not None else round(DUR / v.dt)
    respuestas = []
    while v.k < n:
        for msg in plan.get(v.k, []):
            r = v.recibir(msg)
            if r is not None:
                respuestas.append(r)
        prox = min([k for k in plan if k > v.k] + [n])
        v.avanzar(prox - v.k)
        respuestas += v.respuestas()
    return v, respuestas


PLAN = {0: [{"girar": "-S1", "valor": 1.0, "id": "g"}],
        150: [{"accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2, "id": 1}],
        1000: [{"presionar": "-S0", "id": 2}]}


def test_las_acciones_sin_hora_dan_la_huella_del_lote_y_la_grabacion_tambien(doc, snap_vivo, lote):
    v, resp = _sesion(snap_vivo, PLAN)
    assert [r["tipo"] for r in resp] == ["ack", "ack", "ack"]
    assert [r["t"] for r in resp] == [0.0, 0.3, 2.0]
    h = v.cerrar_lote()
    assert h == lote["resumen"]["huella"]  # = el escenario con las acciones agendadas
    assert v.grabacion == [
        {"t": 0.0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0},
        {"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2},
        {"t": 2.0, "accion": "presionar", "dispositivo": "-S0"}]
    grabado = escenario_grabado(escenario_vivo(escenario_variador(DUR, cajas=True)), v.grabacion, DUR)
    assert correr(snapshot_cosim(doc, grabado, programas=PROGRAMAS))["resumen"]["huella"] == h


def test_otra_hora_otra_huella(snap_vivo, lote):
    plan = {**PLAN, 1000: [], 980: [{"presionar": "-S0"}]}
    v, _ = _sesion(snap_vivo, plan)
    assert v.cerrar_lote() != lote["resumen"]["huella"]


def test_una_accion_que_el_modelo_no_admite_se_rechaza_y_la_corrida_sigue(snap_vivo):
    plan = {0: [{"pulsar": "-S9", "id": "a"}, {"presionar": "-S1", "id": "b"},
                {"girar": "-S1", "valor": 1.0, "id": "c"}],
            5: [{"bailar": "-S1", "id": "d"}, {"pulsar": "-S1", "t": 3, "id": "e"},
                {"evento": {"tipo": "atasco", "junta": "no_existe", "par_Nm": 10}, "id": "f"},
                {"evento": {"tipo": "producto", "nombre": "x"}, "id": "g"}]}
    v, resp = _sesion(snap_vivo, plan, trazas=False, n=40)
    por_id = {r["id"]: r for r in resp}
    assert por_id["a"]["tipo"] == "rechazo" and "-S9" in por_id["a"]["motivo"]
    assert por_id["b"]["tipo"] == "rechazo" and "no admite «presionar»" in por_id["b"]["motivo"]
    assert por_id["c"]["tipo"] == "ack"
    assert por_id["d"]["tipo"] == "rechazo" and "una acción por mensaje" in por_id["d"]["motivo"]
    assert por_id["e"]["tipo"] == "rechazo" and "«t»" in por_id["e"]["motivo"]
    assert por_id["f"]["tipo"] == "rechazo" and "«no_existe» no está en la simulación" in por_id["f"]["motivo"]
    assert por_id["g"]["tipo"] == "rechazo" and "MuJoCo no crea cuerpos" in por_id["g"]["motivo"]
    assert v.k == 40 and [g["accion"] for g in v.grabacion] == ["girar"]  # sólo lo aceptado


def test_un_evento_en_vivo_con_duracion_se_deshace_solo(snap_vivo):
    junta = next(iter(snap_vivo.dinamica.juntas))
    v, resp = _sesion(snap_vivo, {10: [{"evento": {"tipo": "atasco", "junta": junta, "par_Nm": 50,
                                                   "duracion_s": 0.02}, "id": 1}]}, trazas=False, n=40)
    assert resp == [{"tipo": "ack", "id": 1, "t": 0.02,
                     "evento": {"tipo": "atasco", "junta": junta, "par_Nm": 50, "duracion_s": 0.02}}]
    assert [e.get("evento") for e in v.c.agenda.eventos] == ["atasco", "atasco.fin"]


def test_los_controles_se_leen_aparte():
    assert leer_mensaje({"control": "pausa"}) == ("control", "pausa")
    assert leer_mensaje({"soltar": "-S1", "id": 4}) == ("accion", {"accion": "soltar", "dispositivo": "-S1"})
    with pytest.raises(EscenarioInvalido):
        leer_mensaje({"control": "dormir"})


def test_sin_historia_el_integrador_no_acumula(snap_vivo):
    v = Vivo(snap_vivo)
    v.recibir({"girar": "-S1", "valor": 1.0})
    for _ in range(60):  # 2 s virtuales en ventanas de 17 intercambios
        v.avanzar(17)
        v.podar()
    integ = v.c.integ
    assert len(integ.frames) <= 1
    assert all(len(lista) <= 1 for tr in integ.trazas.values() for lista in tr.values())
    assert all(len(x) == 0 for x in integ.fotos.flancos + integ.fotos.muestras)


def test_la_tabla_y_el_fotograma(snap_vivo):
    v = Vivo(snap_vivo)
    v.recibir({"girar": "-S1", "valor": 1.0})
    v.recibir({"accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2})
    v.avanzar(1)
    nuevas, valores = v.fot.reunir()
    tabla = v.fot.tabla()
    assert nuevas == tabla["senales"] and "-M1.rpm" in tabla["senales"]
    assert {"-K1.estado"} <= set(v.fot.textos_cambiados())  # el estado del PLC es texto
    mandos = {m["designacion"]: m for m in tabla["mandos"]}
    assert mandos["-S0"]["tipo"] == "seta" and mandos["-S0"]["color"] == "rojo"
    assert mandos["-S0"]["fondo"] == "amarillo" and mandos["-S0"]["acciones"] == ["presionar", "liberar"]
    assert mandos["-S1"]["tipo"] == "pulsador" and mandos["-S1"]["potenciometro"] is True
    assert tabla["productos"] and tabla["cuerpos"] and tabla["bandas"]
    for _ in range(300):
        v.avanzar(17)
        v.fot.reunir()
    nuevas, valores = v.fot.reunir()
    f = leer_fotograma(v.fot.empacar(v.t, 1.0, valores))
    assert f["formato"] == FORMATO and math.isclose(f["t"], v.t, rel_tol=1e-6)
    assert f["cuerpos"].shape == (len(tabla["cuerpos"]), 7)
    assert np.allclose(np.linalg.norm(f["cuerpos"][:, 3:], axis=1), 1.0, atol=1e-4)
    vivos = [k for k, p in enumerate(f["productos"]) if not np.isnan(p[0])]
    assert vivos and all(v.c.integ.activo[k] for k in vivos)  # NaN = todavía no nació
    rpm = f["senales"][v.fot.senales.index("-M1.rpm")]
    assert rpm > 1000  # arrancó con la rampa
    assert len(f["senales"]) == len(v.fot.senales)
    assert f["bandas"][0] != 0.0 and not np.isnan(f["juntas"]).any()
    n = CABECERA + 7 * (len(f["cuerpos"]) + len(f["productos"])) + len(f["juntas"]) + len(f["bandas"])
    assert len(v.fot.empacar(v.t, 1.0, valores)) == 4 * (n + len(v.fot.senales))


def test_sumideros_en_el_escenario(doc):
    esc = escenario_variador(1.0, cajas=True)
    esc["mecanica"] = {**esc["mecanica"], "sumideros": [{"punto_mm": [1200, 0, 0], "normal": [1, 0, 0]}]}
    assert leer_escenario(esc).mecanica["sumideros"][0]["normal"] == [1, 0, 0]
    snap = snapshot_cosim(doc, esc, programas=PROGRAMAS)
    assert len(snap.dinamica.sumideros) == 1  # llegó a la petición de la dinámica
    for malo, texto in (([{"punto_mm": [0, 0]}], "falta «normal»"),
                        ([{"punto_mm": [0, 0, 0], "normal": [0, 0, 0]}], "[0, 0, 0]"),
                        ([{"punto": [0, 0, 0], "normal": [1, 0, 0]}], "¿Quisiste decir «punto_mm»?"),
                        ({"punto_mm": [0, 0, 0]}, "es una lista")):
        with pytest.raises(EscenarioInvalido, match=texto.replace("[", r"\[").replace("?", r"\?")):
            leer_escenario({**esc, "mecanica": {"sumideros": malo}})
