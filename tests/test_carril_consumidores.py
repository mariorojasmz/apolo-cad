"""Lo que lee los índices del regenerate, con y sin carril (V8.1 F1, D1).

- **Sin carril, nada cambia**: firmas y claves de checkpoint byte-idénticas a las del algoritmo
  de antes (copiado aquí: firma encadenada sobre TODO el log, checkpoint en el último y cada
  `_REGEN_STRIDE`), en frío y a lo largo de execute/edit/remove/undo/redo, sobre un documento
  con `run_script` y otro con faja, componente de catálogo, `fasten` y variables.
- **Con carril**: `geomcache.pack` empaca el checkpoint del último comando de ESCENA (con el log
  terminado en el carril, el `len(commands) - 1` de antes no encontraba checkpoint y el open
  caliente no se poblaba nunca), el open caliente reanuda sin ejecutar nada y `prefijos` salta
  el carril. El carril de un `insert_project` (F3, D9) se prueba en
  `tests/test_electrico_insertado.py` con los comandos reales.

El comando de prueba se evalúa con el evaluador mínimo de F1 (`carril.ordenados`).
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest
from pydantic import BaseModel, Field

from apolo.commands import registry as registry_mod
from apolo.commands.registry import REGISTRY
from apolo.commands.spec import CommandSpec, version_tag
from apolo.doc import carril
from apolo.doc.document import Document
from apolo.doc.geomcache import pack, unpack
from apolo.doc.prefijos import iter_prefijos

CABLE = "cable_prueba"


class CableDePrueba(BaseModel):
    """Conductor de prueba del carril (sólo existe en estos tests)."""

    desde: str = Field(..., title="Desde")
    hasta: str = Field(..., title="Hasta")
    seccion_mm2: float = Field(1.5, gt=0, title="Sección")


def _nunca(ctx, cmd_id, p):
    raise AssertionError("un comando del carril no corre en el bucle del regenerate")


@pytest.fixture
def cable(monkeypatch):
    spec = CommandSpec(CABLE, "Cable de prueba", "electrico", CableDePrueba, _nunca,
                       kind="electrico")
    monkeypatch.setitem(REGISTRY, CABLE, spec)
    monkeypatch.setattr(carril, "EVALUADOR", carril.ordenados)
    return CABLE


@pytest.fixture
def ejecutados(monkeypatch):
    llamadas: list[str] = []
    real = registry_mod.run_executor

    def contar(spec, ctx, cmd_id, model):
        llamadas.append(cmd_id)
        return real(spec, ctx, cmd_id, model)

    monkeypatch.setattr(registry_mod, "run_executor", contar)
    return llamadas


def _caja(nombre: str, x: float) -> dict:
    return {"name": nombre, "width": 10, "depth": 10, "height": 10, "position": {"x": x}}


# ============================================================ sin carril: idéntico a antes
def _sig_vieja(prev: str, cmd: dict) -> str:
    """`_cmd_sig` de main@d4a7cce, copiado."""
    h = hashlib.sha1(prev.encode())
    h.update(cmd["id"].encode())
    h.update(json.dumps(cmd["params"], sort_keys=True, default=str).encode())
    h.update(version_tag(REGISTRY, cmd["type"]).encode())
    return h.hexdigest()


class _CuentasViejas:
    """Las cuentas de firmas y claves de checkpoint del regenerate de main@d4a7cce, sin
    geometría: firma encadenada sobre TODO el log, `_ckpts_ok` contra len(commands), reanudar
    del checkpoint previo al primer cambio y guardar el último y cada 16."""

    def __init__(self):
        self.sigs: list[str] = []
        self.claves: set[int] = set()
        self.deshacer: list[tuple] = []
        self.rehacer: list[tuple] = []

    def regenerar(self, comandos: list[dict]) -> None:
        sigs, prev = [], ""
        for cmd in comandos:
            prev = _sig_vieja(prev, cmd)
            sigs.append(prev)
        n = len(comandos)
        claves = self.claves if all(0 <= k < n for k in self.claves) else set()
        diverge = 0
        while diverge < min(len(sigs), len(self.sigs)) and sigs[diverge] == self.sigs[diverge]:
            diverge += 1
        resume = max((k for k in claves if k < diverge), default=-1)
        nuevas = {k for k in claves if k <= resume}
        nuevas |= {i for i in range(resume + 1, n) if i == n - 1 or i % 16 == 0}
        self.sigs, self.claves = sigs, nuevas

    def foto(self) -> tuple:
        return list(self.sigs), set(self.claves)

    def mutar(self, doc: Document, op) -> None:
        self.deshacer.append(self.foto())
        op()
        self.rehacer.clear()
        self.regenerar(doc.commands)

    def mover(self, doc: Document, desde: list, hacia: list, op) -> None:
        hacia.append(self.foto())
        self.sigs, self.claves = desde.pop()
        op()
        self.regenerar(doc.commands)


def _igual(doc: Document, viejas: _CuentasViejas) -> None:
    assert doc._regen_sigs == viejas.sigs
    assert set(doc._regen_ckpts) == viejas.claves


def _recorrer_igual(doc: Document, viejas: _CuentasViejas, armar) -> None:
    """Arma el documento comando a comando y lo opera, comparando en cada paso."""
    for tipo, params in armar(doc):
        viejas.mutar(doc, lambda t=tipo, p=params: doc.execute(t, p))
        _igual(doc, viejas)
    caja = next(c["id"] for c in doc.commands if c["type"] == "create_box")
    viejas.mutar(doc, lambda: doc.edit(caja, {"width": 77}, merge=True))
    _igual(doc, viejas)
    viejas.mutar(doc, lambda: doc.execute("create_box", _caja("Extra", -900)))
    _igual(doc, viejas)
    extra = doc.commands[-1]["id"]
    viejas.mutar(doc, lambda: doc.remove_commands([extra]))
    _igual(doc, viejas)
    for _ in range(2):
        viejas.mover(doc, viejas.deshacer, viejas.rehacer, doc.undo)
        _igual(doc, viejas)
    viejas.mover(doc, viejas.rehacer, viejas.deshacer, doc.redo)
    _igual(doc, viejas)
    viejas.mutar(doc, lambda: doc.execute("set_variable", {"name": "Z", "expression": "3"}))
    _igual(doc, viejas)
    frio, en_frio = Document.from_apolo_bytes(doc.to_apolo_bytes()), _CuentasViejas()
    en_frio.regenerar(frio.commands)
    _igual(frio, en_frio)


def test_sin_carril_identico_con_run_script():
    def armar(doc):
        yield "set_variable", {"name": "L", "expression": "120"}
        for i in range(10):
            yield "create_box", {**_caja(f"Caja {i}", 40 * i), "width": "=L/4"}
        yield "run_script", {"name": "Pieza de script", "code": "result = Box(V['L'], 10, 10)"}
        for i in range(8):
            yield "create_cylinder", {"name": f"Cil {i}", "radius": 5, "height": 20,
                                      "position": {"y": 60 + 30 * i}}

    d = Document("script")
    _recorrer_igual(d, _CuentasViejas(), armar)
    assert any(c["type"] == "run_script" for c in d.commands) and len(d.commands) > 16


def test_sin_carril_identico_con_faja_componente_y_fijador():
    def armar(doc):
        yield "set_variable", {"name": "LARGO", "expression": "3000"}
        yield "create_belt_conveyor", {"largo": "=LARGO", "ancho_banda": 600, "altura": 900}
        yield "insert_component", {"component": "DIN912-M6", "position": {"z": 2000}}
        faja = next(f.id for f in doc.scene.values() if f.command_id == doc.commands[1]["id"])
        yield "fasten", {"name": "f_tornillo", "a": faja, "b": doc.commands[-1]["id"],
                         "kind": "perno", "size": "M6", "qty": 1}
        for i in range(16):
            yield "create_box", _caja(f"Bloque {i}", -500 - 20 * i)

    d = Document("faja")
    _recorrer_igual(d, _CuentasViejas(), armar)
    assert {"create_belt_conveyor", "insert_component", "fasten"} <= {c["type"] for c in d.commands}


# ============================================================ geomcache con carril
def _con_carril(cable: str) -> Document:
    d = Document("gc carril")
    d.execute("set_variable", {"name": "S", "expression": "2.5"})
    for i in range(6):
        d.execute("create_box", _caja(f"B{i}", 30 * i))
    d.execute(cable, {"desde": "-Q1:2", "hasta": "-K1:1", "seccion_mm2": "=S"})
    for i in range(6, 20):
        d.execute("create_box", _caja(f"B{i}", 30 * i))
    d.execute(cable, {"desde": "-K1:2", "hasta": "-M1:U"})  # el log TERMINA en el carril
    return d


def _vista(doc: Document) -> list[tuple]:
    return [(e["id"], e["params"].model_dump()) for e in doc.electrico]


def test_open_caliente_con_carril(cable, ejecutados):
    d = _con_carril(cable)
    blob = pack(d)
    assert blob is not None  # con len(commands) - 1 no había checkpoint: nunca se cacheaba
    warm = unpack(blob)
    assert warm is not None and warm[0] == d._regen_sigs
    datos = d.to_apolo_bytes()
    ejecutados.clear()
    caliente = Document.from_apolo_bytes(datos, warm=warm)
    assert ejecutados == []  # reanuda del checkpoint: ningún executor
    frio = Document.from_apolo_bytes(datos)
    assert sorted(caliente.scene) == sorted(frio.scene) == sorted(d.scene)
    assert _vista(caliente) == _vista(frio) == _vista(d)
    assert caliente.check_integrity() == []


def test_open_caliente_tras_tocar_solo_el_carril(cable, ejecutados):
    d = _con_carril(cable)
    warm = unpack(pack(d))
    hilo = d.commands[7]["id"]
    d.edit(hilo, {"seccion_mm2": 6}, merge=True)
    d.execute(cable, {"desde": "-M1:V", "hasta": "-X1:1"})
    ejecutados.clear()
    caliente = Document.from_apolo_bytes(d.to_apolo_bytes(), warm=warm)
    assert ejecutados == []  # las firmas de escena no cambiaron: la caché sigue al día
    assert _vista(caliente) == _vista(d) and len(caliente.electrico) == 3
    assert caliente.check_integrity() == []


# ============================================================ prefijos con carril
def test_prefijos_saltan_el_carril(cable, ejecutados):
    d = Document("prefijos con carril")
    d.execute("set_variable", {"name": "S", "expression": "2.5"})
    a = d.execute("create_box", _caja("A", 0))
    h1 = d.execute(cable, {"desde": "-Q1:2", "hasta": "-K1:1", "seccion_mm2": "=S"})
    b = d.execute("create_box", _caja("B", 30))
    h2 = d.execute(cable, {"desde": "-K1:2", "hasta": "-M1:U"})
    h3 = d.execute(cable, {"desde": "-M1:V", "hasta": "-X1:1"})
    c = d.execute("create_box", _caja("C", 60))
    h4 = d.execute(cable, {"desde": "-X1:2", "hasta": "-X1:3"})
    carril_ids = {h1, h2, h3, h4}
    ejecutados.clear()
    prefijos = list(iter_prefijos(d))
    assert [p.cmd["id"] for p in prefijos] == [d.commands[0]["id"], a, b, c]
    assert [p.k for p in prefijos] == [1, 2, 4, 7]
    # cada executor corre una vez en todo el recorrido; el carril, nunca
    assert ejecutados == [cmd["id"] for cmd in d.commands if cmd["id"] not in carril_ids]
    for p in prefijos:
        fresco = Document()
        fresco.commands = copy.deepcopy(d.commands[: p.k])
        fresco.regenerate()
        assert list(p.escena) == list(fresco.scene)
    # un corte explícito en el carril vale y repite la escena del anterior (mismos shapes)
    explicitos = list(iter_prefijos(d, cortes=[4, 6]))
    assert [p.k for p in explicitos] == [4, 6]
    assert explicitos[1].cmd["id"] == h3
    assert all(explicitos[1].escena[f].shape is explicitos[0].escena[f].shape
               for f in explicitos[0].escena)


# ============================================================ insert_project con carril
def test_insert_project_trae_el_carril_fuera_del_replay_de_escena(cable, ejecutados):
    donante = Document("mini con tablero")
    base = donante.execute("create_box", {"name": "Base", "width": 100, "depth": 50,
                                          "height": 10})
    hilo = donante.execute(cable, {"desde": "-Q1:2", "hasta": "-K1:1"})
    anfitrion = Document("layout")
    digest = anfitrion.add_attachment(donante.to_apolo_bytes())
    cid = anfitrion.execute("insert_project", {"attachment": digest, "name": "M1"})
    assert f"{cid}_{base}" in anfitrion.scene
    # el replay de escena del origen no corre su carril (`_nunca` lo diría); llega aparte, con
    # el id prefijado como sus piezas (F3, D9)
    assert [e["id"] for e in anfitrion.electrico] == [f"{cid}_{hilo}"]
    assert anfitrion.regen_suppressed == [] and anfitrion.check_integrity() == []
