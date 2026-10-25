"""V8.9 F7b: los defectos de código del AIRE que encontró la verificación por MCP (F7 § 5).

Cada test reproduce el defecto de la bitácora (rojo antes del arreglo) y fija el arreglo:
  1. la memoria y el panel tomaban el escenario de FALLA (una seta que corta la carrera a 134 mm)
     como el del tiempo de carrera del cilindro;
  2. `servicio.velocidad_m_s` no decía qué velocidad es (régimen, no el pico transitorio);
  7. una aserción no podía comparar `-QM2.posicion` (texto «14»): «== 14» y «== "14"» daban
     «comparación de tipos»;
  8. los aparatos de campo sin pieza 3D no avisaban;
 12. huecos del catálogo (racores, fotocelda réflex, regulador de caudal, silenciador,
     presostato y detector magnético), con lo que se prenden las reglas de escape y regulación.
"""

from __future__ import annotations

import pytest
from neumatica_escena import empujador

from apolo.library.neumatica.memoria import reglas as reglas_memoria
from apolo.services import neumatica as N
from apolo.services.electrico import modelo

PRODUCTO = {"t": 4, "tipo": "producto", "nombre": "caja", "dims_mm": [300, 200, 150], "masa_kg": 5}
FALLA = {"t": 7.4, "tipo": "falla", "dispositivo": "-K1", "falla": "salida_pegada"}


def _esc(eventos: list, cil: dict) -> dict:
    return {"escenario": {"eventos": eventos},
            "resultado": {"aire": {"cilindros": {"-MM1": cil}, "medicion": "muestras cada 20 ms"}}}


#: Las cifras medidas en la F7 sobre la copia de la 77 (bitácora § 2), carrera 800.
F7 = {
    "marcha": _esc([PRODUCTO], {"x_max_mm": 0.0, "v_max_m_s": 0.0022}),
    "desvio": _esc([PRODUCTO], {"x_max_mm": 800.384, "t_avance_s": 1.0529, "t_retroceso_s": 1.1031,
                                "v_max_m_s": 1.1526}),
    "desvio_lado": _esc([PRODUCTO], {"x_max_mm": 800.832, "t_avance_s": 1.0483, "t_retroceso_s": 1.1049,
                                     "v_max_m_s": 1.3111}),
    "seta_desvio": _esc([PRODUCTO, FALLA], {"x_max_mm": 134.034, "t_avance_s": 0.2943,
                                            "t_retroceso_s": 0.1474, "v_max_m_s": 1.4993}),
}


# ── 1. el escenario nominal para el tiempo, el peor para el impacto ───────────────────────────


def test_el_tiempo_sale_del_escenario_nominal_y_el_impacto_del_pico():
    """Antes: `cosim_vigente` elegía por cilindro el escenario con el mayor `v_max_m_s`, también
    uno de falla → «seta_desvio» (134 de 800 mm, 0,29/0,15 s). Ahora el tiempo es el del nominal
    (carrera completa, sano, el avance más lento: «desvio») y el pico, el de todos."""
    lec = N.lecturas(F7)["-MM1"]
    assert lec["escenario"] == "desvio"
    assert (lec["t_avance_s"], lec["t_retroceso_s"], lec["x_max_mm"]) == (1.0529, 1.1031, 800.384)
    assert lec["pico"] == {"v_max_m_s": 1.4993, "escenario": "seta_desvio"}


def test_sin_escenario_sano_completo_cae_al_de_falla_que_si_completa():
    solo_fallas = {"a": _esc([FALLA], {"x_max_mm": 200.0, "t_avance_s": 0.5, "v_max_m_s": 0.6}),
                   "b": _esc([FALLA], {"x_max_mm": 60.0, "t_avance_s": 0.1, "v_max_m_s": 0.9})}
    lec = N.lecturas(solo_fallas)["-MM1"]
    assert lec["escenario"] == "a" and lec["pico"]["escenario"] == "b"
    ruido = N.lecturas({"m": _esc([], {"x_max_mm": 0.0, "v_max_m_s": 0.002})})["-MM1"]
    assert "t_avance_s" not in ruido and ruido["pico"]["v_max_m_s"] == 0.002


@pytest.fixture(scope="module")
def empuja():
    d, _cid = empujador(servicio={"carrera_mm": 200, "velocidad_m_s": 0.5, "masa_kg": 2.0,
                                  "fuerza_N": 50, "ciclos_min": 20})
    return d


def test_la_memoria_no_dice_que_no_llega_por_una_seta(empuja):
    """La repro de la F7: con el escenario de la seta como el «más rápido», la memoria decía «pero
    llegó sólo a 134 de 800 mm» y el panel «no llega al final de su carrera»."""
    esc = {"ciclo": _esc([PRODUCTO], {"x_max_mm": 200.1, "t_avance_s": 0.12, "t_retroceso_s": 0.10,
                                      "v_max_m_s": 2.0}),
           "seta": _esc([PRODUCTO, FALLA], {"x_max_mm": 60.0, "t_avance_s": 0.05, "t_retroceso_s": 0.04,
                                            "v_max_m_s": 3.0})}
    c = N.analizar(modelo(empuja))
    filas = {r["regla"]: r for r in reglas_memoria(c, cosim=N.lecturas(esc))}
    t = filas["tiempo de carrera"]
    assert "llegó sólo" not in t["detalle"] and "«ciclo»" in t["detalle"]
    assert t["valor"]["medido"]["escenario"] == "ciclo"
    imp = filas["energía al fin de carrera"]
    assert imp["valor"]["v_m_s"] == 3.0 and any("«seta»" in h for h in imp["hipotesis"])


# ── 2. qué velocidad es `servicio.velocidad_m_s` ─────────────────────────────────────────────


def test_el_schema_dice_que_la_velocidad_es_la_de_regimen():
    from apolo.commands.models_neumatica import ServicioCilindro

    campo = ServicioCilindro.model_json_schema()["properties"]["velocidad_m_s"]
    assert "RÉGIMEN" in campo["description"] and "pico" in campo["description"]
    assert campo["title"] == "Velocidad de régimen"


# ── 8. los aparatos de campo sin pieza avisan ────────────────────────────────────────────────


def test_los_aparatos_de_campo_sin_pieza_avisan(empuja):
    """La repro de la F7 (r1): -B2, -AZ1, -QM1 y -QM2 sin `pieza` pasaban `electrical_check` y la
    puerta sin aviso: «pieza sin ligar» sólo mira refs que ya tienen una pieza en la escena. El
    cilindro (ligado), la red (suministro) y lo del tablero (+TAB1, riel o puerta) no avisan."""
    from apolo.services.electrico import CAMPO_SIN_PIEZA, chequeo

    ch = chequeo(empuja)
    filas = [r for r in ch["reglas"] if r["regla"] == CAMPO_SIN_PIEZA]
    assert sorted(r["elementos"][0] for r in filas) == ["-AZ1", "-B1", "-QM1", "-QM2"]
    assert all(r["estado"] == "aviso" and "insert_component" in r["recomendacion"] for r in filas)
    assert CAMPO_SIN_PIEZA not in {r["regla"] for r in ch["revisadas"]}


def test_ligado_o_sin_aparatos_de_campo_la_regla_sale_en_revisadas():
    from apolo.services.electrico import CAMPO_SIN_PIEZA, chequeo

    from apolo.doc.document import Document

    d = Document("tablero solo")
    d.execute_many([{"type": "add_device", "params": {"ref": "RED-3F-220V-60HZ", "designacion": "-G1"}},
                    {"type": "add_device", "params": {"ref": "ITM-C2-2P", "designacion": "-F1",
                                                      "ubicacion": "+TAB1"}}])
    ch = chequeo(d)
    assert CAMPO_SIN_PIEZA not in {r["regla"] for r in ch["reglas"]}
    assert CAMPO_SIN_PIEZA in {r["regla"] for r in ch["revisadas"]}


# ── 12. los huecos del catálogo ──────────────────────────────────────────────────────────────


def test_el_catalogo_trae_lo_que_faltaba_y_prende_las_reglas_de_la_f4():
    from apolo.library.catalog import CATALOG

    for ref, tipo in (("REG-CAUDAL-L-6", "regulador_caudal"), ("REG-CAUDAL-L-8", "regulador_caudal"),
                      ("SIL-G18", "silenciador"), ("SIL-G14", "silenciador"), ("SIL-G12", "silenciador")):
        assert CATALOG[ref].neumatico.tipo == tipo
    for ref in ("SENS-MAG-RANURA-PNP", "FOTO-M18-REFLEX"):
        e = CATALOG[ref].electrico
        assert (e.funcion, e.montaje, e.modelo["tipo"]) == ("B", "campo", "sensor")
    assert "REFLECTOR-50" in CATALOG and "RACOR-G18-6" in CATALOG
    assert {"silenciador", "regulador_caudal"} <= N.disponibles()


def test_con_silenciadores_y_reguladores_en_el_catalogo_el_erc_los_pide(empuja):
    """El empujador sin silenciadores ni reguladores: ahora las dos reglas de la F4 avisan."""
    reglas = N.reglas(modelo(empuja))
    sil = [r for r in reglas if r["regla"] == "escape sin silenciador" and r["estado"] == "aviso"]
    reg = [r for r in reglas if r["regla"] == "regulación de velocidad" and r["estado"] == "aviso"]
    assert sil and reg


def _filas(d) -> dict:
    from apolo.services.electrico import filas_bom

    return {f["ref"]: f for f in filas_bom(d)}


def test_la_bom_del_aire_compra_los_racores(empuja):
    """r1 de la F7: «la BOM del aire no sirve para comprar» (sin racores). Un racor recto macho por
    extremo de tubo en un puerto roscado: FRL G1/4 → corte G1/4 → válvula G1/8 en PU-8, válvula
    G1/8 → cilindro G1/8 en PU-6."""
    f = _filas(empuja)
    assert (f["RACOR-G14-8"]["cantidad"], f["RACOR-G18-8"]["cantidad"], f["RACOR-G18-6"]["cantidad"]) == (3, 1, 4)


def test_un_silenciador_roscado_no_compra_tubo_ni_racor():
    d, _cid = empujador()
    antes = _filas(d)
    d.execute_many([{"type": "add_device", "params": {"ref": "SIL-G18", "designacion": "-RZ1"}},
                    {"type": "add_tubo", "params": {"desde": "-QM2:3", "hasta": "-RZ1:1", "ref": "TUBO-PU-6"}}])
    f = _filas(d)
    assert f["SIL-G18"]["cantidad"] == 1
    assert f["TUBO-PU-6"] == antes["TUBO-PU-6"] and f["RACOR-G18-6"] == antes["RACOR-G18-6"]
    sil = [r for r in N.reglas(modelo(d)) if r["regla"] == "escape sin silenciador" and r["estado"] != "ok"]
    assert "-QM2:3" not in {r["elementos"][0] for r in sil}


# ── 7. una aserción compara la posición de una válvula (texto) ───────────────────────────────


def _res_valvula() -> dict:
    return {"trazas": {"discretas": {"-QM2.posicion": [[0.0, "12"], [1.0, "14"], [2.5, "12"]]}},
            "final": {"-QM2.posicion": "12"}, "resumen": {"duracion_s": 3.0}}


@pytest.mark.parametrize("txt", ["-QM2.posicion == 14 en 1,5 s", '-QM2.posicion == "14" en 1,5 s',
                                 "-QM2.posicion == «14» en 1,5 s", "-QM2.posicion != 14 al_final"])
def test_la_posicion_de_la_valvula_se_compara_con_su_texto(txt):
    """Antes: `_valor` quitaba las comillas y leía «14» como número, y el veredicto respondía
    «comparación de tipos» (la sugerencia de `veredicto.py` proponía justo «== 14»)."""
    from apolo.cosim.aserciones import leer_aserciones
    from apolo.cosim.tipos import revisar
    from apolo.cosim.veredicto import evaluar

    a = leer_aserciones([txt], 3.0)
    fila = evaluar(a, _res_valvula())["aserciones"][0]
    assert fila["pasa"], fila["detalle"]
    assert revisar(a, {"-QM2.posicion": "12"}) == ([], [])


def test_un_orden_contra_un_texto_sigue_siendo_error():
    from apolo.cosim.aserciones import leer_aserciones
    from apolo.cosim.veredicto import evaluar

    fila = evaluar(leer_aserciones(["-QM2.posicion > 12 en 1,5 s"], 3.0), _res_valvula())["aserciones"][0]
    assert not fila["pasa"] and "comparación de tipos" in fila["detalle"]
