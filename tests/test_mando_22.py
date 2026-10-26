"""La serie Ø22 con su agujero y su corte redondo (plan pedidos-de-extensiones-ii, F1: D1–D3).

- D1: toda ref con `specs.agujero` (la seta y los pulsadores, selectores y pilotos Ø22) sale
  círculo en la puerta, con el Ø de SU ficha; lo demás, su recorte o la huella de su caja. El
  dato se lee al cargar (mal escrito no carga) y una caja con agujero redondo no carga.
- D2: el builder `mando_22` (bisel y frente delante, cuello Ø22, portacontactos detrás) da la
  huella de 30 × 30 × (delante + detras) con el origen en la cara de apoyo y las anclas de la seta;
  sus `delante`/`detras` son los de `tablero.puerta`.
- La faja piloto (`tests/data/tablero_piloto.json`): la colocación sigue entrando en el 500 × 400,
  la puerta tiene un agujero redondo por mando Ø22 y ningún mando se mete en la chapa.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from build123d import Box, GeomType, Pos

from apolo.commands.tablero_geom import huecos_por_ref
from apolo.library.builders_mandos import CUELLO_D, mando_22
from apolo.library.catalog import CATALOG, build_component
from apolo.library.electrico.ficha_tablero import (
    FichaTablero,
    MarcoPuerta,
    agujero_mm,
    parse_tablero,
    verificar_agujero,
)

PILOTO = json.loads((Path(__file__).parent / "data" / "tablero_piloto.json").read_text(encoding="utf-8"))
SERIE_22 = ("PULS-22-VERDE-NA", "PULS-22-ROJO-NC", "PULS-22-AZUL-NA", "SEL-22-2POS-1NA",
            "SEL-22-3POS-2NA", "PILOTO-24V-VERDE", "PILOTO-24V-ROJO", "PILOTO-24V-AMBAR")
MANDOS_PILOTO = ("S0", "S1", "S2", "H1", "H2")


# ── D1: el agujero es un dato de la ficha ──────────────────────────────────────────────────
def test_toda_la_serie_22_trae_su_agujero_con_la_fuente_leida():
    for ref in SERIE_22:
        c = CATALOG[ref]
        assert c.specs["agujero"] == "Ø22,5" and c.specs["cotas_verificadas"] is False, ref
        assert "diámetro de montaje 22,5 mm" in c.electrico.fuente, ref
        assert c.familia == "mando_22", ref


def test_toda_ref_con_agujero_sale_circulo_en_la_puerta():
    con = sorted(r for r, c in CATALOG.items() if c.specs.get("agujero") is not None)
    assert set(SERIE_22) | {"ESTOP-40", "ESTOP-40-2NC"} <= set(con)
    huecos = huecos_por_ref(con, CATALOG)
    assert huecos == {r: ("circulo", agujero_mm(CATALOG[r].specs, r)) for r in con}
    assert {h[1] for h in huecos.values()} == {22.5}
    # sin agujero: la huella de su caja (no va) o el recorte de su ficha
    otros = huecos_por_ref(["SECC-25A-3P", "HMI-7IN-24VDC"], CATALOG)
    assert "SECC-25A-3P" not in otros and otros["HMI-7IN-24VDC"][0] == "rect"


@pytest.mark.parametrize("texto, d", [("Ø22,5", 22.5), ("Ø22.5", 22.5), ("22,3", 22.3), (" Ø 30 ", 30.0)])
def test_el_agujero_se_lee_con_coma_o_punto(texto, d):
    assert agujero_mm({"agujero": texto}) == d


def test_sin_agujero_es_none_y_mal_escrito_no_carga():
    assert agujero_mm({}) is None and agujero_mm(None) is None
    for malo in ("serie Ø22", "Ø0", "", "Ø-3"):
        with pytest.raises(ValueError, match=r"specs\.agujero .*como «Ø22,5»"):
            agujero_mm({"agujero": malo}, "X")


def test_una_caja_con_agujero_redondo_no_carga():
    puerta = FichaTablero(puerta=MarcoPuerta(12.0, 38.0))
    with pytest.raises(ValueError, match=r"la caja cruzaría la chapa; usa un builder con cuello"):
        verificar_agujero({"agujero": "Ø22,5"}, "box", puerta, "X")
    verificar_agujero({"agujero": "Ø22,5"}, "mando_22", puerta, "X")  # con cuello, sí
    verificar_agujero({"agujero": "Ø22,5"}, "box", None, "X")         # fuera de la puerta, no aplica


# ── D2: el builder con cuello ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ref", SERIE_22)
def test_la_huella_es_la_de_la_caja_y_el_origen_la_cara_de_apoyo(ref):
    c = CATALOG[ref]
    forma = build_component(ref)[0]
    bb = forma.bounding_box()
    p = c.tablero.puerta
    assert len(forma.solids()) == 1
    assert (round(bb.size.X, 3), round(bb.size.Y, 3)) == (30.0, 30.0)
    assert (round(bb.min.Z, 3), round(bb.max.Z, 3)) == (-p.detras_mm, p.delante_mm)
    assert c.anchors == {"montaje": {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, -1.0]},
                         "agujero": {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, -1.0]}}


def test_por_la_chapa_pasa_solo_el_cuello():
    forma = build_component("PULS-22-VERDE-NA")[0]
    chapa = forma & (Pos(0, 0, -1.0) * Box(100, 100, 1.5))  # una puerta de 1,5 mm
    bb = chapa.bounding_box()
    assert CUELLO_D < 22.5 and round(bb.size.X, 3) == round(bb.size.Y, 3) == CUELLO_D


def test_el_builder_rechaza_lo_que_no_arma():
    with pytest.raises(ValueError, match="tipo «boton» desconocido"):
        mando_22(tipo="boton")
    with pytest.raises(ValueError, match="panel_mm 8 fuera de 1–6 mm"):
        mando_22(panel_mm=8)
    with pytest.raises(ValueError, match="no cubre el bisel"):
        mando_22(width=25)


def test_el_frente_partido_es_el_de_la_ficha_de_armado():
    params = {"tipo": "pulsador", "width": 30, "height": 30, "delante": 12, "detras": 38}
    t = parse_tablero({"puerta": {"delante_mm": 12, "detras_mm": 38}}, "P", familia="mando_22",
                      params=params, montaje="puerta")
    assert (t.puerta.delante_mm, t.puerta.detras_mm) == (12.0, 38.0)
    with pytest.raises(ValueError, match=r"puerta\.detras_mm: 40 no es el param `detras`"):
        parse_tablero({"puerta": {"delante_mm": 12, "detras_mm": 40}}, "P", familia="mando_22",
                      params=params, montaje="puerta")


# ── la faja piloto ─────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def piloto():
    from apolo.doc.document import Document

    acciones = [{"type": "add_device", "params": {"ref": d["ref"], "designacion": d["designacion"],
                                                  "ubicacion": "+TAB1",
                                                  **({"cantidad": d["cantidad"]} if "cantidad" in d else {})}}
                for d in PILOTO["dispositivos"]]
    d = Document()
    d.execute_many(acciones + [{"type": "layout_tablero", "params": {"ubicacion": "TAB1"}}])
    return d, next(c["id"] for c in d.commands if c["type"] == "layout_tablero")


def test_la_piloto_entra_y_su_puerta_corta_redondo_cada_mando_22(piloto):
    from apolo.commands.tablero import dispositivos, plan
    from apolo.commands.models_tablero import LayoutTableroParams

    d, c = piloto
    assert d.scene[f"{c}_gabinete"].component == "TABLERO-5040"  # sigue entrando en el 500 × 400
    cmd = next(x for x in d.commands if x["type"] == "layout_tablero")

    class _Ctx:  # lo que `dispositivos` lee del ExecContext
        carril = [x for x in d.commands if x["type"] == "add_device"]
        variables: dict = {}

    _, arm, _ = plan(LayoutTableroParams.model_validate(cmd["params"]), dispositivos(_Ctx, "TAB1"))
    formas = {h.clave: (h.forma, h.medidas[-1] if h.forma == "circulo" else None) for h in arm.huecos}
    assert formas == {**{m: ("circulo", 22.5) for m in MANDOS_PILOTO}, "Q1": ("rect", None)}
    puerta = d.scene[f"{c}_puerta"].shape
    cilindros = [f for f in puerta.faces() if f.geom_type == GeomType.CYLINDER]
    assert len(cilindros) == len(MANDOS_PILOTO)  # un agujero pasante redondo por mando


def test_ningun_mando_se_mete_en_la_chapa_de_la_puerta(piloto):
    d, c = piloto
    puerta = d.scene[f"{c}_puerta"].shape
    for m in MANDOS_PILOTO:
        mando = d.scene[f"{c}_d_{m}"].shape
        assert (mando & puerta).volume < 1e-3, m  # el cuello pasa por su agujero sin tocarlo
        assert mando.bounding_box().min.Y < puerta.bounding_box().min.Y  # el frente asoma
