"""`create_belt_conveyor` v6 (plan faja-larga-en-tramos, F1): tramos empernados, rodillos de
retorno y perno pasante con buje en la cama.

- D1: con `tramo_max` el bastidor sale en N tramos IGUALES (largueros, cama y guardas laterales)
  unidos por placas de empalme soldadas y atornilladas por fuera del tubo, con una estación de
  patas junto a cada empalme (ninguna pata sobre una placa);
- D2: el sello pone `tramo_max = 6000` y `criterio = 6` en toda faja nueva; un log de antes no
  los trae y regenera con las mismas piezas y cotas;
- D3: rodillos de retorno cada ≤ 3 m cuando el ramal libre pasa 3 m (la ruta de la banda los
  cuenta como apoyos por afuera);
- D4: la placa del soporte de cama, con perno pasante que cruza el larguero por un buje soldado.
"""

from __future__ import annotations

import pytest
from build123d import Vector

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library.belt_conveyor_cotas import VANO_MAX
from apolo.library.belt_conveyor_retorno import PASO_RETORNO
from apolo.library.bom import bom_from_scene
from apolo.library.checks import interference_report


def _faja(**params):
    d = Document()
    cid = d.execute("create_belt_conveyor", params)
    return d, cid


def _rol(d, rol: str) -> list[str]:
    return sorted(f.id for f in d.scene.values() if f.name.split(" · ")[-1].startswith(rol))


def _bb(d, fid):
    return d.scene[fid].shape.bounding_box()


@pytest.fixture(scope="module", params=[6000, 3000], ids=["6m", "3m"])
def larga(request):
    """La faja de la clasificadora de 12 puestos (10 200 mm entre tambores)."""
    d, cid = _faja(largo=10200, tramo_max=request.param)
    return d, cid, request.param


def test_el_sello_pone_tramos_de_6_m_y_el_criterio_6():
    d, _ = _faja()
    p = d.commands[0]["params"]
    assert p["tramo_max"] == 6000 and p["criterio"] == 8  # F1b: 7 (pie, motor); F1c: 8
    props = REGISTRY["create_belt_conveyor"].model.model_json_schema()["properties"]
    assert "tramo_max" in props and "criterio" not in props  # lo visible, lo que el agente cambia
    assert REGISTRY["create_belt_conveyor"].version == 6


def test_tramos_iguales(larga):
    """Bastidor de 10 474 mm: con 6000 → 2 tramos; con 3000 → 4."""
    d, cid, tramo = larga
    n = {6000: 2, 3000: 4}[tramo]
    for i in (1, 2):
        rails = [d.scene[f"{cid}_rail{i}_{k}"] for k in range(1, n + 1)]
        assert f"{cid}_rail{i}_{n + 1}" not in d.scene
        cortes = {round(r.cut_length, 6) for r in rails}
        assert len(cortes) == 1 and next(iter(cortes)) <= tramo  # iguales y de barra comercial
    # F1c (criterio 8, D13): cama y guardas laterales en paños ≤ 3 m dentro de cada tramo (con
    # tramos de 6 m, 2 paños por tramo; con 3 m, uno)
    panos = {6000: 2 * n, 3000: n}[tramo]
    assert len(_rol(d, "Cama de deslizamiento")) == panos
    assert len(_rol(d, "Guarda lateral")) == 2 * panos
    assert len(_rol(d, "Placa de empalme")) == 4 * (n - 1)
    # la BOM pide barras ≤ tramo_max (nada de 10 474 mm)
    tubos = [r for r in bom_from_scene(d.scene) if r["ref"] == "TUBO-4X2"]
    assert tubos and all(r["longitud_mm"] <= tramo for r in tubos)
    assert sum(r["cantidad"] for r in tubos) == 2 * n
    camas = [_bb(d, f) for f in _rol(d, "Cama de deslizamiento")]
    assert all(b.size.X <= min(tramo, 3000) for b in camas)


def test_cada_empalme_con_su_pata_y_ninguna_sobre_una_placa(larga):
    d, cid, _ = larga
    placas = [_bb(d, f) for f in _rol(d, "Placa de empalme")]
    patas = [_bb(d, f) for f in _rol(d, "Pata (")]
    xs = sorted({round(b.center().X, 3) for b in patas})
    for p in placas:
        assert all(b.max.X < p.min.X or b.min.X > p.max.X for b in patas)  # no la pisa
        # una estación a menos de 150 mm de cada empalme
        assert min(abs(x - p.center().X) for x in xs) < 150.0
    assert all(b - a <= VANO_MAX + 1e-6 for a, b in zip(xs, xs[1:]))


def test_empalme_soldado_y_atornillado_por_fuera(larga):
    d, cid, _ = larga
    por_nombre = {f["name"].split(f"{cid}_", 1)[1]: f for f in d.fasteners.values()}
    pernos = [f for k, f in por_nombre.items() if k.startswith("empalme") and "_sold" not in k]
    sold = [f for k, f in por_nombre.items() if k.startswith("empalme") and k.endswith("_sold")]
    assert pernos and all(f["kind"] == "perno" and f["size"] == "M12" and f["qty"] >= 3
                          and "por fuera del tubo" in f["nota"] for f in pernos)
    assert len(sold) == 2 * len(pernos)
    assert all(f["kind"] == "soldadura" and f["throat_mm"] and f["length_mm"] for f in sold)
    # la placa sale del tubo por fuera y por debajo: ahí van los pernos, con llave
    rail = _bb(d, f"{cid}_rail2_1")
    placa = _bb(d, f"{cid}_empalme1_2_cola")
    assert placa.max.Y > rail.max.Y + 40 and placa.min.Z < rail.min.Z - 40


def test_larga_sin_interferencias_y_con_camino_a_tierra(larga):
    from apolo.assembly.connectivity import build_graph, soundness_report

    d, _, _ = larga
    r = interference_report(d.scene)
    assert not r["truncado"]
    assert [(i["a"], i["b"], i["volumen_mm3"]) for i in r["interferencias"]] == []
    rep = soundness_report(build_graph(d.scene, d.joints, d.mates, d.fasteners, d.grounds))
    assert rep["floating"] == [] and rep["n_grounded"] == len(d.scene)
    unidas = {f[k] for f in d.fasteners.values() for k in ("a", "b")}
    assert set(d.scene) <= unidas


def test_retorno_cada_3_m_en_la_larga(larga):
    d, cid, _ = larga
    rodillos = _rol(d, "Rodillo de retorno")
    xs = sorted(_bb(d, f).center().X for f in rodillos)
    half = 10200 / 2.0
    pts = [-half] + xs + [half]
    assert len(xs) >= 3 and all(b - a <= PASO_RETORNO + 1e-6 for a, b in zip(pts, pts[1:]))
    banda = d.scene[f"{cid}_banda"].shape
    for f in rodillos:
        # a 0,5 mm de la cara exterior del ramal (inclinado: el motriz va engomado): apoya, no
        # desvía la banda
        assert d.scene[f].shape.distance_to(banda) == pytest.approx(0.5, abs=0.05)
        assert d.scene[f].component == "RODILLO-50"
    soportes = _rol(d, "Soporte del rodillo de retorno")
    assert len(soportes) == 2 * len(rodillos)
    tipos = {(f["a"], f["b"]): f for f in d.fasteners.values()}
    for s in soportes:
        (u,) = [f for (a, b), f in tipos.items() if a == s and "rail" in b]
        assert u["kind"] == "perno" and "pasante" in u["nota"]
    # la cuña rodillo ↔ banda va resguardada: cajón atornillado a los soportes, con alas a 15 mm
    # bajo el ramal (ranura ≤ 20 mm, ISO 13857)
    guardas = _rol(d, "Guarda del rodillo de retorno")
    assert len(guardas) == len(rodillos)
    for g in guardas:
        assert all(f["kind"] == "perno" for (a, _b), f in tipos.items() if a == g)
        assert 14.0 < d.scene[g].shape.distance_to(banda) <= 17.0


def test_3_m_no_lleva_retorno_y_4_m_sale_en_un_tramo():
    d3, _ = _faja(largo=3000)
    assert not _rol(d3, "Rodillo de retorno")
    d4, cid = _faja(criterio=7)  # el bastidor de la F1 (el 8 parte la cama en paños: F1c)
    assert _rol(d4, "Larguero") == [f"{cid}_rail1", f"{cid}_rail2"]
    assert _rol(d4, "Cama de deslizamiento") == [f"{cid}_cama"] and not _rol(d4, "Placa de empalme")
    # el mismo bastidor de la v5 (salvo D3/D4): barra, patas y soportes en las mismas cotas
    assert [d4.scene[f"{cid}_rail{i}"].cut_length for i in (1, 2)] == [4274.3, 4274.3]
    patas = sorted({round(_bb(d4, f).center().X, 2) for f in _rol(d4, "Pata (")})
    assert patas == [-1806.1, 2000.0]
    sops = sorted(round(_bb(d4, f"{cid}_sop{k}").center().X, 2) for k in range(1, 7))
    assert sops == [-1824.2, -1080.72, -337.24, 406.24, 1149.72, 1893.2]
    assert len(_rol(d4, "Rodillo de retorno")) == 1  # 4 m entre tambores > 3 m libres
    assert interference_report(d4.scene)["interferencias"] == []


def test_la_ruta_de_la_banda_cuenta_el_rodillo_como_apoyo():
    """D3: el rodillo apoya el ramal de retorno por AFUERA (≤ 1 mm): el lazo sigue abrazando
    los dos tambores y la marcha lo hace girar con la banda."""
    from apolo.library.marcha_visual import armar
    from apolo.services.marcha_visual import extraer_marcha_visual

    d, cid = _faja(largo=4000, ancho_banda=500, altura=800)
    bb = _bb(d, f"{cid}_banda")
    banda = {"pieza": f"{cid}_banda", "junta": f"{cid}_eje_motriz", "d": (1.0, 0, 0),
             "n": (0, 0, 1.0), "a": (0, -1.0, 0), "e": (1.0, 0, 0),
             "centro_mm": [0.0, 0.0, bb.max.Z - 2.0], "radio_m": 0.055, "masa_kg": 9.0}
    vis = extraer_marcha_visual(d, [banda])
    res = {"cuerpos": [{"name": "b", "junta": f"{cid}_eje_motriz", "tipo": "continua",
                        "eje": [0, -1, 0], "piezas": [f"{cid}_tambor_motriz"]}],
           "juntas": {f"{cid}_eje_motriz": {"par": [9.0, 3.0, 2.2, 2.2, 2.2]}}}
    (f,) = armar(vis, res)["fajas"]
    assert sorted(f["envueltos"]) == [f"{cid}_tambor_cola", f"{cid}_tambor_motriz"]
    assert f["apoyos"] == [f"{cid}_ret1"]


def test_la_placa_del_soporte_de_cama_con_perno_pasante_y_buje():
    """D4: la tuerca ya no queda dentro del tubo cerrado: el perno cruza el larguero por un buje
    soldado y se aprieta por fuera; la BOM compra su largo y su tuerca."""
    from apolo.library.belt_conveyor_bastidor import pernos_soporte
    from apolo.library.belt_conveyor_cotas import cotas

    d, cid = _faja()
    p = REGISTRY["create_belt_conveyor"].model.model_validate(d.commands[0]["params"])
    (u,) = [f for f in d.fasteners.values() if f["name"] == f"{cid}_sop1_p_larg"]
    assert u["kind"] == "perno" and u["size"] == "M8" and "pasante M8x70" in u["nota"]
    c = cotas(p.largo, p.ancho_banda, p.altura, p.tambor_motriz, p.tambor_cola, p.tubo, p.tensor,
              p.motor, p.espesor_banda, True, True, p.tramo_max, p.criterio)
    x = _bb(d, f"{cid}_sop1").center().X
    rail = d.scene[f"{cid}_rail2"].shape
    for xb, zb in pernos_soporte(c, x):
        assert rail.is_inside(Vector(xb, c.rail_y, zb + 5.5))      # pared del buje
        assert not rail.is_inside(Vector(xb, c.rail_y, zb))        # su barreno
        assert not rail.is_inside(Vector(xb, c.rail_y, zb + 9.0))  # el hueco del tubo
    from apolo.library.tornilleria_declarada import filas_declaradas

    filas = filas_declaradas(d.scene, d.fasteners)
    m8 = [r for r in filas if r["ref"] == "PERNO-HEX-M8" and r.get("longitud_mm") == 70.0]
    assert m8 and not any(r.get("sin_largo") for r in m8)
    assert any(r["categoria"] == "tuercas" for r in filas)


def test_un_log_de_antes_regenera_igual():
    """Los params de hoy sin los campos nuevos: una pieza, sin retorno, con las mismas piezas y
    cotas que la v5 (cifras medidas con el código de antes de la v6)."""
    d, cid = _faja(largo=10200)
    for k in ("tramo_max", "criterio"):
        del d.commands[0]["params"][k]
    viejo = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert "tramo_max" not in viejo.commands[0]["params"]
    assert len(viejo.scene) == 108 and len(viejo.fasteners) == 145
    assert [viejo.scene[f"{cid}_rail{i}"].cut_length for i in (1, 2)] == [10474.3, 10474.3]
    assert not _rol(viejo, "Rodillo de retorno") and not _rol(viejo, "Placa de empalme")
    patas = sorted({round(_bb(viejo, f).center().X, 2) for f in _rol(viejo, "Pata (")})
    assert patas == [-4906.1, -1570.73, 1764.63, 5100.0]
    (u,) = [f for f in viejo.fasteners.values() if f["name"] == f"{cid}_sop1_p_larg"]
    assert u["nota"] == "placa del soporte atornillada al alma del larguero"
    # y es la misma geometría que pedir la v5 a mano
    ref, _ = _faja(largo=10200, tramo_max=None, criterio=5)
    assert set(ref.scene) == set(viejo.scene)
    for fid, f in ref.scene.items():
        assert viejo.scene[fid].shape.volume == pytest.approx(f.shape.volume, rel=1e-9), fid
    # editar un log de antes tampoco lo sella
    viejo.edit(cid, {**viejo.commands[0]["params"], "altura": 950})
    assert "tramo_max" not in viejo.commands[0]["params"]


def test_tramo_demasiado_corto_es_un_error_accionable():
    from apolo.doc import DocumentError
    from apolo.commands.registry import CommandError

    d = Document()
    with pytest.raises((CommandError, DocumentError), match="tramo_max"):
        d.execute("create_belt_conveyor", {"largo": 2000, "tramo_max": 1000})
