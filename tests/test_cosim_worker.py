"""El worker de la co-simulación y el determinismo (plan V8.3 D9 y D11).

  - dos corridas del mismo escenario sobre el mismo snapshot dan la MISMA huella de trazas (y
    las mismas trazas), bit a bit; otro escenario, otra huella;
  - el worker en proceso aparte (`subprocess.Popen`, BLAS de un hilo) devuelve lo mismo que la
    corrida en proceso, importó el MISMO `apolo` y no cargó OCCT, build123d ni el catálogo;
  - un error en el worker vuelve como texto (`CosimError`), no como un cuelgue;
  - los módulos del bucle (`cosim` raíz y la física sin OCCT) sólo importan lo permitido: el
    gate de AST como el de `test_capas_cosim.py` y un subproceso por módulo.
"""

from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mujoco")

import apolo  # noqa: E402
from apolo.cosim.planificador import correr  # noqa: E402
from apolo.cosim.proceso import CosimError, correr_en_proceso  # noqa: E402
from apolo.cosim.worker import PESADOS  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from cosim_lazo_banco import PROGRAMAS, escenario_variador, faja_variador  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
CORE = RAIZ / "core" / "apolo"
#: Lo que pueden importar de `apolo` los módulos que corren en el worker.
FISICA_PURA = ("physics.dinamica_integrador", "physics.dinamica_arrastre", "physics.dinamica_control",
               "physics.dinamica_datos", "physics.dinamica_flujo", "physics.dinamica_nacimiento",
               "physics.dinamica_serie", "physics.sensores", "physics.sim")
DEL_WORKER = [CORE / "cosim" / n for n in ("acople.py", "agenda.py", "aserciones.py", "corrida.py", "datos.py",
                                           "externo.py", "flujo.py", "puerto_plc.py", "ritmo.py",
                                           "escenario.py", "planificador.py", "proceso.py", "proceso_vivo.py",
                                           "tablero.py", "trazas.py", "vivo.py", "vivo_fotograma.py", "vivo_lazo.py",
                                           "worker.py", "worker_vivo.py", "__init__.py")] + [
    CORE / (m.replace(".", "/") + ".py") for m in FISICA_PURA] + sorted(
    (CORE / "cosim" / "neumatica").glob("*.py"))  # V8.9 F3 (D15): el aire corre en el worker


@pytest.fixture(scope="module")
def snap():
    esc = escenario_variador(2.5, cajas=True, acciones=[{"t": 2.0, "accion": "presionar", "dispositivo": "-S0"}])
    return snapshot_cosim(faja_variador(), esc, programas=PROGRAMAS)


@pytest.fixture(scope="module")
def local(snap):
    return correr(snap)


def _json(res: dict) -> dict:
    return json.loads(json.dumps(res))


def test_dos_corridas_dan_la_misma_huella_bit_a_bit(snap, local):
    otra = correr(snap)
    assert otra["resumen"]["huella"] == local["resumen"]["huella"]
    assert json.dumps(otra["trazas"], sort_keys=True) == json.dumps(local["trazas"], sort_keys=True)
    assert otra["eventos"] == local["eventos"] and otra["final"] == local["final"]
    # hubo de todo: contactos, PLC, variador, banda, cajas y fotocelda
    assert local["final"]["-K1.Main.cuenta"] >= 1 and local["trazas"]["discretas"]["-B1.activo"][1:]
    # otro escenario (la seta medio segundo antes): otra huella
    esc = copy.deepcopy(snap.escenario)
    esc.acciones[-1] = type(esc.acciones[-1])(1.5, "presionar", "-S0")
    distinto = copy.copy(snap)
    distinto.escenario = esc
    assert correr(distinto)["resumen"]["huella"] != local["resumen"]["huella"]


def test_el_worker_en_proceso_aparte_devuelve_lo_mismo(snap, local):
    res = correr_en_proceso(snap, timeout_s=600)
    p = res["proceso"]
    assert Path(p["apolo"]).resolve() == Path(apolo.__file__).resolve()  # en un worktree: el MISMO árbol
    assert p["modulos_pesados"] == [] and p["blas_hilos"] == "1"
    assert p["arranque_s"] > 0 and p["total_s"] >= p["arranque_s"]
    esperado = _json(local)
    assert res["resumen"]["huella"] == esperado["resumen"]["huella"]
    assert res["trazas"] == esperado["trazas"]
    assert res["eventos"] == esperado["eventos"] and res["final"] == esperado["final"]


def test_un_error_del_worker_vuelve_como_texto(snap):
    roto = copy.copy(snap)
    roto.dinamica = copy.copy(snap.dinamica)
    roto.dinamica.xml = "<mujoco><worldbody><body"
    with pytest.raises(CosimError, match="No se pudo construir el mundo dinámico"):
        correr_en_proceso(roto, timeout_s=300)


# ── el worker no carga la geometría ──────────────────────────────────────────────────────────


def _imports(archivo: Path) -> list[tuple[int, str]]:
    paquete = ".".join(archivo.relative_to(RAIZ / "core").with_suffix("").parts[:-1])
    out = []
    for n in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            out += [(n.lineno, a.name) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = paquete.split(".")[: len(paquete.split(".")) - (n.level - 1)]
                out.append((n.lineno, ".".join(base + ([n.module] if n.module else []))))
            else:
                out.append((n.lineno, n.module or ""))
    return out


def _permitido(mod: str) -> bool:
    partes = mod.split(".")
    if partes[0] in ("OCP", "build123d", "vtk", "vtkmodules", "fastapi", "starlette"):
        return False
    if partes[0] != "apolo" or len(partes) == 1:
        return True
    resto = ".".join(partes[1:])
    return partes[1] in ("cosim", "plc") or resto == "physics" or resto in FISICA_PURA


def test_los_modulos_del_bucle_solo_importan_lo_puro():
    errores = [f"{a.relative_to(RAIZ).as_posix()}:{ln}: importa `{mod}`"
               for a in DEL_WORKER for ln, mod in _imports(a) if not _permitido(mod)]
    assert not errores, "el worker no carga OCCT ni el catálogo (V8.3 D11):\n" + "\n".join(errores)


def test_el_gate_caza_un_import_de_la_geometria(tmp_path, monkeypatch):
    malo = tmp_path / "core" / "apolo" / "cosim" / "malo.py"
    malo.parent.mkdir(parents=True)
    malo.write_text("from apolo.physics.banda import ArrastreBanda\nimport build123d\n"
                    "from ..library.catalog import CATALOG\nfrom .tablero import Tablero\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "RAIZ", tmp_path)
    malos = [m for _, m in _imports(malo) if not _permitido(m)]
    assert malos == ["apolo.physics.banda", "build123d", "apolo.library.catalog"]


@pytest.mark.parametrize("modulo", ["apolo.cosim.worker", "apolo.cosim.planificador", "apolo.cosim.proceso",
                                    "apolo.physics.dinamica_integrador", "apolo.cosim.datos",
                                    "apolo.cosim.worker_vivo", "apolo.cosim.proceso_vivo",
                                    "apolo.cosim.neumatica.red", "apolo.cosim.externo"])
def test_cada_modulo_del_worker_se_importa_sin_occt(modulo):
    codigo = ("import sys, importlib\n"
              f"importlib.import_module('{modulo}')\n"
              f"malos = [m for m in sys.modules if any(m == p or m.startswith(p + '.') for p in {PESADOS!r})]\n"
              "assert not malos, malos\n")
    res = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stderr[-2000:]
