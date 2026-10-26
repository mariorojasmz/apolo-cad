"""La corrida de un escenario por la API de extensiones (plan pedidos-de-extensiones-iii, F1):
`preparar_corrida` bajo el lock del llamador, `correr_corrida` fuera, con sus errores propios y el
texto del núcleo; y el banco de la co-simulación cargado por su ruta desde fuera de la suite (D8).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mujoco")

from apolo import extensiones_api  # noqa: E402
from apolo.cosim.planificador import correr  # noqa: E402
from apolo.services import corrida_escenario as C  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from apolo.services.errors import ServiceError  # noqa: E402
from cosim_lazo_banco import PROGRAMAS, escenario_variador, faja_variador  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def doc():
    return faja_variador()


def test_la_extension_la_importa_de_la_superficie():
    for n in ("preparar_corrida", "correr_corrida", "CorridaPreparada", "CorridaError",
              "EscenarioRechazado", "CorridaFallida"):
        assert getattr(extensiones_api, n) is getattr(C, n)
    assert issubclass(C.EscenarioRechazado, C.CorridaError) and issubclass(C.CorridaFallida, C.CorridaError)


def test_un_escenario_que_el_nucleo_no_toma_vuelve_con_su_texto_exacto(doc):
    malo = escenario_variador(0.5, acciones=({"t": 0.1, "accion": "presionar", "dispositivo": "-S9"},))
    with pytest.raises(ServiceError) as nucleo:
        snapshot_cosim(doc, malo)
    with pytest.raises(C.EscenarioRechazado) as e:
        C.preparar_corrida(doc, malo)
    assert e.value.motivo == nucleo.value.detail and e.value.status_code == 400
    with pytest.raises(C.EscenarioRechazado) as e:
        C.preparar_corrida(doc, "no-existe")
    assert e.value.status_code == 404 and "no-existe" in e.value.motivo


def test_la_corrida_da_lo_mismo_que_el_camino_de_la_api(doc):
    """El worker en su proceso devuelve la MISMA huella que el planificador en este proceso."""
    esc = escenario_variador(0.6)
    prep = C.preparar_corrida(doc, esc, programas=PROGRAMAS)
    assert prep.nombre is None and prep.escenario is esc
    res = C.correr_corrida(prep)
    local = correr(snapshot_cosim(doc, esc, programas=PROGRAMAS))
    assert res["resumen"]["huella"] == local["resumen"]["huella"]
    assert {"trazas", "final", "eventos", "hipotesis"} <= set(res)


def test_un_worker_que_falla_es_corrida_fallida(doc, monkeypatch):
    from apolo.cosim import proceso

    def cae(snap, *, timeout_s=None):
        raise proceso.CosimError("el worker de la co-simulación se cayó (código 3)")

    monkeypatch.setattr(proceso, "correr_en_proceso", cae)
    prep = C.preparar_corrida(doc, escenario_variador(0.3), programas=PROGRAMAS)
    with pytest.raises(C.CorridaFallida) as e:
        C.correr_corrida(prep)
    assert e.value.motivo == "el worker de la co-simulación se cayó (código 3)"


def test_el_banco_se_carga_por_su_ruta_sin_tests_en_el_path(tmp_path):
    """Como lo carga una extensión: primero su copia de `tablero_electrico` con otro nombre, después
    el banco, todo por `spec_from_file_location` y sin `tests/` en `sys.path` (D8)."""
    tests = RAIZ / "tests"
    codigo = (
        "import importlib.util, json, sys\n"
        f"T = {str(tests)!r}\n"
        "assert not any(p.rstrip('/\\\\').endswith('tests') for p in sys.path), sys.path\n"
        "def cargar(nombre, archivo):\n"
        "    spec = importlib.util.spec_from_file_location(nombre, T + '/' + archivo)\n"
        "    m = importlib.util.module_from_spec(spec); sys.modules[nombre] = m\n"
        "    spec.loader.exec_module(m); return m\n"
        "te = cargar('_nucleo_tablero_electrico', 'tablero_electrico.py')\n"
        "b = cargar('_nucleo_cosim_lazo_banco', 'cosim_lazo_banco.py')\n"
        "print(json.dumps({'banco': b.arranque_variador_plc is sys.modules['tablero_electrico'].arranque_variador_plc,\n"
        "                  'cmds': len(b.arranque_variador_plc()) == len(te.arranque_variador_plc())}))\n")
    out = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True,
                         timeout=180, cwd=tmp_path)
    assert out.returncode == 0, out.stderr[-2000:]
    assert json.loads(out.stdout.strip().splitlines()[-1]) == {"banco": True, "cmds": True}
