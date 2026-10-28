"""Los puntos de extensión del núcleo (plan nucleo-abierto-extensiones-privadas, F1a: D3, D12,
A1–A7) con la extensión FALSA de `tests/ext_prueba/`:

- apagadas (`APOLO_EXTENSIONES=0`, lo que fija `conftest.py`), el núcleo queda idéntico: 63
  comandos, 93 tools y 393 refs, sin nada en `GET /api/health`;
- cargada (`APOLO_EXTENSIONES_EXTRA`), cada punto: comando con prefijo en el MISMO `REGISTRY`
  (regenera, lo ve la vista persona con su pestaña), ruta, tool (MCP por stdio y el registro del
  chat), YAML del catálogo, modelo de la co-sim (también en el worker), `epoch_catalogo` en la
  firma (A4) y la vigencia de un escenario por la versión de la extensión;
- los rechazos (sin prefijo, contrato incompatible, kind eléctrico, tool con punto, choque con
  otra extensión o con un tramo de rutas del núcleo, import roto): TODO O NADA, con el motivo,
  sin tumbar el arranque;
- el gate de D9: el núcleo no nombra al paquete privado.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import pickle
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from apolo import extensiones

RAIZ = Path(__file__).resolve().parents[1]
EXTRA = "APOLO_EXTENSIONES_EXTRA"


def _entorno_hijo(extra: str, url: str | None = None) -> dict:
    """El entorno de un proceso hijo con la extensión falsa: sin el `APOLO_EXTENSIONES=0` de la
    suite y con `tests/` en el PYTHONPATH (ahí vive `ext_prueba`). `url`: la API a la que habla
    el MCP (nunca la :8000 de la máquina: un proceso de Mario la cambiaría)."""
    env = {k: v for k, v in os.environ.items() if k != "APOLO_EXTENSIONES"}
    env[EXTRA] = extra
    if url is not None:
        env["APOLO_URL"] = url
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(RAIZ / "core"), str(RAIZ / "tests"), os.environ.get("PYTHONPATH")) if p)
    return env


@pytest.fixture
def con_prueba(extensiones_aisladas, monkeypatch):
    """La extensión falsa cargada en ESTE proceso; al salir, el núcleo queda como estaba."""
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")
    estado = extensiones_aisladas.cargar()
    assert estado == [{"nombre": "ext-prueba", "version": "0.1.0", "cargada": True}], estado
    return extensiones_aisladas


# ── apagadas: el núcleo idéntico ─────────────────────────────────────────────────────────────

def test_la_suite_corre_con_las_extensiones_apagadas():
    assert os.environ.get("APOLO_EXTENSIONES") == "0" and extensiones.apagadas()


def test_apagadas_el_nucleo_queda_identico(extensiones_aisladas, monkeypatch):
    from apolo import mcp_server
    from apolo.commands.registry import REGISTRY
    from apolo.library.catalog import CATALOG

    monkeypatch.setenv("APOLO_EXTENSIONES", "0")
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")  # aunque la pidan
    assert extensiones_aisladas.cargar() == [] and extensiones_aisladas.descubrir() == []
    assert len(REGISTRY) == 63 and len(CATALOG) == 473  # + 1 anclaje de expansión (plantilla-rodillos-cadena F6), + 1 interruptor de posición (lo-que-se-mueve F2), +1 comando de cadena-de-izaje F1; +7 de bloqueo-de-vastago, +6 de amortiguador-externo, +20 de V8.9 F7b, +2 de plc-en-el-lazo F1d1, +1 de V8.9 F8, +5 de V8.5 F3, +2 cables sin PE
    assert len(asyncio.run(mcp_server.mcp.list_tools())) == 93
    assert extensiones_aisladas.routers() == [] and extensiones_aisladas.webui() is None


def test_las_instaladas_no_se_cuelan_salvo_que_el_test_las_pida(extensiones_aisladas, monkeypatch):
    """Una extensión instalada en el venv (entry point) no aparece junto a la falsa: la suite
    fija `APOLO_EXTENSIONES_INSTALADAS=0` (conftest). Quitándola, el entry point vuelve."""
    import importlib.metadata as md

    ep = md.EntryPoint("instalada", "ext_prueba:DUPLICADA", extensiones.GRUPO)
    monkeypatch.setattr(md, "entry_points", lambda group=None: [ep] if group == extensiones.GRUPO
                        else [])
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")
    assert os.environ["APOLO_EXTENSIONES_INSTALADAS"] == "0"
    assert [o for o, _e, _err in extensiones_aisladas.descubrir()] == ["ext_prueba:EXTENSION"]
    with extensiones.aislado():
        monkeypatch.delenv("APOLO_EXTENSIONES_INSTALADAS")
        assert [o for o, _e, _err in extensiones.descubrir()] == [
            "instalada (ext_prueba:DUPLICADA)", "ext_prueba:EXTENSION"]


def test_health_publica_las_extensiones_vacias_sin_ninguna():
    from fastapi.testclient import TestClient

    import apolo.api.main as api

    assert TestClient(api.app).get("/api/health").json()["extensiones"] == []


def test_release_cuenta_las_tools_con_list_tools_y_sin_extensiones():
    spec = importlib.util.spec_from_file_location("release_f1a", RAIZ / "scripts" / "release.py")
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    assert release.count_tools() == 93  # el regex sobre mcp_server.py daba 76
    assert os.environ["APOLO_EXTENSIONES"] == "0"


# ── cargada: cada punto ──────────────────────────────────────────────────────────────────────

def test_cada_punto_entra_al_registro_del_nucleo(con_prueba):
    from apolo.commands import command_schemas_persona
    from apolo.commands.pistas import PESTANAS, PISTAS
    from apolo.commands.registry import REGISTRY
    from apolo.cosim.modelos import DE_EXTENSION, MODELOS
    from apolo.library.catalog import CATALOG, CATEGORIES
    from apolo.library.electrico.ficha import TIPOS_MODELO
    from ext_prueba.modelos import Lampara

    assert "prueba.hola" in REGISTRY and len(REGISTRY) == 64 and "prueba.hola" in PISTAS
    assert PESTANAS["prueba"] == {"orden": 90, "rotulo": "Prueba"}
    assert CATALOG["prueba.caja"].category == "prueba_catalogo" and len(CATALOG) == 474  # 473 del núcleo + 1
    assert CATEGORIES[-1] == "prueba_catalogo"
    assert MODELOS["prueba.lampara"] is Lampara and "prueba.lampara" in TIPOS_MODELO
    assert DE_EXTENSION["prueba.lampara"] == ("ext-prueba", "0.1.0")
    persona = {e["type"]: e for e in command_schemas_persona()}["prueba.hola"]
    assert persona["pestana"] == {"orden": 90, "rotulo": "Prueba"}
    assert persona["pista"].startswith("Crea una caja de prueba")
    rutas = [r.path for router in con_prueba.routers() for r in router.routes]
    assert rutas[0] == "/api/prueba/hola" and "/api/prueba/caja" in rutas  # F1d: la fachada
    assert con_prueba.cargar() == con_prueba.estado()  # idempotente: no carga dos veces
    assert len(REGISTRY) == 64


def test_al_salir_el_nucleo_queda_como_estaba(monkeypatch):
    from apolo.commands.registry import REGISTRY
    from apolo.cosim.modelos import MODELOS
    from apolo.library.catalog import CATALOG, CATEGORIES

    antes = (dict(REGISTRY), dict(CATALOG), list(CATEGORIES), dict(MODELOS), extensiones.estado())
    monkeypatch.delenv("APOLO_EXTENSIONES", raising=False)
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")
    with extensiones.aislado():
        assert extensiones.cargar()[0]["cargada"]
        assert "prueba.hola" in REGISTRY
    assert (dict(REGISTRY), dict(CATALOG), list(CATEGORIES), dict(MODELOS),
            extensiones.estado()) == antes


def test_el_comando_y_la_ref_regeneran_como_los_del_nucleo(con_prueba):
    from apolo.doc import Document

    d = Document("ext")
    d.execute_many([{"type": "prueba.hola", "params": {"lado": 30}},
                    {"type": "insert_component", "params": {"component": "prueba.caja"}}])
    hola, caja = d.commands[0]["id"], d.commands[1]["id"]
    assert abs(d.scene[hola].shape.volume - 30 ** 3) < 1e-6
    assert any(f.component == "prueba.caja" for f in d.scene.values())
    d.edit(hola, {"lado": 20})
    assert abs(d.scene[hola].shape.volume - 20 ** 3) < 1e-6
    assert caja in {c["id"] for c in d.commands}


def test_el_epoch_del_catalogo_entra_solo_a_quien_nombra_su_ref(con_prueba):
    """D12/A4: sin la ref, la firma histórica; con ella, «|ext:extensión@epoch». Un compuesto
    (insert_project) lleva el de toda extensión: su adjunto puede insertar refs que sus params
    no nombran."""
    from apolo.commands.registry import REGISTRY
    from apolo.commands.spec import version_tag

    assert version_tag(REGISTRY, "insert_component", {"component": "prueba.caja"}) == (
        "|v:insert_component@2|ext:ext-prueba@1")
    assert version_tag(REGISTRY, "insert_component", {"component": "UCP205"}) == "|v:insert_component@2"
    assert version_tag(REGISTRY, "create_box", {"name": "prueba.caja de nombre"}) == ""
    assert version_tag(REGISTRY, "insert_project", {"attachment": "x"}).endswith("|ext:ext-prueba@1")
    assert version_tag(REGISTRY, "insert_component") == "|v:insert_component@2"  # sin params


def test_sin_extensiones_la_firma_es_la_historica():
    from apolo.commands.registry import REGISTRY
    from apolo.commands.spec import REFS_DE_EXTENSION, version_tag

    assert REFS_DE_EXTENSION == {}
    assert version_tag(REGISTRY, "insert_component", {"component": "x"}) == "|v:insert_component@2"
    assert "|ext:" not in version_tag(REGISTRY, "insert_project", {"attachment": "x"})


def test_la_tool_se_registra_con_su_lugar_en_el_chat(con_prueba):
    from apolo.tools import catalogo
    from apolo.tools.fastmcp_limpio import FastMCPLimpio

    mcp = FastMCPLimpio("prueba")
    llamadas = []
    servidor = {"_api": None, "_submit_and_wait": None,
                "_mutacion": lambda *a, **k: llamadas.append(a) or "hecho"}
    assert con_prueba.registrar_tools(mcp, servidor) == ["prueba_hola", "prueba_informe"]
    assert [t.name for t in asyncio.run(mcp.list_tools())] == ["prueba_hola", "prueba_informe"]
    assert "prueba_hola" in catalogo.FUERA_DEL_CHAT and catalogo.DE_EXTENSION["prueba_hola"] == "ext-prueba"
    out = asyncio.run(mcp.call_tool("prueba_hola", {"lado": 12}))
    assert "hecho" in json.dumps(out[0][0].text if isinstance(out, tuple) else out[0].text)
    assert llamadas == [("POST", "/api/commands", {"type": "prueba.hola", "params": {"lado": 12.0}},
                         "diff")]
    con_prueba.registrar_tools(mcp, servidor)  # repetir para la misma extensión no rompe nada


def test_el_modelo_viaja_en_el_snapshot_y_el_worker_lo_registra(con_prueba):
    from apolo.cosim import modelos as M
    from apolo.cosim.datos import CosimSnapshot
    from ext_prueba.modelos import Lampara

    clases, versiones = M.de_extension(["red", "prueba.lampara", None])
    assert clases == {"prueba.lampara": Lampara} and versiones == {"ext-prueba": "0.1.0"}
    snap = CosimSnapshot(dinamica=None, red={}, dispositivos=[], programas=[], motores=[],
                         sensores=[], escenario=None, modelos_extension=clases,
                         extensiones=versiones)
    copia = pickle.loads(pickle.dumps(snap))  # lo que recibe el worker
    del M.MODELOS["prueba.lampara"]  # el worker no buscó extensiones
    M.registrar_modelos(copia.modelos_extension)  # lo que hace worker.main
    assert M.MODELOS["prueba.lampara"] is Lampara
    M.registrar_modelos(copia.modelos_extension)  # idempotente
    with pytest.raises(ValueError, match="ya es de otra clase"):
        M.registrar_modelos({"prueba.lampara": M.Piloto})
    assert M.crear_modelo("-H9", "prueba.ref", {"tipo": "prueba.lampara"}).paso(0.01, {"U_V": 24}) == {
        "encendida": True}


def test_el_escenario_vence_si_cambia_la_extension_de_sus_modelos(con_prueba, monkeypatch):
    from apolo.services import electrico
    from apolo.services import escenarios as E

    tablero = SimpleNamespace(dispositivos=[SimpleNamespace(modelo={"tipo": "prueba.lampara"})])
    monkeypatch.setattr(electrico, "modelo", lambda doc: tablero)
    esc = {"duracion_s": 1}
    base = E.resultado_compacto({"veredicto": "pasa", "aserciones": []}, {}, firma="f",
                                hash_esc=E.hash_escenario(esc), simulacion=None,
                                extensiones={"ext-prueba": "0.1.0"})
    assert base["extensiones"] == {"ext-prueba": "0.1.0"}
    assert "extensiones" not in E.resultado_compacto({"veredicto": "pasa", "aserciones": []}, {},
                                                     firma="f", hash_esc="h", simulacion=None)
    doc = SimpleNamespace(escenarios={"a": {"escenario": esc, "resultado": base}})
    assert E.estado(doc, "a", "f") == {"estado": "pasa"}
    base["extensiones"] = {"ext-prueba": "0.0.9"}
    st = E.estado(doc, "a", "f")
    assert st["estado"] == "vencido" and "cambió una extensión" in st["motivo"]


def test_un_resultado_con_extension_vence_si_ya_no_esta_cargada(monkeypatch):
    from apolo.cosim import COSIM_EPOCH
    from apolo.services import electrico
    from apolo.services import escenarios as E

    monkeypatch.setattr(electrico, "modelo", lambda doc: SimpleNamespace(dispositivos=[]))
    esc = {"duracion_s": 1}
    res = {"veredicto": "pasa", "firma_documento": "f", "hash_escenario": E.hash_escenario(esc),
           "cosim_epoch": COSIM_EPOCH, "extensiones": {"ext-prueba": "0.1.0"}}
    doc = SimpleNamespace(escenarios={"a": {"escenario": esc, "resultado": res}})
    assert E.estado(doc, "a", "f")["estado"] == "vencido"
    del res["extensiones"]
    assert E.estado(doc, "a", "f") == {"estado": "pasa"}


def test_la_ui_de_una_extension_gana_salvo_apolo_ui_nucleo(tmp_path, monkeypatch):
    from apolo import paths

    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.delenv("APOLO_UI", raising=False)
    assert paths.ui_dist(tmp_path) == tmp_path
    monkeypatch.setenv("APOLO_UI", "nucleo")
    assert paths.ui_dist(tmp_path) != tmp_path
    monkeypatch.delenv("APOLO_UI")
    assert paths.ui_dist(tmp_path / "sin-build") != tmp_path / "sin-build"


def test_cargar_publica_la_webui_de_la_extension(extensiones_aisladas, monkeypatch, tmp_path):
    import ext_prueba
    from dataclasses import replace

    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(ext_prueba, "CON_UI", replace(ext_prueba.EXTENSION, webui=tmp_path),
                        raising=False)
    monkeypatch.setenv(EXTRA, "ext_prueba:CON_UI")
    assert extensiones_aisladas.cargar()[0]["cargada"]
    assert extensiones_aisladas.webui() == tmp_path


# ── rechazos: todo o nada, con el motivo ─────────────────────────────────────────────────────

@pytest.mark.parametrize(("extra", "motivo"), [
    ("ext_prueba:SIN_PREFIJO", "no lleva el prefijo «prueba.»"),
    ("ext_prueba:CONTRATO_VIEJO", "pide el contrato de extensiones 2–3"),
    ("ext_prueba:ELECTRICA", "kind «electrico»"),
    ("ext_prueba:TOOL_CON_PUNTO", "sin punto"),
    ("ext_prueba:NO_EXISTE", "no se pudo importar"),
    ("ext_prueba:NO_ES_EXTENSION", "no es una apolo.extensiones.Extension"),
    ("modulo_que_no_existe:X", "no se pudo importar"),
])
def test_lo_que_no_cumple_no_se_carga_y_dice_por_que(extensiones_aisladas, monkeypatch, extra, motivo):
    from apolo.commands.registry import REGISTRY
    from apolo.cosim.modelos import MODELOS
    from apolo.library.catalog import CATALOG

    monkeypatch.setenv(EXTRA, extra)
    (e,) = extensiones_aisladas.cargar()  # nunca lanza
    assert e["cargada"] is False and motivo in e["motivo"], e
    # todo o nada: ni su catálogo ni su modelo (que se suman ANTES que los comandos) quedaron
    assert len(REGISTRY) == 63 and "prueba.caja" not in CATALOG and "prueba.lampara" not in MODELOS
    assert extensiones_aisladas.routers() == []


def test_dos_extensiones_no_comparten_prefijo(extensiones_aisladas, monkeypatch):
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION,ext_prueba:DUPLICADA")
    primera, segunda = extensiones_aisladas.cargar()
    assert primera["cargada"] and not segunda["cargada"]
    assert "choca con la extensión «ext-prueba»" in segunda["motivo"]


def test_el_prefijo_no_puede_ser_un_tramo_de_rutas_del_nucleo(extensiones_aisladas, monkeypatch):
    monkeypatch.setenv(EXTRA, "ext_prueba:EN_RUTAS_DEL_NUCLEO")
    (e,) = extensiones_aisladas.cargar(rutas_nucleo=["/api/fea/static", "/api/health"])
    assert not e["cargada"] and "ya es un tramo de rutas del núcleo" in e["motivo"]


# ── de punta a punta, en procesos aparte (como corren la API y el MCP) ───────────────────────

_API = """
import json
from fastapi.testclient import TestClient
import apolo.api.main as api
from apolo.doc import Document

api.DOC = Document("t")
c = TestClient(api.app)
health = c.get("/api/health").json()
r = c.post("/api/commands", json={"type": "prueba.hola", "params": {"lado": 30}})
nombres = [getattr(x, "name", None) for x in api.app.routes]
paths = [getattr(x, "path", None) for x in api.app.routes]
print(json.dumps({
    "extensiones": health["extensiones"],
    "comando": r.status_code, "piezas": [f["name"] for f in r.json().get("features", [])],
    "ruta": c.get("/api/prueba/hola").json(),
    "schema": c.get("/api/schemas/prueba.hola").status_code,
    "catalogo": [x["ref"] for x in c.get("/api/catalog").json() if x["ref"].startswith("prueba.")],
    # la de la extensión va después de las del núcleo y antes de la UI (si hay bundle)
    "tras_el_nucleo": paths.index("/api/prueba/hola") > paths.index("/api/health"),
    "antes_de_la_ui": "ui" not in nombres or paths.index("/api/prueba/hola") < nombres.index("ui"),
}))
"""


def test_la_api_carga_la_extension_y_sirve_cada_punto():
    out = subprocess.run([sys.executable, "-B", "-c", _API], capture_output=True, text=True,
                         env=_entorno_hijo("ext_prueba:EXTENSION,ext_prueba:CONTRATO_VIEJO"),
                         timeout=600, cwd=RAIZ)
    assert out.returncode == 0, out.stderr[-3000:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    ok, vieja = res["extensiones"]
    assert ok == {"nombre": "ext-prueba", "version": "0.1.0", "cargada": True}
    assert vieja["cargada"] is False and "contrato" in vieja["motivo"]  # y la API arrancó igual
    assert res["comando"] == 200 and "Hola" in res["piezas"]
    assert res["ruta"] == {"hola": "desde la extensión de prueba"} and res["schema"] == 200
    assert res["catalogo"] == ["prueba.caja"]
    assert res["tras_el_nucleo"] and res["antes_de_la_ui"]


_MCP = """
import asyncio, json, runpy, sys
import apolo.tools.fastmcp_limpio as f

def run(self, *a, **k):
    servidor = sys.modules["__main__"]
    servidor._mutacion = lambda *a, **k: "mutacion " + json.dumps(a[2])
    nombres = [t.name for t in asyncio.run(self.list_tools())]
    if "prueba_hola" not in nombres:
        print(json.dumps({"n": len(nombres), "nombres": nombres}))
        return
    out = asyncio.run(self.call_tool("prueba_hola", {"lado": 7}))
    bloques = out[0] if isinstance(out, tuple) else out
    from apolo.tools import catalogo
    pesados = sorted(m for m in sys.modules if m.split(".")[0] in ("OCP", "build123d"))
    print(json.dumps({"n": len(nombres), "nombres": nombres, "salida": bloques[0].text,
                      "fuera": "prueba_hola" in catalogo.FUERA_DEL_CHAT, "pesados": pesados}))

f.FastMCPLimpio.run = run
runpy.run_module("apolo.mcp_server", run_name="__main__", alter_sys=True)
"""


def _mcp_hijo(url: str):
    out = subprocess.run([sys.executable, "-B", "-c", _MCP], capture_output=True, text=True,
                         env=_entorno_hijo("ext_prueba:EXTENSION", url), timeout=300, cwd=RAIZ)
    return out


def test_el_mcp_por_stdio_registra_la_tool_al_final_sin_cargar_occt():
    from apolo.pruebas import api_falsa

    cargada = [{"nombre": "ext-prueba", "version": "0.1.0", "cargada": True}]
    with api_falsa({"/api/extensiones": cargada}) as url:
        out = _mcp_hijo(url)
    assert out.returncode == 0, out.stderr[-3000:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["n"] == 95 and res["nombres"][-2:] == ["prueba_hola", "prueba_informe"]
    assert res["salida"] == 'mutacion {"type": "prueba.hola", "params": {"lado": 7.0}}'
    assert res["fuera"] and res["pesados"] == []  # los comandos perezosos no se resolvieron


# ── D9: el núcleo no nombra al paquete privado ───────────────────────────────────────────────

_PRIVADO = re.compile(r"(?<![A-Za-z0-9_])apolo[-_]pro(?![A-Za-z0-9_])", re.IGNORECASE)
_OMITIR = {"__pycache__", "node_modules", "webui", "dist", ".pytest_cache"}


def _fuentes(raiz: Path):
    for dirpath, dirnames, filenames in os.walk(raiz):
        dirnames[:] = [d for d in dirnames if d not in _OMITIR and not d.endswith(".egg-info")]
        for nombre in filenames:
            ruta = Path(dirpath) / nombre
            try:
                yield ruta, ruta.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue  # binarios


def test_el_nucleo_no_nombra_al_paquete_privado():
    """D1/D9: ni `core/`, ni `ui/src`, ni `scripts/` nombran al paquete privado (las rutas de
    `docs/`, la bitácora y los tests no cuentan: hablan DE él)."""
    hallados = [f"{ruta.relative_to(RAIZ).as_posix()}:{texto[:m.start()].count(chr(10)) + 1}"
                for carpeta in ("core", "ui/src", "scripts") if (RAIZ / carpeta).is_dir()
                for ruta, texto in _fuentes(RAIZ / carpeta) for m in _PRIVADO.finditer(texto)]
    assert not hallados, "el núcleo nombra al paquete privado (D9):\n" + "\n".join(hallados)


def test_el_gate_caza_el_nombre_y_no_confunde_apolo_project():
    nombre = "apolo" + "_pro"
    assert _PRIVADO.search(f"import {nombre}") and _PRIVADO.search("pip install apolo" + "-pro")
    assert not _PRIVADO.search("APOLO_PROJECT=74") and not _PRIVADO.search("apolo-proyecto")
