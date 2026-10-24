"""`layout_tablero` (plan V8.5 F1b: D1, D5, D8, D12, A9, A15): el tablero de la faja piloto armado.

- La faja piloto (`tests/data/tablero_piloto.json`, los 12 aparatos de +TAB1) se arma entera en
  el TABLERO-5040 con «auto»: gabinete hueco, placa, rieles con topes, canaletas, un cuerpo por
  aparato, mandos en la puerta; interferencia CERO entre sus piezas (sin exclusiones: el
  super-comando lo prueba él mismo, como la faja de banda).
- D5: la puerta abre 0–110° sin chocar (FK real + booleanas), el recorrido puro detecta un choque
  con su cifra y una pata delante de la bisagra da el error del comando.
- Ref fija que no entra, ref fija mayor, overrides (D8) y errores accionables.
- D12: sin el comando, las firmas de siempre; editar un conductor NO re-ejecuta el layout, editar
  un aparato sí (la firma de F1a).
- A9: un aparato con `pieza` no se redibuja (dentro del gabinete); fuera, error con la cifra.
- El lint del orden (D1/A15) y la BOM sin doble cobro.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from apolo.commands import registry as registry_mod
from apolo.commands.errors import CommandError
from apolo.commands.registry import REGISTRY
from apolo.commands.spec import version_tag
from apolo.doc.document import Document
from apolo.doc.errors import DocumentError
from apolo.library.checks import interference_report

PILOTO = json.loads((Path(__file__).parent / "data" / "tablero_piloto.json").read_text(encoding="utf-8"))
ERRORES = (CommandError, DocumentError)


def _dispositivos(sin_pieza: bool = True, **cambios) -> list[dict]:
    out = []
    for d in PILOTO["dispositivos"]:
        p = {"ref": d["ref"], "designacion": d["designacion"], "ubicacion": "+TAB1"}
        if "cantidad" in d:
            p["cantidad"] = d["cantidad"]
        if not sin_pieza and d.get("pieza"):
            p["pieza"] = d["pieza"]
        p.update(cambios.get(d["designacion"], {}))
        out.append({"type": "add_device", "params": p})
    return out


def _layout(**params) -> dict:
    return {"type": "layout_tablero", "params": {"ubicacion": "TAB1", **params}}


def _doc(acciones: list[dict]) -> Document:
    d = Document()
    d.execute_many(acciones)
    return d


def _cid(d: Document) -> str:
    return next(c["id"] for c in d.commands if c["type"] == "layout_tablero")


@pytest.fixture(scope="module")
def piloto() -> Document:
    return _doc(_dispositivos() + [_layout(position={"z": 1200})])


# ── la faja piloto armada ───────────────────────────────────────────────────────────────────
def test_la_faja_piloto_se_arma_entera(piloto):
    d, c = piloto, _cid(piloto)
    nuestras = {fid: f for fid, f in d.scene.items() if f.command_id == c}
    assert set(nuestras) == set(d.scene)
    assert d.scene[f"{c}_gabinete"].component == "TABLERO-5040"  # «auto»: el más chico
    assert d.scene[f"{c}_gabinete"].name == "Tablero +TAB1 · Gabinete"
    for des in ("F1", "F2", "T1", "T2", "K1", "Q1", "S0", "S1", "S2", "H1", "H2"):
        assert f"{c}_d_{des}" in d.scene, des
    assert {f"{c}_d_X0_1", f"{c}_d_X0_2"} <= set(d.scene)  # un borne por unidad
    assert sum(1 for k in d.scene if k.startswith(f"{c}_riel_")) == 3
    assert sum(1 for k in d.scene if k.startswith(f"{c}_tope_")) == 6
    assert f"{c}_tapa_3" in d.scene  # la bornera cierra con su tapa
    assert d.scene[f"{c}_riel_1"].component == "RIEL-DIN-TH35-7.5"
    assert d.scene[f"{c}_riel_1"].cut_length == pytest.approx(235.0)
    # el gabinete es la caja del catálogo y todo cae dentro de ella (el frente, con la puerta)
    caja = d.scene[f"{c}_gabinete"].shape.bounding_box()
    assert (round(caja.size.X), round(caja.size.Y + 1.5), round(caja.size.Z)) == (500, 200, 400)
    for fid, f in nuestras.items():
        bb = f.shape.bounding_box()
        if fid.startswith(f"{c}_d_") and fid[len(c) + 3:] in ("Q1", "S0", "S1", "S2", "H1", "H2"):
            assert bb.min.Y < caja.min.Y - 1.5, fid  # asoma por delante de la puerta
            continue
        assert caja.min.X - 1e-6 <= bb.min.X and bb.max.X <= caja.max.X + 1e-6, fid
        assert caja.min.Z - 1e-6 <= bb.min.Z and bb.max.Z <= caja.max.Z + 1e-6, fid
    # interferencia CERO entre sus piezas, sin excluir nada
    r = interference_report(d.scene)
    assert r["interferencias"] == [] and not r["truncado"]


def test_la_puerta_es_una_junta_y_sus_mandos_la_siguen(piloto):
    d, c = piloto, _cid(piloto)
    j = d.joints[f"{c}_puerta"]
    assert (j["type"], j["parent"], j["child"], j["lower"], j["upper"]) == (
        "giratoria", f"{c}_gabinete", f"{c}_puerta", 0.0, 110.0)
    assert j["axis"] == [0.0, 0.0, -1.0] and j["origin"][:2] == [-250.0, -100.0]  # bisagra izquierda
    assert j["recorrido"] == {"de_deg": 0.0, "a_deg": 110.0, "angulos_revisados": 111, "choques": 0}
    fijas = {v["child"] for v in d.joints.values() if v["type"] == "fija"}
    assert fijas == {f"{c}_d_{x}" for x in ("Q1", "S0", "S1", "S2", "H1", "H2")}
    assert all(d.joints[f"{c}_jf_d_{x}"]["parent"] == f"{c}_puerta" for x in ("Q1", "S0"))
    # lo de adentro, sostenido: placa a los espárragos, rieles a la placa, aparatos al riel
    f = d.fasteners
    assert (f[f"{c}_u_placa"]["a"], f[f"{c}_u_placa"]["b"]) == (f"{c}_placa", f"{c}_gabinete")
    assert f[f"{c}_u_riel_1"]["b"] == f"{c}_placa" and f[f"{c}_u_riel_1"]["size"] == "M4"
    assert (f[f"{c}_u_d_F1"]["b"], f[f"{c}_u_d_F1"]["kind"]) == (f"{c}_riel_1", "contacto")
    assert (f[f"{c}_u_d_T2"]["b"], f[f"{c}_u_d_T2"]["qty"]) == (f"{c}_placa", 4)  # columna de placa


def test_la_puerta_abre_sin_chocar_en_todo_su_recorrido(piloto):
    from apolo.robotics.pose import posed_shapes

    d, c = piloto, _cid(piloto)
    junta = f"{c}_puerta"
    movil = {f"{c}_puerta"} | {v["child"] for v in d.joints.values() if v["type"] == "fija"}
    frente = d.scene[f"{c}_gabinete"].shape.bounding_box().min.Y
    for ang in range(0, 111, 10):
        posed, avisos = posed_shapes(d, {junta: ang})
        assert avisos == []
        excl = {frozenset((a, b)) for a in movil for b in movil}  # lo que gira junto
        r = interference_report(d.scene, shapes_override=posed, exclude_pairs=excl)
        assert r["interferencias"] == [], (ang, r["interferencias"][:3])
    abierta = posed_shapes(d, {junta: 90})[0][f"{c}_puerta"].bounding_box()
    assert abierta.max.Y <= frente + 1e-6 and abierta.min.Y < frente - 400  # abre hacia AFUERA
    seta = posed_shapes(d, {junta: 90})[0][f"{c}_d_S0"].bounding_box()
    assert seta.max.Y < frente  # el mando se fue con la puerta


# ── D5: el recorrido puro y la puerta que pega ─────────────────────────────────────────────
def test_el_recorrido_detecta_un_choque_con_su_cifra(piloto):
    from apolo.commands.tablero import dispositivos, plan
    from apolo.commands.models_tablero import LayoutTableroParams
    from apolo.commands.state import ExecContext, RegenState
    from apolo.doc.carril import lectura
    from apolo.library.electrico.armado import Caja, Pieza
    from apolo.library.electrico.recorrido_puerta import recorrer

    d = piloto
    cmd = next(x for x in d.commands if x["type"] == "layout_tablero")
    ctx = ExecContext(RegenState(variables=dict(d.variables_raw)), {},
                      lectura(cmd, [x for x in d.commands if x["type"] == "add_device"]))
    _, arm, _ = plan(LayoutTableroParams(ubicacion="+TAB1"), dispositivos(ctx, "+TAB1"))
    assert recorrer(arm) == (None, 111)
    # un poste fijo delante del gabinete, a 300 mm de la bisagra: la puerta lo barre
    poste = Pieza("poste", "Poste de prueba", "placa", Caja(-60, -40, -320, -300, -100, 100))
    choque, n = recorrer(replace(arm, piezas=arm.piezas + (poste,)))
    assert n == 111 and choque.fijo == "Poste de prueba" and choque.movil == "Puerta"
    assert 20 < choque.angulo_deg < 60 and choque.penetracion_mm > 1


def test_una_pata_delante_de_la_bisagra_no_deja_abrir():
    pata = {"type": "create_box", "params": {"name": "Pata", "width": 40, "depth": 40, "height": 300,
                                             "position": {"x": -50, "y": -300, "z": 0}}}
    with pytest.raises(ERRORES) as exc:
        _doc([pata] + _dispositivos() + [_layout()])
    msg = str(exc.value)
    assert "la puerta no abre" in msg and "«Pata»" in msg and "°" in msg and "mm³" in msg


# ── gabinete, overrides y errores (D1, D8) ──────────────────────────────────────────────────
def test_con_una_ref_que_no_alcanza_dice_cuanto_falta_y_donde_entra():
    with pytest.raises(ERRORES) as exc:
        _doc(_dispositivos() + [_layout(gabinete="GAB-6040")])
    msg = str(exc.value)
    assert "no entra en GAB-6040" in msg and "con «auto» entra en TABLERO-5040" in msg


def test_ref_fija_mayor_y_bisagra_derecha():
    d = _doc(_dispositivos() + [_layout(gabinete="GAB-8060", bisagra="derecha")])
    c = _cid(d)
    assert d.scene[f"{c}_gabinete"].component == "GAB-8060"
    j = d.joints[f"{c}_puerta"]
    assert j["axis"] == [0.0, 0.0, 1.0] and j["origin"][0] == pytest.approx(300.0)
    # los mandos, lejos de la bisagra: ahora a la izquierda
    assert d.scene[f"{c}_d_Q1"].shape.bounding_box().center().X < 0


def test_un_gabinete_declarado_es_el_de_auto():
    disp = _dispositivos() + [{"type": "add_device", "params": {
        "ref": "GAB-8060", "designacion": "-U1", "ubicacion": "+TAB1"}}]
    d = _doc(disp + [_layout()])
    assert d.scene[f"{_cid(d)}_gabinete"].component == "GAB-8060"
    with pytest.raises(ERRORES, match="el circuito declara el gabinete -U1 = GAB-8060"):
        _doc(disp + [_layout(gabinete="TABLERO-5040")])


def test_override_de_orden_y_designacion_desconocida():
    d = _doc(_dispositivos() + [_layout(overrides={"-F2": {"orden": 1}})])
    c = _cid(d)
    x = {k: d.scene[f"{c}_d_{k}"].shape.bounding_box().min.X for k in ("F1", "F2")}
    assert x["F2"] < x["F1"]
    with pytest.raises(ERRORES) as exc:
        _doc(_dispositivos() + [_layout(overrides={"-Q9": {"orden": 1}})])
    assert "override «-Q9»: no hay ese aparato en el tablero" in str(exc.value)


def test_las_expresiones_de_un_dispositivo_se_resuelven_en_el_layout():
    """A15: con las variables de su punto del log (el documento sube los set_variable a la
    cabecera); una que no existe es error accionable del layout."""
    var = {"type": "set_variable", "params": {"name": "n", "expression": "3"}}
    d = _doc(_dispositivos(**{"-X0": {"cantidad": "=n"}}) + [_layout(), var])
    assert f"{_cid(d)}_d_X0_3" in d.scene
    with pytest.raises(ERRORES) as exc:
        _doc(_dispositivos(**{"-X0": {"cantidad": "=nada"}}) + [_layout()])
    assert "no valida en este punto del log" in str(exc.value)


def test_la_rotacion_que_tuerce_la_bisagra_es_error():
    with pytest.raises(ERRORES, match="no alineado con un eje del mundo"):
        _doc(_dispositivos() + [_layout(rotation={"x": 30})])


def test_girado_en_z_la_puerta_sigue_abriendo():
    d = _doc(_dispositivos() + [_layout(rotation={"z": 90}, position={"x": 1000})])
    j = d.joints[f"{_cid(d)}_puerta"]
    assert j["axis"] == [0.0, 0.0, -1.0] and j["recorrido"]["choques"] == 0


# ── D12: vigencia y firma ───────────────────────────────────────────────────────────────────
def test_sin_el_comando_las_firmas_de_siempre():
    sin = {k: v for k, v in REGISTRY.items() if k != "layout_tablero"}
    for tipo in ("insert_project", "create_belt_conveyor", "create_roller_conveyor"):
        assert version_tag(REGISTRY, tipo) == version_tag(sin, tipo)
    assert REGISTRY["layout_tablero"].version == 1 and REGISTRY["layout_tablero"].lee_carril


@pytest.fixture
def ejecutados(monkeypatch):
    llamadas: list[str] = []
    real = registry_mod.run_executor

    def contar(spec, ctx, cmd_id, model):
        llamadas.append(spec.type)
        return real(spec, ctx, cmd_id, model)

    monkeypatch.setattr(registry_mod, "run_executor", contar)
    return llamadas


def test_editar_un_conductor_no_reejecuta_el_layout_y_un_aparato_si(ejecutados):
    acciones = _dispositivos() + [
        {"type": "add_wire", "params": {"puntos": ["-F1:2", "-T1:L"], "color": "BK"}},
        _layout()]
    d = _doc(acciones)
    c = _cid(d)
    hilo = next(x["id"] for x in d.commands if x["type"] == "add_wire")
    ejecutados.clear()
    d.edit(hilo, {"puntos": ["-F1:2", "-T1:L"], "color": "BU"})
    assert "layout_tablero" not in ejecutados
    x0 = next(x["id"] for x in d.commands if x["params"].get("designacion") == "-X0")
    ejecutados.clear()
    d.edit(x0, {"ref": "BORNE-PE-4", "designacion": "-X0", "ubicacion": "+TAB1", "cantidad": 3})
    assert ejecutados.count("layout_tablero") == 1
    assert f"{c}_d_X0_3" in d.scene


# ── A9: lo ya modelado no se redibuja ───────────────────────────────────────────────────────
def test_un_aparato_con_pieza_no_se_redibuja(piloto):
    c = _cid(piloto)
    centro = piloto.scene[f"{c}_d_T2"].shape.bounding_box().center()
    vfd = {"type": "insert_component", "params": {
        "component": "VFD-2K2-220", "name": "Variador",
        "position": {"x": centro.X, "y": centro.Y, "z": centro.Z}}}
    d = _doc([vfd] + _dispositivos(**{"-T2": {"pieza": "$1"}}) + [_layout(position={"z": 1200})])
    c2, vid = _cid(d), d.commands[0]["id"]
    assert f"{c2}_d_T2" not in d.scene and vid in d.scene
    assert d.fasteners[f"{c2}_u_d_T2"]["a"] == vid  # se atornilla a la placa igual
    r = interference_report(d.scene)
    assert r["interferencias"] == []
    # la BOM: el variador una vez (su pieza), y nada de lo dibujado se cobra otra vez por el carril
    from apolo.library.bom import bom_from_scene
    from apolo.services.electrico import filas_bom, piezas_sin_ligar, modelo

    escena = [f for f in bom_from_scene(d.scene) if f["ref"] == "VFD-2K2-220"]
    assert [f["cantidad"] for f in escena] == [1]
    assert filas_bom(d) == [] and piezas_sin_ligar(d, modelo(d)) == []


def test_una_pieza_fuera_del_gabinete_es_error_con_la_cifra():
    seta = {"type": "insert_component", "params": {"component": "ESTOP-40", "name": "Seta de la cola",
                                                   "position": {"x": 2000, "y": 0, "z": 0}}}
    with pytest.raises(ERRORES) as exc:
        _doc([seta] + _dispositivos(**{"-S0": {"pieza": "$1"}}) + [_layout()])
    msg = str(exc.value)
    assert "-S0 está ligado a la pieza" in msg and "mm del gabinete TABLERO-5040" in msg
    assert "un mando de puerta va EN la puerta" in msg and "muévela a su lugar" in msg


# ── el lint del orden y la BOM ──────────────────────────────────────────────────────────────
def test_el_lint_avisa_lo_que_viene_despues_del_layout(piloto):
    from apolo.services.electrico import reglas_erc

    assert not [r for r in reglas_erc(piloto) if r["regla"] == "layout del tablero al final"]
    caja = {"type": "create_box", "params": {"name": "Soporte", "width": 10, "depth": 10, "height": 10,
                                             "position": {"x": 2000}}}
    d = _doc(_dispositivos() + [_layout(), caja])
    c = _cid(d)
    d.execute("ground", {"name": "anclaje_tablero", "feature": f"{c}_gabinete"})
    avisos = [r for r in reglas_erc(d) if r["regla"] == "layout del tablero al final"]
    assert len(avisos) == 1 and avisos[0]["estado"] == "aviso"
    det = avisos[0]["detalle"]
    assert "(create_box)" in det and "ground" not in det and f"remove_commands(['{c}'])" in det


def test_lo_dibujado_no_se_cobra_dos_veces(piloto):
    from apolo.library.bom import bom_from_scene
    from apolo.services.electrico import filas_bom, modelo, piezas_sin_ligar
    from apolo.services.tablero import dibujados

    m = modelo(piloto)
    assert set(dibujados(piloto, m)) == {d["designacion"] for d in PILOTO["dispositivos"]}
    assert filas_bom(piloto) == [] and piezas_sin_ligar(piloto, m) == []
    filas = {f["ref"]: f["cantidad"] for f in bom_from_scene(piloto.scene)}
    assert filas["BORNE-PE-4"] == 2 and filas["VFD-2K2-220"] == 1 and filas["TABLERO-5040"] == 1
