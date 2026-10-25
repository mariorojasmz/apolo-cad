"""La acción `escribir` de la co-simulación (plan plc-en-el-lazo F1c1, D10): una pantalla o un
SCADA escriben una variable del programa del PLC.

  - su forma en el escenario (variable, valor, t > 0) y en vivo;
  - `agenda.validar` (el snapshot) rechaza al DECLARAR una ruta que no existe o no se escribe, un
    valor de otro tipo, un dispositivo que no es un PLC con programa y un PLC externo cuyo conector
    no trae `escribir`;
  - en el lote se aplica con su hora y queda en `eventos`; un PLC sin tensión no la atiende: queda
    como rechazo (sin `accion`: no es ancla) y la corrida sigue;
  - en vivo: ack o rechazo, la grabación la lleva y, vuelta escenario, da la MISMA huella;
  - un puerto de afuera con `escribir` la recibe ya validada (ruta y tipo, por el núcleo);
  - `Compilado.simbolos` no se persiste: ni en el `.apolo` ni en la caché de la SQLite.
"""

from __future__ import annotations

import io
import types
import zipfile

import pytest

from apolo.cosim.agenda import Agenda
from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
from apolo.plc import compilar
from apolo.services.errors import ServiceError
from cosim_lazo_banco import PROGRAMA, PROGRAMAS, escenario_variador, faja_variador

ESCRIBIR = {"accion": "escribir", "dispositivo": "-K1", "variable": "Main.en_marcha", "valor": True}
DUR = 1.5


def _esc(*acciones, duracion=DUR) -> dict:
    return {"duracion_s": duracion, "acciones": list(acciones)}


# ── la forma (sin tablero) ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("accion,texto", [
    ({"t": 0.1, "accion": "escribir", "dispositivo": "-K1", "valor": 1}, "«escribir» pide «variable»"),
    ({"t": 0.1, "accion": "escribir", "dispositivo": "-K1", "variable": "x"}, "«escribir» pide «valor»"),
    ({**ESCRIBIR, "t": 0.1, "valor": "50"}, "true/false o un número finito, llegó '50'"),
    ({**ESCRIBIR, "t": 0.1, "valor": float("nan")}, "un número finito"),
    ({**ESCRIBIR, "t": 0.0}, "«escribir» en t = 0 no llega: el PLC arranca en el primer intercambio"),
    ({**ESCRIBIR, "t": 0.1, "actuador": "marcha"}, "«actuador» es de un mando"),
    ({**ESCRIBIR, "t": 0.1, "durante_s": 0.2}, "«durante_s» es de «pulsar»"),
    ({"t": 0.1, "accion": "pulsar", "dispositivo": "-S1", "variable": "x"}, "«variable» es de «escribir»"),
])
def test_la_forma_de_escribir(accion, texto):
    with pytest.raises(EscenarioInvalido, match=None) as e:
        leer_escenario(_esc(accion))
    assert texto in str(e.value)


def test_la_accion_bien_formada_lleva_su_variable():
    [a] = leer_escenario(_esc({**ESCRIBIR, "t": 0.3, "valor": 1})).acciones
    assert (a.accion, a.dispositivo, a.variable, a.valor) == ("escribir", "-K1", "Main.en_marcha", 1)


# ── un puerto de afuera, sin corrida ─────────────────────────────────────────────────────────

class Puerto:
    """Un PLC de afuera mínimo para la agenda: guarda lo que le escriben."""

    def __init__(self, estado="RUN"):
        self.compilado, self.estado, self.escrito = compilar(PROGRAMA), estado, []

    def escribir(self, ruta, valor):
        self.escrito.append((ruta, valor))


TAB = types.SimpleNamespace(modelos={}, redes_ac=[])


def test_un_puerto_de_afuera_recibe_la_escritura_ya_validada():
    p = Puerto()
    ag = Agenda(leer_escenario(_esc({**ESCRIBIR, "t": 0.1, "variable": "Main.cuenta", "valor": 5.0})), TAB,
                plcs={"-K1": p})
    ag.aplicar(1.0)
    assert p.escrito == [("Main.cuenta", 5)] and type(p.escrito[0][1]) is int  # el tipo, por el núcleo
    assert ag.eventos == [{"t": 1.0, "programado_s": 0.1, "accion": "escribir", "dispositivo": "-K1",
                           "variable": "Main.cuenta", "valor": 5.0}]
    malo = Agenda(leer_escenario(_esc({**ESCRIBIR, "t": 0.1, "valor": 7})), TAB, plcs={"-K1": p})
    with pytest.raises(ValueError, match="es BOOL"):
        malo.aplicar(1.0)
    assert len(p.escrito) == 1  # no le llegó nada inválido


def test_un_puerto_sin_tension_no_la_atiende_y_sin_escribir_se_rechaza():
    p = Puerto(estado="SIN_TENSION")
    ag = Agenda(leer_escenario(_esc({**ESCRIBIR, "t": 0.1})), TAB, plcs={"-K1": p})
    ag.aplicar(1.0)
    assert p.escrito == [] and ag.eventos == [{
        "t": 1.0, "programado_s": 0.1, "rechazo": "escribir", "dispositivo": "-K1", "variable": "Main.en_marcha",
        "valor": True, "motivo": "-K1 está sin tensión: no atiende la escritura de «Main.en_marcha»"}]
    sin = types.SimpleNamespace(compilado=p.compilado, estado="RUN")
    with pytest.raises(ValueError, match="el PLC externo -K1 no admite «escribir»"):
        Agenda(leer_escenario(_esc({**ESCRIBIR, "t": 0.1})), TAB, plcs={"-K1": sin}).aplicar(1.0)
    with pytest.raises(ValueError, match="«-K2» no es un PLC con programa"):
        Agenda(leer_escenario(_esc({**ESCRIBIR, "t": 0.1, "dispositivo": "-K2"})), TAB,
               plcs={"-K1": p}).aplicar(1.0)


# ── con la máquina (snapshot, lote y vivo) ───────────────────────────────────────────────────

pytest.importorskip("mujoco")


@pytest.fixture(scope="module")
def doc():
    return faja_variador()


def _con(*acciones, duracion=DUR) -> dict:
    """La faja por variador con el potenciómetro a fondo y lo que se pida (sin pulsar marcha)."""
    esc = escenario_variador(duracion)
    esc["acciones"] = [esc["acciones"][0], *acciones]
    return esc


@pytest.mark.parametrize("cambio,texto", [
    ({"variable": "Main.en_marca"}, "no existe la variable «Main.en_marca». ¿Quisiste decir «Main.en_marcha»?"),
    ({"variable": "foto"}, "«foto» está en una entrada (%IX0.0)"),
    ({"variable": "vfd_marcha"}, "«vfd_marcha» está en una salida (%QX0.0)"),
    ({"variable": "Main.flanco.Q"}, "es un miembro de una instancia de R_TRIG"),
    ({"variable": "Main.cuenta", "valor": 1.5}, "«Main.cuenta» es INT: se escribe un número entero"),
    ({"dispositivo": "-S1"}, "«-S1» no es un PLC con programa"),
])
def test_validar_rechaza_al_declarar(doc, cambio, texto):
    from apolo.services.cosim_snapshot import snapshot_cosim

    with pytest.raises(ServiceError) as e:
        snapshot_cosim(doc, _con({**ESCRIBIR, "t": 0.3, **cambio}), programas=PROGRAMAS)
    assert e.value.status_code == 400 and texto in str(e.value.detail)


def test_con_un_plc_externo_sin_escribir_se_rechaza_al_declarar(doc, monkeypatch):
    from apolo.cosim import puerto_plc
    from apolo.services.cosim_snapshot import snapshot_cosim
    from ext_prueba.conector_plc import ConectorTCP

    monkeypatch.setitem(puerto_plc.CONECTORES, "prueba.tcp", ConectorTCP)
    externo = {"-K1": {"conector": "prueba.tcp", "config": {"host": "127.0.0.1", "puerto": 9}}}
    with pytest.raises(ServiceError) as e:  # se valida antes de conectar: nadie escucha en el 9
        snapshot_cosim(doc, _con({**ESCRIBIR, "t": 0.3}), programas=PROGRAMAS, plc_externo=externo)
    assert "el PLC externo -K1 no admite «escribir»: su conector no trae escribir(ruta, valor)" in e.value.detail
    snap = snapshot_cosim(doc, _con(), programas=PROGRAMAS, plc_externo=externo)  # sin escribir, pasa
    assert set(snap.externos) == {"-K1"}


@pytest.fixture(scope="module")
def lote(doc):
    from apolo.cosim.planificador import correr
    from apolo.services.cosim_snapshot import snapshot_cosim

    return correr(snapshot_cosim(doc, _con({**ESCRIBIR, "t": 0.3}), programas=PROGRAMAS))


def test_en_el_lote_la_escritura_arranca_la_faja_con_su_hora(lote):
    [e] = [x for x in lote["eventos"] if x.get("accion") == "escribir"]
    assert e == {"t": 0.3, "programado_s": 0.3, **ESCRIBIR}
    assert lote["final"]["-K1.Main.en_marcha"] is True and lote["final"]["-M1.rpm"] > 1000


def test_un_plc_sin_tension_no_la_atiende_y_la_corrida_sigue(doc):
    from apolo.cosim.planificador import correr
    from apolo.services.cosim_snapshot import snapshot_cosim

    esc = {**_con({**ESCRIBIR, "t": 0.1}, duracion=0.3), "condiciones": {"red_conectada": False}}
    res = correr(snapshot_cosim(doc, esc, programas=PROGRAMAS))
    [e] = [x for x in res["eventos"] if x.get("rechazo")]
    assert "accion" not in e and e["motivo"] == "-K1 está sin tensión: no atiende la escritura de «Main.en_marcha»"
    assert res["final"]["-K1.Main.en_marcha"] is False


def test_en_vivo_ack_y_rechazo_y_la_grabacion_da_la_misma_huella(doc, lote):
    from apolo.cosim.planificador import correr
    from apolo.cosim.vivo import Vivo, escenario_grabado, escenario_vivo
    from apolo.services.cosim_snapshot import snapshot_cosim

    base = _con({**ESCRIBIR, "t": 0.3})
    v = Vivo(snapshot_cosim(doc, escenario_vivo(base), programas=PROGRAMAS), trazas=True)
    n = round(DUR / v.dt)
    plan = {0: [{"girar": "-S1", "valor": 1.0, "id": "g"}, {**ESCRIBIR, "id": "temprano"}],
            10: [{**ESCRIBIR, "variable": "Main.nada", "id": "malo"}, {"escribir": "-K1", "variable": "foto",
                                                                        "valor": True, "id": "entrada"}],
            150: [{**ESCRIBIR, "id": "e"}]}
    resp = []
    while v.k < n:
        for msg in plan.get(v.k, []):
            r = v.recibir(msg)
            if r is not None:
                resp.append(r)
        v.avanzar(min([k for k in plan if k > v.k] + [n]) - v.k)
        resp += v.respuestas()
    por_id = {r["id"]: r for r in resp}
    assert por_id["g"]["tipo"] == "ack" and por_id["e"] == {"tipo": "ack", "id": "e", "t": 0.3, "accion": ESCRIBIR}
    assert por_id["temprano"]["tipo"] == "rechazo" and "sin tensión" in por_id["temprano"]["motivo"]
    assert por_id["malo"]["tipo"] == "rechazo" and "no existe la variable «Main.nada»" in por_id["malo"]["motivo"]
    assert por_id["entrada"]["tipo"] == "rechazo" and "está en una entrada" in por_id["entrada"]["motivo"]
    assert v.grabacion == [{"t": 0.0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0},
                           {"t": 0.3, **ESCRIBIR}]
    h = v.cerrar_lote()
    assert h == lote["resumen"]["huella"]
    grabado = escenario_grabado(escenario_vivo(base), v.grabacion, DUR)
    assert correr(snapshot_cosim(doc, grabado, programas=PROGRAMAS))["resumen"]["huella"] == h


def test_simbolos_no_se_persiste(tmp_path, monkeypatch):
    from apolo.doc.geomcache import pack
    from apolo.doc.document import Document
    from apolo.projects import ProjectStore
    from tablero_electrico import arranque_variador_plc

    monkeypatch.delenv("APOLO_GEOM_CACHE", raising=False)
    d = Document("con-programa")
    d.execute("create_box", {"name": "Gabinete", "width": 600, "depth": 200, "height": 800})
    d.execute_many(arranque_variador_plc())
    d.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    assert d.electrico.programas[0].compilado.simbolos  # en memoria, sí
    with zipfile.ZipFile(io.BytesIO(d.to_apolo_bytes())) as z:
        for nombre in z.namelist():
            assert b"simbolos" not in z.read(nombre), nombre
    assert b"simbolos" not in (pack(d) or b"")
    st = ProjectStore(tmp_path / "base.db")
    pid = st.create(d)
    st.load(pid)  # el open frío puebla la caché de geometría
    fila = st.load_geom_cache(pid)
    assert fila is not None and b"simbolos" not in fila[1]
    assert b"simbolos" not in (tmp_path / "base.db").read_bytes()
