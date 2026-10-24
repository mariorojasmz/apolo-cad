"""Un comando de ESCENA que lee el carril (V8.5 F1a: D1, A5, A6, A14, A15).

- Lo que lee (`ExecContext.carril`) es lo que firma: los `add_device` de SU ubicación y los
  `add_cable` que entran o salen de ella, con sólo los campos que cambian la geometría.
- Su firma cambia con un dispositivo de su ubicación y NO con un conductor, un programa, un
  dispositivo de otra ubicación ni los `ajustes`: editar eso no re-ejecuta nada.
- Checkpoint justo antes de él: editar un dispositivo re-ejecuta sólo el layout y la cola.
- Un log sin un comando que lea el carril: firmas y checkpoints de siempre.

El comando que lee es de prueba (`layout_prueba`): el real, `layout_tablero`, es de F1b.
"""

from __future__ import annotations

import hashlib
import json
from types import MappingProxyType

import pytest
from pydantic import BaseModel, Field

from apolo.commands import registry as registry_mod
from apolo.commands.registry import REGISTRY, validate_params
from apolo.commands.spec import CommandSpec, version_tag
from apolo.doc import carril
from apolo.doc.document import Document, _cmd_sig

from tablero_electrico import dev, wire

LAYOUT = "layout_prueba"


class LayoutDePrueba(BaseModel):
    """Lee el carril de su ubicación (sólo existe en estos tests)."""

    ubicacion: str = Field("", title="Ubicación")
    alto: float = Field(10, gt=0, title="Alto")


@pytest.fixture
def leido(monkeypatch):
    """Registra el comando de prueba; devuelve la lista de `ctx.carril` que recibió."""
    vistos: list[tuple] = []

    def _exec(ctx, cmd_id, p):
        vistos.append(ctx.carril)

    spec = CommandSpec(LAYOUT, "Layout de prueba", "tablero", LayoutDePrueba, _exec,
                       lee_carril=True)
    monkeypatch.setitem(REGISTRY, LAYOUT, spec)
    return vistos


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
    return {"type": "create_box", "params": {"name": nombre, "width": 10, "depth": 10,
                                             "height": 10, "position": {"x": x}}}


def _doc(n_cajas: int = 20, layout: bool = True) -> Document:
    """n cajas, el carril de un tablero chico (+TAB1, +CAMPO) y el layout al final."""
    d = Document()
    acciones = [{"type": "set_variable", "params": {"name": "n", "expression": "4"}}]
    acciones += [_caja(f"Caja {i}", 20 * i) for i in range(n_cajas)]
    acciones += [
        dev("RED-3F-220V-60HZ", "-G1", "+RED"),
        dev("SECC-25A-3P", "-Q1"),
        dev("ITM-C2-2P", "-F1"),
        dev("BORNE-PE-4", "-X0", cantidad="=n"),
        dev("MOTOR-075", "-M1", "+CAMPO", ajustes={"conexion": "triangulo"}),
        {"type": "add_cable", "params": {"designacion": "-W1", "ref": "CABLE-4G1.5",
                                         "desde": "+TAB1", "hasta": "-M1"}},
        {"type": "add_cable", "params": {"designacion": "-W2", "ref": "CABLE-4G1.5",
                                         "desde": "-Q1", "hasta": "+CAMPO"}},
        {"type": "add_cable", "params": {"designacion": "-W3", "ref": "CABLE-4G1.5",
                                         "desde": "+RED", "hasta": "-M1"}},
        wire("-G1:L1", "-Q1:1", color="BK", largo_m=1.0),
    ]
    if layout:
        acciones.append({"type": LAYOUT, "params": {"ubicacion": "TAB1"}})
    d.execute_many(acciones)
    return d


def _id(d: Document, tipo: str, designacion: str | None = None) -> str:
    return next(c["id"] for c in d.commands if c["type"] == tipo and (
        designacion is None or c["params"].get("designacion") == designacion))


# ============================================================ lo que lee
def test_lee_solo_su_ubicacion_y_los_cables_que_entran_o_salen(leido):
    d = _doc()
    lectura = leido[-1]
    assert [(e["type"], e["params"].get("designacion")) for e in lectura] == [
        ("add_device", "-Q1"), ("add_device", "-F1"), ("add_device", "-X0"),
        ("add_cable", None), ("add_cable", None)]  # -W1 (+TAB1) y -W2 (-Q1 es de +TAB1)
    cables = [e["id"] for e in lectura if e["type"] == "add_cable"]
    assert cables == [_id(d, "add_cable", "-W1"), _id(d, "add_cable", "-W2")]
    # sólo los campos que cambian la geometría (A5), crudos: el `=n` lo resuelve el executor
    x0 = next(e for e in lectura if e["params"].get("designacion") == "-X0")
    assert dict(x0["params"]) == {"ref": "BORNE-PE-4", "designacion": "-X0",
                                  "ubicacion": "+TAB1", "cantidad": "=n"}
    assert dict(lectura[-1]["params"]) == {"ref": "CABLE-4G1.5", "desde": "-Q1",
                                           "hasta": "+CAMPO"}
    # A15: se valida con las variables del punto del layout en el log
    assert validate_params("add_device", dict(x0["params"]), d.variables_raw).cantidad == 4


def test_la_lectura_es_de_solo_lectura(leido):
    _doc(n_cajas=2)
    entrada = leido[-1][0]
    assert isinstance(entrada, MappingProxyType) and isinstance(entrada["params"], MappingProxyType)
    with pytest.raises(TypeError):
        entrada["params"]["ref"] = "otra"
    with pytest.raises(TypeError):
        entrada["id"] = "c999"


def test_un_comando_que_no_lee_recibe_un_carril_vacio(monkeypatch):
    vistos = []
    real = REGISTRY["create_box"].executor

    def espia(ctx, cmd_id, p):
        vistos.append(ctx.carril)
        return real(ctx, cmd_id, p)

    monkeypatch.setattr(REGISTRY["create_box"], "executor", espia)
    _doc(n_cajas=2, layout=False)
    assert vistos == [(), ()]


def test_sin_ubicacion_lee_todo_el_carril_propio(leido):
    d = _doc(n_cajas=1, layout=False)
    d.execute(LAYOUT, {})
    tipos = [e["type"] for e in leido[-1]]
    assert tipos.count("add_device") == 5 and tipos.count("add_cable") == 3
    assert "add_wire" not in tipos


def test_lee_carril_solo_en_un_comando_de_escena():
    with pytest.raises(ValueError, match="sólo un comando de escena"):
        CommandSpec("x", "x", "x", LayoutDePrueba, lambda c, i, p: None, kind="electrico",
                    lee_carril=True)


# ============================================================ la firma
def test_la_firma_cambia_con_un_dispositivo_de_su_ubicacion(leido, ejecutados):
    d = _doc()
    sigs = list(d._regen_sigs)
    k = len(sigs) - 1  # el layout es el último de escena
    ejecutados.clear()
    d.edit(_id(d, "add_device", "-F1"), {"ref": "ITM-C16-3P"}, merge=True)
    assert d._regen_sigs[:k] == sigs[:k] and d._regen_sigs[k] != sigs[k]
    assert ejecutados == [_id(d, LAYOUT)]  # A6: sólo el layout, desde el checkpoint previo
    assert leido[-1][1]["params"]["ref"] == "ITM-C16-3P"

    for edicion in ({"cantidad": 6}, {"pieza": "c2"}):  # la cantidad y la pieza también
        antes = d._regen_sigs[k]
        d.edit(_id(d, "add_device", "-X0"), edicion, merge=True)
        assert d._regen_sigs[k] != antes

    antes = d._regen_sigs[k]  # un dispositivo NUEVO en su ubicación
    d.execute("add_device", {"ref": "ITM-C2-2P", "designacion": "-F2", "ubicacion": "+TAB1"})
    assert d._regen_sigs[k] != antes
    antes = d._regen_sigs[k]  # un cable que pasa a salir de su ubicación
    d.edit(_id(d, "add_cable", "-W3"), {"desde": "+TAB1"}, merge=True)
    assert d._regen_sigs[k] != antes


def test_la_firma_no_cambia_con_un_conductor_ni_con_lo_ajeno(leido, ejecutados):
    d = _doc()
    sigs, claves = list(d._regen_sigs), sorted(d._regen_ckpts)
    ejecutados.clear()
    d.edit(_id(d, "add_wire"), {"largo_m": 2.5, "color": "BU"}, merge=True)  # un conductor
    d.execute("add_wire", {"puntos": ["-Q1:2", "-F1:1"], "color": "BK"})
    d.edit(_id(d, "add_device", "-M1"), {"ref": "MOTOR-075", "pieza": "c3"}, merge=True)  # +CAMPO
    d.execute("add_device", {"ref": "ITM-C2-2P", "designacion": "-F9", "ubicacion": "+CAMPO"})
    d.edit(_id(d, "add_cable", "-W1"), {"largo_m": 7.5}, merge=True)  # el largo no es geometría
    d.edit(_id(d, "add_cable", "-W3"), {"hasta": "+CAMPO"}, merge=True)  # sigue sin tocar +TAB1
    assert ejecutados == []
    assert d._regen_sigs == sigs and sorted(d._regen_ckpts) == claves


def test_los_ajustes_de_un_dispositivo_no_entran_a_la_firma(leido, ejecutados):
    d = _doc(n_cajas=3, layout=False)
    d.execute("add_device", {"ref": "GM-2.5-4A", "designacion": "-Q2", "ubicacion": "+TAB1",
                             "ajustes": {"Ir_A": 3.2}})
    d.execute(LAYOUT, {"ubicacion": "+TAB1"})
    sigs = list(d._regen_sigs)
    ejecutados.clear()
    d.edit(_id(d, "add_device", "-Q2"), {"ajustes": {"Ir_A": 3.6}}, merge=True)
    assert ejecutados == [] and d._regen_sigs == sigs


def test_la_firma_cuenta_la_historica_mas_el_hash_de_lo_que_lee(leido):
    d = _doc(n_cajas=2)
    escena, lane, _ = carril.separar(d.commands)
    lay = escena[-1]
    h = hashlib.sha1(d._regen_sigs[-2].encode())
    h.update(lay["id"].encode())
    h.update(json.dumps(lay["params"], sort_keys=True, default=str).encode())
    h.update(version_tag(REGISTRY, LAYOUT, lay["params"]).encode())
    plano = [{"id": e["id"], "type": e["type"], "params": dict(e["params"])}
             for e in carril.lectura(lay, lane)]
    h.update(("|carril:" + hashlib.sha1(json.dumps(plano, sort_keys=True).encode())
              .hexdigest()).encode())
    assert d._regen_sigs[-1] == h.hexdigest()
    assert d._regen_sigs[-2] == _cmd_sig(d._regen_sigs[-3], escena[-2])  # la de antes, igual


def test_un_layout_sin_dispositivos_tambien_firma_lo_que_lee(leido):
    d = Document()
    d.execute(LAYOUT, {"ubicacion": "+TAB1"})
    sola = d._regen_sigs[-1]
    assert sola != _cmd_sig("", d.commands[0])
    d.execute("add_device", {"ref": "ITM-C2-2P", "designacion": "-F1", "ubicacion": "+TAB1"})
    assert d._regen_sigs[-1] != sola


# ============================================================ checkpoint (A6)
def test_checkpoint_justo_antes_del_layout(leido, ejecutados):
    d = _doc(n_cajas=20)  # escena: set_variable + 20 cajas + layout → layout en el índice 21
    k = carril.n_escena(d.commands) - 1
    assert k == 21 and k % Document._REGEN_STRIDE != 0
    assert carril.antes_de_leer(carril.separar(d.commands).escena) == {k - 1}
    assert {k - 1, k} <= set(d._regen_ckpts)
    # sin el checkpoint extra se reanudaría del 16 y re-ejecutaría 5 cajas
    sigs = list(d._regen_sigs)
    ejecutados.clear()
    d.edit(_id(d, "add_device", "-Q1"), {"ref": "SECC-40A-3P"}, merge=True)
    assert ejecutados == [_id(d, LAYOUT)]
    # deshacer repone la caché del snapshot: la firma de antes, sin re-ejecutar nada
    ejecutados.clear()
    d.undo()
    assert ejecutados == [] and d._regen_sigs == sigs
    assert d._regen_ckpts.keys() >= {k - 1, k}


def test_una_caja_despues_del_layout_tambien_se_reejecuta(leido, ejecutados):
    d = _doc(n_cajas=2)
    d.execute("create_box", {"name": "Después", "width": 5, "depth": 5, "height": 5})
    ejecutados.clear()
    d.edit(_id(d, "add_device", "-F1"), {"ref": "ITM-C16-3P"}, merge=True)
    assert ejecutados == [_id(d, LAYOUT), d.commands[-1]["id"]]


def test_open_caliente_con_un_layout(leido, ejecutados):
    from apolo.doc.geomcache import pack, unpack

    d = _doc(n_cajas=4)
    blob = pack(d)
    assert blob is not None
    ejecutados.clear()
    abierto = Document.from_apolo_bytes(d.to_apolo_bytes(), warm=unpack(blob))
    assert ejecutados == [] and abierto._regen_sigs == d._regen_sigs
    # un dispositivo editado deja vieja la caché: el layout vuelve a correr, no se sirve viejo
    d.edit(_id(d, "add_device", "-F1"), {"ref": "ITM-C16-3P"}, merge=True)
    ejecutados.clear()
    abierto = Document.from_apolo_bytes(d.to_apolo_bytes(), warm=unpack(blob))
    assert _id(d, LAYOUT) in ejecutados and abierto._regen_sigs == d._regen_sigs
    assert leido[-1][1]["params"]["ref"] == "ITM-C16-3P"


# ============================================================ sin layout: lo de siempre
def test_sin_comando_que_lea_las_firmas_y_claves_son_las_de_siempre():
    d = _doc(n_cajas=20, layout=False)
    escena, lane, _ = carril.separar(d.commands)
    assert lane and carril.antes_de_leer(escena) == set()
    sigs, prev = [], ""
    for cmd in escena:
        prev = _cmd_sig(prev, cmd)
        sigs.append(prev)
    assert carril.firmas(escena, lane) == carril.firmas(escena) == sigs == d._regen_sigs
    n = len(escena)
    assert set(d._regen_ckpts) == {i for i in range(n) if i == n - 1 or i % 16 == 0}
