"""El worker caliente del sandbox de scripts (plan sandbox-caliente, F1).

Cada test usa scripts ÚNICOS (`_unico`) para que la caché no los responda: lo que se prueba
es el worker. Los que dependen del tiempo llevan márgenes amplios (otra suite puede estar
corriendo en la misma máquina).
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

import apolo
import apolo.sandbox as sb
from apolo.sandbox import ScriptError, run_script_to_shape


def _unico(cuerpo: str = "result = Box(1, 2, 3)") -> str:
    return f"# {uuid.uuid4().hex}\n{cuerpo}"


def _pid() -> int:
    info = sb.worker_info()
    assert info is not None, "no hay worker vivo"
    return info["pid"]


def _worker_nuevo() -> None:
    with sb.SANDBOX_LOCK:
        sb._retirar()


# ── un worker, muchos scripts ─────────────────────────────────────────────────

def test_dos_scripts_seguidos_los_atiende_el_mismo_worker():
    run_script_to_shape(_unico())
    pid = _pid()
    forma = run_script_to_shape(_unico("result = Cylinder(2, 5)"))
    assert forma.volume > 0
    assert _pid() == pid


def test_el_worker_importa_el_mismo_apolo_y_nada_del_kernel():
    run_script_to_shape(_unico())
    info = sb.worker_info()
    # en un worktree, sin PYTHONPATH el hijo probaría OTRO árbol (CLAUDE.md raíz)
    assert Path(info["apolo"]).resolve() == Path(apolo.__file__).resolve()
    prohibidos = ("apolo.kernel", "apolo.doc", "apolo.commands", "apolo.state")
    cargados = [m for m in info["modulos"] if any(m == p or m.startswith(p + ".") for p in prohibidos)]
    assert cargados == []


def test_cada_script_tiene_un_namespace_fresco():
    run_script_to_shape(_unico("contaminado = 1\nresult = Box(1, 1, 1)"))
    with pytest.raises(ScriptError, match="contaminado"):
        run_script_to_shape(_unico("result = Box(1, 1, contaminado)"))


def test_print_y_el_fd_1_no_rompen_el_protocolo():
    codigo = (
        "import os\n"
        "print('hola')\n"
        "os.write(1, b'directo al fd 1, como OCCT\\n')\n"
        "for _ in range(64):\n"
        "    print('x' * 8192)\n"  # 512 KB: sin el hilo que drena stderr, el pipe se traba
        "result = Box(1, 2, 3)\n"
    )
    forma = run_script_to_shape(_unico(codigo))
    assert forma.volume == pytest.approx(6)


# ── fallos: el worker se recicla y el siguiente script funciona ───────────────

def test_un_error_del_script_recicla_el_worker():
    run_script_to_shape(_unico())
    pid = _pid()
    with pytest.raises(ScriptError, match="falló"):
        run_script_to_shape(_unico("result = Box(1, 1, no_existe)"))
    assert sb.worker_info() is None
    run_script_to_shape(_unico())
    assert _pid() != pid


def test_timeout_mata_el_worker_y_el_arranque_no_cuenta(monkeypatch):
    run_script_to_shape(_unico())
    pid = _pid()
    monkeypatch.setattr(sb, "SCRIPT_TIMEOUT_S", 3)
    t0 = time.monotonic()
    with pytest.raises(ScriptError, match="superó el límite de 3s"):
        run_script_to_shape(_unico("while True:\n    pass"))
    assert time.monotonic() - t0 < 60
    # el worker nuevo tarda más de 3 s en importar build123d: eso no rechaza el script
    forma = run_script_to_shape(_unico())
    assert forma.volume == pytest.approx(6)
    assert _pid() != pid


def test_un_crash_da_el_codigo_de_salida_y_el_siguiente_funciona():
    run_script_to_shape(_unico())
    with pytest.raises(ScriptError, match="código de salida 3"):
        run_script_to_shape(_unico("import os\nos._exit(3)"))
    assert run_script_to_shape(_unico()).volume == pytest.approx(6)


def test_se_recicla_cada_worker_max_scripts(monkeypatch):
    _worker_nuevo()
    monkeypatch.setattr(sb, "WORKER_MAX_SCRIPTS", 2)
    run_script_to_shape(_unico())
    pid = _pid()
    run_script_to_shape(_unico())
    assert sb.worker_info() is None  # el 2.º lo jubiló
    run_script_to_shape(_unico())
    assert _pid() != pid


def test_cerrar_su_stdin_hace_salir_al_worker():
    run_script_to_shape(_unico())
    with sb.SANDBOX_LOCK:
        proc = sb._worker.proc
        t0 = time.monotonic()
        proc.stdin.close()
        proc.wait(timeout=10)
        assert time.monotonic() - t0 < 10
    assert run_script_to_shape(_unico()).volume == pytest.approx(6)


def test_si_muere_el_padre_el_worker_no_queda_huerfano():
    psutil = pytest.importorskip("psutil")
    padre = subprocess.Popen(
        [sys.executable, "-c",
         "import time, apolo.sandbox as sb\n"
         "sb.run_script_to_shape('result = Box(1, 1, 1)')\n"
         "print(sb.worker_info()['pid'], flush=True)\n"
         "time.sleep(600)\n"],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        pid = int(padre.stdout.readline())
        assert psutil.pid_exists(pid)
    finally:
        padre.kill()
        padre.wait(timeout=30)
    limite = time.monotonic() + 20
    while psutil.pid_exists(pid) and time.monotonic() < limite:
        time.sleep(0.2)
    assert not psutil.pid_exists(pid)


# ── la vuelta: BRep con el mismo resultado que el STEP de antes ───────────────

MUESTRA = {
    "caja": "result = Box(10, 20, 30)",
    "lista_de_dos_cajas": "result = [Box(10, 10, 10), Pos(50, 0, 0) * Box(10, 10, 10)]",
    "compound_de_una_caja": "result = Compound([Pos(5, 5, 5) * Box(4, 4, 4)])",
    # con ubicación PROPIA el STEP la escribe como instancia de ensamblaje → Compound
    "caja_ubicada": "result = Pos(5, 0, 0) * Box(1, 1, 1)",
    "compound_ubicado": "result = Rot(0, 0, 30) * Compound([Box(4, 4, 4)])",
    "caja_menos_cilindro_movida": "result = Pos(5, 0, 0) * (Box(10, 10, 10) - Cylinder(2, 10))",
    "compound_anidado": "result = Compound([Pos(3, 0, 0) * Compound([Box(4, 4, 4)])])",
    "buildpart": (
        "with BuildPart() as p:\n"
        "    Box(30, 20, 10)\n"
        "    Cylinder(4, 10, mode=Mode.SUBTRACT)\n"
        "    Pos(0, 0, 5) * Sphere(3)\n"
        "result = p.part\n"
    ),
}


@pytest.mark.parametrize("nombre", list(MUESTRA))
def test_brep_equivale_a_step(nombre, monkeypatch):
    brep = run_script_to_shape(_unico(MUESTRA[nombre]))
    monkeypatch.setattr(sb, "_FORZAR_STEP", True)
    codigo_step = _unico(MUESTRA[nombre])
    step = run_script_to_shape(codigo_step)
    assert sb._cache[sb._cache_key(codigo_step, {})][0] == b"S"  # sí vino por el respaldo

    assert type(brep).__name__ == type(step).__name__
    assert len(brep.solids()) == len(step.solids())
    assert len(brep.faces()) == len(step.faces())
    assert brep.volume == pytest.approx(step.volume, rel=1e-9)
    b1, b2 = brep.bounding_box(), step.bounding_box()
    for a, b in ((b1.min, b2.min), (b1.max, b2.max)):
        assert (a.X, a.Y, a.Z) == pytest.approx((b.X, b.Y, b.Z), abs=1e-6)


def test_un_compound_de_un_solido_vuelve_como_solid():
    forma = run_script_to_shape(_unico(MUESTRA["compound_de_una_caja"]))
    assert type(forma).__name__ == "Solid"


# ── la caché ──────────────────────────────────────────────────────────────────

def test_la_cache_ya_no_se_limita_a_32_entradas(monkeypatch):
    ejecutados: list[str] = []
    real = sb._ejecutar
    monkeypatch.setattr(sb, "_ejecutar", lambda code, v: ejecutados.append(code) or real(code, v))
    codigos = [_unico(f"result = Box(1, 1, {i + 1})") for i in range(40)]
    for codigo in codigos:
        run_script_to_shape(codigo)
    assert len(ejecutados) == 40
    for codigo in codigos:  # un replay de 40 (el 38 tiene 48) acierta todos
        run_script_to_shape(codigo)
    assert len(ejecutados) == 40


def test_el_tope_en_bytes_desaloja_al_mas_viejo(monkeypatch):
    sb.clear_cache()
    viejo = _unico()
    run_script_to_shape(viejo)
    uno = sb.cache_info()["bytes"]
    assert uno > 0
    monkeypatch.setattr(sb, "_CACHE_MAX_BYTES", int(uno * 2.5))
    run_script_to_shape(_unico())
    run_script_to_shape(_unico())
    info = sb.cache_info()
    assert info["entradas"] == 2
    assert info["bytes"] <= info["max_bytes"]
    assert sb._cache_key(viejo, {}) not in sb._cache


def test_cada_acierto_de_cache_es_una_forma_nueva():
    codigo = _unico()
    a = run_script_to_shape(codigo)
    b = run_script_to_shape(codigo)
    assert a is not b and a.wrapped is not b.wrapped
    assert a.volume == pytest.approx(b.volume)


# ── concurrencia: STATE_LOCK → SANDBOX_LOCK ───────────────────────────────────

def test_regenerate_y_test_script_concurrentes_no_se_traban():
    from apolo.doc import Document
    from apolo.state import STATE_LOCK

    errores: list[BaseException] = []

    def regenerar() -> None:  # el executor: llega con STATE_LOCK tomado
        try:
            with STATE_LOCK:
                doc = Document()
                for i in range(3):
                    doc.execute("run_script", {"name": f"P{i}", "code": _unico(f"result = Box(5, 5, {i + 1})")})
        except BaseException as exc:  # noqa: BLE001
            errores.append(exc)

    def probar() -> None:  # POST /api/script/test: lee variables bajo STATE_LOCK y lo suelta
        try:
            for _ in range(3):
                with STATE_LOCK:
                    variables = {"R": 3}
                run_script_to_shape(_unico("result = Cylinder(V['R'], 10)"), variables)
        except BaseException as exc:  # noqa: BLE001
            errores.append(exc)

    hilos = [threading.Thread(target=f, daemon=True) for f in (regenerar, probar)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=240)
    assert not any(h.is_alive() for h in hilos), "los hilos se trabaron"
    assert errores == []
