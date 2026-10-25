"""Un PLC de AFUERA en el lote (plan plc-en-el-lazo, F1b1: D4–D9 del lote y D15).

  - `RitmoPared` con un reloj falso: espera hasta t₀ + k·Δt (sueño en tajadas y espera activa),
    cuenta los atrasados y perdona una deuda grande (rebase);
  - la cara `PuertoPLC`: `apolo.plc.PLC` la cumple tal cual; `LazoCortado` con su hora;
  - `Extension.conectores_plc`: carga con su origen, `GET /api/extensiones` lo lista y cada
    rechazo deja el registro como estaba (todo o nada);
  - el pedido `plc_externo` de `POST /api/cosim/run`: cada 400 (sin conector cargado, PLC sin
    programa, config inválida, no es un PLC) sale ANTES del worker;
  - de punta a punta con el conector falso de `tests/ext_prueba` y un PLC falso en otro proceso
    (`apolo.plc.PLC` con reloj de pared): `determinista: false`, `lazo` con números medidos por el
    núcleo, sin veredicto y sin resultado guardado; la misma corrida sin externo, sin claves nuevas;
  - matar el PLC falso a mitad del lote da 502 «lazo cortado en t = … s», sin resultado parcial;
  - el módulo del conector no carga su red hasta conectar (D5).
Los PLC falsos se apagan solos al terminar cada test (y si el test muere: cierran con su stdin).
"""

from __future__ import annotations

import copy
import os
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from apolo.cosim import puerto_plc
from apolo.cosim.ritmo import ACTIVA_S, RitmoPared

RAIZ = Path(__file__).resolve().parents[1]
EXTRA = "APOLO_EXTENSIONES_EXTRA"
CLAVES_RES = {"aviso", "avisos", "eventos", "final", "hipotesis", "mecanica", "plc", "resumen", "trazas"}
CLAVES_RESUMEN = {"costo_us_por_intercambio", "duracion_s", "factor_tiempo_real", "huella", "intercambio_s",
                  "intercambios", "resoluciones_potencia", "senales", "t_armado_s", "t_pared_s"}


# ── ritmo de pared (D9) ──────────────────────────────────────────────────────────────────────

class Reloj:
    """Un reloj falso: `dormir` lo adelanta y cada lectura suma `tic` (la espera activa avanza)."""

    def __init__(self, tic: float = 1e-4):
        self.t, self.tic, self.suenos = 100.0, tic, []

    def __call__(self) -> float:
        self.t += self.tic
        return self.t

    def dormir(self, s: float) -> None:
        self.suenos.append(s)
        self.t += s


def test_el_ritmo_espera_hasta_su_hora_con_tajadas_y_espera_activa():
    r = Reloj()
    ritmo = RitmoPared(0.002, reloj=r, dormir=r.dormir)
    assert ritmo.esperar(0) == 0.0 and r.suenos == []  # el primero fija t0
    t0 = ritmo.t0
    for k in range(1, 6):
        assert ritmo.esperar(k) == 0.0
        assert r.t >= t0 + k * 0.002 and r.t - (t0 + k * 0.002) < 2 * r.tic  # ni antes ni tarde
    assert r.suenos and all(s <= 0.002 - ACTIVA_S + 1e-12 for s in r.suenos)  # duerme y termina activo
    # una espera larga duerme en tajadas de 10 ms como mucho
    largo = RitmoPared(0.05, reloj=r, dormir=r.dormir)
    largo.esperar(0)
    r.suenos.clear()
    largo.esperar(1)
    assert len(r.suenos) >= 4 and max(r.suenos) <= 0.010 + 1e-12
    assert ritmo.resumen() == {"intercambios": 6, "atrasados": 0, "atraso_max_ms": 0.0, "rebases": 0}


def test_el_ritmo_cuenta_los_atrasados_y_perdona_una_deuda_grande():
    r = Reloj(tic=1e-6)
    cerca = {"abs": 1e-5}
    ritmo = RitmoPared(0.002, reloj=r, dormir=r.dormir, rebase_s=0.1)
    ritmo.esperar(0)
    t0 = ritmo.t0
    r.t += 0.005  # el intercambio 0 tardó 5 ms: el 1 llega 3 ms tarde
    assert ritmo.esperar(1) == pytest.approx(0.003, **cerca)
    assert ritmo.t0 == t0  # sin rebase: los que siguen se ponen al día sin esperar
    assert ritmo.esperar(2) == pytest.approx(0.001, **cerca) and r.suenos == []
    r.t += 0.5  # una pausa del sistema de medio segundo: se perdona
    assert ritmo.esperar(3) == pytest.approx(0.499, **cerca)
    assert ritmo.rebases == 1 and ritmo.t0 == pytest.approx(r.t - 3 * 0.002, **cerca)
    assert ritmo.esperar(4) == 0.0 and r.t == pytest.approx(ritmo.t0 + 4 * 0.002, **cerca)  # vuelve a esperar
    s = ritmo.resumen()
    assert s["atrasados"] == 3 and s["rebases"] == 1 and s["atraso_max_ms"] == pytest.approx(499.0, abs=0.01)
    with pytest.raises(ValueError):
        RitmoPared(0)


# ── la cara y el corte (D4) ──────────────────────────────────────────────────────────────────

def test_el_plc_virtual_cumple_la_cara_y_el_conector_falso_tambien():
    import pickle

    from apolo.plc import PLC, compilar
    from cosim_lazo_banco import PROGRAMA
    from ext_prueba.conector_plc import ConectorTCP, SinPaso

    assert isinstance(PLC(compilar(PROGRAMA)), puerto_plc.PuertoPLC)
    assert len(puerto_plc.MIEMBROS) == 13 and puerto_plc.problemas_de_clase(ConectorTCP) == []
    assert puerto_plc.problemas_de_clase(SinPaso) == ["no declara «scans»", "no tiene el método «paso»"]
    corte = puerto_plc.LazoCortado("el PLC no contesta", t_s=1.25)
    assert str(corte) == "lazo cortado en t = 1.250 s: el PLC no contesta"
    assert str(pickle.loads(pickle.dumps(corte))) == str(corte)


# ── la extensión: carga, detalle y rechazos (D5) ─────────────────────────────────────────────

@pytest.fixture
def con_prueba(extensiones_aisladas, monkeypatch):
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")
    assert extensiones_aisladas.cargar()[0]["cargada"]
    return extensiones_aisladas


def test_el_conector_entra_con_su_origen_y_la_api_lo_lista(con_prueba):
    from fastapi.testclient import TestClient

    import apolo.api.main as api
    from ext_prueba.conector_plc import ConectorTCP

    assert puerto_plc.CONECTORES == {"prueba.tcp": ConectorTCP}
    assert puerto_plc.DE_EXTENSION == {"prueba.tcp": ("ext-prueba", "0.1.0")}
    (ext,) = TestClient(api.app).get("/api/extensiones").json()
    assert ext["conectores_plc"] == ["prueba.tcp"]


@pytest.mark.parametrize(("extra", "motivo"), [
    ("ext_prueba:CONECTOR_SIN_PREFIJO", "el conector de PLC «tcp» no lleva el prefijo «prueba.»"),
    ("ext_prueba:CONECTOR_INCOMPLETO", "no declara «scans»; no tiene el método «paso»"),
    ("ext_prueba:CONECTOR_SIN_VALIDAR", "no tiene «validar_config(config) -> list[str]»"),
    ("ext_prueba:CONECTOR_OPCIONAL_MALO", "«cerrar» no es llamable"),
    ("ext_prueba:CONECTOR_NO_CLASE", "no es una clase sino str"),
])
def test_un_conector_que_no_cumple_no_carga_la_extension(extensiones_aisladas, monkeypatch, extra, motivo):
    from apolo.cosim.modelos import MODELOS

    monkeypatch.setenv(EXTRA, extra)
    (e,) = extensiones_aisladas.cargar()
    assert e["cargada"] is False and motivo in e["motivo"], e
    # todo o nada: ni el conector ni el modelo (que entra antes) quedaron
    assert puerto_plc.CONECTORES == {} and puerto_plc.DE_EXTENSION == {} and "prueba.lampara" not in MODELOS


def test_un_conector_que_ya_existe_no_carga(extensiones_aisladas, monkeypatch):
    monkeypatch.setitem(puerto_plc.CONECTORES, "prueba.tcp", object)
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")
    (e,) = extensiones_aisladas.cargar()
    assert not e["cargada"] and "el conector de PLC «prueba.tcp» ya existe" in e["motivo"]
    assert puerto_plc.CONECTORES == {"prueba.tcp": object}


def test_el_modulo_del_conector_no_carga_su_red_hasta_conectar(tmp_path):
    codigo = ("import pickle, sys\n"
              "import ext_prueba.conector_plc as c\n"
              "pickle.loads(pickle.dumps(c.ConectorTCP))\n"  # lo que hace el worker con el snapshot
              "assert 'ext_prueba.red_plc' not in sys.modules, 'importó la red al importarse'\n"
              "from types import SimpleNamespace\n"
              "try:\n"
              "    c.ConectorTCP(SimpleNamespace(compilado=None), {'host': '127.0.0.1', 'puerto': 9})\n"
              "except Exception as e:\n"
              "    assert type(e).__name__ == 'LazoCortado', e\n"
              "assert 'ext_prueba.red_plc' in sys.modules\n")
    res = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True, timeout=120,
                         env=_entorno())
    assert res.returncode == 0, res.stderr[-2000:]


# ── el PLC falso en otro proceso ─────────────────────────────────────────────────────────────

def _entorno() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(RAIZ / "core"), str(RAIZ / "tests"), os.environ.get("PYTHONPATH")) if p)
    return env


@contextmanager
def plc_falso(tmp_path, *, avisar: int = 0):
    """El PLC falso escuchando: (proceso, puerto). Se apaga al salir (y solo si el test muere)."""
    from cosim_lazo_banco import PROGRAMA

    fuente = tmp_path / "main.st"
    fuente.write_text(PROGRAMA, encoding="utf-8")
    cmd = [sys.executable, "-B", "-m", "ext_prueba.plc_falso", str(fuente), "--avisar", str(avisar)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=_entorno())
    try:
        linea = proc.stdout.readline()
        assert linea.startswith("PUERTO "), (linea, proc.stderr.read() if proc.poll() is not None else "")
        yield proc, int(linea.split()[1])
    finally:
        for x in (proc.stdin,):
            try:
                x.close()
            except OSError:
                pass
        proc.kill()
        proc.wait(timeout=30)
        proc.stdout.close()
        proc.stderr.close()


def _pedido(puerto: int) -> dict:
    return {"-K1": {"conector": "prueba.tcp", "config": {"host": "127.0.0.1", "puerto": puerto}}}


ESCENARIO = {"duracion_s": 1.2, "mecanica": None, "acoples": None,
             "acciones": [{"t": 0.0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0},
                          {"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha",
                           "durante_s": 0.2}],
             "aserciones": ["-K1.en_marcha al_final"]}


@pytest.fixture(scope="module")
def maquina():
    pytest.importorskip("mujoco")
    from cosim_lazo_banco import FOTO, MECANICA, MOTOR, PROGRAMA, faja_variador

    doc = faja_variador()
    doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    esc = {**ESCENARIO, "mecanica": MECANICA, "acoples": {"motores": MOTOR, "sensores": FOTO}}
    return {"doc": doc, "escenario": esc}


@pytest.fixture
def cliente(maquina, con_prueba, monkeypatch):
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    monkeypatch.setattr(api, "DOC", maquina["doc"])
    monkeypatch.setenv("PYTHONPATH", _entorno()["PYTHONPATH"])  # el worker importa ext_prueba
    c = TestClient(api.app)
    assert c.put("/api/escenarios/marcha", json={"escenario": maquina["escenario"]}).status_code == 200
    return c


def test_cada_pedido_malo_es_400_antes_del_worker(cliente, maquina, monkeypatch):
    from apolo.cosim import proceso

    monkeypatch.setattr(proceso, "correr_en_proceso", lambda *a, **k: pytest.fail("llegó al worker"))

    def run(pedido) -> str:
        r = cliente.post("/api/cosim/run", json={"escenario": "marcha", "plc_externo": pedido})
        assert r.status_code == 400, r.text
        return r.json()["detail"]

    assert "no está cargado; conectores: prueba.tcp" in run({"-K1": {"conector": "prueba.otro", "config": {}}})
    d = run({"-K1": {"conector": "prueba.tcp", "config": {"host": "", "puerto": 0, "x": 1}}})
    assert d.startswith("plc_externo.-K1.config: clave «x» desconocida") and "«puerto» es un entero" in d
    assert "«-Q9» no es un PLC del tablero; PLC: -K1" in run({"-Q9": {"conector": "prueba.tcp"}})
    assert "sin otras claves" in run({"-K1": {"conector": "prueba.tcp", "ip": "1.2.3.4"}})
    assert "`plc_externo` es" in run(["-K1"])
    # un PLC sin programa: la misma faja sin `add_program`
    from cosim_lazo_banco import faja_variador

    import apolo.api.main as api

    monkeypatch.setattr(api, "DOC", faja_variador())
    r = cliente.post("/api/cosim/run", json={"escenario": maquina["escenario"], "plc_externo": _pedido(5)})
    assert r.status_code == 400 and "el PLC no tiene programa" in r.json()["detail"]
    assert 'add_program (plc="-K1")' in r.json()["detail"]


def test_con_el_plc_falso_la_corrida_no_es_determinista_ni_se_guarda(cliente, tmp_path):
    with plc_falso(tmp_path) as (_proc, puerto):
        r = cliente.post("/api/cosim/run", json={"escenario": "marcha", "plc_externo": _pedido(puerto)})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["resumen"]["determinista"] is False
    assert res["veredicto"] is None and res["aserciones"] == [] and "no hay veredicto" in res["veredicto_motivo"]
    assert res["plc_externo"] == {"-K1": {"conector": "prueba.tcp", "extension": "ext-prueba",
                                          "version": "0.1.0"}}
    lazo = res["lazo"]
    assert lazo["intercambios"] == res["resumen"]["intercambios"] + 1
    ida = lazo["ida_y_vuelta"]["-K1"]
    assert ida["n"] > 100 and 0 < ida["mediana_ms"] <= ida["p99_ms"] <= ida["max_ms"]
    assert lazo["atrasados"] >= 0 and lazo["atraso_max_ms"] >= 0
    assert res["resumen"]["factor_tiempo_real"] <= 1.05  # a ritmo de pared, no más rápido
    assert res["guardado"] is False and "no se guarda" in res["aviso_guardado"]
    assert res["avisos"][0].startswith("con un PLC externo la corrida NO es determinista")
    # el PLC de afuera movió la máquina: la marcha enclavó y el motor giró
    fin = cliente.get(f"/api/cosim/simulaciones/{res['simulacion']}",
                      params={"parte": "final", "senales": "-K1.Main.en_marcha,-M1.rpm"}).json()["final"]
    assert fin["-K1.Main.en_marcha"] is True and fin["-M1.rpm"] > 500
    # nada quedó como resultado del escenario
    (fila,) = cliente.get("/api/escenarios").json()["escenarios"]
    assert fila["estado"] == "sin_correr"


def test_sin_externo_el_resultado_no_suma_claves(maquina):
    from apolo.cosim.planificador import correr
    from apolo.services.cosim_snapshot import snapshot_cosim

    snap = snapshot_cosim(maquina["doc"], maquina["escenario"])
    assert snap.externos == {}
    res = correr(snap)
    assert set(res) == CLAVES_RES and set(res["resumen"]) == CLAVES_RESUMEN


def test_un_plc_que_no_contesta_no_arranca_la_corrida(maquina, con_prueba):
    from apolo.cosim.planificador import correr
    from apolo.services.cosim_snapshot import snapshot_cosim

    snap = snapshot_cosim(maquina["doc"], maquina["escenario"])
    snap = copy.copy(snap)
    snap.externos = {"-K1": (puerto_plc.CONECTORES["prueba.tcp"], {"host": "127.0.0.1", "puerto": 9,
                                                                   "timeout_s": 1.0})}
    with pytest.raises(puerto_plc.LazoCortado, match="no se pudo conectar el PLC externo -K1: 127.0.0.1:9 no contesta"):
        correr(snap)


def test_matar_el_plc_a_mitad_del_lote_da_el_error_con_su_hora(cliente, tmp_path):
    with plc_falso(tmp_path, avisar=150) as (proc, puerto):
        def matar():
            if proc.stdout.readline().startswith("PASOS"):
                proc.kill()

        hilo = threading.Thread(target=matar, daemon=True)
        hilo.start()
        r = cliente.post("/api/cosim/run", json={"escenario": "marcha", "plc_externo": _pedido(puerto)})
        hilo.join(timeout=30)
    assert r.status_code == 502, r.text
    m = re.fullmatch(r"lazo cortado en t = (\d+\.\d{3}) s: (.+)", r.json()["detail"])
    assert m, r.json()["detail"]
    assert 0.2 < float(m.group(1)) < 1.2  # a mitad: ~150 pasos de 2 ms, sin resultado parcial
    assert cliente.get("/api/escenarios").json()["escenarios"][0]["estado"] == "sin_correr"
