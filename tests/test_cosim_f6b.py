"""La re-verificación F6b por MCP (plan V8.3 § Bitácora «F6b», defectos 1–3), sin MuJoCo salvo
donde se dice:

  1. la vigencia de un resultado incluye la versión del motor (`COSIM_EPOCH`) y las fichas
     eléctricas del tablero: un resultado de otra versión, sin versión (anterior a F6b) o con un
     YAML cambiado queda «vencido» → AMARILLO en la puerta;
  2. la forma sin comparación sigue el tipo de la señal (booleana = true, texto = no vacío,
     numérica = error) y `set_scenario` revisa los tipos AL DECLARAR (error) y las señales que el
     tablero no da (aviso); el snapshot también, antes de simular;
  3. una banda quieta se rechaza ANTES de preparar la dinámica (la previsión de `prever`), y las
     hipótesis repetidas viajan por id.
"""

from __future__ import annotations

import dataclasses

import pytest
from tablero_electrico import arranque_variador_plc

from apolo.cosim.aserciones import concretar, leer_asercion
from apolo.cosim.consulta import compacto, hipotesis_id, parte
from apolo.cosim.tipos import revisar, valores_iniciales
from apolo.doc.document import Document
from apolo.services import escenarios as E
from apolo.services.electrico import modelo
from apolo.services.errors import ServiceError

ESC = {
    "duracion_s": 3,
    "acciones": [{"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2}],
    "eventos": [{"t": 1, "tipo": "atasco", "junta": "c1_eje_motriz", "par_Nm": 900}],
    "acoples": {"motores": {"-M1": {"junta": "c1_eje_motriz"}}},
    "aserciones": ["-M1.rpm >= 1700 dentro_de 2 s desde pulsar -S1", "-T2.falla dentro_de 1 s desde atasco"],
}


VFD = {"acel_s": 1.0, "decel_s": 1.0}


@pytest.fixture(scope="module")
def doc() -> Document:
    d = Document("f6b")
    d.execute_many(arranque_variador_plc(ajustes_variador=VFD))
    return d


def _eventos():
    from apolo.cosim.escenario import leer_escenario

    return leer_escenario({"duracion_s": 3, "eventos": ESC["eventos"]}).eventos


def _con(**cambios) -> dict:
    return {**ESC, **cambios}


def _guardar(doc, nombre="marcha", **extra):
    ver = {"veredicto": "pasa", "aserciones": [{"asercion": "x", "pasa": True, "detalle": ""}], "n_fallidas": 0}
    comp = E.resultado_compacto(ver, {"resumen": {}}, firma=E.firma_documento(doc),
                                hash_esc=E.hash_escenario(doc.escenarios[nombre]["escenario"]), simulacion="s1")
    comp.update(extra)
    if "sin_epoch" in extra:
        del comp["cosim_epoch"], comp["sin_epoch"]
    assert E.guardar_resultado(doc, nombre, comp)


# ── 1. la vigencia incluye la versión del motor ─────────────────────────────────────────────


def test_un_resultado_de_otra_version_del_motor_vence(doc, monkeypatch):
    import apolo.cosim as cosim

    E.poner(doc, "marcha", ESC)
    _guardar(doc)
    assert E.estado(doc, "marcha")["estado"] == "pasa"
    assert doc.escenarios["marcha"]["resultado"]["cosim_epoch"] == cosim.COSIM_EPOCH
    monkeypatch.setattr(cosim, "COSIM_EPOCH", cosim.COSIM_EPOCH + 1)
    st = E.estado(doc, "marcha")
    assert st["estado"] == "vencido" and st["ultimo"] == "pasa"
    assert st["motivo"] == (f"el motor de la co-simulación cambió (versión {cosim.COSIM_EPOCH - 1} → "
                            f"{cosim.COSIM_EPOCH}) desde que se corrió")
    [fila] = [f for f in E.reglas_escenarios(doc) if f["escenario"] == "marcha"]
    assert fila["estado"] == "aviso" and "motor de la co-simulación cambió" in fila["detalle"]


def test_un_resultado_anterior_a_la_version_es_de_la_version_1(doc):
    """Los resultados guardados antes de F6b no traen `cosim_epoch`: son de la versión 1."""
    E.poner(doc, "viejo", ESC)
    _guardar(doc, "viejo", sin_epoch=True)
    st = E.estado(doc, "viejo")
    assert st["estado"] == "vencido" and "(versión 1 → " in st["motivo"]


def test_una_ficha_del_catalogo_cambiada_vence_aunque_el_log_sea_el_mismo(monkeypatch):
    d = Document("ficha")
    d.execute_many(arranque_variador_plc(ajustes_variador=VFD))
    E.poner(d, "marcha", ESC)
    _guardar(d)
    m = modelo(d)
    otro = [dataclasses.replace(x, modelo={**x.modelo, "In_A": 99.0}) if x.designacion == "-T2" else x
            for x in m.dispositivos]
    monkeypatch.setattr(d, "electrico", dataclasses.replace(m, dispositivos=tuple(otro)))
    st = E.estado(d, "marcha")
    assert st == {"estado": "vencido", "motivo": "la máquina cambió desde que se corrió", "ultimo": "pasa"}


# ── 2. la forma sin comparación y los tipos al declarar ─────────────────────────────────────


def test_la_forma_sin_comparacion_se_marca_y_su_texto_no_inventa_el_true():
    ev = _eventos()
    a = leer_asercion("-T2.falla dentro_de 1 s desde atasco", 0, 3, [], ev)
    b = leer_asercion({"senal": "-T2.falla", "ventana": "dentro_de", "delta_s": 1, "desde": "atasco"}, 0, 3, [], ev)
    assert a == b and a["implicita"] and a["texto"] == "-T2.falla dentro_de 1 s desde atasco"
    explicita = leer_asercion("-T2.rele_falla == true al_final", 0, 3)
    assert "implicita" not in explicita and explicita["texto"] == "-T2.rele_falla == true al_final"
    assert concretar(a, "texto") == ({**a, "op": "!=", "valor": ""}, None)
    assert concretar(a, "bool") == (a, None) and concretar(a, None) == (a, None)
    _, error = concretar(a, "numero")
    assert "es numérica" in error and "«-T2.falla > 0 dentro_de 1 s desde atasco»" in error


def test_la_tabla_de_tipos_sale_sin_simular(doc):
    me = modelo(doc)
    v = valores_iniciales(me.dispositivos, me.programas)
    assert v["-T2.falla"] == "" and v["-T2.estado"] == "parado" and v["-T2.rele_falla"] is False
    assert v["-M1.rpm"] == 0.0 and v["-K1.%QX0.0"] is False and v["-S0.accionado"] is False
    assert not any(k.startswith(("-W1", "-X0", "-U1")) for k in v)  # pasivos: sin modelo


@pytest.mark.parametrize("asercion,error", [
    ("-T2.falla == true dentro_de 1 s desde atasco", "comparación de tipos: «-T2.falla» es un texto"),
    ("-T2.estado dentro_de 1 s desde atasco", "en reposo ya vale «parado»"),
    ("-M1.rpm dentro_de 1 s desde atasco", "«-M1.rpm» es numérica"),
    ("-T2.rele_falla == sobrecorriente al_final", "«-T2.rele_falla == true»"),
    ("-M1.rpm == true al_final", "«-M1.rpm > 0»"),
])
def test_set_scenario_rechaza_al_declarar_un_tipo_que_no_casa(doc, asercion, error):
    with pytest.raises(ServiceError) as e:
        E.poner(doc, "malo", _con(aserciones=[asercion]))
    assert e.value.status_code == 400 and e.value.detail.startswith("aserciones: «")
    assert error in e.value.detail
    assert "malo" not in doc.escenarios


def test_set_scenario_acepta_las_bien_tipadas_y_avisa_la_senal_que_no_existe(doc):
    out = E.poner(doc, "bien", _con(aserciones=[
        "-T2.falla dentro_de 1 s desde atasco", "-T2.falla == sobrecorriente dentro_de 1 s desde atasco",
        '-T2.falla != "" al_final', "-T2.rele_falla dentro_de 1 s desde atasco", "-Q1.cerrado == 1 al_final",
        "-M1.rpm > 0 al_final", "c1_banda.v_m_s >= 0,3 al_final", "-W1.1.I_A < 10 siempre"]))
    assert out["avisos"] == []
    out = E.poner(doc, "typo", _con(aserciones=["-T2.fallo == sobrecorriente al_final"]))
    [aviso] = out["avisos"]
    assert aviso.startswith("«-T2.fallo == sobrecorriente al_final»: la señal «-T2.fallo» no está entre "
                            "las que da el tablero.") and "¿Quisiste decir «-T2.falla»" in aviso


def test_revisar_es_puro_sobre_la_tabla():
    """El alias de PROGRAM («-K1.cuenta» → «-K1.Main.cuenta») vale igual que en el veredicto."""
    tabla = {"-K1.Main.cuenta": 0, "-K1.estado": "SIN_TENSION", "-K1.Main.en_marcha": False}
    bien = [leer_asercion(t, 0, 3) for t in ("-K1.cuenta == 10 al_final", "-K1.en_marcha == 1 al_final",
                                              "-K1.estado == RUN al_final", "-K1.Main.en_marcha al_final")]
    assert revisar(bien, tabla) == ([], [])
    errores, avisos = revisar([leer_asercion("-K1.cuenta == RUN al_final", 0, 3)], tabla)
    assert avisos == [] and "«-K1.Main.cuenta» es numérica" in errores[0]


def test_el_snapshot_revisa_los_tipos_antes_de_preparar_la_dinamica(doc, monkeypatch):
    from apolo.services.cosim_snapshot import snapshot_cosim

    def no_llega(*a, **k):
        raise AssertionError("preparó la dinámica antes de revisar las aserciones")

    monkeypatch.setattr("apolo.physics.dinamica.prepare_dynamics", no_llega)
    with pytest.raises(ServiceError) as e:
        snapshot_cosim(doc, _con(aserciones=["-T2.falla == true dentro_de 1 s desde atasco"]))
    assert e.value.status_code == 400 and "comparación de tipos" in e.value.detail


# ── 3. hipótesis por id ─────────────────────────────────────────────────────────────────────


def test_las_hipotesis_repetidas_viajan_por_id_y_el_resumen_las_da_completas():
    res = {"hipotesis": ["-M1: i = 30, del nombre de c682", "-F1: punto medio"], "resumen": {}}
    ver = {"veredicto": "pasa", "n_fallidas": 0, "aserciones": []}
    hid = hipotesis_id(res["hipotesis"])
    primera = compacto(res, ver, simulacion="s1", escenario="marcha")
    assert primera["hipotesis"] == res["hipotesis"] and primera["hipotesis_id"] == hid
    otra = compacto(res, ver, simulacion="s2", escenario="seta", hipotesis_vistas_en="s1")
    assert "hipotesis" not in otra and otra["hipotesis_id"] == hid
    assert otra["hipotesis_repetidas"]["n"] == 2 and otra["hipotesis_repetidas"]["como_en"] == "s1"
    resumen = parte(res, otra, "resumen")
    assert resumen["hipotesis"] == res["hipotesis"] and "hipotesis_repetidas" not in resumen
    assert hipotesis_id(list(reversed(res["hipotesis"]))) != hid


def test_la_api_compacta_las_hipotesis_de_la_segunda_corrida(monkeypatch):
    """`_correr` con el worker de mentira: la segunda corrida del proyecto con las mismas
    hipótesis las manda por id."""
    import apolo.api.main as api
    from apolo.api.routers import cosim as R

    d = Document("hip")
    d.execute_many(arranque_variador_plc(ajustes_variador=VFD))
    monkeypatch.setattr(api, "DOC", d)
    monkeypatch.setattr(R, "SIMULACIONES", R.Simulaciones())
    snap = type("Snap", (), {"escenario": type("E", (), {"aserciones": []})()})()
    monkeypatch.setattr("apolo.services.cosim_snapshot.snapshot_cosim", lambda *a, **k: snap)
    monkeypatch.setattr("apolo.cosim.proceso.correr_en_proceso",
                        lambda s: {"hipotesis": ["h1", "h2", "h3"], "resumen": {"duracion_s": 1.0}})
    a = R._correr(ESC, guardar=False)
    b = R._correr(ESC, guardar=False)
    assert a["hipotesis"] == ["h1", "h2", "h3"] and "hipotesis" not in b
    assert b["hipotesis_repetidas"]["como_en"] == a["simulacion"]
