"""F3c de puerta-sin-sobrediseno: lo que dieron una mezcladora, un tanque con agitador y un elevador
modelados por MCP (bitácora del plan, § F3c). Modelos mínimos, verde y rojo por punto:

1. la unión atornillada DECLARADA sin agujeros (`union.agujeros`);
2. el espárrago soldado, evaluado con su tuerca (acceso, agarre, retención y largo);
3. el factor de servicio fuera de un transportador, con el servicio declarado;
4. la flecha sin vigas: NO_APLICA, no SIN_EVALUAR;
5. el objetivo de enganche dentro de una holgura funcional ≤ 4 mm;
6. lo eléctrico no es «pieza agregada» candidata a sobrante."""

from __future__ import annotations

from pathlib import Path

import pytest

from apolo.doc import Document
from apolo.library.acceso_herramienta import tool_access_report
from apolo.library.calidad.agarre import evaluar_perno
from apolo.library.calidad.agujeros import compatible, controlar_agujeros, juzgar
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.catalog import CATALOG
from apolo.library.engineering.servicio import fs_requerido
from apolo.library.esparrago import es_esparrago
from apolo.library.lints import es_nombre_de_tornilleria
from apolo.library.requisitos import normalizar_requisitos
from apolo.services.calidad_agujeros import insumos_agujeros
from apolo.services.calidad_mecanica import items_funcion_mecanica
from apolo.services.calidad_pernos import insumos_pernos

TESTIGOS = Path(__file__).resolve().parent / "data" / "testigos"


def _caja(d, nombre, w, dp, h, x=0.0, y=0.0, z=0.0) -> str:
    return d.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                    "position": {"x": x, "y": y, "z": z}})


def _taladro(d, fid, x, z, diam=11.0, y=0.0):
    d.execute("drill_hole", {"feature": fid, "position": {"x": x, "y": y, "z": z}, "axis": "-z",
                             "diameter": diam})


def _item(items, iid):
    return next(i for i in items if i.id == iid)


# ------------------------------------------------------------------ 1. agujeros
def test_compatible_va_de_la_broca_de_machuelo_al_paso_holgado():
    assert compatible(8.5, 10) and compatible(11.0, 10) and compatible(18.0, 10)
    assert not compatible(7.0, 10) and not compatible(42.0, 10)
    assert compatible(14.0, None) and not compatible(2.0, None)


def test_con_punta_roscada_basta_que_una_pieza_tenga_el_agujero():
    u = {"union": "u", "tipo": "fasten", "d": 18.0, "pide": 1, "basta_una": True,
         "piezas": [{"fid": "a", "nombre": "Sensor", "juzgada": True, "agujeros": 0},
                    {"fid": "b", "nombre": "Manguito", "juzgada": True, "agujeros": 1}]}
    assert juzgar(u)[0] == OK
    assert juzgar({**u, "basta_una": False})[0] == FALLA
    assert juzgar({**u, "piezas": [{"fid": "a", "juzgada": False}]}) is None


def _dos_placas(qty=2, nota_anclaje=""):
    d = Document("dos placas")
    base = _caja(d, "Placa base", 300, 200, 12, z=6)
    placa = _caja(d, "Placa de montaje", 120, 80, 10, z=17)
    d.execute("ground", {"name": "g0", "feature": base, "nota": nota_anclaje})
    d.execute("fasten", {"name": "f_placa", "a": placa, "b": base, "kind": "perno",
                         "size": "M10", "qty": qty})
    return d, base, placa


def test_union_declarada_sin_agujeros_falla_nombrando_la_union_y_la_pieza():
    d, base, placa = _dos_placas()
    (it,) = [i for i in controlar_agujeros(insumos_agujeros(d)) if i.id == "agujeros.union"]
    assert it.estado == FALLA and "f_placa" in it.detalle and "Placa de montaje" in it.detalle
    assert set(it.piezas) == {base, placa}
    for f, z in ((placa, 22), (base, 12)):
        _taladro(d, f, -40, z)
    it = _item(controlar_agujeros(insumos_agujeros(d)), "agujeros.union")
    assert it.estado == FALLA and "tiene 1" in it.detalle  # declara 2 pernos, hay un agujero
    for f, z in ((placa, 22), (base, 12)):
        _taladro(d, f, 40, z)
    assert _item(controlar_agujeros(insumos_agujeros(d)), "agujeros.union").estado == OK


def test_join_bolted_taladra_y_pasa():
    d = Document.from_apolo_bytes((TESTIGOS / "mensula_atornillada.apolo").read_bytes())
    ins = insumos_agujeros(d)
    assert [u["tipo"] for u in ins] == ["fasten"]
    assert _item(controlar_agujeros(ins), "agujeros.union").estado == OK


def test_el_anclaje_con_pernos_declarados_pide_sus_taladros():
    d, base, placa = _dos_placas(nota_anclaje="4 pernos de anclaje de expansión M12x100 al piso")
    it = _item(controlar_agujeros(insumos_agujeros(d)), "agujeros.anclaje")
    assert it.estado == FALLA and "Placa base" in it.detalle and "declara 4" in it.detalle
    for x in (-130, 130):
        for y in (-80, 80):
            _taladro(d, base, x, 12, diam=14, y=y)
    assert _item(controlar_agujeros(insumos_agujeros(d)), "agujeros.anclaje").estado == OK
    d, _b, _p = _dos_placas(nota_anclaje="apoya en el piso nivelado")
    assert _item(controlar_agujeros(insumos_agujeros(d)), "agujeros.anclaje").estado == NO_APLICA


def test_no_se_juzga_la_base_soldada_de_un_esparrago_ni_lo_de_compra_ni_sin_perno():
    d = Document("base del espárrago")
    base = _caja(d, "Puente", 200, 200, 10, z=5)  # el espárrago va soldado ENCIMA: no lo cruza
    esp = d.execute("create_cylinder", {"name": "Espárrago soldado (M10x30, ISO 13918)",
                                        "radius": 5, "height": 30, "position": {"z": 25}})
    sop = _caja(d, "Soporte de rodamiento (compra)", 60, 60, 12, z=16)
    d.execute("fasten", {"name": "f_base", "a": base, "b": esp, "kind": "perno", "size": "M10"})
    d.execute("fasten", {"name": "f_sop", "a": sop, "b": esp, "kind": "perno", "size": "M10"})
    d.execute("fasten", {"name": "f_cierre", "a": sop, "b": base, "kind": "perno", "size": "M8",
                         "nota": "cierre de palanca, sin perno suelto"})
    ins = {u["union"]: u for u in insumos_agujeros(d)}
    assert "f_cierre" not in ins
    motivos = {p["fid"]: p.get("motivo", "") for u in ins.values() for p in u["piezas"]}
    assert "base" in motivos[base] and "compra" in motivos[sop]
    assert _item(controlar_agujeros(list(ins.values())), "agujeros.union").estado == NO_APLICA


def test_las_uniones_internas_de_una_plantilla_no_llegan():
    d = Document.from_apolo_bytes((TESTIGOS / "faja.apolo").read_bytes())
    tipo = {c["id"]: c["type"] for c in d.commands}
    internas = {f["name"] for f in d.fasteners.values() if f.get("kind", "perno") == "perno"
                and tipo.get(f.get("command_id")) not in ("fasten", "join_bolted")}
    assert internas  # la plantilla atornilla sus guardas
    assert not internas & {u["union"] for u in insumos_agujeros(d)}


# ------------------------------------------------------------------ 2. espárragos
@pytest.mark.parametrize("nombre, es", [
    ("Espárrago soldado puente-tapa 1 (M10x30 A2, ISO 13918)", True),
    ("Varilla roscada M12 del tensor", True),
    ("Tope elástico de poliuretano izq Ø60x40 con espárrago M10 (compra)", False),
    ("Perno de amarre superior cadena 1 izq M8x60 DIN 931 8.8", False),
])
def test_el_esparrago_se_reconoce_por_su_rol_anclado(nombre, es):
    assert es_esparrago(nombre) is es


def test_lo_que_trae_su_esparrago_no_es_tornilleria():
    assert not es_nombre_de_tornilleria("Tope elástico de poliuretano izq Ø60x40 con espárrago "
                                        "M10 (compra)")
    assert es_nombre_de_tornilleria("Espárrago soldado puente-tapa 1 (M10x30 A2, ISO 13918)")


def _puente_con_esparrago(alto_esparrago=30.0, nombre="Espárrago soldado puente-tapa (M10x30, "
                                                       "ISO 13918)"):
    d = Document("espárrago")
    _caja(d, "Tapa del tanque", 200, 200, 10, z=5)
    puente = _caja(d, "Puente del agitador", 100, 100, 12, z=16)
    _taladro(d, puente, 0, 22)
    esp = d.execute("create_cylinder", {"name": nombre, "radius": 5, "height": alto_esparrago,
                                        "position": {"z": 10 + alto_esparrago / 2}})
    d.execute("insert_component", {"component": "TUERCA-M10", "position": {"z": 26}})
    return d, esp


def test_el_esparrago_soldado_se_evalua_con_su_tuerca():
    d, esp = _puente_con_esparrago()
    (p,) = [x for x in insumos_pernos(d) if x["fid"] == esp]
    assert p["evaluable"] and p["cabeza"] == "esparrago" and p["largo"] == pytest.approx(30, abs=0.1)
    r = evaluar_perno(p)
    assert r["cruza"][0] == OK and r["retencion"][0] == OK and r["largo"][0] == OK
    assert "ISO 13918" in r["largo"][1]
    acc = tool_access_report(d.scene, catalog=CATALOG)
    assert acc["esparragos"] == 1 and not acc["no_evaluados"] and acc["evaluados"] == 1


def test_el_esparrago_corto_no_deja_hilo_fuera_de_la_tuerca():
    d, esp = _puente_con_esparrago(alto_esparrago=21.0)
    (p,) = [x for x in insumos_pernos(d) if x["fid"] == esp]
    r = evaluar_perno(p)
    assert r["retencion"][0] == FALLA and r["largo"][0] == FALLA  # 21 mm: fuera de la serie


def test_un_perno_sin_cabeza_modelada_lo_dice():
    d, esp = _puente_con_esparrago(nombre="Perno M10x30 DIN 933 (cabeza sobre la tapa)")
    (p,) = [x for x in insumos_pernos(d) if x["fid"] == esp]
    assert not p["evaluable"] and "sin cabeza modelada" in p["motivo"]


# ------------------------------------------------------------------ 3. factor de servicio
def test_el_fs_que_pide_el_servicio_sale_de_la_tabla_de_agma():
    assert fs_requerido(None, None)[0] == 1.25
    assert fs_requerido("uniforme", 8)[0] == 1.0 and fs_requerido("moderada", 8)[0] == 1.25
    assert fs_requerido("pesada", 24)[0] == 2.0
    fs, texto = fs_requerido("uniforme", 2)
    assert fs == 1.0 and "mínimo 1,0" in texto  # la tabla da 0,8: nunca menos que el nominal


def test_los_requisitos_del_servicio_se_validan():
    r = normalizar_requisitos({"tipo_carga": "Moderado", "horas_dia": "16",
                               "potencia_absorbida_kw": "0,105", "par_salida_nm": 40})
    assert r == {"tipo_carga": "moderada", "horas_dia": 16.0, "potencia_absorbida_kw": 0.105,
                 "par_salida_nm": 40.0}
    with pytest.raises(ValueError, match="uniforme"):
        normalizar_requisitos({"tipo_carga": "variable"})
    with pytest.raises(ValueError, match="≤ 24"):
        normalizar_requisitos({"horas_dia": 30})


def _agitador(req: dict) -> Document:
    d = Document("agitador")
    _caja(d, "Puente", 300, 200, 12, z=6)
    d.execute("insert_component", {"component": "NMRV-050", "position": {"z": 200}})
    d.set_requirements(req)
    return d


def _fs(d):
    return _item(items_funcion_mecanica(d), "vida.factor_servicio")


def test_factor_de_servicio_de_un_agitador_con_lo_declarado():
    it = _fs(_agitador({}))
    assert it.estado == SIN_EVALUAR and "potencia_absorbida_kw" in str(it.evidencia)
    it = _fs(_agitador({"potencia_absorbida_kw": 0.105}))  # 0,55·0,75/0,105 = 3,93
    assert it.estado == OK and it.evidencia["valores"][0]["factor_servicio"] == pytest.approx(3.93)
    it = _fs(_agitador({"potencia_absorbida_kw": 0.3, "tipo_carga": "pesada", "horas_dia": 24}))
    assert it.estado == FALLA and it.evidencia["valores"][0]["pide"] == 2.0  # 1,375 < 2
    it = _fs(_agitador({"par_salida_nm": 60, "rpm_salida": 50}))  # 9550·0,55·0,75/50 = 78,8 N·m
    assert it.estado == OK and it.evidencia["valores"][0]["factor_servicio"] == pytest.approx(1.31)


# ------------------------------------------------------------------ 4. la flecha sin vigas
def test_un_perfil_que_no_trabaja_como_viga_no_es_una_viga():
    from apolo.services.puerta_hechos import _vigas

    d = Document("riel suelto")
    d.execute("insert_component", {"component": "TUBO-2X2", "length": 800,
                                   "rotation": {"y": 90}, "position": {"z": 300}})
    assert _vigas(d) == {"perfil": 0, "bastidor_faja": 0}
    d = Document.from_apolo_bytes((TESTIGOS / "mensula_atornillada.apolo").read_bytes())
    assert _vigas(d)["perfil"] == 0


# ------------------------------------------------------------------ 5. holgura funcional
def test_un_objetivo_de_enganche_en_una_rendija_de_2_mm_no_se_sondea():
    from build123d import Box, Pos

    from apolo.library.seguridad.peligros import resultado_peligro
    from apolo.services.calidad_sondas import Trazador, fuera_de_holguras, holgura

    tr = Trazador({"caja": [Pos(0, 0, 0) * Box(10, 10, 10)],
                   "aro": [Pos(12, 0, 0) * Box(10, 10, 10)],
                   "lejos": [Pos(30, 0, 0) * Box(10, 10, 10)]})
    ancho, entre = holgura(tr, (6.0, 0.0, 0.0))
    assert ancho == pytest.approx(2.0, abs=0.05) and set(entre) == {"caja", "aro"}
    assert holgura(tr, (21.0, 0.0, 0.0)) is None  # 8 mm entre el aro y lo lejos: entra el dedo
    assert holgura(tr, (0.0, 0.0, 0.0)) is None   # dentro de un sólido: no es una rendija
    p = fuera_de_holguras(tr, {"tipo": "enganche", "objetivos": [(6.0, 0.0, 0.0)]})
    assert p["objetivos"] == [] and p["en_holgura"][0]["ancho_mm"] == pytest.approx(2.0, abs=0.05)
    assert resultado_peligro({**p, "id": "x"}, [], 0.0)["estado"] == OK
    cuna = fuera_de_holguras(tr, {"tipo": "atrapamiento", "objetivos": [(6.0, 0.0, 0.0)]})
    assert cuna["objetivos"] == [(6.0, 0.0, 0.0)]  # una cuña se abre hacia afuera: su peligro


# ------------------------------------------------------------------ 6. lo eléctrico no se agrega
def test_lo_del_tablero_y_los_dispositivos_no_son_piezas_agregadas():
    from tablero_electrico import arranque_directo

    from apolo.services.calidad_sobrantes import del_carril

    d = Document("con tablero")
    motor = d.execute("insert_component", {"component": "MOTOR-075", "position": {"z": 200}})
    d.execute_many(arranque_directo(pieza_motor=motor)
                   + [{"type": "layout_tablero", "params": {"ubicacion": "TAB1",
                                                            "position": {"x": 800, "z": 1200}}}])
    guarda = _caja(d, "Guarda del acople", 100, 100, 3, z=400)
    carril = del_carril(d)
    tablero = {f for f, x in d.scene.items()
               if d.commands[[c["id"] for c in d.commands].index(x.command_id.split("_")[0])][
                   "type"] == "layout_tablero"}
    assert tablero and tablero <= carril and motor in carril and guarda not in carril


# ------------------------------------------------------------------ 7–9. el costo de la puerta
def test_la_geometria_de_masa_se_mide_una_vez_por_corrida(monkeypatch):
    from apolo.library.engineering import mass as M

    d = Document("masas")
    fid = _caja(d, "Bloque", 100, 50, 20, z=10)
    sin_memo = M.feature_mass(d.scene[fid])
    llamadas = []
    real = M._shape_com
    monkeypatch.setattr(M, "_shape_com", lambda s: llamadas.append(s) or real(s))
    with M.memo_de_geometria():
        a = M.feature_mass(d.scene[fid])
        b = M.feature_mass(d.scene[fid], default_material="aluminio")  # otro material: otra masa
        M.scene_mass_properties(d.scene)
    assert len(llamadas) == 1 and a == sin_memo and b["masa_kg"] != a["masa_kg"]
    M.feature_mass(d.scene[fid])  # fuera del `with`, sin memo
    assert len(llamadas) == 2


def test_get_job_de_la_puerta_llega_resumido_como_la_tool():
    from apolo.tools.calidad import de_job

    r = {"aprobado": False, "version_registro": "10", "conteos": {}, "por_familia": {},
         "items": [{"id": "a", "estado": "FALLA", "evidencia": {"mucho": "x" * 1000}},
                   {"id": "b", "estado": "OK", "evidencia": {}}]}
    corto = de_job(r, "diff")
    assert [p["id"] for p in corto["pendientes"]] == ["a"] and "items" not in corto
    assert de_job(r, "full") == r and de_job({"features": []}, "diff") is None
