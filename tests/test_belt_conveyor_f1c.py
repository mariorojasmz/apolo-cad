"""`create_belt_conveyor` F1c (plan faja-larga-en-tramos, D10–D14; criterio 8).

Lo que el revisor de taller a ciegas encontró en la plantilla del criterio 7 (piloto
clasificadora-manual, 10,2 m) y vale para toda faja:

- D10/D11: la brida de la UCF y el marco del UCT a ROSCA en su placa (la tuerca ya no cae dentro
  del larguero), con su cuenta;
- D12: cada unión `perno` con sus agujeros en la geometría (la MISMA medida de `union.agujeros`);
  nada se atornilla a un tubo cerrado con la tuerca adentro; la cama del espesor de su cuenta;
- D13: cama y guardas laterales en paños ≤ 3 m;
- D14: la BOM compra cada tornillo de la plantilla con su largo;
- lo sellado con el criterio 7 regenera igual (cifras medidas con el código de antes).
"""

from __future__ import annotations

import hashlib
import re

import pytest

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library.catalog import CATALOG
from apolo.library.checks import interference_report


def _faja(**params):
    d = Document()
    cid = d.execute("create_belt_conveyor", params)
    return d, cid


def _rol(d, rol: str) -> list[str]:
    return sorted(f.id for f in d.scene.values() if f.name.split(" · ")[-1].startswith(rol))


def _plan(d):
    from apolo.library.belt_conveyor import belt_conveyor_parts

    q = REGISTRY["create_belt_conveyor"].model.model_validate(d.commands[0]["params"])
    return belt_conveyor_parts(q.largo, q.ancho_banda, q.altura, q.tambor_motriz, q.tambor_cola,
                               q.tubo, None if q.tensor == "ninguno" else q.tensor,
                               None if q.motor == "ninguno" else q.motor, q.espesor_banda,
                               q.guardas, q.cierres, q.tramo_max, q.criterio, q.lado_abierto)


@pytest.fixture(scope="module", params=["4m", "10m"])
def faja(request):
    """La de 4 m por defecto y la del piloto clasificadora-manual (10,2 m, banda a 850 mm, en
    tramos de 6 m, abierta del lado de los operarios)."""
    if request.param == "4m":
        return _faja()
    return _faja(largo=10200, altura=850, lado_abierto="-y")


def _es_tubo(feat) -> bool:
    comp = CATALOG.get(feat.component or "")
    return comp is not None and comp.category == "tubos_estructurales"


def test_el_sello_pone_el_criterio_8():
    d, _ = _faja()
    assert d.commands[0]["params"]["criterio"] == 8


# ------------------------------------------------------------------ D12: agujeros
def test_cada_union_atornillada_tiene_sus_agujeros(faja):
    """La MISMA medida de `union.agujeros` (que no mira las uniones internas de una plantilla):
    toda pieza a medida de una unión `perno` tiene sus agujeros compatibles en la zona."""
    from apolo.services.calidad_agujeros import _MARGEN_MM, _PRISIONERO_RE, _cruce, _Medidor, \
        _metrica

    d, cid = faja
    med = _Medidor(d)
    faltan, juzgadas = [], 0
    for f in d.fasteners.values():
        if f["kind"] != "perno":
            continue
        for x, y in ((f["a"], f["b"]), (f["b"], f["a"])):
            zona = _cruce(med.caja(x), med.caja(y), _MARGEN_MM)
            p = med.pieza(x, _metrica(f["size"]), zona, None,
                          bool(_PRISIONERO_RE.search(f.get("nota") or "")))
            if p["juzgada"]:
                juzgadas += 1
                if p["agujeros"] < f["qty"]:
                    faltan.append((f["name"], x, p["agujeros"], f["qty"]))
    assert faltan == []
    assert juzgadas > 45


def test_ninguna_tuerca_dentro_de_un_tubo_cerrado(faja):
    """Lo que se atornilla a un tubo de catálogo (largueros, soportes de cama) lo cruza de lado a
    lado por un buje (agujeros coaxiales en sus DOS paredes, nota «pasante») o va a espárragos
    soldados por fuera (el tubo, sin agujero en la zona). Nada más llega a un tubo."""
    from apolo.services.calidad_agujeros import _cruce, _Medidor

    d, cid = faja
    med = _Medidor(d)
    vistas = {"pasante": 0, "espárrago": 0}
    for f in d.fasteners.values():
        if f["kind"] != "perno":
            continue
        for tubo, otra in ((f["a"], f["b"]), (f["b"], f["a"])):
            if not _es_tubo(d.scene[tubo]):
                continue
            nota = f["nota"]
            zona = _cruce(med.caja(tubo), med.caja(otra), 1.0)
            d_nom = float(f["size"][1:])
            suyos = med.agujeros(tubo, d_nom, zona)
            bb = d.scene[tubo].shape.bounding_box()
            if "pasante" in nota:
                vistas["pasante"] += 1
                eje = [max(range(3), key=lambda k: abs(a["eje"][k])) for a in suyos]
                lado = (bb.size.X, bb.size.Y, bb.size.Z)
                cruzan = [a for a, k in zip(suyos, eje) if a["hi"][k] - a["lo"][k] >= lado[k] - 1.0]
                assert len(cruzan) >= f["qty"], (f["name"], tubo, len(cruzan))
            else:
                assert re.search(r"espárrago .* soldado", nota), (f["name"], nota)
                vistas["espárrago"] += 1
                assert suyos == [], (f["name"], tubo)
    assert vistas["pasante"] > 30 and vistas["espárrago"] >= 4


# ------------------------------------------------------------------ D10, D11: rosca en placa
def test_chumacera_y_tensor_a_rosca_en_su_placa(faja):
    from apolo.library.belt_conveyor_tambores_taller import PLACA_TENSOR_T
    from apolo.services.calidad_agujeros import agujeros_de

    d, cid = faja
    roscas = {r["union"]: r for r in _plan(d).calculos["roscas"]}
    for suf, perno in (("chum_m1_placa", "M10x25 DIN 933"), ("tensor1_placa", "M12x65 DIN 933")):
        r = roscas[suf]
        assert r["ok"] and r["perno"] == perno
        assert r["pide_mm"] <= r["enganche_mm"] <= r["placa_mm"] - 0.5  # la punta, en la placa
    por_nombre = {f["name"].split(f"{cid}_", 1)[1]: f for f in d.fasteners.values()}
    u = por_nombre["tensor1_placa"]
    assert u["b"] == f"{cid}_tensor1_placa" and "tensor1_larg" not in por_nombre
    assert por_nombre["tensor1_placa_sold"]["kind"] == "soldadura"
    assert "M12x65 DIN 933 a la rosca de la placa porta-tensor" in u["nota"]
    assert "M10x25 DIN 933 a la rosca de la placa porta-chumacera" in por_nombre[
        "chum_m1_placa"]["nota"]
    # la geometría: 4 agujeros a la broca de machuelo (M10 → Ø8,5; M12 → Ø10,2)
    for fid, broca in ((f"{cid}_chum_m1_placa", 8.5), (f"{cid}_tensor1_placa", 10.2)):
        assert sum(abs(a["d"] - broca) < 0.05 for a in agujeros_de(d.scene[fid].shape)) == 4
    # el marco del tensor apoya en su placa, no en el larguero
    rail = d.scene[f"{cid}_rail1" if f"{cid}_rail1" in d.scene else f"{cid}_rail1_1"]
    tensor = d.scene[f"{cid}_tensor1"].shape.bounding_box()
    assert tensor.max.Y == pytest.approx(rail.shape.bounding_box().min.Y - PLACA_TENSOR_T)


# ------------------------------------------------------------------ D13: paños; D12: cama
def test_cama_y_guardas_laterales_en_panos_de_3_m(faja):
    from apolo.library.belt_conveyor_bastidor import x_soportes

    d, cid = faja
    panos = _rol(d, "Cama de deslizamiento") + _rol(d, "Guarda lateral") + _rol(
        d, "Guarda cubre-ranura")
    assert panos and all(d.scene[f].shape.bounding_box().size.X <= 3000.0 for f in panos)
    # cada paño de cama apoya en un soporte junto a cada punta (a 40 mm en una junta; en los
    # extremos de la faja, corrido lo que pide la tuerca del perno pasante)
    sops = x_soportes(_plan_cotas(d))
    for f in _rol(d, "Cama de deslizamiento"):
        bb = d.scene[f].shape.bounding_box()
        assert any(40.0 - 1e-6 <= x - bb.min.X <= 250.0 for x in sops)
        assert any(40.0 - 1e-6 <= bb.max.X - x <= 250.0 for x in sops)


def _plan_cotas(d):
    from apolo.library.belt_conveyor_cotas import cotas

    q = REGISTRY["create_belt_conveyor"].model.model_validate(d.commands[0]["params"])
    return cotas(q.largo, q.ancho_banda, q.altura, q.tambor_motriz, q.tambor_cola, q.tubo,
                 None if q.tensor == "ninguno" else q.tensor,
                 None if q.motor == "ninguno" else q.motor, q.espesor_banda, q.guardas,
                 q.cierres, q.tramo_max, q.criterio, q.lado_abierto)


def test_la_cama_del_espesor_de_su_cuenta(faja):
    """Viga continua sobre sus soportes con 50 kg/m de diseño + banda + chapa: 4 mm. Las de 2 a 3
    mm tampoco dan la flecha (manda el voladizo de 40 mm de la punta del paño: el escalón en la
    junta) y no dejan a ras la cabeza del DIN 7991."""
    d, cid = faja
    calc = _plan(d).calculos["cama"]
    assert calc["ok"] and calc["espesor_mm"] == 4.0
    assert calc["flecha_mm"] <= calc["flecha_adm_mm"] and calc["sigma_mpa"] <= calc["sigma_adm_mpa"]
    assert [x["espesor_mm"] for x in calc["descartadas"]] == [2.0, 2.5, 3.0]
    assert all(x["flecha_mm"] > x["flecha_adm_mm"] and "a ras" in x["motivo"]
               for x in calc["descartadas"])
    for f in _rol(d, "Cama de deslizamiento"):
        assert d.scene[f].shape.bounding_box().size.Z == pytest.approx(4.0)
    assert calc["peso_pano_max_kg"] < 50.0  # 148 kg con 6 mm en un tramo de 5 m


# ------------------------------------------------------------------ D14: BOM
def test_la_bom_compra_cada_tornillo_con_su_largo(faja):
    from apolo.services.bom_filas import filas_extra

    d, _ = faja
    filas = filas_extra(d)
    assert filas and [r["descripcion"] for r in filas if r.get("sin_largo")] == []
    desc = " | ".join(r["descripcion"] for r in filas)
    for que in ("Espárrago M6 ISO 13918", "Tornillo avellanado M6 DIN 7991",
                "Prisionero M8 DIN 916", "PERNO-HEX-M10", "PERNO-HEX-M12", "TUERCA-M6"):
        assert que in desc
    # cada perno de la plantilla lleva su designación en la nota
    for f in d.fasteners.values():
        if f["kind"] == "perno":
            assert re.search(rf"\b{f['size']}x\d+", f["nota"]), (f["name"], f["nota"])


def test_la_bom_lee_prisionero_esparrago_y_avellanado_con_largo():
    from apolo.library.tornilleria_declarada import _lo_declarado

    casos = {"prisionero M8x25 DIN 916": ("Prisionero M8 DIN 916", 25.0, False),
             "espárrago M6x12 ISO 13918 soldado + tuerca": ("Espárrago M6 ISO 13918", 12.0, True),
             "tornillo M6x65 DIN 7991 + tuerca, pasante": ("Tornillo avellanado M6 DIN 7991",
                                                           65.0, True),
             "tornillo autorroscante M6x16": ("Tornillo autorroscante M6", 16.0, False)}
    for nota, (desc, largo, tuerca) in casos.items():
        size = re.search(r"M\d+", nota).group(0)
        fij, con_tuerca = _lo_declarado({"size": size, "nota": nota})
        assert (fij["descripcion"], fij["largo"], con_tuerca) == (desc, largo, tuerca)
    # sin designación, como antes: sin largo
    assert _lo_declarado({"size": "M8", "nota": "chaveta + prisionero"})[0]["largo"] is None


# ------------------------------------------------------------------ armado
def test_sin_interferencias_y_a_tierra(faja):
    from apolo.assembly.connectivity import build_graph, soundness_report

    d, _ = faja
    r = interference_report(d.scene)
    assert not r["truncado"]
    assert [(i["a"], i["b"], i["volumen_mm3"]) for i in r["interferencias"]] == []
    rep = soundness_report(build_graph(d.scene, d.joints, d.mates, d.fasteners, d.grounds))
    assert rep["floating"] == [] and rep["n_grounded"] == len(d.scene)


@pytest.mark.parametrize("params", [{"tensor": "ninguno", "largo": 6000},
                                    {"motor": "MOTOR-150", "lado_abierto": "+y"},
                                    {"tramo_max": 3000, "largo": 10200}],
                         ids=["sin-tensor", "motor-150", "tramos-3m"])
def test_variantes_sin_interferencias_ni_agujeros_faltantes(params):
    d, cid = _faja(**params)
    assert interference_report(d.scene)["interferencias"] == []
    test_cada_union_atornillada_tiene_sus_agujeros((d, cid))


# ------------------------------------------------------------------ logs viejos
def _huella(doc) -> tuple:
    notas = sorted({f.get("nota") or "" for f in doc.fasteners.values()})
    return (len(doc.scene), len(doc.fasteners),
            round(sum(f.shape.volume for f in doc.scene.values()), 1),
            hashlib.sha1("|".join(notas).encode()).hexdigest()[:10])


@pytest.mark.parametrize("params, huella", [
    ({"criterio": 7}, (78, 101, 97844838.8, "626e601531")),
    ({"criterio": 7, "largo": 10200, "altura": 850, "lado_abierto": "-y"},
     (169, 221, 193069814.1, "b297e76c51")),
    ({"criterio": 6}, (70, 91, 97805836.0, "e44c0e58c8")),
], ids=["7-4m", "7-10m", "6-4m"])
def test_lo_sellado_antes_del_8_regenera_igual(params, huella):
    """Piezas, uniones, volumen y notas de las uniones medidos con el código de antes de la F1c."""
    d, _ = _faja(**params)
    viejo = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert _huella(viejo)[:2] == huella[:2]
    assert _huella(viejo)[2] == pytest.approx(huella[2], rel=1e-7)
    assert _huella(viejo)[3] == huella[3]
