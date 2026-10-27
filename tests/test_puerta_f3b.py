"""F3b de puerta-sin-sobrediseno: falsos positivos y huecos en máquinas que NO son fajas (una
mezcladora, un tanque con agitador y un elevador modelados por MCP dieron lo mismo).

Cada punto con su modelo mínimo, verde y rojo: (1) la bisagra de servicio no es peligro y la
accionada sí; (2) resguardo = lo que cubre un peligro o lo declarado, y lo soldado con acceso por un
resguardo móvil es cerramiento; (3) la L10 lee las rpm y la carga DECLARADAS, sin inventar;
(4) las funciones tienen su canal (no son un requisito); (5) el piso es el apoyo de lo anclado;
(6) el acople y la salida del motorreductor son peligro.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.seguridad.modelo import Pieza, Redondo
from apolo.library.seguridad.transmision_rigida import acoples_rigidos, pares_salida
from apolo.services.calidad_juntas import clasificar
from apolo.services.calidad_seguridad import (
    ID_GUARDA,
    analisis,
    controles_seguridad,
    datos_calidad,
    resguardos,
)


def _caja(d, nombre, w, dp, h, x=0.0, y=0.0, z=0.0):
    return d.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                    "position": {"x": x, "y": y, "z": z}})


# ------------------------------------------------------------------ (1) juntas de servicio
def _gabinete(tipo: str = "giratoria"):
    """Un gabinete anclado con su puerta en bisagra y un piloto montado en la puerta."""
    d = Document("gabinete")
    g = _caja(d, "Gabinete", 400, 200, 600, z=300)
    d.execute("ground", {"name": "piso", "feature": g})
    p = _caja(d, "Puerta", 400, 2, 600, y=-101, z=300)
    m = _caja(d, "Piloto Ø22", 30, 30, 30, x=100, y=-117, z=400)
    d.execute("add_joint", {"name": "bisagra", "type": tipo, "parent": g, "child": p,
                            "origin": {"x": -200, "y": -101, "z": 300}, "axis": {"z": 1},
                            "lower": 0, "upper": 110})
    d.execute("add_joint", {"name": "fija_piloto", "type": "fija", "parent": p, "child": m})
    return d, g, p, m


def test_la_bisagra_de_servicio_no_es_peligro():
    d, _g, p, m = _gabinete()
    assert clasificar(d)["bisagra"]["accionada"] is False
    an = analisis(d)
    assert not an["peligros"] and not an["gira"]
    assert {p, m} <= an["moviles"]  # se mueve igual: no es resguardo fijo ni ancla un cable


@pytest.mark.parametrize("como", ["continua", "escenario", "actuador"])
def test_la_junta_accionada_si_es_peligro(como):
    d, g, p, _m = _gabinete("continua" if como == "continua" else "giratoria")
    if como == "escenario":
        d.escenarios = {"abre": {"escenario": {"acoples": {"motores": {"-M1": {"junta": "bisagra"}}}}}}
    if como == "actuador":
        mot = d.execute("insert_component", {"component": "NMRV-050",
                                             "position": {"x": 0, "y": -300, "z": 300}})
        d.execute("fasten", {"name": "u", "a": mot, "b": p, "kind": "perno"})
    c = clasificar(d)["bisagra"]
    assert c["accionada"] is True, c
    ids = [x["id"] for x in analisis(d)["peligros"]]
    assert any(i.startswith("giro:") for i in ids), ids


# ------------------------------------------------------------------ (2) qué es resguardo
def _rg(*guardas):
    return {"guardas": [{"ids": [i], "nombre": i, "estado": e, "motivo": "", "pernos": [],
                         "soldadas": ["x"] if e == "FALLA" else [], "contactos": [],
                         "moviles": []} for i, e in guardas], "excluidas_por_girar": []}


def test_resguardo_es_lo_que_cubre_un_peligro_o_lo_declarado():
    rg = _rg(("tapa_bornera", "FALLA"), ("guarda", "OK"), ("declarada", "FALLA"))
    res = {"giro:x": {"bloqueado_por": ["guarda", "pared"]}}
    r = resguardos(rg, res, set(), {"declarada"})
    assert [g["nombre"] for g in r["guardas"]] == ["guarda", "declarada"]
    assert r["no_resguardan"] == [{"ids": ["tapa_bornera"], "nombre": "tapa_bornera"}]


def test_lo_soldado_con_acceso_por_un_resguardo_movil_es_cerramiento():
    rg = _rg(("tapa_soldada", "FALLA"))
    con_boca = resguardos(rg, {"eje": {"bloqueado_por": ["tapa_soldada", "boca"]}}, {"boca"}, set())
    assert con_boca["guardas"][0]["estado"] == "OK"
    assert "cerramiento permanente" in con_boca["guardas"][0]["motivo"]
    # sin la boca (o detrás de una guarda atornillada) sigue siendo FALLA
    sin_boca = resguardos(rg, {"eje": {"bloqueado_por": ["tapa_soldada", "guarda"]}}, set(), set())
    assert sin_boca["guardas"][0]["estado"] == "FALLA"


def test_la_tapa_que_no_cubre_nada_no_se_juzga_como_resguardo():
    d = Document("tapa-suelta")
    base = _caja(d, "Base", 600, 400, 20, z=10)
    d.execute("ground", {"name": "piso", "feature": base})
    tapa = _caja(d, "Tapa final de bornera", 40, 10, 40, x=250, y=150, z=40)
    d.execute("fasten", {"name": "u", "a": tapa, "b": base, "kind": "contacto"})
    rg = analisis(d)["guardas"]
    assert [g["estado"] for g in rg["guardas"]] == ["FALLA"]  # el rol sale del nombre
    it = next(i for i in controles_seguridad(d, electrico=False)["items"] if i["id"] == ID_GUARDA)
    assert it["estado"] == "NO_APLICA" and it["evidencia"]["no_resguardan"][0]["ids"] == [tapa]


# ------------------------------------------------------------------ (3) la L10 con lo declarado
def _rodamientos(rpm_var=None, **req):
    d = Document("agitador")
    for x in (0, 200):
        d.execute("insert_component", {"component": "6205", "position": {"x": x}})
    if rpm_var is not None:
        d.execute("set_variable", {"name": "rpm_salida", "expression": str(rpm_var)})
    if req:
        d.set_requirements(req)
    return d


def _l10(d):
    from apolo.services.engineering_rules import structure_rules

    return [r for r in structure_rules(d, (d.requirements or {}).get("carga_kg"), None)
            if r["regla"].startswith("vida L10")]


def test_l10_sin_rpm_ni_carga_no_se_calcula():
    (r,) = _l10(_rodamientos())
    assert r["estado"] == "aviso" and "sin rpm" in r["detalle"]


def test_l10_con_rpm_declaradas_y_sin_carga_lo_dice_sin_inventarla():
    (r,) = _l10(_rodamientos(rpm_var=43, carga_kg=550))  # el producto no es lo que carga el eje
    assert r["estado"] == "aviso" and "43 rpm (variable rpm_salida)" in r["detalle"]
    assert "carga_rodamiento_n" in r["recomendacion"] and not r.get("calc")


def test_l10_con_rpm_y_carga_declaradas_se_calcula():
    (r,) = _l10(_rodamientos(rpm_var=43, rpm_salida=200, carga_rodamiento_n=800))
    assert r["calc"]["entradas"]["velocidad"] == "200 rpm"  # el requisito gana a la variable
    assert "requisito rpm_salida" in r["detalle"] and r["estado"] == "ok"
    (malo,) = _l10(_rodamientos(rpm_salida=1500, carga_rodamiento_n=6000))
    assert malo["estado"] == "error"


# ------------------------------------------------------------------ (4) las funciones, por su canal
def test_funciones_no_es_un_requisito():
    from apolo.library.requisitos import normalizar_requisitos

    for valor in ([{"funcion": "x"}], '[{"funcion": "x"}]'):
        with pytest.raises(ValueError, match="set_functions"):
            normalizar_requisitos({"funciones": valor})


def test_funciones_acepta_el_objeto_y_los_sinonimos_y_la_puerta_las_lee(monkeypatch):
    from apolo.library.calidad import puerta as P

    d = Document("f")
    monkeypatch.setattr(api, "DOC", d)
    c = TestClient(api.app)
    r = c.put("/api/funciones", json={"funciones": {
        "accionamiento": {"solucion": "NMRV eje hueco", "descartadas": [
            {"alternativa": "coaxial + cadena", "motivo": "más piezas que resguardar"}]},
        "estructura": {"solucion": "pórticos soldados", "alternativas": [
            {"solucion": "riostras bajas", "motivo": "redundantes con la base anclada"}]}}})
    assert r.status_code == 200, r.text
    assert [f["descartadas"][0]["solucion"] for f in d.funciones] == ["coaxial + cadena",
                                                                     "riostras bajas"]
    fams = {"accionamiento": ["m"], "estructura": ["e"]}
    assert P.soluciones_por_funcion({"hechos": {"familias_funcion": fams},
                                     "funciones": d.funciones})["estado"] == "OK"


# ------------------------------------------------------------------ (5) el piso
def test_el_piso_es_el_apoyo_de_lo_anclado_no_el_perno_que_entra_en_la_losa():
    d = Document("anclada")
    placa = _caja(d, "Placa de anclaje", 200, 200, 10, z=5)
    d.execute("ground", {"name": "piso", "feature": placa})
    perno = _caja(d, "Perno de anclaje de expansión M12x100", 12, 12, 100, z=-40)
    d.execute("fasten", {"name": "u", "a": perno, "b": placa, "kind": "perno"})
    dc = datos_calidad(d)
    assert dc["caja"][0][2] == pytest.approx(-90.0) and dc["z_piso"] == pytest.approx(0.0)


# ------------------------------------------------------------------ (6) acople y salida del motor
def _p(i, rol="", cat=None, caja=((0, 0, 0), (10, 10, 10)), redondo=None):
    return Pieza(i, i, rol, cat, None, caja, redondo)


def test_el_acople_entre_el_motor_y_lo_que_gira_gira():
    piezas = {"ac": _p("ac"), "mot": _p("mot", "equipo", "motorreductores"),
              "tam": _p("tam", "gira", "tambores"), "est": _p("est", "estructura"),
              "base": _p("base")}
    uniones = [{"a": "ac", "b": "tam", "kind": "perno"}, {"a": "ac", "b": "mot", "kind": "perno"},
               {"a": "base", "b": "mot", "kind": "perno"}, {"a": "base", "b": "est", "kind": "perno"}]
    cuerpo = {"tam": frozenset({"tam"})}
    assert acoples_rigidos(piezas, uniones, {"tam"}, cuerpo) == {"ac"}  # la base no: no toca giro
    soldado = [{**u, "kind": "soldadura"} if u["a"] == "ac" else u for u in uniones]
    assert acoples_rigidos(piezas, soldado, {"tam"}, cuerpo) == set()


def test_el_acople_de_la_plantilla_de_faja_es_peligro():
    d = Document("faja")
    d.execute("create_belt_conveyor", {})
    an = analisis(d)
    assert "c1_acople" in an["acoples"]
    (t,) = [p for p in an["peligros"] if p["id"].startswith("transmision:")]
    assert t["piezas"] == ["c1_acople"] and t["tipo"] == "enganche"


def test_par_salida_del_motorreductor_con_el_eje_que_lo_cruza():
    mot = _p("mot", "equipo", "motorreductores_sinfin", ((-60, -50, -80), (60, 50, 80)))
    eje = _p("eje", "eje", None, ((-12, -300, -12), (12, 60, 12)),
             Redondo(1, (0.0, -120.0, 0.0), 12.0, 360.0))
    lejos = _p("lejos", "eje", None, ((288, -300, -12), (312, 60, 12)),
               Redondo(1, (300.0, -120.0, 0.0), 12.0, 360.0))
    piezas = {"mot": mot, "eje": eje, "lejos": lejos}
    assert [(m, e) for m, e, _c in pares_salida(piezas, [{"eje"}, {"lejos"}])] == [("mot", "eje")]


def test_la_salida_del_eje_hueco_expuesta_es_peligro_y_alcanzable():
    d = Document("eje-hueco")
    base = _caja(d, "Base", 800, 400, 20, z=10)
    d.execute("ground", {"name": "piso", "feature": base})
    mot = d.execute("insert_component", {"component": "NMRV-050",
                                         "position": {"x": 0, "y": 0, "z": 600}})
    eje = d.execute("create_cylinder", {"name": "Eje de salida Ø25", "radius": 12.5,
                                        "height": 300, "position": {"x": 0, "y": -100, "z": 600},
                                        "rotation": {"x": 90}})
    d.execute("add_joint", {"name": "giro", "type": "continua", "parent": base, "child": eje,
                            "origin": {"x": 0, "y": 0, "z": 600}, "axis": {"y": 1}})
    an = analisis(d)
    sal = [p for p in an["peligros"] if p["id"] == f"salida_motor:{mot}:{eje}"]
    assert sal and sal[0]["objetivos"] and sal[0]["forman"] == [mot]
    r = controles_seguridad(d, an=an, electrico=False, brazo_doblado=False)
    assert r["resultados"][sal[0]["id"]]["estado"] == "FALLA"  # sin tapa: la mano llega al cubo
