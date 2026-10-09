"""El carril del log en el documento (V8.1 F1, D1): `doc/carril.py` y su uso en `document.py`.

Un comando del carril (`CommandSpec.kind == "electrico"`) vive en el log, pero no entra a la
firma encadenada ni ocupa índice de checkpoint: editarlo, insertarlo o borrarlo en cualquier
posición no re-ejecuta ningún executor de escena (V8.0 midió 5 s dentro de la firma contra
8,5 ms fuera). Se evalúa DESPUÉS del bucle, contra la escena y las variables finales, y el
resultado queda en `doc.electrico`. Estricto en las mutaciones, tolerante en la carga.

El comando de prueba se registra SÓLO aquí (monkeypatch del REGISTRY): los comandos eléctricos
reales son de F3. Los executors se cuentan envolviendo `run_executor` en `commands.registry`,
donde `execute_command` lo busca (parchearlo en `spec` no alcanza, V8.0).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from apolo.commands import registry as registry_mod
from apolo.commands.errors import CommandError
from apolo.commands.registry import REGISTRY
from apolo.commands.spec import KINDS, CommandSpec
from apolo.doc import carril
from apolo.doc.document import Document, DocumentError

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
    return CABLE


@pytest.fixture
def ejecutados(monkeypatch):
    """Los cmd_id de cada executor que corre (escena o variables)."""
    llamadas: list[str] = []
    real = registry_mod.run_executor

    def contar(spec, ctx, cmd_id, model):
        llamadas.append(cmd_id)
        return real(spec, ctx, cmd_id, model)

    monkeypatch.setattr(registry_mod, "run_executor", contar)
    return llamadas


def _caja(i: int) -> dict:
    return {"type": "create_box", "params": {"name": f"Caja {i}", "width": 10, "depth": 10,
                                             "height": 10, "position": {"x": 20 * i}}}


def _hilo(desde: str, hasta: str, seccion="=S") -> dict:
    return {"type": CABLE, "params": {"desde": desde, "hasta": hasta, "seccion_mm2": seccion}}


def _log_60() -> tuple[Document, str]:
    """60 comandos: la variable S, 4 cajas, el cable en la posición 5 y 54 cajas más."""
    d = Document("carril")
    acciones = [{"type": "set_variable", "params": {"name": "S", "expression": "2.5"}}]
    acciones += [_caja(i) for i in range(4)]
    acciones.append(_hilo("-Q1:2", "-K1:1"))
    acciones += [_caja(i) for i in range(4, 58)]
    ids = d.execute_many(acciones)
    assert len(d.commands) == 60 and d.commands[5]["id"] == ids[5]
    return d, ids[5]


def _insertar_en(doc: Document, pos: int, tipo: str, params: dict) -> str:
    """Inserta un comando en MITAD del log (como lo hará el carril de `insert_project`, F3)."""
    hecho: dict[str, str] = {}

    def aplicar():
        hecho["id"] = doc._append_record(tipo, params)
        doc.commands.insert(pos, doc.commands.pop())

    doc._mutate(aplicar)
    return hecho["id"]


def _vista(doc: Document) -> list[tuple]:
    return [(e["id"], e["type"], e["params"].model_dump()) for e in doc.electrico]


# ------------------------------------------------------------------ separar el log
def test_kind_electrico_es_valido():
    assert "electrico" in KINDS
    with pytest.raises(ValueError, match="kind 'otro' inválido"):
        CommandSpec("x", "X", "electrico", CableDePrueba, _nunca, kind="otro")


def test_separar_da_escena_carril_y_posiciones(cable):
    log = [{"id": "c1", "type": "set_variable", "params": {}},
           {"id": "c2", "type": CABLE, "params": {}},
           {"id": "c3", "type": "create_box", "params": {}},
           {"id": "c4", "type": "no_existe", "params": {}},  # desconocido: de escena, como hoy
           {"id": "c5", "type": CABLE, "params": {}}]
    parte = carril.separar(log)
    assert [c["id"] for c in parte.escena] == ["c1", "c3", "c4"]
    assert [c["id"] for c in parte.carril] == ["c2", "c5"]
    assert parte.posiciones == [0, 2, 3]
    assert carril.n_escena(log) == 3
    assert not carril.es_carril({"id": "c9", "type": ["no", "hashable"], "params": {}})


def test_sin_carril_el_modelo_es_vacio_y_no_llama_al_evaluador(monkeypatch):
    def no_evaluar(*_):
        raise AssertionError("sin carril no se evalúa nada")

    monkeypatch.setattr(carril, "EVALUADOR", no_evaluar)
    d = Document()
    assert d.electrico == []
    d.execute("create_box", {"name": "A", "width": 10, "depth": 10, "height": 10})
    assert d.electrico == [] and d.check_integrity() == []


# ------------------------------------------------------------------ evaluación
def test_evalua_contra_la_escena_y_las_variables_finales(cable, monkeypatch):
    vistos = {}

    def evaluador(entradas, escena, variables, fallo):
        vistos.update(ids=[e["id"] for e in entradas], escena=set(escena), variables=variables)
        return ("modelo", len(entradas))

    monkeypatch.setattr(carril, "EVALUADOR", evaluador)
    d = Document()
    d.execute("set_variable", {"name": "S", "expression": "1.5"})
    hilo = d.execute(cable, {"desde": "-Q1:2", "hasta": "-K1:1", "seccion_mm2": "=S*2"})
    caja = d.execute("create_box", {"name": "Tras el cable", "width": 10, "depth": 10,
                                    "height": 10})
    d.execute("set_variable", {"name": "T", "expression": "=S+1"})  # se hoistea, igual es final
    assert d.electrico == ("modelo", 1)
    assert vistos["ids"] == [hilo]
    assert caja in vistos["escena"]  # la pieza creada DESPUÉS del cable en el log
    assert vistos["variables"] == {"S": 1.5, "T": 2.5}


def test_el_evaluador_por_defecto_valida_y_ordena(cable):
    d, hilo = _log_60()
    d.execute(cable, {"desde": "-K1:2", "hasta": "-X1:3", "seccion_mm2": 1})
    vista = _vista(d)
    assert [v[0] for v in vista] == [hilo, d.commands[-1]["id"]]
    assert vista[0][2] == {"desde": "-Q1:2", "hasta": "-K1:1", "seccion_mm2": 2.5}  # =S resuelto
    d.execute("set_variable", {"name": "S", "expression": "4"})
    assert _vista(d)[0][2]["seccion_mm2"] == 4.0


def test_fallo_del_evaluador_estricto_lanza_y_tolerante_suprime(cable, monkeypatch):
    def quisquilloso(entradas, escena, variables, fallo):
        buenos = []
        for e in entradas:
            if e["params"].hasta == "-X9:1":
                fallo(e, "el dispositivo -X9 no existe")
                continue
            buenos.append(e["id"])
        return buenos

    monkeypatch.setattr(carril, "EVALUADOR", quisquilloso)
    d = Document()
    bueno = d.execute(cable, {"desde": "-Q1:2", "hasta": "-K1:1"})
    with pytest.raises(DocumentError, match="no existe"):
        d.execute(cable, {"desde": "-K1:2", "hasta": "-X9:1"})
    assert [c["id"] for c in d.commands] == [bueno] and d.electrico == [bueno]
    d.commands.append({"id": "c9", "type": CABLE, "params": {"desde": "a", "hasta": "-X9:1"}})
    abierto = Document.from_apolo_bytes(d.to_apolo_bytes(), tolerant=True)
    assert abierto.electrico == [bueno]
    assert abierto.regen_suppressed == [
        {"command_id": "c9", "type": CABLE, "error": "el dispositivo -X9 no existe"}]


# ------------------------------------------------------------------ 0 executors de escena
def test_editar_insertar_y_borrar_en_el_carril_no_reejecuta_la_escena(cable, ejecutados):
    d, hilo = _log_60()
    sigs, claves = list(d._regen_sigs), sorted(d._regen_ckpts)
    assert len(sigs) == 59  # el cable no tiene firma

    ejecutados.clear()
    d.edit(hilo, {"seccion_mm2": 4}, merge=True)
    assert ejecutados == [] and _vista(d)[0][2]["seccion_mm2"] == 4.0

    nuevo = _insertar_en(d, 5, CABLE, {"desde": "-K1:2", "hasta": "-M1:U"})
    assert ejecutados == [] and d.commands[5]["id"] == nuevo
    assert [v[0] for v in _vista(d)] == [nuevo, hilo]  # el orden del LOG

    d.edit_many([{"command_id": hilo, "params": {"seccion_mm2": 6}},
                 {"command_id": nuevo, "params": {"seccion_mm2": 1}}], merge=True)
    d.remove_commands([nuevo])
    assert ejecutados == []
    assert d._regen_sigs == sigs and sorted(d._regen_ckpts) == claves
    assert [v[0] for v in _vista(d)] == [hilo] and d.check_integrity() == []

    # contraste: el contador sí ve un cambio de escena temprano (re-ejecuta la cola)
    d.edit(d.commands[3]["id"], {"width": 12}, merge=True)
    assert len(ejecutados) >= 50


def test_deshacer_y_rehacer_el_carril(cable, ejecutados):
    d, hilo = _log_60()
    nuevo = d.execute(cable, {"desde": "-K1:2", "hasta": "-M1:U", "seccion_mm2": 1})
    d.edit(hilo, {"seccion_mm2": 6}, merge=True)
    d.remove_commands([nuevo])
    ejecutados.clear()
    assert [v[0] for v in _vista(d)] == [hilo]
    d.undo()  # vuelve el cable borrado
    assert [v[0] for v in _vista(d)] == [hilo, nuevo]
    d.undo()  # vuelve la sección de antes
    assert _vista(d)[0][2]["seccion_mm2"] == 2.5
    d.undo()  # el cable nuevo desaparece
    assert [v[0] for v in _vista(d)] == [hilo]
    d.redo(3)
    assert [v[0] for v in _vista(d)] == [hilo] and _vista(d)[0][2]["seccion_mm2"] == 6.0
    assert ejecutados == [] and d.check_integrity() == []


def test_las_etiquetas_de_deshacer_nombran_el_carril(cable):
    d, hilo = _log_60()
    d.edit(hilo, {"seccion_mm2": 6}, merge=True)
    d.execute(cable, {"desde": "-K1:2", "hasta": "-M1:U"})
    assert d.undo_labels[:2] == ["Cable de prueba", "Editar Cable de prueba: Sección"]


# ------------------------------------------------------------------ estricto / tolerante
def test_estricto_en_la_mutacion(cable):
    d, hilo = _log_60()
    antes, n_undo, vista = list(d.commands), len(d._undo), _vista(d)
    with pytest.raises(CommandError, match="seccion_mm2"):  # la puerta de execute
        d.execute(cable, {"desde": "a", "hasta": "b", "seccion_mm2": -1})
    with pytest.raises(DocumentError, match=r"Error al regenerar c\d+ \(cable_prueba\)"):
        d.execute_many([_hilo("a", "b", "=NO_EXISTE*2")])  # lo valida el regenerate
    with pytest.raises(DocumentError, match="NO_EXISTE"):
        d.edit_many([{"command_id": hilo, "params": {"seccion_mm2": "=NO_EXISTE"}}],
                    merge=True)
    var = d.commands[0]["id"]
    with pytest.raises(DocumentError, match=hilo):  # borrar la variable que usa el cable
        d.remove_commands([var])
    assert d.commands == antes and len(d._undo) == n_undo and _vista(d) == vista


def test_tolerante_en_la_carga(cable):
    d, hilo = _log_60()
    d.commands.append({"id": "c90", "type": CABLE, "params": {"desde": "x"}})  # sin `hasta`
    d.commands.append({"id": "c91", "type": CABLE,
                       "params": {"desde": "x", "hasta": "y", "seccion_mm2": "=NADA"}})
    datos = d.to_apolo_bytes()
    with pytest.raises(DocumentError, match="c90"):
        Document.from_apolo_bytes(datos)
    abierto = Document.from_apolo_bytes(datos, tolerant=True)
    assert [s["command_id"] for s in abierto.regen_suppressed] == ["c90", "c91"]
    assert all(s["type"] == CABLE for s in abierto.regen_suppressed)
    assert [v[0] for v in _vista(abierto)] == [hilo]
    assert len(abierto.scene) == 58 and [c["id"] for c in abierto.commands][-2:] == ["c90", "c91"]


def test_ida_y_vuelta_de_un_apolo_con_carril(cable, tmp_path):
    d, _ = _log_60()
    d.execute(cable, {"desde": "-K1:2", "hasta": "-M1:U", "seccion_mm2": 1})
    ruta = tmp_path / "con_carril.apolo"
    d.save(ruta)
    otra = Document.load(ruta)
    assert otra.commands == d.commands
    assert _vista(otra) == _vista(d)
    assert otra._regen_sigs == d._regen_sigs and len(otra._regen_sigs) == 59
    assert set(otra.scene) == set(d.scene) and otra.check_integrity() == []


def test_un_log_solo_de_carril(cable):
    d = Document()
    hilo = d.execute(cable, {"desde": "-Q1:2", "hasta": "-K1:1"})
    assert d.scene == {} and d._regen_sigs == [] and d._regen_ckpts == {}
    assert [v[0] for v in _vista(d)] == [hilo] and d.check_integrity() == []
    d.undo()
    assert d.electrico == [] and d.commands == []
