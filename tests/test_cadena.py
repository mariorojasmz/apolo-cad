"""Comando `create_chain` y regla «transmisión por cadena» (plan `docs/plans/cadenas-pinones.md`,
F2: D7, D8, D9, D11, D12).

La cadena es RELACIONAL: se arma entre dos piñones de catálogo ya colocados, lee sus anclas
vivas en cada regenerate, cierra el lazo con eslabones pares sentados en los asientos de los
dientes, declara el contacto con cada piñón y la regla la recalcula desde el log.
"""

from __future__ import annotations

import math
import random
import time

import pytest
from fastapi.testclient import TestClient

from apolo.commands import CommandError
from apolo.commands.exec_transmision import medir_transmision
from apolo.commands.models_transmision import CreateChainParams
from apolo.commands.registry import DEFINITIONS
from apolo.doc import Document, DocumentError
from apolo.library.bom import bom_from_scene
from apolo.library.catalog import CATALOG
from apolo.library.checks import MIN_VOLUME_MM3
from apolo.library.engineering.cadena import regla_cadena
from apolo.library.transmision import eslabones_pares
from apolo.services.transmision_rules import chain_rules

ERRORES = (DocumentError, CommandError)


def _par(doc, ref_a="PINON-ASA40-1-Z15", ref_b=None, c=95.25, rot_a=(0, 0, 0), rot_b=None,
         pos_b=None):
    """Dos piñones: A en el origen y B a `c` en X (o en `pos_b`), con giros XYZ."""
    rot_b = rot_a if rot_b is None else rot_b
    a = doc.execute("insert_component", {"component": ref_a, "rotation": dict(zip("xyz", rot_a))})
    b = doc.execute("insert_component", {
        "component": ref_b or ref_a, "position": pos_b or {"x": c},
        "rotation": dict(zip("xyz", rot_b)),
    })
    return a, b


def _vol(s) -> float:
    if s is None:
        return 0.0
    return s.volume if hasattr(s, "volume") else sum(x.volume for x in s)


def _regla(doc, inicio="transmisión por cadena"):
    return next(r for r in chain_rules(doc) if r["regla"].startswith(inicio))


# ------------------------------------------------------------------ el comando
def test_cadena_entre_dos_pinones_eslabones_pares_largo_y_contactos():
    doc = Document("cadena")
    a, b = _par(doc, "PINON-ASA40-1-Z15", "PINON-ASA40-1-Z30", c=400.0)
    cid = doc.execute("create_chain", {"name": "Cadena motriz", "pinon_a": a, "pinon_b": b})
    f = doc.scene[cid]
    n, _cx = eslabones_pares(12.7, 15, 30, 400.0)
    assert n % 2 == 0
    assert f.component == "CADENA-ASA40-1" and f.cut_length == pytest.approx(n * 12.7)
    assert f.mesh_key in DEFINITIONS and f.matrix is not None and len(f.shape.solids()) == 1
    for lado, fid in (("a", a), ("b", b)):
        fij = doc.fasteners[f"{cid}_{lado}"]
        assert (fij["a"], fij["b"], fij["kind"], fij["command_id"]) == (cid, fid, "contacto", cid)
    fila = next(r for r in bom_from_scene(doc.scene) if r["ref"] == "CADENA-ASA40-1")
    assert f"({n} eslabones)" in fila["descripcion"]
    assert fila["peso_unitario_kg"] == pytest.approx(0.62 * n * 12.7 / 1000, abs=1e-3)


@pytest.mark.parametrize("cadena,ref_a,ref_b,c,hilera,detalle,volteado", [
    ("CADENA-ASA40-1", "PINON-ASA40-1-Z15", "PINON-ASA40-1-Z30", 300.0, 1, "eslabones", True),
    ("CADENA-08B-1", "PINON-08B-1-Z14", "PINON-08B-1-Z25", 250.0, 1, "eslabones", False),
    ("CADENA-ASA40-1", "PINON-ASA40-DS-Z15", "PINON-ASA40-DS-Z15", 95.25, 2, "eslabones", False),
    ("CADENA-ASA40-2", "PINON-ASA40-2-Z15", "PINON-ASA40-2-Z14", 200.0, 1, "eslabones", False),
    ("CADENA-10B-1", "PINON-10B-1-Z15", "PINON-10B-1-Z19", 300.0, 1, "simple", False),
    ("CADENA-08B-1", "PINON-08B-DS-Z14", "PINON-08B-DS-Z14", 101.6, 1, "simple", False),
])
def test_la_cadena_no_choca_con_sus_pinones_con_fases_arbitrarias(cadena, ref_a, ref_b, c, hilera,
                                                                   detalle, volteado):
    """Rodillos sentados en los asientos: con fases al azar y ejes cualesquiera (incluso un piñón
    VOLTEADO), el volumen común cadena ↔ piñón queda bajo la tolerancia de interferencia. Fuera:
    la 40B12 y la 08B z9, cuyo cubo PUBLICADO solapa la placa (test aparte)."""
    azar = random.Random(f"{cadena}-{ref_a}-{ref_b}")
    fa, fb = azar.uniform(0, 360), azar.uniform(0, 360)
    doc = Document("fases")
    a, b = _par(doc, ref_a, ref_b, pos_b={"x": c, "z": 40.0}, rot_a=(90, 0, fa),
                rot_b=(-90 if volteado else 90, 0, fb))
    doc.execute("transform", {"feature": b, "translate": {"z": -40.0}})
    cid = doc.execute("create_chain", {"cadena": cadena, "pinon_a": a, "pinon_b": b,
                                       "hilera_a": hilera, "hilera_b": hilera, "detalle": detalle})
    cadena_3d = doc.scene[cid].shape
    for fid in (a, b):
        assert _vol(cadena_3d & doc.scene[fid].shape) < MIN_VOLUME_MM3, fid


def test_los_cubos_publicados_que_solapan_la_cadena_estan_declarados():
    """La 40B12 (cubo Ø39.7) y la 08B z9 (Ø24) pasan el cubo máximo que deja la placa: el solape
    es del dato publicado, no del comando, y su `no_publicado` lo dice."""
    for ref, cadena in (("PINON-ASA40-1-Z12", "CADENA-ASA40-1"), ("PINON-08B-1-Z9", "CADENA-08B-1")):
        doc = Document("cubos")
        a, b = _par(doc, ref, "PINON-08B-1-Z25" if "08B" in ref else "PINON-ASA40-1-Z30", c=250.0)
        cid = doc.execute("create_chain", {"cadena": cadena, "pinon_a": a, "pinon_b": b})
        assert _vol(doc.scene[cid].shape & doc.scene[a].shape) > MIN_VOLUME_MM3
        assert "solapa" in CATALOG[ref].specs["no_publicado"]


def test_editar_la_variable_de_centros_mueve_la_cadena():
    doc = Document("variable")
    doc.execute("set_variable", {"name": "t", "expression": "95.25"})
    a, b = _par(doc, "PINON-ASA40-DS-Z15", pos_b={"x": "=t"})
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    antes = doc.scene[cid]
    x_antes, clave_antes = antes.shape.bounding_box().max.X, antes.mesh_key
    var = next(c["id"] for c in doc.commands if c["type"] == "set_variable")
    doc.edit(var, {"name": "t", "expression": "107.95"})
    f = doc.scene[cid]
    assert f.cut_length == pytest.approx(32 * 12.7)
    assert f.shape.bounding_box().max.X == pytest.approx(x_antes + 12.7, abs=0.05)
    assert f.mesh_key != clave_antes
    assert _vol(f.shape & doc.scene[b].shape) < MIN_VOLUME_MM3


def _caja(doc, **_kw):
    return doc.execute("create_box", {"width": 50, "depth": 50, "height": 50,
                                      "position": {"x": 200}})


@pytest.mark.parametrize("caso,montaje,params,mensaje", [
    ("asa_con_bs", {"ref_a": "PINON-08B-1-Z15"}, {}, "no son intercambiables"),
    ("ejes", {"rot_b": (0, 5, 0)}, {}, "no son paralelos"),
    ("plano", {"pos_b": {"x": 95.25, "z": 3.0}}, {}, r"mismo plano.*\+3\.00"),
    ("cerca", {"c": 60.0}, {}, "demasiado cerca"),
    ("doble_sobre_simple", {}, {"cadena": "CADENA-ASA40-2"}, "sólo sobre piñón dúplex"),
    ("doble_sobre_doble_simple", {"ref_a": "PINON-ASA40-DS-Z15"}, {"cadena": "CADENA-ASA40-2"},
     "sólo sobre piñón dúplex"),
    ("simple_sobre_duplex", {"ref_a": "PINON-ASA40-2-Z15"}, {}, "doble-simple"),
    ("hilera_2_en_simple", {}, {"hilera_b": 2}, "sólo tiene la hilera 1"),
    ("duplex_volteado", {"ref_a": "PINON-ASA40-2-Z15", "rot_b": (180, 0, 0)},
     {"cadena": "CADENA-ASA40-2"}, "volteado"),
    ("doble_en_hilera_2", {"ref_a": "PINON-ASA40-2-Z15"}, {"cadena": "CADENA-ASA40-2",
                                                          "hilera_a": 2}, "hilera_a es 1"),
    ("no_existe", {}, {"pinon_b": "nada"}, "No existe la pieza 'nada'"),
    ("misma_pieza", {}, {"pinon_b": "$a"}, "misma pieza"),
    ("no_es_pinon", {}, {"pinon_b": "$caja"}, "no es un piñón"),
])
def test_montajes_imposibles_se_rechazan_con_su_correccion(caso, montaje, params, mensaje):
    doc = Document(caso)
    a, b = _par(doc, **montaje)
    sust = {"$a": a, "$caja": _caja(doc) if "$caja" in params.values() else None}
    params = {k: sust.get(v, v) if isinstance(v, str) else v for k, v in params.items()}
    with pytest.raises(ERRORES, match=mensaje):
        doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, **params})


def test_cadena_desconocida_se_rechaza_al_entrar():
    doc = Document("ref")
    a, b = _par(doc)
    with pytest.raises(ERRORES, match="cadena desconocida"):
        doc.execute("create_chain", {"pinon_a": a, "pinon_b": b, "cadena": "PINON-ASA40-1-Z15"})


def test_lazo_1a1_z15_a_95_25_da_30_eslabones_sin_holgura():
    doc = Document("1a1")
    a, b = _par(doc, "PINON-ASA40-DS-Z15", c=95.25)
    cid = doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    t = medir_transmision(doc.scene, CreateChainParams(pinon_a=a, pinon_b=b))
    assert (t.eslabones, t.centros) == (30, pytest.approx(95.25))
    assert t.centros_exactos == pytest.approx(95.25, abs=1e-6)
    assert doc.scene[cid].cut_length == pytest.approx(381.0)


def test_mesh_key_compartido_entre_lazos_iguales():
    """Dos lazos con los mismos números (aunque uno vaya en la hilera 2 y en otro lugar) tienen
    la misma `mesh_key` y COMPARTEN la geometría construida (misma TShape de OCCT)."""
    doc = Document("instancias")
    a1, b1 = _par(doc, "PINON-ASA40-DS-Z15", rot_a=(90, 0, 10))
    a2, b2 = _par(doc, "PINON-ASA40-DS-Z15", rot_a=(90, 0, 10), pos_b={"x": 95.25, "y": 500})
    doc.execute("transform", {"feature": a2, "translate": {"y": 500}})
    c1 = doc.execute("create_chain", {"pinon_a": a1, "pinon_b": b1})
    c2 = doc.execute("create_chain", {"pinon_a": a2, "pinon_b": b2, "hilera_a": 2, "hilera_b": 2})
    f1, f2 = doc.scene[c1], doc.scene[c2]
    assert f1.mesh_key == f2.mesh_key and f1.mesh_key in DEFINITIONS
    assert f1.shape.wrapped.IsPartner(f2.shape.wrapped)
    assert f1.matrix != f2.matrix
    c3 = doc.execute("create_chain", {"pinon_a": a1, "pinon_b": b1, "hilera_a": 2,
                                      "hilera_b": 2, "detalle": "simple"})
    assert doc.scene[c3].mesh_key != f1.mesh_key


# ------------------------------------------------------------------ la regla
def test_regla_error_por_abrazamiento_menor_a_120():
    doc = Document("abrazamiento")
    a, b = _par(doc, "PINON-ASA40-1-Z15", "PINON-ASA40-1-Z60", c=170.0)
    doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    r = _regla(doc)
    assert r["estado"] == "error" and "abrazamiento" in r["detalle"]
    assert r["calc"]["norma"] and r["calc"]["titulo"].startswith("Transmisión por cadena")


def test_regla_aviso_por_pocos_dientes_y_sin_aviso_de_centros_en_1a1_corto():
    doc = Document("1a1")
    a, b = _par(doc, "PINON-ASA40-DS-Z15", c=95.25)
    doc.execute("create_chain", {"pinon_a": a, "pinon_b": b})
    r = _regla(doc)
    assert r["estado"] == "aviso" and "15 dientes" in r["detalle"]
    assert "pasos" not in r["detalle"]  # 7.5 p: el rodillo a rodillo va corto por diseño
    assert any("rpm_a" in m for m in r["no_aplica"])
    # el mismo 7.5 p en una reducción SÍ avisa
    regla = regla_cadena(["x"], cadena="CADENA-ASA40-1", serie="ASA 40", paso=12.7, hileras=1,
                         za=17, zb=19, centros=150.0, eslabones=42, centros_exactos=150.0)
    assert "fuera de 30–50 p" in regla["detalle"]


def _reduccion(ref_a, ref_b, c_aprox=508.0, **params):
    """A z_a → B z_b con los centros EXACTOS de un número par de eslabones (sin flecha)."""
    za, zb = CATALOG[ref_a].specs["z"], CATALOG[ref_b].specs["z"]
    _n, cx = eslabones_pares(CATALOG[ref_a].specs["paso"], za, zb, c_aprox)
    doc = Document("reduccion")
    a, b = _par(doc, ref_a, ref_b, c=math.floor(cx * 1000) / 1000)
    doc.execute("create_chain", {"pinon_a": a, "pinon_b": b,
                                 "cadena": CATALOG[ref_a].specs["cadena"], **params})
    return _regla(doc)


def test_regla_potencia_con_la_tabla_ok_y_excedida():
    ok = _reduccion("PINON-ASA40-1-Z17", "PINON-ASA40-1-Z30", potencia_kw=0.3, rpm_a=100)
    cap = 0.80 * 0.745699872  # z17 a 100 rpm (ACA), una hilera
    assert ok["estado"] == "ok" and ok["no_aplica"] == []
    assert ok["calc"]["fs"] == pytest.approx(cap / (0.3 * 1.3), abs=0.01)
    assert ok["calc"]["norma"].startswith("ASME B29.1 (tabla ACA)")
    mal = _reduccion("PINON-ASA40-1-Z17", "PINON-ASA40-1-Z30", potencia_kw=1.5, rpm_a=100)
    assert mal["estado"] == "error" and "capacidad" in mal["detalle"] and mal["calc"]["fs"] < 1


def test_regla_08b_usa_la_tabla_asa_como_sustituto_declarado():
    r = _reduccion("PINON-08B-1-Z17", "PINON-08B-1-Z30", potencia_kw=0.3, rpm_a=100)
    assert r["calc"]["fs"] is not None and "sustituto" in r["calc"]["norma"]


def test_regla_10b_y_rpm_fuera_de_tabla_no_aplica_sin_inventar_capacidad():
    r = _reduccion("PINON-10B-1-Z15", "PINON-10B-1-Z19", c_aprox=600.0, potencia_kw=1.0, rpm_a=100)
    assert r["calc"]["fs"] is None and any("10B" in m for m in r["no_aplica"])
    rapido = _reduccion("PINON-ASA40-1-Z17", "PINON-ASA40-1-Z30", potencia_kw=0.3, rpm_a=2000)
    assert rapido["calc"]["fs"] is None
    assert any("fuera de la tabla" in m for m in rapido["no_aplica"])
    assert rapido["estado"] == "aviso" and "m/s" in rapido["detalle"]  # 7.2 m/s: lubricación
    assert "7.20 m/s" in rapido["calc"]["resultado"]


def test_regla_pura_flecha_por_redondeo_y_eslabones_impares():
    flojo = regla_cadena(["x"], cadena="CADENA-ASA40-1", serie="ASA 40", paso=12.7, hileras=1,
                         za=17, zb=17, centros=100.0, eslabones=34, centros_exactos=108.0)
    assert flojo["estado"] == "aviso" and "flecha" in flojo["detalle"]
    impar = regla_cadena(["x"], cadena="CADENA-ASA40-1", serie="ASA 40", paso=12.7, hileras=1,
                         za=17, zb=17, centros=100.0, eslabones=33, centros_exactos=101.6)
    assert impar["estado"] == "error" and "impares" in impar["detalle"]


def test_lazos_iguales_salen_en_una_sola_regla():
    doc = Document("iguales")
    a1, b1 = _par(doc, "PINON-ASA40-DS-Z15")
    doc.execute("create_chain", {"name": "Lazo 1", "pinon_a": a1, "pinon_b": b1})
    doc.execute("create_chain", {"name": "Lazo 2", "pinon_a": a1, "pinon_b": b1,
                                 "hilera_a": 2, "hilera_b": 2})
    reglas = [r for r in chain_rules(doc) if r["regla"].startswith("transmisión por cadena")]
    assert len(reglas) == 1 and "Lazo 2" in reglas[0]["calc"]["entradas"]["lazos iguales"]


def test_aviso_si_un_pinon_se_mueve_despues_de_la_cadena():
    doc = Document("desfase")
    a, b = _par(doc, "PINON-ASA40-DS-Z15")
    doc.execute("create_chain", {"name": "Lazo", "pinon_a": a, "pinon_b": b})
    assert not any(r["regla"].startswith("cadena desfasada") for r in chain_rules(doc))
    doc.execute("transform", {"feature": b, "translate": {"x": 12.7}})
    assert _regla(doc, "cadena desfasada")["estado"] == "aviso"


def test_api_checks_muestra_la_regla_de_la_cadena():
    import apolo.api.main as api

    api.DOC = Document("checks-cadena")
    a, b = _par(api.DOC, "PINON-ASA40-1-Z17", "PINON-ASA40-1-Z30", c=400.0)
    api.DOC.execute("create_chain", {"pinon_a": a, "pinon_b": b, "potencia_kw": 0.3, "rpm_a": 100})
    data = TestClient(api.app).post("/api/checks", json={}).json()
    regla = next(r for r in data["estructura"] if r["regla"].startswith("transmisión por cadena"))
    assert regla["calc"]["fs"] is not None and "no_aplica" in regla


# ------------------------------------------------------------------ medición (D7, F2)
def test_medicion_30_lazos_eslabones_contra_simple():
    """El rodillo a rodillo: 31 piñones doble-simple Z15 a 95.25 mm y 30 lazos 1:1 alternando
    hilera 1 y 2. Mide el regenerate de los 30 lazos y su teselado (lo que hace `scene_payload`:
    la definición una vez + volumen y caja de cada pieza). Los números van a la bitácora del
    plan; aquí sólo cotas holgadas (la suite puede correr en paralelo con otra)."""
    from apolo.api import scene as sc

    doc = Document("medicion")
    pin = doc.execute("insert_component", {"component": "PINON-ASA40-DS-Z15",
                                           "rotation": {"x": 90}})
    pat = doc.execute("pattern_linear", {"feature": pin, "count": 31, "spacing": {"x": 95.25}})
    pins = [pin] + [f"{pat}_{i}" for i in range(1, 31)]
    tiempos = {}
    for detalle in ("eslabones", "simple"):
        for k in [k for k in DEFINITIONS if k.startswith("cadena|")]:
            DEFINITIONS.pop(k)
        sc._DEF_MESH_CACHE.clear()
        t0 = time.process_time()  # CPU del proceso: otro worker de la suite no infla la cuenta
        ids = doc.execute_many([{"type": "create_chain", "params": {
            "name": f"Lazo {i}", "pinon_a": pins[i], "pinon_b": pins[i + 1], "detalle": detalle,
            "hilera_a": 1 + i % 2, "hilera_b": 1 + i % 2}} for i in range(30)])
        t1 = time.process_time()
        for cid in ids:
            sc._definition_mesh(doc.scene[cid].mesh_key)
            sc._cached_render(doc.scene[cid].shape, want_mesh=False)
        tiempos[detalle] = (t1 - t0, time.process_time() - t1)
        assert len({doc.scene[cid].mesh_key for cid in ids}) == 1  # se construye y tesela UNA vez
        doc.undo()
    print("\n30 lazos (s de CPU: regenerate, teselado):", {k: tuple(round(x, 2) for x in v)
                                                         for k, v in tiempos.items()})
    # Lo que importa es el orden simple < eslabones y no un desastre. Con reloj de pared, la PC
    # cargada por otras suites midió 31 s (2026-10-21) y, si la carga cambiaba entre las dos
    # medidas, el orden podía invertirse: por eso CPU del proceso.
    assert sum(tiempos["simple"]) < sum(tiempos["eslabones"]) < 90.0
