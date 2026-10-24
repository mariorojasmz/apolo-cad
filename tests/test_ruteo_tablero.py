"""Ruteo, largos y llenado del tablero armado (plan V8.5 F2: D3, D4, D9, A8, A10, D12).

- La faja piloto (`tests/data/tablero_piloto.json`: los aparatos de +TAB1, su cableado y lo de
  campo) armada con `layout_tablero`: el largo de cada conductor DE PLACA contra un ruteo hecho
  A MANO (polilínea por la ranura, el eje de la canaleta y la diagonal al tornillo, con las
  cotas del layout), ±5 %; los de puerta, contra el criterio del lazo, declarado (A8).
- Reglas: tramo directo (puente, mismo aparato, dos mandos de puerta), lazo de bisagra, salida
  al prensaestopas, «sale del tablero sin cable» (A10), largo declarado que difiere, llenado que
  se pasa (D3), la cara de cada borne por familia o por ficha (D4).
- BOM: los conductores sin largo se compran por el ruteado; la puerta (y la placa, si la trae)
  viene con el gabinete y no se cobra aparte (D9).
- D12: el ruteo se calcula al leer: editar un conductor no re-ejecuta el layout y el ruteo lo ve.
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

from apolo.doc.document import Document
from apolo.library.electrico.bornes_pos import CaraBorne, Criterio, caras
from apolo.library.electrico.colocacion_modelo import Canaleta, Colocado, Layout
from apolo.library.electrico.ruteo import ConBornes, Entrada, Marco, rutear

PILOTO = json.loads((Path(__file__).parent / "data" / "tablero_piloto.json").read_text(encoding="utf-8"))


def _acciones(conductores: list[dict] | None = None, gabinete: str | None = None) -> list[dict]:
    acc = []
    for d in PILOTO["dispositivos"]:
        p = {"ref": d["ref"], "designacion": d["designacion"], "ubicacion": "+TAB1"}
        if "cantidad" in d:
            p["cantidad"] = d["cantidad"]
        acc.append({"type": "add_device", "params": p})
    acc += [{"type": "add_device", "params": d} for d in PILOTO["campo"]]
    acc += [{"type": "add_cable", "params": {k: v for k, v in c.items() if k != "id"}}
            for c in PILOTO["cables"]]
    for c in PILOTO["conductores"] if conductores is None else conductores:
        acc.append({"type": "add_wire", "params": {k: v for k, v in c.items() if k != "id"}})
    acc.append({"type": "layout_tablero", "params": {"ubicacion": "TAB1",
                                                     **({"gabinete": gabinete} if gabinete else {})}})
    return acc


def _doc(acciones) -> Document:
    d = Document()
    d.execute_many(acciones)
    return d


@pytest.fixture(scope="module")
def piloto() -> Document:
    return _doc(_acciones())


def _tablero(doc):
    from apolo.services.tablero import ruteos

    (t,) = ruteos(doc)
    return t


def _ruta(t, *puntos):
    return next(r for r in t.ruteo.rutas if r.puntos == tuple(puntos))


def _largo(polilinea, reservas: int = 2) -> float:
    return sum(math.dist(a, b) for a, b in zip(polilinea, polilinea[1:])) + 50.0 * reservas


# ── el ruteo a mano de los conductores de placa (las cotas del layout, en mm de la placa) ────
# Layout de la piloto en el TABLERO-5040 (placa útil 450 × 350): -F1 u 199,5–253,5 v 235–325,
# -F2 253,5–289,5, -K1 199,5–309,5 v 110–210, -T1 309,5–381,5 v 115–205, -T2 (columna) u 25–165
# v 165–325, fondo 145. Canaletas 25 × 40 (eje a w = 20): arriba v = 337,5; bajo la fila de
# alimentación v = 222,5 (u 165–450); bajo control v = 97,5; bajo la columna v = 152,5 (u 0–190);
# verticales u = 12,5, 177,5 (la de la columna, hasta v = 325) y 437,5. Bornes: tornillo a 10 mm
# del borde de su cara y al 60 % del fondo (w = 52,5 en el riel; 87 en el variador, 43,5 en la
# fuente); la regleta de control del variador al frente (w = 145, v = 205).
A_MANO = {
    ("-F1:2", "-T2:L1"): [(208.5, 245, 52.5), (208.5, 222.5, 20), (177.5, 222.5, 20), (177.5, 337.5, 20),
                          (42.5, 337.5, 20), (42.5, 315, 87)],
    ("-F1:4", "-T2:L2"): [(226.5, 245, 52.5), (226.5, 222.5, 20), (177.5, 222.5, 20), (177.5, 337.5, 20),
                          (77.5, 337.5, 20), (77.5, 315, 87)],
    ("-F1:6", "-T2:L3"): [(244.5, 245, 52.5), (244.5, 222.5, 20), (177.5, 222.5, 20), (177.5, 337.5, 20),
                          (112.5, 337.5, 20), (112.5, 315, 87)],
    ("-F2:2", "-T1:L"): [(262.5, 245, 52.5), (262.5, 222.5, 20), (177.5, 222.5, 20), (177.5, 97.5, 20),
                         (321.5, 97.5, 20), (321.5, 125, 43.5)],
    # por la vertical derecha: 374 mm de canaleta contra 396 por la de la columna
    ("-F2:4", "-T1:N"): [(280.5, 245, 52.5), (280.5, 222.5, 20), (437.5, 222.5, 20), (437.5, 97.5, 20),
                         (345.5, 97.5, 20), (345.5, 125, 43.5)],
    ("-T2:RA", "-K1:I0.4"): [(110, 205, 145), (110, 152.5, 20), (177.5, 152.5, 20), (177.5, 222.5, 20),
                             (246.25, 222.5, 20), (246.25, 200, 52.5)],
    ("-K1:Q0.0", "-T2:DI1"): [(220.65, 120, 52.5), (220.65, 97.5, 20), (177.5, 97.5, 20), (177.5, 152.5, 20),
                              (30, 152.5, 20), (30, 205, 145)],
    ("-K1:Q0.3", "-T2:DI3"): [(246.04, 120, 52.5), (246.04, 97.5, 20), (177.5, 97.5, 20), (177.5, 152.5, 20),
                              (50, 152.5, 20), (50, 205, 145)],
}


def test_el_layout_es_el_que_se_midio_a_mano(piloto):
    t = _tablero(piloto)
    caja = {a.designacion: (a.u0, a.v0, a.ancho, a.alto, a.w0, a.w1) for a in t.layout.aparatos}
    assert caja["-F1"] == pytest.approx((199.5, 235, 54, 90, 7.5, 82.5))
    assert caja["-T2"] == pytest.approx((25, 165, 140, 160, 0, 145))
    assert caja["-K1"] == pytest.approx((199.5, 110, 110, 100, 7.5, 82.5))
    assert caja["-T1"] == pytest.approx((309.5, 115, 72, 90, 7.5, 67.5))
    assert caja["-S1"][:2] == pytest.approx((255, 275))


@pytest.mark.parametrize("puntos", list(A_MANO))
def test_cada_conductor_de_placa_con_5_por_ciento_de_la_mano(piloto, puntos):
    r = _ruta(_tablero(piloto), *puntos)
    mano = _largo(A_MANO[puntos])
    assert r.largo_mm == pytest.approx(mano, rel=0.05), (puntos, r.largo_mm, mano)
    assert not r.sale and len(r.segmentos) == 1 and r.segmentos[0].modo == "canaleta"


def test_el_de_la_f0_da_lo_mismo_que_la_mano(piloto):
    """-F1:2 → -T2:L1: 391,2 mm de recorrido + 100 de reserva (la F0 midió 485,7 en su layout)."""
    r = _ruta(_tablero(piloto), "-F1:2", "-T2:L1")
    assert r.largo_mm == pytest.approx(491.2, abs=0.2)
    assert r.declarado_mm == 500 and r.usado_mm == 500 and r.origen == "declarado"


def test_un_conductor_de_puerta_paga_el_lazo_de_bisagra(piloto):
    """A8: de -S1:14 por la puerta hasta la vertical de la bisagra (u 12,5) a media altura
    (v 175), el lazo de 300 y de ahí por las canaletas a -K1:I0.0 (u 224,25, v 200)."""
    r = _ruta(_tablero(piloto), "-S1:14", "-K1:I0.0")
    puerta = abs(277.5 - 12.5) + abs(290 - 175) + 300.0
    canaleta = _largo([(12.5, 175, 20), (12.5, 152.5, 20), (177.5, 152.5, 20), (177.5, 222.5, 20),
                       (224.25, 222.5, 20), (224.25, 200, 52.5)])
    assert r.largo_mm == pytest.approx(puerta + canaleta, rel=1e-3)
    assert "lazo de bisagra" in r.segmentos[0].criterio


def test_tramos_directos_puente_mismo_aparato_y_mandos_de_puerta(piloto):
    t = _tablero(piloto)
    puente = _ruta(t, "-T2:+10V", "-T2:AI1").segmentos[0]
    assert (puente.modo, puente.criterio) == ("directo", "tramo directo: puente")
    assert puente.largo_mm == pytest.approx(10 + 100)  # dos bornes vecinos de la regleta + reservas
    reparto = _ruta(t, "-T1:L+", "-K1:L+", "-K1:3L+", "-S1:13", "-S2:11", "-S0:11", "-T2:RC")
    modos = [(s.de, s.a, s.modo) for s in reparto.segmentos]
    assert ("-K1:L+", "-K1:3L+", "directo") in modos
    s = next(x for x in reparto.segmentos if x.de == "-S1:13")
    assert s.modo == "directo" and s.criterio == "tramo directo: dos mandos de la puerta"
    assert s.largo_mm == pytest.approx(70 + 100)  # -S1:13 (u 262,5) → -S2:11 (u 192,5), misma altura
    # sin la regla, cada mando pagaría dos lazos: el reparto de 24 V queda en ~3 m, no en 5
    assert reparto.largo_mm < 3200


def test_lo_que_sale_va_al_prensaestopas_y_sin_cable_avisa(piloto):
    from apolo.services.electrico import reglas_erc

    t = _tablero(piloto)
    red = _ruta(t, "-G1:L1", "-Q1:1")
    assert red.sale and red.cable is None and "prensaestopas" in red.segmentos[0].criterio
    motor = _ruta(t, "-T2:U", "-M1:U1")
    assert motor.sale and motor.cable == "-W1"
    filas = [r for r in reglas_erc(piloto) if r["regla"] == "sale del tablero sin cable"]
    nombrados = {f["detalle"].split(" (")[0] for f in filas}
    ids = {r.id for r in t.ruteo.rutas if r.sale and r.cable is None}
    assert len(filas) == 4 and nombrados == ids  # la red entra por 4 hilos sueltos (F0, A10)
    assert all("add_cable" in f["detalle"] and f["estado"] == "aviso" for f in filas)


def test_el_largo_declarado_que_no_se_sostiene_avisa(piloto):
    from apolo.services.electrico import reglas_erc

    filas = [r for r in reglas_erc(piloto) if r["regla"] == "largo declarado vs ruteado"]
    det = next(f["detalle"] for f in filas if "-Q1:2 → -F1:1 → -F2:1" in f["detalle"])
    assert "declarado 0.60 m" in det and "ruteado" in det and '{"largo_m": null}' in det
    # -F1:2 → -T2:L1 declara 0,50 y rutea 0,49: no avisa
    assert not any("-F1:2 → -T2:L1" in f["detalle"] for f in filas)


def test_la_bom_compra_lo_ruteado(piloto):
    """Sin `largo_m`, el conductor de dentro se compra por su ruteado; con él, el declarado (D3)."""
    from apolo.services.electrico import filas_bom

    sin = [{k: v for k, v in c.items() if k != "largo_m"} for c in PILOTO["conductores"]]
    d = _doc(_acciones(sin))
    t = _tablero(d)
    filas = {f["ref"]: f for f in filas_bom(d) if f["ref"].startswith("COND-")}
    esperado = sum(r.largo_mm for r in t.ruteo.rutas if not r.sale and r.cable is None
                   and any(c.get("tipo") == "COND-H07VK-2.5" and tuple(c["puntos"]) == r.puntos
                           for c in sin))
    f25 = filas["COND-H07VK-2.5"]
    assert f25["longitud_mm"] == pytest.approx(esperado, abs=0.5) and "aviso" not in f25
    assert f25["largo_origen"]["n_declarados"] == 0 and f25["largo_origen"]["n_ruteados"] == 7
    # los hilos sueltos de la red salen del tablero: sin largo declarado, siguen sin comprarse
    assert any(f["ref"] == "COND-H07VK-4" and f.get("sin_largo") for f in filas_bom(d))
    # con el declarado, la BOM de siempre (no se mezcla)
    f_decl = next(f for f in filas_bom(piloto) if f["ref"] == "COND-H07VK-2.5")
    assert f_decl["longitud_mm"] == pytest.approx(1000 * (0.6 + 0.6 + 0.4 + 0.5 * 3 + 1.5))
    assert "largo_origen" not in f_decl


def test_el_circuito_publica_el_largo_ruteado(piloto):
    from apolo.services.electrico import circuito

    c = circuito(piloto)
    f12 = next(x for x in c["conductores"] if x["puntos"] == ["-F1:2", "-T2:L1"])
    assert f12["largo_ruteado_m"] == pytest.approx(0.491, abs=1e-3) and f12["largo_m"] == 0.5
    red = next(x for x in c["conductores"] if x["puntos"] == ["-G1:L1", "-Q1:1"])
    assert red["sale_del_tablero"] is True


def test_el_llenado_de_la_piloto_sobra_y_el_que_se_pasa_avisa(piloto):
    from apolo.services.electrico import reglas_erc

    t = _tablero(piloto)
    assert t.ruteo.llenados and max(x.fraccion for x in t.ruteo.llenados) < 0.5
    assert all(t.canaletas[x.canaleta].startswith(f"{t.cid}_canaleta_") for x in t.ruteo.llenados)
    assert not [r for r in reglas_erc(piloto) if r["regla"] == "llenado de canaleta"]
    # 40 conductores de 4 mm² (Ø 4,5) más por la misma canaleta: 636 mm² de más sobre 756 útiles
    extra = [{"puntos": ["-F1:2", "-T2:L1"], "tipo": "COND-H07VK-4", "color": "BK"}] * 40
    d = _doc(_acciones(PILOTO["conductores"] + extra))
    filas = [r for r in reglas_erc(d) if r["regla"] == "llenado de canaleta"]
    assert filas and all(f["estado"] in ("aviso", "error") for f in filas)
    det = filas[0]["detalle"]
    assert "CANALETA-25X40" in det and "de 756 mm²" in det and "tope 50 %" in det
    assert filas[0]["elementos"][0].startswith(f"{_tablero(d).cid}_canaleta_")


def test_editar_un_conductor_no_rearma_y_el_ruteo_lo_ve():
    """D12: el ruteo no está en la geometría: se lee del carril vivo."""
    d = _doc(_acciones(PILOTO["conductores"][:8]))
    cid = next(c["id"] for c in d.commands if c["type"] == "add_wire"
               and c["params"]["puntos"] == ["-F1:2", "-T2:L1"])
    antes = d.scene[next(k for k in d.scene if k.endswith("_gabinete"))].shape
    d.edit(cid, {"puntos": ["-F1:2", "-T2:L2"], "tipo": "COND-H07VK-2.5"})
    assert d.scene[next(k for k in d.scene if k.endswith("_gabinete"))].shape is antes
    r = _ruta(_tablero(d), "-F1:2", "-T2:L2")
    assert r.largo_mm == pytest.approx(491.2 - 35, abs=0.2)  # L2 está 35 mm más cerca por arriba


# ── la puerta y la placa vienen con el gabinete (D9) ──────────────────────────────────────
def test_la_puerta_no_se_cobra_aparte(piloto):
    from apolo.library.bom import bom_from_scene
    from apolo.services.cobros import costeo
    from apolo.services.tablero import incluidas

    t = _tablero(piloto)
    inc = incluidas(piloto)
    assert inc == {f"{t.cid}_puerta": f"{t.cid}_gabinete"}  # el 5040 no trae placa (se compra)
    filas = bom_from_scene(piloto.scene, incluidas=inc)
    assert not any("Puerta" in f["descripcion"] for f in filas)
    gab = next(f for f in filas if f["ref"] == "TABLERO-5040")
    assert gab["incluye"] == ["Tablero +TAB1 · Puerta"]
    assert any("Placa de montaje" in f["descripcion"] for f in filas)
    descr = [r["descripcion"] for r in costeo(piloto)["rows"]]
    assert not any("Puerta" in x for x in descr) and any("Placa" in x for x in descr)


def test_un_gabinete_con_placa_la_trae():
    from apolo.services.tablero import incluidas

    d = _doc(_acciones([], gabinete="GAB-8060"))
    t = _tablero(d)
    assert incluidas(d) == {f"{t.cid}_puerta": f"{t.cid}_gabinete", f"{t.cid}_placa": f"{t.cid}_gabinete"}


# ── la cara de cada borne (D4) ─────────────────────────────────────────────────────────────
def test_caras_por_familia_por_ficha_y_supuestas():
    from apolo.library.catalog import CATALOG

    def de(ref, **kw):
        c = CATALOG[ref]
        t = c.tablero
        return caras([(b.id, b.lado) for b in c.electrico.bornes], tipo=c.electrico.modelo.get("tipo"),
                     montaje=c.electrico.montaje, bornera=c.electrico.bornera,
                     propias=t.bornes if t is not None else None, **kw)

    itm = de("ITM-C16-3P")
    assert [itm[b].cara for b in "123456"] == ["arriba", "abajo"] * 3
    cont = de("CONT-9A-24VDC")
    assert (cont["13"].cara, cont["14"].cara, cont["A1"].cara, cont["A2"].cara) == (
        "arriba", "abajo", "arriba", "abajo")
    plc = de("PLC-14DI-10DO-24VDC")
    assert (plc["I0.3"].cara, plc["Q0.3"].cara, plc["L+"].cara, plc["3M"].cara) == (
        "arriba", "abajo", "arriba", "abajo")
    vfd = de("VFD-2K2-220")
    assert (vfd["L1"].cara, vfd["U"].cara, vfd["DI1"].cara) == ("arriba", "abajo", "frente")
    assert vfd["L1"].origen.startswith("ficha: orden de SINAMICS V20")
    fuente = de("FUENTE-24VDC-5A")
    assert (fuente["L"].cara, fuente["L+"].cara) == ("abajo", "arriba") and fuente["L"].origen.startswith("ficha")
    assert {x.cara for x in de("PULS-22-VERDE-NA").values()} == {"atras"}
    assert de("BORNE-PE-4")["1"].cara == "ambas"
    assert de("CONT-AUX-1NA1NC", acopla_frente=True)["53"].cara == "frente"
    raro = caras([("X9", None)], tipo=None, montaje="din")
    assert raro["X9"] == CaraBorne("arriba", "supuesto")


def test_un_borne_supuesto_queda_marcado_en_el_ruteo():
    lay = Layout("G", (Colocado("-A1", "R", "placa", 100, 100, 40, 60, 0, 50, "control"),
                       Colocado("-A2", "R", "placa", 200, 100, 40, 60, 0, 50, "control")),
                 (), (Canaleta("v", 0, 25, 0, 300), Canaleta("v", 375, 400, 0, 300),
                      Canaleta("h", 0, 400, 275, 300), Canaleta("h", 0, 400, 50, 75)), ())
    raras = {"X": CaraBorne("arriba", "supuesto")}
    ap = {d: ConBornes(c, raras) for d, c in (("-A1", lay.aparatos[0]), ("-A2", lay.aparatos[1]))}
    r = rutear(lay, Marco(400, 300, 40, "izquierda", 20), ap, [Entrada("w1", ("-A1:X", "-A2:X"), 3.0)])
    assert any("centro de la cara de arriba" in s for s in r.rutas[0].supuestos)


# ── el llenado puro (D3) ───────────────────────────────────────────────────────────────────
def test_llenado_que_se_pasa_con_su_tramo():
    a1 = Colocado("-A1", "R", "placa", 50, 100, 40, 60, 0, 50, "control")
    a2 = Colocado("-A2", "R", "placa", 300, 100, 40, 60, 0, 50, "control")
    lay = Layout("G", (a1, a2), (), (Canaleta("v", 0, 25, 0, 300), Canaleta("v", 375, 400, 0, 300),
                                     Canaleta("h", 0, 400, 275, 300), Canaleta("h", 0, 400, 50, 75)), ())
    uno = {"1": CaraBorne("abajo", "familia"), "2": CaraBorne("arriba", "familia")}
    ap = {"-A1": ConBornes(a1, uno), "-A2": ConBornes(a2, uno)}
    marco = Marco(400, 300, 40, "izquierda", 20, util_mm2=400.0)
    hilos = [Entrada(f"w{i}", ("-A1:1", "-A2:1"), 4.5) for i in range(16)]  # 16 × 15,9 = 254 mm²
    r = rutear(lay, marco, ap, hilos)
    (abajo,) = [x for x in r.llenados if lay.canaletas[x.canaleta].v0 == 50]
    assert abajo.fraccion == pytest.approx(16 * math.pi * 4.5 ** 2 / 4 / 400.0, rel=1e-3)
    assert abajo.fraccion > 0.5 and abajo.pasa is not None
    a, b = abajo.pasa
    assert a == pytest.approx(70) and b == pytest.approx(320)  # de borne a borne por la canaleta
    assert len(abajo.conductores) == 16
    # con la mitad no pasa el tope
    r2 = rutear(lay, marco, ap, hilos[:8])
    assert all(x.pasa is None for x in r2.llenados)
    assert r2.criterio == Criterio().supuestos()


# ── la ficha `tablero.bornes` (D4) y las capas ─────────────────────────────────────────────
def test_la_ficha_de_bornes_se_valida():
    from apolo.library.electrico.ficha_tablero import parse_tablero

    ids = ("L", "N", "L+")
    ok = parse_tablero({"bornes": {"abajo": ["L", "N"], "arriba": ["L+"], "fuente": "orden de X"}},
                       "R", montaje="din", bornes=ids)
    assert ok.bornes.de("L+") == "arriba" and ok.bornes.fuente == "orden de X"
    with pytest.raises(ValueError, match="el borne «LL» no existe"):
        parse_tablero({"bornes": {"abajo": ["LL"], "fuente": "x"}}, "R", montaje="din", bornes=ids)
    with pytest.raises(ValueError, match="ya tiene cara"):
        parse_tablero({"bornes": {"abajo": ["L"], "arriba": ["L"], "fuente": "x"}}, "R",
                      montaje="din", bornes=ids)
    with pytest.raises(ValueError, match="fuente"):
        parse_tablero({"bornes": {"abajo": ["L"]}}, "R", montaje="din", bornes=ids)
    with pytest.raises(ValueError, match="sólo un aparato de placa o de riel"):
        parse_tablero({"bornes": {"abajo": ["L"], "fuente": "x"}}, "R", montaje="puerta", bornes=ids)


def test_el_ruteo_es_puro():
    carpeta = Path(__file__).resolve().parents[1] / "core" / "apolo" / "library" / "electrico"
    prohibidos = ("build123d", "OCP", "apolo.doc", "apolo.kernel", "apolo.library.catalog",
                  "apolo.commands", "apolo.services")
    for nombre in ("ruteo.py", "bornes_pos.py"):
        for nodo in ast.walk(ast.parse((carpeta / nombre).read_text(encoding="utf-8"))):
            mods = [a.name for a in nodo.names] if isinstance(nodo, ast.Import) else (
                [nodo.module or ""] if isinstance(nodo, ast.ImportFrom) and not nodo.level else [])
            assert not any(m.startswith(prohibidos) for m in mods), nombre
            if isinstance(nodo, ast.ImportFrom) and nodo.level:
                assert (nodo.module or "") not in ("catalog", "loader", "builders"), nombre


def test_sin_tablero_armado_nada_cambia():
    from apolo.services.electrico import filas_bom, reglas_erc
    from apolo.services.tablero import incluidas, ruteos

    acc = [a for a in _acciones() if a["type"] != "layout_tablero"]
    d = _doc(acc)
    assert ruteos(d) == [] and incluidas(d) == {}
    reglas = {r["regla"] for r in reglas_erc(d)}
    assert not reglas & {"llenado de canaleta", "sale del tablero sin cable", "largo declarado vs ruteado"}
    assert not any("largo_origen" in f for f in filas_bom(d))
