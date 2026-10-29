"""Puerta de publicación F3 — seguridad y reparabilidad sobre documentos REALES (plan
puerta-de-publicacion, D4/D5/D9): cada control con su caso bueno y su defecto SEMBRADO.

Fixtures con comandos reales: una faja hecha a mano (tambores, banda de `run_script`, largueros,
cama, patas, `fasten`, `ground`) y una transmisión de `create_chain` entre dos piñones de
catálogo. La plantilla `create_belt_conveyor` no sirve de testigo: sus ramales rectos quedan a
la altura del piso (ver la bitácora F3 del plan).
"""

from __future__ import annotations

import pytest

from apolo.doc import Document
from apolo.services.calidad_reparabilidad import (
    ID_BANDA,
    ID_DESMONTABLE,
    ID_SIN_SOLDADURA,
    controles_reparabilidad,
)
from apolo.services.calidad_seguridad import (
    ID_ELECTRICO,
    ID_GUARDA,
    ID_RESGUARDO,
    controles_f3,
    controles_seguridad,
)

ESQUEMA = {"id", "titulo", "estado", "modo_de_falla", "norma", "evidencia", "piezas", "detalle"}

# racetrack hueco: dos tambores R50 a x = ±600, eje Y, z = 700; banda de 4 mm y 400 de ancho
_BANDA = (
    "def region(r):\n"
    "    a = Pos(-600, 0, 700) * Cylinder(r, 400, rotation=(90, 0, 0))\n"
    "    b = Pos(600, 0, 700) * Cylinder(r, 400, rotation=(90, 0, 0))\n"
    "    return a + b + Pos(0, 0, 700) * Box(1200, 400, 2 * r)\n"
    "result = region(54) - region(50)\n"
)


def _faja(cama: str = "soldadura", guardas: str | None = None, chumacera: str | None = None):
    """Faja a mano. `cama`: cómo se une la cama a los largueros (soldada = marco cerrado que
    abraza la banda). `guardas`: None (sin guardas de tambor) o el tipo de unión de las guardas
    a los largueros. `chumacera`: si hay una chumacera de la cola y cómo se une al larguero."""
    d = Document("faja-prueba")
    ids = {}

    def caja(clave, nombre, w, dp, h, x=0.0, y=0.0, z=0.0):
        ids[clave] = d.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                              "position": {"x": x, "y": y, "z": z}})

    for s, lado in ((1, "+X"), (-1, "-X")):
        nombre = "Tambor motriz" if s > 0 else "Tambor de cola"
        ids[f"tambor{lado}"] = d.execute("create_cylinder", {
            "name": nombre, "radius": 50, "height": 450,
            "position": {"x": 600 * s, "z": 700}, "rotation": {"x": 90}})
        ids[f"eje{lado}"] = d.execute("create_cylinder", {
            "name": f"Eje {'motriz' if s > 0 else 'de cola'} Ø25", "radius": 12.5, "height": 560,
            "position": {"x": 600 * s, "z": 700}, "rotation": {"x": 90}})
    ids["banda"] = d.execute("run_script", {"name": "Banda PVC 2 capas", "code": _BANDA})
    for s, lado in ((1, "+Y"), (-1, "-Y")):
        caja(f"larg{lado}", f"Larguero ({lado})", 1500, 40, 100, y=260 * s, z=700)
        for x in (-500, 500):
            caja(f"pata{lado}{x}", f"Pata ({lado}, {x:+d})", 40, 40, 650, x=x, y=260 * s, z=325)
    caja("cama", "Cama de deslizamiento", 1100, 520, 8, z=745)
    n = 0

    def fasten(a, b, kind):
        nonlocal n
        n += 1
        d.execute("fasten", {"name": f"u{n}", "a": ids[a], "b": ids[b], "kind": kind})

    for lado in ("+Y", "-Y"):
        for x in (-500, 500):
            fasten(f"pata{lado}{x}", f"larg{lado}", "soldadura")
            d.execute("ground", {"name": f"g{n}", "feature": ids[f"pata{lado}{x}"]})
        fasten("cama", f"larg{lado}", cama)
    for lado in ("+X", "-X"):
        fasten(f"eje{lado}", f"tambor{lado}", "soldadura")
        fasten(f"eje{lado}", "larg+Y", "contacto")
    if guardas:
        for s, lado in ((1, "+X"), (-1, "-X")):
            caja(f"guarda{lado}", f"Guarda del tambor ({lado})", 180, 600, 200, x=610 * s, z=700)
            fasten(f"guarda{lado}", "larg+Y", guardas)
            fasten(f"guarda{lado}", "larg-Y", guardas)
    if chumacera:
        caja("chum", "Chumacera de cola (-Y)", 60, 30, 60, x=-600, y=-295, z=700)
        fasten("chum", "larg-Y", chumacera)
    return d, ids


def _item(items, id_):
    it = next(i for i in items if i["id"] == id_)
    assert set(it) == ESQUEMA
    return it


def _peligro(it, tambor_id):
    return next(p for p in it["evidencia"]["peligros"] if p["id"].endswith(f":{tambor_id}")
                and p["id"].startswith("atrapamiento:"))


@pytest.fixture(scope="module")
def faja_sin_guardas():
    d, ids = _faja()
    return d, ids, controles_f3(d, n_direcciones=48)


# ------------------------------------------------------------------ cuña banda ↔ tambor
def test_cuna_sin_guarda_falla(faja_sin_guardas):
    d, ids, r = faja_sin_guardas
    it = _item(r["items"], ID_RESGUARDO)
    assert it["estado"] == "FALLA"
    p = _peligro(it, ids["tambor+X"])
    assert p["estado"] == "FALLA" and p["n_alcanzan"] > 0
    f = p["fallas"][0]  # la evidencia: dirección, punto de entrada y distancia
    assert len(f["direccion"]) == 3 and len(f["entrada"]) == 3 and f["distancia_mm"] <= 850
    assert ids["tambor+X"] in it["piezas"]
    # la tabla de riesgos nombra el peligro, su tipo y que no tiene medida
    fila = next(x for x in r["riesgos"] if "Tambor motriz" in x["peligro"])
    assert fila["tipo"] == "atrapamiento" and fila["verificacion"] == ID_RESGUARDO
    assert fila["estado"] == "FALLA" and fila["zona"]["puntos"]


def test_cuna_con_guarda_ok():
    d, ids = _faja(guardas="perno")
    r = controles_seguridad(d, n_direcciones=48)
    it = _item(r["items"], ID_RESGUARDO)
    for lado in ("+X", "-X"):
        assert _peligro(it, ids[f"tambor{lado}"])["estado"] == "OK"
    assert it["estado"] == "OK", it["detalle"]
    fila = next(x for x in r["riesgos"] if "Tambor motriz" in x["peligro"])
    assert ids["guarda+X"] in fila["medida"]
    assert _item(r["items"], ID_GUARDA)["estado"] == "OK"


# caja de chapa alrededor del tambor +X con una ranura de 24 mm en su cara −X por la que pasa cada
# ramal de la banda (4 mm): sin empujar la banda quedan ~10 mm a cada lado
_CAJA_RANURADA = (
    "caja = Pos(600, 0, 700) * Box(260, 600, 200) - Pos(600, 0, 700) * Box(254, 594, 194)\n"
    "for z in (648, 752):\n"
    "    caja = caja - Pos(471.5, 0, z) * Box(10, 420, 24)\n"
    "result = caja\n"
)


def test_la_banda_que_cruza_una_ranura_de_la_guarda_se_empuja():
    """8D de la re-revisión de la faja central (F6): la banda cruza la guarda por una ranura de
    ~10 mm a cada lado (24 mm empujándola) a menos de 100 mm de la cuña. Con la banda como pared
    y sólo rectas, la cuña sale resguardada (el hueco); con la banda empujable (en un tramo libre
    dentro de la abertura no tapa ni estrecha) y el brazo doblado, FALLA."""
    d, ids = _faja()
    g = d.execute("run_script", {"name": "Guarda del tambor (+X)", "code": _CAJA_RANURADA})
    for k, lado in enumerate(("+Y", "-Y")):
        d.execute("fasten", {"name": f"gr{k}", "a": g, "b": ids[f"larg{lado}"],
                             "kind": "perno", "size": "M8", "qty": 2})
    antes = _item(controles_seguridad(d, n_direcciones=48, brazo_doblado=False,
                                      banda_empujable=False)["items"], ID_RESGUARDO)
    assert _peligro(antes, ids["tambor+X"])["estado"] == "OK"
    pared = _item(controles_seguridad(d, n_direcciones=48, banda_empujable=False)["items"],
                  ID_RESGUARDO)
    assert _peligro(pared, ids["tambor+X"])["estado"] == "OK"  # el brazo doblado solo, tampoco
    it = _item(controles_seguridad(d, n_direcciones=48)["items"], ID_RESGUARDO)
    p = _peligro(it, ids["tambor+X"])
    assert p["estado"] == "FALLA" and p["n_alcanzan"] > 0, p


def test_guarda_soldada_falla():
    d, ids = _faja(guardas="soldadura")
    it = _item(controles_seguridad(d, n_direcciones=16)["items"], ID_GUARDA)
    assert it["estado"] == "FALLA" and ids["guarda+X"] in it["piezas"]
    assert "soldada" in it["detalle"]


def test_sin_carril_electrico_no_aplica(faja_sin_guardas):
    it = _item(faja_sin_guardas[2]["items"], ID_ELECTRICO)
    assert it["estado"] == "NO_APLICA" and "sin tablero" in it["evidencia"]["motivo"]


# ------------------------------------------------------------------ reparabilidad
def test_banda_en_marco_soldado_cerrado_falla(faja_sin_guardas):
    d, ids, r = faja_sin_guardas
    it = _item(r["items"], ID_BANDA)
    assert it["estado"] == "FALLA"
    b = it["evidencia"]["bandas"][0]
    assert b["eje"] == "Y" and set(b["bloqueos"]) == {"+Y", "-Y"}
    assert ids["larg+Y"] in b["bloqueos"]["+Y"]


def test_banda_con_cama_atornillada_es_montable_por_su_empalme_de_campo():
    """faja-compacta F1b (D12, registro v20): la cama atornillada ya no basta. La banda sin fin
    la atraviesa la cama (los ejes de los tambores no cuentan: son su apoyo) y cambiarla obliga a
    desarmarla; con el empalme de campo de catálogo unido a la banda, sale abriéndolo."""
    d, ids = _faja(cama="perno")
    it = _item(controles_reparabilidad(d)["items"], ID_BANDA)
    assert it["estado"] == "FALLA", it["detalle"]
    assert it["evidencia"]["bandas"][0]["atraviesan"] == [ids["cama"]]
    g = d.execute("insert_component", {"component": "EMPALME-GRAPA-ART", "length": 400,
                                       "name": "Empalme de campo de la banda",
                                       "position": {"x": 0, "y": 0, "z": 645},
                                       "rotation": {"z": 90}})
    d.execute("fasten", {"name": "empalme", "a": g, "b": ids["banda"], "kind": "contacto"})
    it = _item(controles_reparabilidad(d)["items"], ID_BANDA)
    assert it["estado"] == "OK" and "empalme de campo" in it["detalle"], it["detalle"]


def test_chumacera_soldada_al_bastidor_falla():
    d, ids = _faja(chumacera="soldadura")
    items = controles_reparabilidad(d)["items"]
    it = _item(items, ID_SIN_SOLDADURA)
    assert it["estado"] == "FALLA" and it["piezas"] == [ids["chum"]]
    assert it["evidencia"]["soldadas"][0]["soldadura"][:2] == [ids["chum"], ids["larg-Y"]]


def test_chumacera_atornillada_ok_y_desmontable():
    d, ids = _faja(chumacera="perno")
    items = controles_reparabilidad(d)["items"]
    assert _item(items, ID_SIN_SOLDADURA)["estado"] == "OK"
    it = _item(items, ID_DESMONTABLE)
    assert it["estado"] == "OK", it["detalle"]


# ------------------------------------------------------------------ transmisión por cadena
def _transmision(guarda: str | None):
    """Dos piñones ASA 40 Z15 (eje Y, z = 600) + cadena + placa de soporte al piso. `guarda`:
    None, «cerrada» (caja que encierra todo) o «abierta_abajo» (tapa, frente y extremos)."""
    d = Document("cadena-prueba")
    a = d.execute("insert_component", {"component": "PINON-ASA40-1-Z15",
                                       "position": {"z": 600}, "rotation": {"x": 90}})
    b = d.execute("insert_component", {"component": "PINON-ASA40-1-Z15",
                                       "position": {"x": 400, "z": 600}, "rotation": {"x": 90}})
    c = d.execute("create_chain", {"name": "Cadena de transmisión", "pinon_a": a, "pinon_b": b})
    placa = d.execute("create_box", {"name": "Placa de soporte", "width": 600, "depth": 10,
                                     "height": 700, "position": {"x": 200, "y": -40, "z": 350}})
    d.execute("ground", {"name": "g", "feature": placa})
    piezas = []
    if guarda == "cerrada":
        piezas.append(("Guarda de la cadena", 540, 70, 160, 200, 0, 600))
    elif guarda == "abierta_abajo":
        piezas += [("Guarda de la cadena · tapa", 540, 70, 10, 200, 0, 680),
                   ("Guarda de la cadena · frente", 540, 5, 160, 200, 33, 600),
                   ("Guarda de la cadena · extremo (-X)", 5, 70, 160, -70, 0, 600),
                   ("Guarda de la cadena · extremo (+X)", 5, 70, 160, 470, 0, 600)]
    for k, (nombre, w, dp, h, x, y, z) in enumerate(piezas):
        g = d.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                     "position": {"x": x, "y": y, "z": z}})
        d.execute("fasten", {"name": f"gp{k}", "a": g, "b": placa, "kind": "perno"})
    return d, (a, b, c)


def _trans(d):
    it = _item(controles_seguridad(d, n_direcciones=48)["items"], ID_RESGUARDO)
    return it, next(p for p in it["evidencia"]["peligros"] if p["id"].startswith("transmision:"))


def test_cadena_expuesta_falla():
    d, (a, b, c) = _transmision(None)
    it, p = _trans(d)
    assert it["estado"] == "FALLA" and p["estado"] == "FALLA" and p["tipo"] == "atrapamiento"
    assert {a, b, c} <= set(it["piezas"])


def test_cadena_expuesta_por_abajo_falla():
    d, _ = _transmision("abierta_abajo")
    it, p = _trans(d)
    assert p["estado"] == "FALLA"
    assert all(f["direccion"][2] > 0 for f in p["fallas"])  # sólo llega desde abajo


def test_cadena_encerrada_ok():
    d, _ = _transmision("cerrada")
    it, p = _trans(d)
    assert p["estado"] == "OK" and it["estado"] == "OK"


def test_prefijo_de_plantilla_no_es_rol():
    """«Faja de banda · Tensor trotadora» no es una banda: el primer tramo común de un
    super-comando es el nombre de la máquina (calibración: sin esto el tensor y la cama eran
    «flexibles»)."""
    from apolo.services.calidad_seguridad import datos_calidad

    d = Document()
    d.execute("create_belt_conveyor", {"largo": 2000, "ancho_banda": 400, "altura": 800})
    piezas = datos_calidad(d)["piezas"]
    assert piezas["c1_banda"].rol == "flexible"
    assert piezas["c1_tensor1"].rol != "flexible" and piezas["c1_cama"].rol != "flexible"
    assert piezas["c1_tambor_motriz"].rol == "gira"
