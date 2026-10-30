"""`higiene.limpiable` (plan hallazgos-del-revisor-en-la-puerta, F6/D9): en equipo higiénico cada
soldadura con contacto lineal es continua (o declara su sellado sanitario) y cada tubo que se
fabrica está cerrado por una pieza soldada.

Casos: el requisito `higienico` (validado; ausente = no aplica), el criterio puro de la soldadura y
del ítem, los tubos medidos sobre geometría sintética (tapa soldada, tapa sin soldar, tubos a tope,
un casquillo con roscado ciego y una placa con agujero que no son tubos) y la mesa inox real del
repo hermano de máquinas (el test se salta sin el archivo)."""

from __future__ import annotations

from pathlib import Path

import pytest

from apolo.doc import Document
from apolo.library.calidad import higiene as hg
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.registro import VERSION_REGISTRO, evaluar
from apolo.library.requisitos import es_higienico, normalizar_requisitos
from apolo.services import puerta_publicacion as pp
from apolo.services.calidad_higiene import extremos_huecos, higiene

TESTIGOS = Path(__file__).resolve().parent / "data" / "testigos"
_INOX = "maquinas/mesa-inox-1200/mesa-inox-1200.apolo"
_D16 = "maquinas/mesa-soldadura-d16-1000/mesa-soldadura-d16-1000.apolo"


def _hermano(ruta: str) -> Path | None:
    """Un `.apolo` del repo hermano de máquinas, buscado desde los ancestros de este archivo (un
    checkout o un worktree)."""
    for anc in Path(__file__).resolve().parents:
        hallados = sorted(anc.glob(f"*/{ruta}"))
        if hallados:
            return hallados[0]
    return None


# ------------------------------------------------------------------ el requisito
def test_el_requisito_higienico_se_valida_y_ausente_no_aplica():
    assert normalizar_requisitos({"higienico": "sí"}) == {"higienico": True}
    assert normalizar_requisitos({"higienico": {"valor": "no", "asumido": True}}) == {
        "higienico": False, "asumidos": ["higienico"]}
    with pytest.raises(ValueError, match="higienico"):
        normalizar_requisitos({"higienico": "a veces"})
    assert not es_higienico({}) and not es_higienico(None)
    assert es_higienico({"higienico": True}) and es_higienico({"higienico": "Sí"})
    assert not es_higienico({"higienico": "no"})


# ------------------------------------------------------------------ el criterio, puro
@pytest.mark.parametrize("nota, sellado", [
    ("cordón intermitente + sellado sanitario con silicona FDA", True),
    ("Sello sanitario en el borde del ala", True),
    ("sellada con silicona sanitaria", True),
    ("sellado", False),
    ("silicona sanitaria", False),
    ("", False),
])
def test_el_sellado_sanitario_se_declara_en_la_nota(nota, sellado):
    assert hg.sellado_sanitario(nota) is sellado


def _sold(decl=None, cordon=1100.0, sellado=False, union="w"):
    return {"union": union, "a": "a1", "b": "b1", "nombre_a": "Repisa", "nombre_b": "Larguero",
            "cordon_mm": cordon, "largo_declarado_mm": decl, "sellado": sellado, "nota": ""}


def test_la_soldadura_es_continua_sin_largo_o_con_el_largo_de_su_contacto():
    assert hg.juzgar_soldadura(_sold())[0] == OK  # ISO 2553: sin largo corre toda la junta
    assert hg.juzgar_soldadura(_sold(1099.5))[0] == OK  # el redondeo
    estado, motivo = hg.juzgar_soldadura(_sold(240.0))
    assert estado == FALLA and "860 mm de rendija" in motivo
    assert hg.juzgar_soldadura(_sold(240.0, sellado=True))[0] == OK


def test_el_item_falla_nombra_las_piezas_y_lo_sin_medir_se_justifica():
    datos = {"soldaduras": [_sold(240.0), _sold(union="w2")], "otras_formas": 1,
             "tubos": [{"id": "t1", "nombre": "Pata", "extremos": 2,
                        "abiertos": [{"centro": [0, 0, 0], "normal": [0, 0, 1], "ancho_mm": 37,
                                      "holgura_mm": 37.0}]}],
             "sin_medir": []}
    r = hg.limpiable({"higiene": datos})
    assert r["estado"] == FALLA and r["piezas"] == ["a1", "b1", "t1"], r
    assert "1 soldadura(s) con rendija y 1 tubo(s) abierto(s)" in r["detalle"]
    sin = {"soldaduras": [], "tubos": [],
           "sin_medir": [{"que": "tubo Pata", "piezas": ["t1"], "motivo": "OCCT"}]}
    r = hg.limpiable({"higiene": sin})
    assert r["estado"] == SIN_EVALUAR and r["evidencia"]["sin_medir"][0]["regla"] == hg.REGLA_SIN_MEDIR
    js = [{"regla": hg.REGLA_SIN_MEDIR, "pieza": "t1", "porque": "la pata es maciza, no un tubo hueco"}]
    assert hg.limpiable({"higiene": sin, "justificadas": js})["estado"] == OK
    assert hg.limpiable({"higiene": None})["estado"] == SIN_EVALUAR
    assert hg.limpiable({"higiene": {"error": "boom"}})["estado"] == SIN_EVALUAR


# ------------------------------------------------------------------ geometría sintética
def _caja(doc, nombre, w, dp, h, x, y, z) -> str:
    return doc.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                      "position": {"x": x, "y": y, "z": z}})


def _id(doc, nombre: str) -> str:
    return next(fid for fid, f in doc.scene.items() if f.name == nombre)


def _tubo(doc, nombre, x, y, z0, alto, lado=40.0, e=2.0) -> str:
    """Un tubo cuadrado vertical abierto en sus dos extremos (z0 … z0 + alto)."""
    afuera = _caja(doc, nombre, lado, lado, alto, x, y, z0 + alto / 2)
    luz = _caja(doc, "luz", lado - 2 * e, lado - 2 * e, alto + 2, x, y, z0 + alto / 2)
    doc.execute("boolean_op", {"name": nombre, "operation": "cut", "target": afuera,
                               "tools": [luz]})
    return _id(doc, nombre)


def _soldar(doc, nombre, a, b, **extra):
    doc.execute("fasten", {"name": nombre, "a": a, "b": b, "kind": "soldadura", "throat_mm": 2,
                           **extra})


def _base_con_tubo() -> tuple[Document, str, str]:
    doc = Document()
    placa = _caja(doc, "Placa base", 200, 200, 10, 0, 0, 5)
    doc.execute("ground", {"name": "g0", "feature": placa})
    tubo = _tubo(doc, "Pata", 0, 0, 10, 300)
    _soldar(doc, "w_pata", tubo, placa)
    doc.set_requirements({"higienico": True})
    return doc, placa, tubo


def test_el_tubo_abierto_arriba_falla_y_la_tapa_soldada_lo_cierra():
    doc, _placa, tubo = _base_con_tubo()
    datos = higiene(doc)
    (t,) = datos["tubos"]
    assert t["id"] == tubo and t["extremos"] == 2
    (abierto,) = t["abiertos"]  # abajo lo cierra la placa soldada; arriba, nada
    assert abierto["normal"] == [0.0, 0.0, 1.0] and abierto["holgura_mm"] is None
    (w,) = datos["soldaduras"]
    assert w["union"] == "w_pata" and w["largo_declarado_mm"] is None
    assert hg.limpiable({"higiene": datos})["estado"] == FALLA
    # una tapa que apoya sin soldar no cierra nada: el agua entra por la junta
    tapa = _caja(doc, "Placa de cierre", 40, 40, 3, 0, 0, 311.5)
    assert higiene(doc)["tubos"][0]["abiertos"]
    _soldar(doc, "w_tapa", tapa, tubo)
    datos = higiene(doc)
    assert datos["tubos"][0]["abiertos"] == []
    assert hg.limpiable({"higiene": datos})["estado"] == OK


def test_la_soldadura_corta_falla_salvo_el_sellado_declarado():
    doc, placa, tubo = _base_con_tubo()
    tapa = _caja(doc, "Placa de cierre", 40, 40, 3, 0, 0, 311.5)
    _soldar(doc, "w_tapa", tapa, tubo, length_mm=60)
    datos = higiene(doc)
    (w,) = [s for s in datos["soldaduras"] if s["union"] == "w_tapa"]
    assert w["cordon_mm"] > 150  # el perímetro exterior del tubo de 40
    r = hg.limpiable({"higiene": datos})
    assert r["estado"] == FALLA and tapa in r["piezas"], r["detalle"]
    cmd = doc.commands[-1]
    doc.edit(cmd["id"], {**cmd["params"], "nota": "intermitente + sellado sanitario (silicona FDA)"})
    assert hg.limpiable({"higiene": higiene(doc)})["estado"] == OK


def test_dos_tubos_a_tope_soldados_se_cierran_entre_si():
    """Lo mismo que un inglete: sus luces se comunican y cada extremo libre se juzga aparte."""
    doc, placa, tubo = _base_con_tubo()
    otro = _tubo(doc, "Prolongación", 0, 0, 310, 200)
    _soldar(doc, "w_tope", otro, tubo)
    datos = higiene(doc)
    por_id = {t["id"]: t for t in datos["tubos"]}
    assert por_id[tubo]["abiertos"] == []
    (arriba,) = por_id[otro]["abiertos"]
    assert arriba["centro"][2] == pytest.approx(510.0)


def test_un_roscado_ciego_o_un_agujero_de_perno_no_son_tubos():
    doc = Document()
    casq = _caja(doc, "Casquillo", 30, 30, 40, 0, 0, 20)
    broca = doc.execute("create_cylinder", {"name": "broca", "radius": 4.25, "height": 32,
                                            "position": {"x": 0, "y": 0, "z": 16}})
    doc.execute("boolean_op", {"name": "Casquillo", "operation": "cut", "target": casq,
                               "tools": [broca]})
    placa = _caja(doc, "Placa", 200, 100, 10, 300, 0, 5)
    agujero = doc.execute("create_cylinder", {"name": "agujero", "radius": 7, "height": 20,
                                              "position": {"x": 300, "y": 0, "z": 5}})
    doc.execute("boolean_op", {"name": "Placa", "operation": "cut", "target": placa,
                               "tools": [agujero]})
    for nombre in ("Casquillo", "Placa"):
        assert extremos_huecos(doc.scene[_id(doc, nombre)].shape) == [], nombre


def test_sin_el_requisito_no_aplica_y_no_se_mide():
    doc, _placa, _tubo_id = _base_con_tubo()
    doc.set_requirements({})
    assert higiene(doc) is None
    ins = pp.reunir(doc, expand=lambda x: x, gravedad={"resultado": None, "motivo": ""},
                    sobrantes=False)
    assert ins["higiene"] is None
    r = evaluar(ins)
    assert r["version_registro"] == VERSION_REGISTRO == "31"
    it = {i["id"]: i for i in r["items"]}["higiene.limpiable"]
    assert it["estado"] == NO_APLICA and "higienico" in it["detalle"]


# ------------------------------------------------------------------ la mesa inox real
def _item(doc) -> dict:
    ins = pp.reunir(doc, expand=lambda x: x, gravedad={"resultado": None, "motivo": ""},
                    sobrantes=False)
    return {i["id"]: i for i in evaluar(ins)["items"]}["higiene.limpiable"]


@pytest.mark.skipif(_hermano(_INOX) is None, reason="sin el repo hermano de máquinas (mesa inox)")
def test_la_mesa_inox_falla_por_la_repisa_y_la_pata_abierta_y_pasa_corregida():
    doc = Document.from_apolo_bytes(_hermano(_INOX).read_bytes())
    assert _item(doc)["estado"] == NO_APLICA  # el encargo no lo declaraba
    doc.set_requirements({**doc.requirements, "higienico": True})
    it = _item(doc)
    assert it["estado"] == FALLA, it["detalle"]
    ev = it["evidencia"]
    # la repisa (c46): 240 mm declarados en los 1 101 mm de cada larguero; también la cubierta, los
    # refuerzos y los casquillos declaran menos que su línea (en el revisor eran «perimetrales»)
    assert "c46" in it["piezas"], it["piezas"]
    assert ev["con_rendija"] == 2 + 4 + 20 + 4, ev["soldaduras"]  # repisa, cubierta, refuerzos,
    # casquillos
    patas = {t["id"] for t in ev["tubos_abiertos"]}
    assert patas == {"c21", "c22", "c23", "c24"}, ev["tubos_abiertos"]
    assert all(a["normal"] == [0.0, 0.0, 1.0] for t in ev["tubos_abiertos"] for a in t["abiertos"])
    # corregida: soldaduras continuas (sin largo) y la pata a tope contra la cubierta, soldada
    for c in [c for c in doc.commands if c["type"] == "fasten"
              and c["params"].get("kind") == "soldadura"]:
        doc.edit(c["id"], {k: v for k, v in c["params"].items() if k != "length_mm"})
    h_pata = next(c for c in doc.commands if c["type"] == "set_variable"
                  and c["params"]["name"] == "h_pata")
    doc.edit(h_pata["id"], {"name": "h_pata", "expression": "H - t_ch - z_pie - e_tap"})
    doc.execute("fasten", {"name": "W_cub_pata", "a": "c45", "b": "c21+c22+c23+c24",
                           "kind": "soldadura", "throat_mm": 1})
    it = _item(doc)
    assert it["estado"] == OK, it["detalle"]


@pytest.mark.skipif(_hermano(_D16) is None, reason="sin el repo hermano de máquinas (mesa Ø16)")
def test_la_mesa_de_soldadura_no_aplica():
    doc = Document.from_apolo_bytes(_hermano(_D16).read_bytes())
    assert _item(doc)["estado"] == NO_APLICA
