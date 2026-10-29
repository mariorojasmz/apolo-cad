"""`create_roller_conveyor` F9: lo que el piloto de la familia `rodillos-cadena` destapó en la
plantilla (plan `docs/plans/plantilla-rodillos-cadena.md`, § F9 — contrato, E11–E19; medido en
§ Bitácora F9).

- E11: `union: "empernado"` (placas de cabeza y orejas de travesaño atornilladas);
- E12–E14: `motor: "auto"` (el sello) = el sinfín NMRV más chico que da la cuenta a la tensión de
  la red, con su cadena a FS ≥ 1,2 contra el par nominal y el piñón del motor ≥ Z17, de ejes
  ortogonales: arma con W 400;
- E15–E18 (`mantenimiento`, el sello): tensor empujador y pernos modelados con bujes, cárter
  atornillado, tapas extremas, peine y faldón interior de la guarda de cadenas, largos declarados;
- E19: la salida del motorreductor se sondea sólo por la cara por la que sale lo que gira.

Un log v4 (sin los campos nuevos) regenera idéntico: huella congelada con el código de e7ab995.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from apolo.commands.registry import REGISTRY
from apolo.doc import Document
from apolo.library import rodillos_cadena_sinfin as sf
from apolo.library.bom import bom_from_scene
from apolo.library.catalog import CATALOG
from apolo.library.rodillos_cadena import disposicion
from banco_guardas import interferencias_sin_tope

#: el piloto de la familia (L, W, H de la tienda) y el máximo; mercado Perú (Lima, 220 V)
PILOTO = {"largo": 2000, "ancho_util": 400, "altura": 500, "carga_kg": 500,
          "velocidad_m_s": 0.25, "union": "empernado", "red_v": 220}
MAXIMO = {"largo": 4000, "ancho_util": 800, "altura": 750, "carga_kg": 450,
          "velocidad_m_s": 0.25, "union": "empernado", "red_v": 220}
F8 = {"taller": True, "eje": "hexagonal", "pie": "base"}
#: un log v4 (F8 sellado, sin `mantenimiento` ni `motor`): huella con el código de e7ab995
HUELLA_V4 = {"libre": ((176, 212, "2e25259503a588a5"),
                       [10469859.28, 127349.36, -9527.6, 103850.38, 136650.64, 9527.6, 112421.42]),
             "cadena": ((402, 502, "9b9dcc343ef4582c"),
                        [32241799.25, 603614.6, 10836.29, 250111.19, 638891.95, 55159.12,
                         271473.52])}
LOGS_V4 = {"libre": {"largo": 1500, "ancho_util": 400, "paso": 75, "motriz": "libre", **F8},
           "cadena": {"largo": 3000, "velocidad_m_s": 0.25, "carga_kg": 200, **F8}}


def _doc(params: dict) -> Document:
    doc = Document("rodillos-f9")
    doc.execute("create_roller_conveyor", dict(params))
    return doc


@pytest.fixture(scope="module")
def piloto():
    return _doc(PILOTO)


@pytest.fixture(scope="module")
def maximo():
    return _doc(MAXIMO)


def _disp(p: dict):
    return disposicion(p["largo"], p["ancho_util"], 95.25, "TUBOR-2", p["altura"], p["carga_kg"],
                       True, "auto", p["velocidad_m_s"], True, True, "hexagonal", "base",
                       p["red_v"], p["union"], True)


def _huella(doc) -> tuple:
    piezas = sorted([fid, f.name, f.component or ""] for fid, f in doc.scene.items())
    uniones = sorted([u["name"], u["kind"], u["a"], u["b"], u.get("nota", "")]
                     for u in doc.fasteners.values())
    anclajes = sorted([g["feature"], g.get("nota", "")] for g in doc.grounds.values())
    s = json.dumps([piezas, uniones, anclajes], ensure_ascii=False)
    return len(piezas), len(uniones), hashlib.sha256(s.encode()).hexdigest()[:16]


def _geom(doc) -> list[float]:
    v, c = 0.0, [0.0] * 6
    for f in doc.scene.values():
        b = f.shape.bounding_box()
        v += float(f.shape.volume)
        for i, x in enumerate((b.min.X, b.min.Y, b.min.Z, b.max.X, b.max.Y, b.max.Z)):
            c[i] += x
    return [v, *c]


# ------------------------------------------------------------------ el sello y la compatibilidad
def test_el_comando_nuevo_nace_con_motor_auto_y_mantenimiento(piloto):
    p = piloto.commands[0]["params"]
    assert (p["motor"], p["mantenimiento"], p["union"]) == ("auto", True, "empernado")
    spec = REGISTRY["create_roller_conveyor"]
    assert spec.version == 5
    props = spec.model.model_json_schema()["properties"]
    assert "mantenimiento" not in props and {"red_v", "union"} <= set(props)
    assert "auto" in props["motor"]["enum"]
    # un log v4 no trae los campos: el motor y la motriz de siempre
    m = spec.model.model_validate(LOGS_V4["cadena"])
    assert (m.motor, m.mantenimiento, m.union, m.red_v) == ("MOTOR-037", False, "soldado", 220)


@pytest.mark.parametrize("caso", ["libre", "cadena"])
def test_un_log_v4_regenera_las_mismas_piezas_y_cotas(caso):
    doc = _doc({**LOGS_V4[caso], "mantenimiento": False, "motor": "MOTOR-037"})
    assert doc.check_integrity() == []
    assert _huella(doc) == HUELLA_V4[caso][0]
    v, *c = _geom(doc)
    assert v == pytest.approx(HUELLA_V4[caso][1][0], rel=1e-6)
    assert c == pytest.approx(HUELLA_V4[caso][1][1:], abs=0.5)


# ------------------------------------------------------------------ E12–E14 (puro)
@pytest.mark.parametrize("p", [PILOTO, MAXIMO], ids=["piloto", "maximo"])
def test_motor_auto_sinfin_a_220_v_con_la_cadena_por_su_par_nominal(p):
    d = _disp(p)
    m = d.motriz
    assert m.tipo == "sinfin" and CATALOG[m.motor].category == "motorreductores_sinfin"
    assert sf.sirve_red(m.motor, 220.0) and 220.0 in sf.tensiones(m.motor)
    assert m.z_pinon >= sf.Z_MOTRIZ_MIN
    assert d.velocidad_m_s == pytest.approx(0.25, rel=0.10)
    assert d.potencia_req_kw <= m.potencia_kw
    rpm_rodillo = d.velocidad_m_s * 60000.0 / (3.141592653589793 * d.d_rodillo)
    assert sf.fs_cadena(m.potencia_kw, rpm_rodillo) >= sf.FS_CADENA
    assert d.ancho_util == p["ancho_util"]  # E13: el ancho útil es W, con el motor debajo


def test_un_motor_de_400_v_no_sirve_en_lima():
    assert not sf.sirve_red("MOTOR-150", 220.0)  # «400V»
    assert sf.sirve_red("MOTOR-037", 220.0)      # «230/400V»: 230 a −4,3 % (zona A)
    assert sf.sirve_red("NMRV-040", 220.0)


def test_si_ningun_motor_sirve_el_error_dice_que_falta():
    with pytest.raises(ValueError, match=r"FS .* < 1\.2.*kW|kW.*FS .* < 1\.2"):
        _disp({**PILOTO, "carga_kg": 1500})


# ------------------------------------------------------------------ E19 (la puerta, puro + OCCT)
def test_la_salida_del_sinfin_se_sondea_solo_por_donde_sale_el_eje():
    """El eje que sale SÓLO por la brida (−Y): ningún objetivo del lado de la tapa (+Y)."""
    from apolo.services.calidad_seguridad import analisis

    d = Document("salida")
    base = d.execute("create_box", {"name": "Base", "width": 800, "depth": 400, "height": 20,
                                    "position": {"x": 0, "y": 0, "z": 10}})
    d.execute("ground", {"name": "piso", "feature": base})
    mot = d.execute("insert_component", {"component": "NMRV-050",
                                         "position": {"x": 0, "y": 0, "z": 600}})
    eje = d.execute("create_cylinder", {"name": "Eje de salida Ø25", "radius": 12.5,
                                        "height": 230, "position": {"x": 0, "y": -135, "z": 600},
                                        "rotation": {"x": 90}})
    d.execute("add_joint", {"name": "giro", "type": "continua", "parent": base, "child": eje,
                            "origin": {"x": 0, "y": 0, "z": 600}, "axis": {"y": 1}})
    sal = [p for p in analisis(d)["peligros"] if p["id"] == f"salida_motor:{mot}:{eje}"]
    assert sal and sal[0]["objetivos"]
    assert all(o[1] < 0 for o in sal[0]["objetivos"])


# ------------------------------------------------------------------ las máquinas
def test_el_piloto_arma_con_w_400_empernado_y_sin_choques(piloto):
    sc = piloto.scene
    tubo = sc["c1_tubo"].shape.bounding_box()
    assert tubo.max.Y - tubo.min.Y == pytest.approx(PILOTO["ancho_util"], abs=0.01)
    assert CATALOG[sc["c1_motor"].component].category == "motorreductores_sinfin"
    tipos = {u["name"]: u["kind"] for u in piloto.fasteners.values()}
    pata_larg = [k for n, k in tipos.items() if "_pata_larg_" in n]
    trav_pata = [k for n, k in tipos.items() if "_trav_pata_" in n]
    assert pata_larg and set(pata_larg) == {"perno"}   # E11: nada soldado entre larguero y pata
    assert trav_pata and set(trav_pata) == {"perno"}
    assert tipos["c1_carter_base0"] == "perno"          # E16
    assert {"c1_tapa_ext0", "c1_tapa_ext1", "c1_peine", "c1_faldon_int", "c1_collar_eje",
            "c1_perno_tensor_m", "c1_perno_tensor_p"} <= set(sc)
    assert interferencias_sin_tope({f: x.shape for f, x in sc.items()}, set()) == []


def test_ninguna_union_perno_queda_sin_largo_en_la_bom(piloto):
    """E18: lo modelado sale con su largo de catálogo y lo declarado, con su designación."""
    from apolo.library.tornilleria_declarada import filas_declaradas

    filas = bom_from_scene(piloto.scene, piloto.default_material())
    filas += filas_declaradas(piloto.scene, piloto.fasteners)
    assert not [f for f in filas if "sin declarar" in json.dumps(f, ensure_ascii=False)]
    pernos = [u for u in piloto.fasteners.values() if u["kind"] == "perno"]
    assert pernos and all("DIN" in (u.get("nota") or "") for u in pernos)


def test_la_carrera_del_tensor_cabe_y_su_tornillo_es_de_catalogo(piloto):
    from apolo.library.largos_perno import en_catalogo

    m = _disp(PILOTO).motriz
    for s in ("m", "p"):
        perno = piloto.scene[f"c1_perno_tensor_{s}"]
        assert en_catalogo("PERNO-HEX-M10", perno.cut_length)
        # la oreja baja el recorrido de tensado antes de tocar el tope (con la contratuerca)
        tope, oreja = piloto.scene[f"c1_tope_{s}"].shape, piloto.scene[f"c1_oreja_{s}"].shape
        assert tope.distance_to(oreja) >= m.tensado_mm
        assert perno.shape.distance_to(tope) < 0.05  # la cabeza apoya en el tope


@pytest.mark.torture
def test_el_maximo_arma_sin_choques(maximo):
    sc = maximo.scene
    assert CATALOG[sc["c1_motor"].component].category == "motorreductores_sinfin"
    assert interferencias_sin_tope({f: x.shape for f, x in sc.items()}, set()) == []


# ------------------------------------------------------------------ la puerta (tortura)
def _puerta(doc) -> dict:
    from apolo.library.calidad.registro import evaluar
    from apolo.services import puerta_publicacion as pp

    ins = pp.reunir(doc, expand=lambda x: x, gravedad={
        "resultado": {"fell": [], "estables": list(doc.scene), "n_grounded": len(doc.grounds)},
        "motivo": ""}, sobrantes=False)
    ins["marcha"] = {"resultado": "sin_marcha", "detalle": "no se corre en este test"}
    return {i["id"]: i for i in evaluar(ins)["items"]}


GATE = ("entrega.semaforo", "union.acceso_herramienta", "riesgos.partes_moviles",
        "consumibles.reemplazables", "riesgos.resguardos_desmontables_con_herramienta",
        "union.contacto_real", "union.distancia_al_borde")


@pytest.mark.torture
@pytest.mark.parametrize("cual", ["piloto", "maximo"])
def test_la_puerta_no_falla_en_lo_que_es_de_la_plantilla(cual, request):
    items = _puerta(request.getfixturevalue(cual))
    assert {i: items[i]["estado"] for i in GATE} == {i: "OK" for i in GATE}
    # E14: la cadena con FS ≥ 1,2 contra el par nominal del motor elegido
    fs = [v["fs"] for v in items["transmision.capacidad"]["evidencia"]["valores"]]
    assert fs and min(fs) >= 1.2


@pytest.mark.torture
@pytest.mark.xfail(strict=True, reason=(
    "Bitácora F9 (F9-e): la regla «transmisión por cadena» da AVISO (→ FALLA en el ítem) por el "
    "Z15 del piñón doble-simple del rodillo (< 17: el único de catálogo) y por los 12 pasos de "
    "centros de la cadena motriz (< 30 salvo 1:1); con H 500 y 0,25 m/s no hay geometría ni "
    "relación NMRV que lo evite. Decisión de Mario."))
def test_transmision_capacidad_sin_falla(piloto):
    assert _puerta(piloto)["transmision.capacidad"]["estado"] == "OK"
