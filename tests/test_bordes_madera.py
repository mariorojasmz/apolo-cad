"""Distancias en MADERA (plan hallazgos-del-revisor-en-la-puerta, D7 y F4): un perno o tornillo en
una pieza de madera a ≥ 4·d de la testa y ≥ 3·d del canto (criterio de diseño con los mínimos
descargados a3,c y a4,c de EN 1995-1-1, tabla 8.4) y ningún tornillo que rosque en la testa. La
medida es UNA (`library/borde_agujero.medir_madera`) para la puerta (`borde.madera`,
`borde.testa` dentro de `union.distancia_al_borde`) y para `join_bolted` criterio 7. Los `.apolo`
reales de los pilotos de madera (fuera del repo) se buscan en los repos hermanos: sin ellos, esos
tests se saltan."""

from pathlib import Path

import pytest
from build123d import Box, Cylinder, Pos

from apolo.commands.registry import CommandError
from apolo.doc import Document
from apolo.doc.errors import DocumentError
from apolo.kernel.rayo import Rayos
from apolo.library.borde_agujero import medir_madera, veta
from apolo.library.calidad.bordes import controlar_bordes
from apolo.library.calidad.item import FALLA, NO_APLICA, OK
from apolo.library.calidad.registro import VERSION_REGISTRO
from apolo.services.calidad_bordes import insumos_bordes
from apolo.services.calidad_pernos import _Escena, insumos_pernos

Z = (0.0, 0.0, 1.0)


# ── la medida ───────────────────────────────────────────────────────────────────────────


def _liston(x: float, y: float = 0.0, largo: float = 300.0, ancho: float = 45.0):
    """Listón `largo` (X, la veta) × `ancho` × 20 (z ∈ [0, 20]) con un taladro Ø6,6 en (x, y)."""
    return (Pos(0, 0, 10) * Box(largo, ancho, 20)
            - Pos(x, y, 10) * Cylinder(3.3, 40)).solids()[0]


def _medir(sol, x, y=0.0, d=6.0, tornillo=False):
    return medir_madera(Rayos(sol), (x, y, -5.0), Z, 5.0, 25.0, d, veta(sol), tornillo=tornillo)


def test_la_veta_es_el_eje_largo_y_un_taco_no_tiene():
    v = veta(_liston(0.0))
    assert abs(v[0]) == pytest.approx(1.0, abs=1e-6)
    assert veta((Box(45, 45, 40)).solids()[0]) is None  # tan ancho como largo


def test_perno_a_2_5d_de_la_testa_falla_y_a_5d_cumple():
    r = _medir(_liston(150.0 - 15.0), 150.0 - 15.0)  # 15 mm de la testa = 2,5·d
    assert r["estado"] == "medido" and not r["cumple"]
    assert r["lado"] == "testa" and r["distancia"] == pytest.approx(15.0, abs=0.1)
    assert r["requerido"] == pytest.approx(24.0) and r["canto"] == pytest.approx(22.5, abs=0.1)
    ok = _medir(_liston(150.0 - 30.0), 150.0 - 30.0)
    assert ok["cumple"] and ok["testa"] == pytest.approx(30.0, abs=0.1)


def test_canto_pide_3d():
    r = _medir(_liston(0.0, y=22.5 - 12.0), 0.0, y=22.5 - 12.0)  # 12 mm del canto < 18
    assert not r["cumple"] and r["lado"] == "canto"
    assert r["distancia"] == pytest.approx(12.0, abs=0.1) and r["requerido"] == pytest.approx(18.0)


def test_tornillo_a_lo_largo_de_la_veta_es_en_testa():
    poste = (Pos(0, 0, 150) * Box(45, 45, 300)).solids()[0]
    r = medir_madera(Rayos(poste), (0, 0, 310), (0, 0, -1), 10, 60, 6.0, veta(poste),
                     tornillo=True)
    assert r["estado"] == "en_testa"


def test_tornillo_sin_agujero_modelado_se_mide_igual():
    maciza = (Pos(0, 0, 10) * Box(300, 45, 20)).solids()[0]
    r = _medir(maciza, 140.0, tornillo=True)  # sin piloto: el eje dentro de la madera
    assert r["estado"] == "medido" and r["testa"] == pytest.approx(10.0, abs=0.1)


# ── el control puro ─────────────────────────────────────────────────────────────────────


def _agujero(**kw):
    base = {"perno": "p1", "perno_nombre": "Perno M6", "pieza": "a", "nombre": "Pata",
            "madera": True, "estado": "medido", "d": 6.0, "testa": 15.0, "canto": 22.5,
            "testa_min": 24.0, "canto_min": 18.0, "cumple": False, "lado": "testa",
            "distancia": 15.0, "requerido": 24.0, "sin_veta": False}
    return {**base, **kw}


def test_control_madera_nombra_pieza_perno_y_distancias():
    _dist, _paso, mad, testa = controlar_bordes([_agujero()], [])
    assert mad.estado == FALLA and mad.piezas == ["a", "p1"]
    assert "«Pata» (de «Perno M6»): 15 mm a la testa < 24 mm (4·d, d = 6 mm)" in mad.detalle
    caso = mad.evidencia["casos"][0]
    assert caso["distancia_mm"] == 15.0 and caso["requerido_mm"] == 24.0
    assert "EN 1995-1-1" in mad.norma and "criterio de diseño" in mad.norma
    assert testa.estado == OK and _dist.estado == NO_APLICA  # la madera no es chapa


def test_control_tornillo_en_testa_y_perno_a_lo_largo():
    en_testa = _agujero(estado="en_testa", perno_nombre="Tirafondo pivote", nombre="Larguero")
    a_lo_largo = _agujero(perno="p2", estado="a_lo_largo")
    _d, _p, mad, testa = controlar_bordes([en_testa, a_lo_largo], [])
    assert testa.estado == FALLA and "«Tirafondo pivote» en «Larguero»" in testa.detalle
    assert testa.evidencia["a_lo_largo"] == 1
    assert mad.estado == NO_APLICA  # nada medido de través: el general lo cuenta como nada


def test_tornillo_sin_geometria_no_bloquea():
    sin = {"pieza": None, "nombre": None, "perno": None, "madera": True,
           "estado": "sin_geometria", "n": 3, "motivo": "x"}
    _d, _p, mad, testa = controlar_bordes([sin, _agujero(cumple=True)], [])
    assert mad.estado == OK and mad.evidencia["no_juzgados"] == {"sin_geometria": 3}
    assert testa.estado == OK


# ── sobre un documento ─────────────────────────────────────────────────────────────────


def _listones(doc, x_agujero: float, perno="PERNO-HEX-M6", tuerca="TUERCA-M6"):
    """Dos listones 300 × 45 × 20 de madera apilados (x ∈ [-150, 150]) con un paso Ø6,6 en
    `x_agujero` y un perno M6 con su tuerca."""
    a = doc.execute("create_box", {"name": "Pata", "width": 300, "depth": 45, "height": 20,
                                   "position": {"z": 10}})
    b = doc.execute("create_box", {"name": "Zapata", "width": 300, "depth": 45, "height": 20,
                                   "position": {"z": 30}})
    for f in (a, b):
        doc.set_material(f, "madera")
        doc.execute("drill_hole", {"feature": f, "position": {"x": x_agujero, "z": 40},
                                   "axis": "-z", "diameter": 6.6})
    doc.execute("insert_component", {"component": perno, "length": 60,
                                     "position": {"x": x_agujero, "z": 40}})
    if tuerca:
        doc.execute("insert_component", {"component": tuerca, "position": {"x": x_agujero,
                                                                            "z": -2.5}})
    return a, b


def _bordes(doc):
    esc = _Escena(doc.scene)
    pernos = insumos_pernos(doc, escena=esc)
    return {i.id: i for i in controlar_bordes(*insumos_bordes(doc, pernos, esc))}


def test_la_puerta_mide_la_madera_y_no_la_tabla_de_chapas():
    doc = Document("listones")
    a, b = _listones(doc, 150.0 - 15.0)  # 2,5·d de la testa
    it = _bordes(doc)
    mad = it["borde.madera"]
    assert mad.estado == FALLA and mad.evidencia["fallan"] == 2  # los dos listones
    assert {c["pieza"] for c in mad.evidencia["casos"]} == {a, b}
    assert all(c["lado"] == "testa" and c["distancia_mm"] == pytest.approx(15.0, abs=0.2)
               for c in mad.evidencia["casos"])
    assert it["borde.distancia"].estado == NO_APLICA  # la madera salió de la tabla 3.3
    ok = Document("listones-ok")
    _listones(ok, 150.0 - 30.0)
    assert _bordes(ok)["borde.madera"].estado == OK


def test_el_tornillo_de_madera_sin_hexagono_se_mide():
    """La F0 dejó 128 tornillos avellanados de catálogo sin medir (`TIRAFONDO-*`, sin llave)."""
    doc = Document("tornillo")
    a = doc.execute("create_box", {"name": "Larguero", "width": 300, "depth": 19, "height": 90,
                                   "position": {"z": 45}})
    doc.set_material(a, "madera")
    # un tornillo 4×40 por el canto de 19 mm (cabeza a ras): a 9,5 mm de cada cara (pide 3·4)
    doc.execute("insert_component", {"component": "TIRAFONDO-4x40",
                                     "position": {"x": 0, "y": 0, "z": 90 - 21}})
    it = _bordes(doc)
    caso = it["borde.madera"].evidencia["casos"][0]
    assert it["borde.madera"].estado == FALLA and caso["lado"] == "canto"
    assert caso["distancia_mm"] == pytest.approx(9.5, abs=0.3) and caso["requerido_mm"] == 12.0


def test_el_tornillo_en_la_testa_falla():
    doc = Document("testa")
    poste = doc.execute("create_box", {"name": "Poste", "width": 45, "depth": 45, "height": 600,
                                       "position": {"z": 300}})
    doc.set_material(poste, "madera")
    doc.execute("insert_component", {"component": "TIRAFONDO-5x60",
                                     "position": {"z": 600 - 31.25}})
    it = _bordes(doc)
    assert it["borde.testa"].estado == FALLA
    assert it["borde.testa"].evidencia["casos"][0]["pieza"] == poste


def test_el_item_general_aplica_con_solo_tornillos_de_madera():
    from apolo.library.calidad import registro
    from apolo.services.calidad_mecanica import items_funcion_mecanica
    from apolo.services.puerta_hechos import hechos

    doc = Document("solo-tornillos")
    poste = doc.execute("create_box", {"name": "Poste", "width": 45, "depth": 45, "height": 600,
                                       "position": {"z": 300}})
    doc.set_material(poste, "madera")
    doc.execute("insert_component", {"component": "TIRAFONDO-5x60",
                                     "position": {"z": 600 - 31.25}})
    h = hechos(doc, {})
    assert h["elementos"]["tornilleria"] == {}
    assert h["elementos"]["tornilleria_madera"] == {"tornillo": 1}
    insumos = {"hechos": h, "fuentes": {"mecanica": items_funcion_mecanica(doc, reglas=[])}}
    r = registro.evaluar(insumos, registro=[e for e in registro.REGISTRO
                                            if getattr(e, "clave", "") == "mecanica"])
    it = next(i for i in r["items"] if i["id"] == "union.distancia_al_borde")
    assert it["estado"] == FALLA and "borde.testa" in it["detalle"]
    assert VERSION_REGISTRO == "29"


# ── join_bolted criterio 7 ─────────────────────────────────────────────────────────────


def _carpinteria(nombre: str) -> Document:
    doc = Document(nombre)
    doc.set_vertical("carpinteria")
    return doc


def test_join_bolted_en_madera_no_cabe_a_4d_de_la_testa():
    """La zapata solapa 30 mm la punta de la pata: el patrón ya no cabe a 4·d de la testa."""
    doc = _carpinteria("jb-testa")
    pata = doc.execute("create_box", {"name": "Pata", "width": 600, "depth": 90, "height": 45,
                                      "position": {"z": 22.5}})
    zap = doc.execute("create_box", {"name": "Zapata", "width": 130, "depth": 40, "height": 20,
                                     "position": {"x": 335, "z": 55}})
    with pytest.raises((CommandError, DocumentError),
                       match=r"no admite ni un perno M6 con distancia al borde ≥24 mm en madera "
                             r"\(4·d según la veta"):
        doc.execute("join_bolted", {"a": zap, "b": pata, "size": "M6", "count": 1})
    # el criterio 6 (log guardado) no mira la madera: regenera igual que antes
    doc.execute("join_bolted", {"a": zap, "b": pata, "size": "M6", "count": 1, "criterio": 6})


def test_join_bolted_en_madera_mide_la_testa_que_la_huella_no_ve():
    """Una muesca en la zapata deja su testa a 12 mm del agujero: la caja no lo ve, la medida sí."""
    doc = _carpinteria("jb-muesca")
    pata = doc.execute("create_box", {"name": "Pata", "width": 600, "depth": 90, "height": 45,
                                      "position": {"z": 22.5}})
    zap = doc.execute("create_box", {"name": "Zapata", "width": 200, "depth": 60, "height": 20,
                                     "position": {"z": 55}})
    muesca = doc.execute("create_box", {"width": 28, "depth": 35, "height": 40,
                                        "position": {"x": 26, "y": 12.5, "z": 55}})
    zap = doc.execute("boolean_op", {"name": "Zapata", "operation": "cut", "target": zap,
                                     "tools": [muesca]})
    with pytest.raises((CommandError, DocumentError),
                       match=r"agujero 1 de la unión queda a 12 mm de la testa de «Zapata», que "
                             r"es de madera: pide ≥ 24 mm = 4·d \(d = 6 mm; criterio de diseño"):
        doc.execute("join_bolted", {"a": zap, "b": pata, "size": "M6", "count": 1})


def test_join_bolted_en_madera_lejos_de_la_testa_pasa():
    doc = _carpinteria("jb-ok")
    pata = doc.execute("create_box", {"name": "Pata", "width": 600, "depth": 90, "height": 45,
                                      "position": {"z": 22.5}})
    zap = doc.execute("create_box", {"name": "Zapata", "width": 60, "depth": 90, "height": 20,
                                     "position": {"x": 240, "z": 55}})
    cid = doc.execute("join_bolted", {"a": zap, "b": pata, "size": "M6", "count": 1})
    params = next(c for c in doc.commands if c["id"] == cid)["params"]
    assert params["criterio"] == 8 and set(params["madera"]) == {pata, zap}


def test_join_bolted_rechaza_el_tornillo_en_la_testa():
    doc = _carpinteria("jb-tornillo")
    poste = doc.execute("create_box", {"name": "Poste", "width": 45, "depth": 45, "height": 600,
                                       "position": {"z": 300}})
    tapa = doc.execute("create_box", {"name": "Tapa", "width": 100, "depth": 45, "height": 10,
                                      "position": {"z": 605}})
    with pytest.raises((CommandError, DocumentError), match=r"entraría por la testa de «.*»"):
        doc.execute("join_bolted", {"a": tapa, "b": poste, "size": "M6", "count": 1})


# ── los pilotos de madera (fuera del repo) ─────────────────────────────────────────────


def _piloto(nombre: str, ronda: str | None = None) -> Document:
    raiz = Path.home() / "source" / "repos"
    patron = (f"*/maquinas/{nombre}/rondas/{ronda}.apolo" if ronda
              else f"*/maquinas/{nombre}/{nombre}.apolo")
    hallados = sorted(raiz.glob(patron)) if raiz.exists() else []
    if not hallados:
        pytest.skip(f"sin el .apolo real de {nombre} (fuera del repo)")
    return Document.from_apolo_bytes(hallados[0].read_bytes())


def test_mesa_plegable_los_m6_de_la_zapata_a_2_5d_de_la_testa_fallan():
    it = _bordes(_piloto("mesa-plegable-madera-1200"))
    casos = [c for c in it["borde.madera"].evidencia["casos"]
             if "zapata" in (c["perno_nombre"] or "").lower() and c["lado"] == "testa"]
    assert it["borde.madera"].estado == FALLA and casos
    assert all(c["distancia_mm"] / c["d_mm"] == pytest.approx(2.5, abs=0.05) for c in casos)


def test_silla_ronda_1_el_tirafondo_en_la_testa_falla():
    it = _bordes(_piloto("silla-plegable-450", "modelado"))
    assert it["borde.testa"].estado == FALLA
    nombres = [c["perno_nombre"] for c in it["borde.testa"].evidencia["casos"]]
    assert any("Tirafondo pivote" in (n or "") for n in nombres)
