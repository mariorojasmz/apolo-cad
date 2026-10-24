"""El evento `falla` en la co-simulación (plan cosim-fallas D3–D6): en lote y en vivo, con la
faja del banco (`cosim_lazo_banco`). Cada falla se compara con su gemelo SIN falla (el mismo
escenario sin el evento): la máquina que para con todo sano y la que no para con el aparato malo.

  - de un aparato (contactor soldado o que no cierra, piloto fundido, guardamotor abierto, PLC con
    una salida pegada o detenido, STO con un canal pegado);
  - de la red: un contacto pegado en el MANDO (el NC de la seta) y en la POTENCIA (los polos del
    contactor), un corto que puentea la seta y otro que tumba la fuente;
  - la traza la registra, las aserciones anclan a ella y la huella es determinista;
  - en vivo entra sin hora, `quitar` la repara y la grabación vuelta escenario da la misma huella;
  - lo que no existe se rechaza al declarar o en `agenda.validar` (snapshot), con su pista.
"""

from __future__ import annotations

import pytest

from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
from apolo.cosim.veredicto import evaluar
from apolo.services.errors import ServiceError

pytest.importorskip("mujoco")

from apolo.cosim.planificador import correr  # noqa: E402
from apolo.cosim.vivo import Vivo, escenario_grabado, escenario_vivo  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from cosim_lazo_banco import PROGRAMAS, escenario_directo, escenario_variador, faja_directo, faja_variador  # noqa: E402

SETA_DIRECTO = {"t": 1.2, "accion": "presionar", "dispositivo": "-S0"}
SETA_VARIADOR = {"t": 1.5, "accion": "presionar", "dispositivo": "-S0"}


@pytest.fixture(scope="module")
def directo():
    return faja_directo()


@pytest.fixture(scope="module")
def variador():
    return faja_variador()


def _directo(doc, *eventos, dur=1.8, acciones=(SETA_DIRECTO,), aserciones=()):
    esc = escenario_directo(dur, acciones=acciones, eventos=eventos)
    esc["aserciones"] = list(aserciones)
    return correr(snapshot_cosim(doc, esc))


def _variador(doc, *eventos, dur=2.2, acciones=(SETA_VARIADOR,)):
    return correr(snapshot_cosim(doc, escenario_variador(dur, acciones=acciones, eventos=eventos),
                                 programas=PROGRAMAS))


@pytest.fixture(scope="module")
def sano(directo):
    return _directo(directo)


def _gira(res) -> bool:
    return res["final"]["-M1.I_A"] > 0.5 and res["final"]["-M1.rpm"] > 100


# ── el escenario, puro ───────────────────────────────────────────────────────────────────────


def test_las_tres_formas_de_una_falla_se_leen():
    esc = leer_escenario({"duracion_s": 3, "eventos": [
        {"t": 1, "tipo": "falla", "dispositivo": "-K1", "falla": "soldado", "duracion_s": 0.5},
        {"t": 1, "tipo": "falla", "rama": "-S0:11-12", "falla": "pegado"},
        {"t": 2, "tipo": "falla", "falla": "corto", "a": "-X1:1", "b": "-X1:PE", "R_ohm": 0.5},
        {"t": 2.5, "tipo": "falla", "dispositivo": "-K1", "falla": "soldado", "quitar": True}],
        "aserciones": ["-K1.cerrado dentro_de 0,1 s desde falla -K1", "-K1.cerrado == false dentro_de 0,1 s "
                       "desde falla.fin"]})
    a, b, c, d = esc.eventos
    assert a.datos == {"dispositivo": "-K1", "falla": "soldado"} and a.duracion_s == 0.5
    assert b.datos == {"rama": "-S0:11-12", "falla": "pegado", "valor": True}  # pegado: cerrado
    assert c.datos == {"a": "-X1:1", "b": "-X1:PE", "falla": "corto", "R_ohm": 0.5}
    assert d.datos["quitar"] is True


@pytest.mark.parametrize("malo,texto", [
    ({"tipo": "falla", "falla": "soldado"}, "una sola forma; llegó ninguna"),
    ({"tipo": "falla", "falla": "soldado", "dispositivo": "-K1", "rama": "-K1:13-14"}, "llegó dispositivo, rama"),
    ({"tipo": "falla", "falla": "corto", "a": "-X1:1"}, "«b» es un punto"),
    ({"tipo": "falla", "falla": "corto", "dispositivo": "-K1"}, "un corto es"),
    ({"tipo": "falla", "rama": "-W1", "falla": "pegada"}, "¿Quisiste decir «pegado»?"),
    ({"tipo": "falla", "rama": "-S0:11-12", "falla": "pegado", "valor": "sí"}, "true (cerrado) o false"),
    ({"tipo": "falla", "dispositivo": "-K1", "falla": "soldado", "quitar": True, "duracion_s": 1}, "no lleva «duracion_s»"),
    ({"tipo": "falla", "dispositivo": "-K1", "falla": "soldado", "R_ohm": 1}, "«R_ohm» es del corto"),
    ({"tipo": "falla", "dispositivo": "-K1", "fala": "soldado"}, "¿Quisiste decir «falla»?"),
])
def test_una_falla_mal_escrita_dice_que_corregir(malo, texto):
    with pytest.raises(EscenarioInvalido) as e:
        leer_escenario({"duracion_s": 2, "eventos": [{"t": 1, **malo}]})
    assert texto in str(e.value)


def test_set_scenario_acepta_la_falla_y_tipa_la_averia_al_declarar(directo):
    from apolo.services import escenarios as E

    esc = escenario_directo(1.0, eventos=[{"t": 0.5, "tipo": "falla", "dispositivo": "-Q3", "falla": "soldado"}])
    E.poner(directo, "soldado", {**esc, "aserciones": ["-Q3.averia == soldado dentro_de 0,1 s desde falla -Q3"]})
    assert "soldado" in directo.escenarios
    with pytest.raises(ServiceError) as e:
        E.poner(directo, "malo", {**esc, "aserciones": ["-Q3.averia == true al_final"]})
    assert "«-Q3.averia» es un texto" in e.value.detail
    E.quitar(directo, "soldado")


def test_el_ancla_falla_fin_pide_duracion():
    with pytest.raises(EscenarioInvalido, match="no tiene «falla.fin»"):
        leer_escenario({"duracion_s": 2, "eventos": [{"t": 1, "tipo": "falla", "dispositivo": "-K1",
                                                      "falla": "soldado"}],
                        "aserciones": ["-K1.cerrado dentro_de 1 s desde falla.fin"]})


# ── de un aparato ────────────────────────────────────────────────────────────────────────────


def test_contactor_soldado_la_seta_no_corta_el_motor(directo, sano):
    assert not _gira(sano) and not sano["final"]["-Q3.cerrado"]  # sano: la seta para
    res = _directo(directo, {"t": 0.8, "tipo": "falla", "dispositivo": "-Q3", "falla": "soldado"},
                   aserciones=["-Q3.averia == soldado dentro_de 0,1 s desde falla -Q3",
                               "-M1.rpm > 100 al_final", "-S0.accionado al_final"])
    assert _gira(res) and res["final"]["-Q3.cerrado"] and res["final"]["-Q3.averia"] == "soldado"
    assert [e for e in res["eventos"] if e.get("evento") == "falla"] == [
        {"t": 0.8, "programado_s": 0.8, "evento": "falla", "dispositivo": "-Q3", "falla": "soldado"}]
    esc = leer_escenario({"duracion_s": 2, "eventos": [{"t": 0.8, "tipo": "falla", "dispositivo": "-Q3",
                                                        "falla": "soldado"}],
                          "aserciones": ["-Q3.averia == soldado dentro_de 0,1 s desde falla -Q3"]})
    assert evaluar(esc.aserciones, res)["veredicto"] == "pasa"
    assert "-Q3.averia" not in sano["final"]  # sin falla, la señal ni existe


def test_contactor_que_no_cierra_no_arranca_y_su_bobina_no_consume(directo, sano):
    res = _directo(directo, {"t": 0.0, "tipo": "falla", "dispositivo": "-Q3", "falla": "no_cierra"},
                   acciones=())
    assert not _gira(res) and res["final"]["-Q3.I_bobina_A"] == 0.0
    assert res["final"]["-T1.I_A"] < 0.05  # la bobina cortada no carga la fuente


def test_piloto_fundido_con_la_maquina_en_marcha(directo):
    sano = _directo(directo, acciones=())
    res = _directo(directo, {"t": 0.0, "tipo": "falla", "dispositivo": "-P1", "falla": "fundido"}, acciones=())
    assert sano["final"]["-P1.encendido"] and _gira(res) and not res["final"]["-P1.encendido"]


def test_guardamotor_abierto_solo_para_el_motor_y_con_duracion_queda_disparado(directo):
    res = _directo(directo, {"t": 0.9, "tipo": "falla", "dispositivo": "-Q2", "falla": "abierto",
                             "duracion_s": 0.3}, acciones=())
    assert not _gira(res) and res["final"]["-Q2.disparado"] and res["final"]["-Q2.averia"] == ""
    assert [e["evento"] for e in res["eventos"] if "evento" in e] == ["falla", "falla.fin"]


# ── de la red: contacto pegado (mando y potencia), corto ─────────────────────────────────────


def test_el_nc_de_la_seta_pegado_en_el_mando(directo, sano):
    res = _directo(directo, {"t": 0.5, "tipo": "falla", "rama": "-S0:11-12", "falla": "pegado", "valor": True})
    assert _gira(res) and res["final"]["-S0.accionado"]  # la seta apretada y su NC sigue cerrado
    assert not _gira(sano)


def test_los_polos_del_contactor_pegados_en_la_potencia(directo):
    polos = [{"t": 0.8, "tipo": "falla", "rama": f"-Q3:{a}-{a + 1}", "falla": "pegado"} for a in (1, 3, 5)]
    res = _directo(directo, *polos)
    assert _gira(res) and not res["final"]["-Q3.cerrado"]  # la bobina soltó y los polos no
    abierto = {"t": 0.0, "tipo": "falla", "rama": "-Q3:5-6", "falla": "pegado", "valor": False}
    res = _directo(directo, abierto, acciones=())
    assert res["final"]["-Q3.cerrado"] and res["final"]["-M1.rpm"] < 100  # en dos fases no arranca


def test_un_corto_que_puentea_la_seta_y_otro_que_tumba_la_fuente(directo):
    puente = {"t": 0.5, "tipo": "falla", "falla": "corto", "a": "-S0:11", "b": "-S0:12"}
    assert _gira(_directo(directo, puente))
    corto = {"t": 0.8, "tipo": "falla", "falla": "corto", "a": "-T1:L+", "b": "-T1:M", "duracion_s": 0.4}
    res = _directo(directo, corto, acciones=(), dur=1.6)
    assert not _gira(res) and "-T1.limitando" in res["trazas"]["discretas"]
    assert any(v for _, v in res["trazas"]["discretas"]["-T1.limitando"])


def test_un_corto_entre_fases_en_la_potencia_dispara_el_magnetico(directo):
    corto = {"t": 0.8, "tipo": "falla", "falla": "corto", "a": "-Q3:2", "b": "-Q3:4"}
    res = _directo(directo, corto, acciones=(), dur=1.0)
    assert res["final"]["-Q2.disparado"] and res["final"]["-Q2.causa"] == "magnético"
    assert not _gira(res)


# ── PLC y STO (la faja por variador) ─────────────────────────────────────────────────────────


def test_salida_del_plc_pegada_la_seta_igual_corta_por_el_sto(variador):
    pegada = {"t": 1.0, "tipo": "falla", "dispositivo": "-K1", "falla": "salida_pegada",
              "valor": {"borne": "Q0.0", "valor": True}}
    res = _variador(variador, pegada)
    f = res["final"]
    assert f["-K1.%QX0.0"] and f["-T2.sto"] and not f["-T2.par_habilitado"]  # el STO salva
    canales = [{"t": 1.0, "tipo": "falla", "dispositivo": "-T2", "falla": "canal_sto_pegado", "valor": c}
               for c in ("S1", "S2")]
    res = _variador(variador, pegada, *canales)
    assert res["final"]["-T2.par_habilitado"] and res["final"]["-M1.rpm"] > 100  # con los dos, no
    assert any("discrepancia" in h for h in res["hipotesis"])
    uno = _variador(variador, canales[0])
    assert uno["final"]["-T2.sto"]  # con un canal pegado, el otro corta


def test_plc_detenido_y_reparado_vuelve_a_run(variador):
    res = _variador(variador, {"t": 1.0, "tipo": "falla", "dispositivo": "-K1", "falla": "detenido",
                               "duracion_s": 0.4}, acciones=())
    estados = [v for _, v in res["trazas"]["discretas"]["-K1.estado"]]
    assert "STOP" in estados and estados[-1] == "RUN"
    assert res["final"]["-M1.rpm"] < 100  # la marcha se perdió con la CPU detenida


# ── determinismo y lo que no existe ──────────────────────────────────────────────────────────


def test_la_misma_falla_da_la_misma_huella(directo):
    ev = {"t": 0.8, "tipo": "falla", "dispositivo": "-Q3", "falla": "soldado"}
    a, b = _directo(directo, ev), _directo(directo, ev)
    assert a["resumen"]["huella"] == b["resumen"]["huella"]
    otra = _directo(directo, {**ev, "t": 0.9})
    assert otra["resumen"]["huella"] != a["resumen"]["huella"]


@pytest.mark.parametrize("ev,texto", [
    ({"dispositivo": "-Q4", "falla": "soldado"}, "¿Quisiste decir «-Q3»?"),
    ({"dispositivo": "-Q3", "falla": "trabado"}, "fallas: soldado, no_cierra"),
    ({"dispositivo": "-K1", "falla": "soldado"}, "no tiene el dispositivo «-K1»"),
    ({"rama": "-S0:11-13", "falla": "pegado"}, "¿Quisiste decir «-S0:11-12»?"),
    ({"falla": "corto", "a": "-S0:11", "b": "-Q3:1"}, "redes distintas"),
    ({"falla": "corto", "a": "-S0:11", "b": "-S0:99"}, "«-S0:99» no es un punto"),
])
def test_lo_que_no_existe_se_rechaza_en_el_snapshot(directo, ev, texto):
    esc = escenario_directo(1.0, eventos=[{"t": 0.5, "tipo": "falla", **ev}])
    with pytest.raises(ServiceError) as e:
        snapshot_cosim(directo, esc)
    assert e.value.status_code == 400 and texto in e.value.detail


# ── en vivo ──────────────────────────────────────────────────────────────────────────────────

DUR = 2.0
PEGAR = {"tipo": "falla", "dispositivo": "-K1", "falla": "salida_pegada", "valor": {"borne": "Q0.1", "valor": True}}


@pytest.fixture(scope="module")
def snap_vivo(variador):
    return snapshot_cosim(variador, escenario_vivo(escenario_variador(DUR)), programas=PROGRAMAS)


def test_en_vivo_la_falla_entra_sin_hora_se_quita_y_la_grabacion_da_la_misma_huella(variador, snap_vivo):
    v = Vivo(snap_vivo, trazas=True)
    plan = {0: [{"girar": "-S1", "valor": 1.0}], 200: [{"evento": PEGAR, "id": "f"}],
            500: [{"evento": {**PEGAR, "quitar": True}, "id": "q"}],
            600: [{"evento": {"tipo": "falla", "dispositivo": "-K1", "falla": "soldado"}, "id": "x"}]}
    resp = []
    n = round(DUR / v.dt)
    while v.k < n:
        for msg in plan.get(v.k, []):
            r = v.recibir(msg)
            if r is not None:
                resp.append(r)
        prox = min([k for k in plan if k > v.k] + [n])
        v.avanzar(prox - v.k)
        resp += v.respuestas()
        if v.k == 400:
            assert v.c.tab.modelos["-K1"].salida["Q0.1"]  # pegada a mitad de la sesión
    por_id = {r["id"]: r for r in resp if r.get("id")}
    assert por_id["f"]["tipo"] == "ack" and por_id["f"]["t"] == 0.4 and por_id["q"]["tipo"] == "ack"
    assert por_id["x"]["tipo"] == "rechazo" and "fallas: entrada_pegada, salida_pegada, detenido" in por_id["x"]["motivo"]
    assert v.c.tab.modelos["-K1"].averia == "" and not v.c.tab.modelos["-K1"].salidas_pegadas
    assert [g.get("quitar") for g in v.grabacion if g.get("tipo") == "falla"] == [None, True]
    h = v.cerrar_lote()
    grabado = escenario_grabado(escenario_vivo(escenario_variador(DUR)), v.grabacion, DUR)
    assert correr(snapshot_cosim(variador, grabado, programas=PROGRAMAS))["resumen"]["huella"] == h


def test_la_tabla_del_inicio_ofrece_las_fallas_y_las_ramas(snap_vivo):
    tabla = Vivo(snap_vivo).fot.tabla()
    fallas = {f["designacion"]: f for f in tabla["fallas"]}
    assert "-M1" not in fallas and "-G1" not in fallas  # motor y red: ninguna nueva (D2)
    plc = {x["falla"]: x for x in fallas["-K1"]["fallas"]}
    assert plc["salida_pegada"]["pide"] == "borne,valor" and "Q0.0" in plc["salida_pegada"]["opciones"]
    assert {x["falla"]: x.get("opciones") for x in fallas["-T2"]["fallas"]}["canal_sto_pegado"] == ["S1", "S2"]
    assert [x["falla"] for x in fallas["-S0"]["fallas"]] == ["trabado"]
    ramas = {r["id"]: r for r in tabla["ramas"]}
    assert ramas["-S0:11-12"] == {"id": "-S0:11-12", "tipo": "contacto", "red": "mando", "dispositivo": "-S0"}
    assert {r["tipo"] for r in tabla["ramas"]} == {"contacto"}  # sin largo, los hilos son uniones ideales


def test_un_cable_con_largo_es_una_rama_que_se_puede_cortar(directo):
    from apolo.cosim.fallas import catalogo
    from apolo.cosim.tablero import Tablero

    snap = snapshot_cosim(directo, escenario_directo(1.0))
    ramas = {r["id"]: r for r in catalogo(Tablero(snap.red, snap.dispositivos))["ramas"]}
    assert ramas["-W1.1"] == {"id": "-W1.1", "tipo": "conductor", "red": "potencia"}
    res = _directo(directo, {"t": 0.8, "tipo": "falla", "rama": "-W1", "falla": "abierto"}, acciones=(), dur=1.2)
    assert res["final"]["-M1.I_A"] == 0.0  # = el cable_cortado
