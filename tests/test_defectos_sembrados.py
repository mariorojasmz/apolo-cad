"""Defectos SEMBRADOS en la puerta de publicación (plan puerta-de-publicacion, D9 y D14): sobre un
testigo BUENO de `tests/data/testigos/` (que aprueba entero: `test_testigos.py`), una mutación
mínima de modelo —un perno corto, un tensor sin carrera, una guarda soldada…— y la puerta debe
atraparla en SU ítem general. Cada id general del registro tiene ≥ 1 defecto o una exención
escrita con su porqué: agregar un ítem sin su defecto pone roja la suite (8D: cada defecto nuevo de
producción suma aquí su testigo malo antes de corregirse).

Presupuesto: cada defecto corre `reunir` + `evaluar` sobre SU modelo mutado, con la gravedad dada
por estable y sin la marcha (lo caro; la gravedad real sólo en su propio defecto). La faja se
carga del `.apolo` por defecto (≈ 0,9 s) y su puerta tarda ≈ 1,8 s; la ménsula, ≈ 0,3 s."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient
from tablero_electrico import arranque_directo

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.calidad.item import FALLA, OK
from apolo.library.calidad.registro import REGISTRO, Entrada, Fuente, evaluar
from apolo.services import escenarios as E
from apolo.services import puerta_publicacion as pp
from apolo.services.calidad_tensores import poner_tensores

TESTIGOS = Path(__file__).resolve().parent / "data" / "testigos"

#: Ítems generales SIN defecto sembrado, cada uno con su porqué.
EXENTOS = {
    "entrega.no_evaluado": (
        "cada `no_aplica` que da hoy la puerta de entrega está justificado POR CONSTRUCCIÓN "
        "(sujeción con < 5 sólidos, poses sin estudios o sin poses: el mismo dato que el hecho; "
        "gravedad y acceso tienen ítem propio): ningún modelo lo dispara. Vigila que un chequeo "
        "NUEVO de la entrega que no corre no pase como verde; su caso puro: test_puerta_"
        "publicacion::test_lo_que_la_entrega_no_evaluo_se_justifica_o_bloquea"),
    "publicado.sustitutos_fieles": (
        "la cinta animada se DERIVA de la sección del sólido de la banda (D13 de la fábrica) y "
        "sólo se autodetecta la banda de create_belt_conveyor, de lazo convexo: ninguna mutación "
        "de un modelo la hace infiel sin falsear el código. Su defecto sembrado vive en "
        "test_ruta_faja_modelo (la faja en Ω con la regla vieja atraviesa la guarda y la fábrica "
        "no la acepta) y su traducción a FALLA en test_puerta_publicacion::"
        "test_memoria_marcha_erc_y_escenarios"),
}


def _base(nombre: str) -> Document:
    return Document.from_apolo_bytes((TESTIGOS / f"{nombre}.apolo").read_bytes())


def _id(doc, nombre: str) -> str:
    return next(fid for fid, f in doc.scene.items() if f.name == nombre)


def _caja(doc, nombre, w, dp, h, x, y, z) -> str:
    return doc.execute("create_box", {"name": nombre, "width": w, "depth": dp, "height": h,
                                      "position": {"x": x, "y": y, "z": z}})


def _editar_faja(doc, **cambios) -> None:
    (cmd,) = [c for c in doc.commands if c["type"] == "create_belt_conveyor"]
    doc.edit(cmd["id"], {**cmd["params"], **cambios})


# ------------------------------------------------------------------ mutaciones de la ménsula
def escombro(d):  # un bloque olvidado que entra en la placa base
    _caja(d, "Escombro", 40, 40, 40, 120, 60, 10)


def tapa_suelta(d):  # una pieza sin camino de carga: cae con la gravedad
    _caja(d, "Tapa suelta", 100, 100, 5, 0, 0, 200)


def cabeza_encajonada(d):  # cuatro paredes a 1 mm de la cabeza: la llave no entra
    bb = d.scene[_id(d, "Perno M10×35 DIN 933")].shape.bounding_box()
    cx, cy, top = (bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, 22.0
    for k, (dx, dy, w, dp) in enumerate(((-11, 0, 4, 30), (11, 0, 4, 30),
                                         (0, -11, 30, 4), (0, 11, 30, 4))):
        _caja(d, f"Pared ({k})", w, dp, 40, cx + dx, cy + dy, top + 20)


def perno_por_una_aleta(d):  # el defecto del tensor publicado: cruza un ala de la C, no la otra
    d.execute("create_sheet_metal", {"name": "Soporte en C", "ancho": 100, "fondo": 100,
                                     "espesor": 3, "lados": ["frente", "atras"],
                                     "altura_pestana": 50, "position": {"x": 400, "y": 0, "z": 12}})
    _caja(d, "Eje roscado", 40, 50, 30, 400, 5, 37)
    d.execute("insert_component", {"component": "PERNO-HEX-M10", "rotation": {"x": -90},
                                   "position": {"x": 400, "y": 50, "z": 37}})


def perno_corto(d):  # M10×50 a mano por 46 mm de chapa: la tuerca no tiene hilo
    _caja(d, "Placa A", 120, 80, 36, 400, 0, 18)
    _caja(d, "Placa B", 120, 80, 10, 400, 0, 41)
    d.execute("insert_component", {"component": "PERNO-HEX-M10", "position": {"x": 400, "z": 46}})
    d.execute("insert_component", {"component": "TUERCA-M10", "position": {"x": 400, "z": -4}})


def perno_a_medida(d):  # un perno M10×47 modelado a mano: ese largo no se compra
    _caja(d, "Placa A", 120, 80, 20, 400, 0, 10)
    _caja(d, "Placa B", 120, 80, 10, 400, 0, 25)
    r = 16 / math.sqrt(3)
    hexa = [[r * math.cos(math.radians(60 * k)), r * math.sin(math.radians(60 * k))]
            for k in range(6)]
    cab = d.execute("create_extrude_poly", {"name": "Cabeza", "points": hexa, "height": 6.4,
                                            "position": {"x": 400, "y": 0, "z": 33.2}})
    vas = d.execute("create_cylinder", {"name": "Perno M10×47 a medida", "radius": 5,
                                        "height": 47, "position": {"x": 400, "y": 0, "z": 6.5}})
    d.execute("boolean_op", {"name": "Perno M10×47 a medida", "operation": "union",
                             "target": vas, "tools": [cab]})
    d.execute("insert_component", {"component": "TUERCA-M10", "position": {"x": 400, "z": -4}})


def pata_esbelta(d):  # 8 × 8 mm y 1,5 m: pandea con su propio peso y el de la máquina
    p = _caja(d, "Pata esbelta", 8, 8, 1500, 0, 90, 762)
    d.execute("ground", {"name": "gp", "feature": p})


def contrapeso_en_voladizo(d):  # 212 kg atornillados fuera de la huella de apoyo
    c = _caja(d, "Contrapeso", 300, 300, 300, 600, 0, 150)
    d.execute("fasten", {"name": "fc", "a": c, "b": _id(d, "Placa base"), "kind": "perno",
                         "size": "M10", "qty": 4})


def bloque_en_un_m6(d):  # casi 2 t colgando de un solo M6
    c = _caja(d, "Bloque colgado", 1000, 500, 500, 0, 400, 300)
    d.execute("fasten", {"name": "fb", "a": c, "b": _id(d, "Placa base"), "kind": "perno",
                         "size": "M6", "qty": 1})


def cordon_minimo(d):  # 212 kg en un cordón de a = 1 mm y 10 mm de largo
    c = _caja(d, "Bloque soldado", 300, 300, 300, 0, 260, 150)
    d.execute("fasten", {"name": "fs", "a": c, "b": _id(d, "Placa base"), "kind": "soldadura",
                         "throat_mm": 1, "length_mm": 10})


def perno_sin_metrica(d):  # una unión apernada declarada sin métrica: no se puede verificar
    t = _caja(d, "Tapa", 100, 100, 5, 0, 0, 24.5)
    d.execute("fasten", {"name": "ft", "a": t, "b": _id(d, "Ménsula"), "kind": "perno"})


def superficie_sin_espesor(d):  # geometría de construcción que quedó en el modelo
    pts = [[200, 0, 0], [300, 0, 0], [300, 100, 0], [200, 100, 0]]
    d.execute("boundary_surface", {"name": "Chapa sin espesor", "curves": [
        {"points": [a, b]} for a, b in zip(pts, pts[1:] + pts[:1])]})


def cadena_subdimensionada(d):  # ASA 40 simple con 3 kW a 60 rpm
    a, b = (d.execute("insert_component", {"component": "PINON-ASA40-1-Z15", "rotation": {"x": 90},
                                           "position": {"x": x, "y": 300, "z": 600}})
            for x in (0, 400))
    d.execute("create_chain", {"name": "Cadena", "pinon_a": a, "pinon_b": b,
                               "potencia_kw": 3.0, "rpm_a": 60})


def motor_sin_tierra(d):  # el tablero de arranque directo sin el PE del motor
    d.execute_many([c for c in arranque_directo()
                    if c["params"].get("puntos") != ["-X0:2", "-M1:PE"]])


def escenario_que_falla(d):  # su último run, vigente, no llegó a las rpm
    esc = {"duracion_s": 2, "aserciones": ["-M1.rpm >= 1700 dentro_de 1 s desde pulsar -S1"],
           "acciones": [{"t": 0.3, "accion": "pulsar", "dispositivo": "-S1",
                         "actuador": "marcha", "durante_s": 0.2}]}
    E.poner(d, "arranque", esc)
    filas = [{"asercion": esc["aserciones"][0], "pasa": False, "detalle": "llegó a 0 rpm"}]
    E.guardar_resultado(d, "arranque", E.resultado_compacto(
        {"veredicto": "falla", "aserciones": filas}, {"resumen": {}},
        firma=E.firma_documento(d), hash_esc=E.hash_escenario(esc), simulacion=None))


# ------------------------------------------------------------------ mutaciones de la faja
def motor_movido(d):  # el motorreductor corrido 100 mm: choca dentro de la plantilla
    d.execute("transform", {"feature": _id(d, "Faja de banda · Motorreductor"),
                            "translate": {"x": 0, "y": -100, "z": 0}})


def tensor_sin_carrera(d):  # sin la UCT y un tensor declarado de 20 mm (pide ~104)
    _editar_faja(d, tensor="ninguno")
    poner_tensores(d, [{"piezas": [_id(d, "Faja de banda · Tambor de cola")], "carrera_mm": 20,
                        "eje": "x"}])


def carga_de_300_kg(d):  # el encargo pide 300 kg: rodamientos, motor y memoria no dan
    d.set_requirements({**d.requirements, "carga_kg": 300})


def largueros_de_madera(d):  # el bastidor en madera: flecha fuera de L/240
    for i in (1, 2):
        d.set_material(_id(d, f"Faja de banda · Larguero ({i})"), "madera")


def guarda_soldada(d):
    d.execute("fasten", {"name": "guarda_soldada", "a": _id(d, "Faja de banda · Guarda lateral (1)"),
                         "b": _id(d, "Faja de banda · Larguero (1)"), "kind": "soldadura",
                         "throat_mm": 3, "length_mm": 100})


def chumacera_soldada(d):
    d.execute("fasten", {"name": "chumacera_soldada",
                         "a": _id(d, "Faja de banda · Chumacera motriz (−Y)"),
                         "b": _id(d, "Faja de banda · Placa porta-chumacera motriz (−Y)"),
                         "kind": "soldadura", "throat_mm": 3, "length_mm": 100})


def travesano_en_el_lazo(d):  # un travesaño soldado a los dos largueros DENTRO del lazo
    b = _caja(d, "Travesaño interior", 40, 772, 40, 0, 0, 840)
    for k in (1, 2):
        d.execute("fasten", {"name": f"s{k}", "a": b, "b": _id(d, f"Faja de banda · Larguero ({k})"),
                             "kind": "soldadura", "throat_mm": 4, "length_mm": 80})


def sin_guardas(d):
    _editar_faja(d, guardas=False)


def sin_cierres(d):
    """La v5 de create_belt_conveyor sin sus cierres = la v4 TAL CUAL (F6): sin la guarda inferior
    bajo la ranura banda ↔ larguero (35 mm, abierta por abajo entre las guardas de los tambores),
    sin las placas de cierre de los largueros y con el techo de cola sólo sobre el tambor. Por ahí
    el brazo entra al lazo y baja la mano a las cuñas: sólo se ve doblándolo."""
    assert any(f.name.endswith("Guarda inferior (1, tramo 1)") for f in d.scene.values()), \
        "el testigo faja ya no trae sus cierres (create_belt_conveyor v5)"
    _editar_faja(d, cierres=False)


def resguardo_sin_declarar(d):  # D15: nadie dijo por qué las guardas son así
    d.funciones = [f for f in d.funciones if f["funcion"] != "resguardo"]


@dataclass(frozen=True)
class Defecto:
    nombre: str
    base: str
    mutar: Callable
    atrapa: dict
    gravedad_real: bool = False


DEFECTOS = (
    Defecto("escombro", "mensula_atornillada", escombro, {"entrega.semaforo": FALLA}),
    Defecto("tapa_suelta", "mensula_atornillada", tapa_suelta, {"entrega.gravedad": FALLA},
            gravedad_real=True),
    Defecto("cabeza_encajonada", "mensula_atornillada", cabeza_encajonada,
            {"union.acceso_herramienta": FALLA}),
    Defecto("perno_por_una_aleta", "mensula_atornillada", perno_por_una_aleta,
            {"union.agarre": FALLA}),
    Defecto("perno_corto", "mensula_atornillada", perno_corto, {"union.retencion": FALLA}),
    Defecto("perno_a_medida", "mensula_atornillada", perno_a_medida,
            {"union.largo_comercial": FALLA}),
    Defecto("pata_esbelta", "mensula_atornillada", pata_esbelta, {"estructura.pandeo": FALLA}),
    Defecto("contrapeso_en_voladizo", "mensula_atornillada", contrapeso_en_voladizo,
            {"estructura.vuelco": FALLA}),
    Defecto("bloque_en_un_m6", "mensula_atornillada", bloque_en_un_m6,
            {"union.capacidad": FALLA}),
    Defecto("cordon_minimo", "mensula_atornillada", cordon_minimo, {"union.soldaduras": FALLA}),
    Defecto("perno_sin_metrica", "mensula_atornillada", perno_sin_metrica,
            {"union.dimensionadas": FALLA}),
    Defecto("superficie_sin_espesor", "mensula", superficie_sin_espesor,
            {"fabricabilidad": FALLA}),
    Defecto("cadena_subdimensionada", "mensula", cadena_subdimensionada,
            {"transmision.capacidad": FALLA}),
    Defecto("motor_sin_tierra", "mensula", motor_sin_tierra, {"riesgos.electrico": FALLA}),
    Defecto("escenario_que_falla", "mensula", escenario_que_falla,
            {"funcion.escenarios": FALLA}),
    Defecto("motor_movido", "faja", motor_movido, {"montaje.interferencia_interna": FALLA}),
    Defecto("tensor_sin_carrera", "faja", tensor_sin_carrera,
            {"transmision_flexible.tension": FALLA}),
    Defecto("carga_de_300_kg", "faja", carga_de_300_kg,
            {"elementos_rodantes.l10": FALLA, "accionamiento.factor_servicio": FALLA,
             "ingenieria.reglas": FALLA, "memoria.veredicto": FALLA}),
    Defecto("largueros_de_madera", "faja", largueros_de_madera,
            {"estructura.flecha": FALLA, "memoria.veredicto": FALLA}),
    Defecto("guarda_soldada", "faja", guarda_soldada,
            {"riesgos.resguardos_desmontables_con_herramienta": FALLA}),
    Defecto("chumacera_soldada", "faja", chumacera_soldada, {"consumibles.reemplazables": FALLA}),
    Defecto("travesano_en_el_lazo", "faja", travesano_en_el_lazo,
            {"consumibles.reemplazables": FALLA}),
    Defecto("sin_guardas", "faja", sin_guardas, {"riesgos.partes_moviles": FALLA}),
    Defecto("sin_cierres", "faja", sin_cierres, {"riesgos.partes_moviles": FALLA}),
    Defecto("resguardo_sin_declarar", "faja", resguardo_sin_declarar,
            {"diseno.soluciones_por_funcion": FALLA}),
)


def generales() -> set[str]:
    """Los ids GENERALES del registro: las entradas y las claves del mapa de cada fuente."""
    out = set()
    for e in REGISTRO:
        out |= set(e.mapa) if isinstance(e, Fuente) else {e.id} if isinstance(e, Entrada) else set()
    return out


def _puerta(doc, gravedad_real: bool) -> dict:
    if gravedad_real:  # el endpoint entero: la gravedad de MuJoCo (sin banda no hay marcha)
        api.DOC = doc
        r = TestClient(api.app).post("/api/puerta-publicacion")
        assert r.status_code == 200, r.text
        return r.json()
    ins = pp.reunir(doc, expand=lambda x: x, gravedad={
        "resultado": {"fell": [], "estables": list(doc.scene), "n_grounded": len(doc.grounds)},
        "motivo": ""})
    ins["marcha"] = {"resultado": "sin_marcha", "detalle": "no se corre en los defectos"}
    return evaluar(ins)


# ------------------------------------------------------------------ cobertura
def test_cada_item_general_tiene_su_defecto_o_su_exencion():
    gen = generales()
    atrapados = {iid for d in DEFECTOS for iid in d.atrapa}
    assert atrapados <= gen, f"defectos con ids que el registro no tiene: {atrapados - gen}"
    assert set(EXENTOS) <= gen, f"exenciones de ids que ya no existen: {set(EXENTOS) - gen}"
    assert not atrapados & set(EXENTOS), "un ítem exento que ya tiene defecto: quita la exención"
    faltan = gen - atrapados - set(EXENTOS)
    assert not faltan, ("ítem(s) del registro sin defecto sembrado ni exención: "
                        f"{sorted(faltan)}. Suma su testigo malo a DEFECTOS (D9)")
    assert len({d.nombre for d in DEFECTOS}) == len(DEFECTOS)
    assert {d.base for d in DEFECTOS} <= {p.stem for p in TESTIGOS.glob("*.apolo")}


# ------------------------------------------------------------------ cada defecto, atrapado
@pytest.mark.parametrize("defecto", DEFECTOS, ids=lambda d: d.nombre)
def test_la_puerta_atrapa_el_defecto_sembrado(defecto):
    doc = _base(defecto.base)
    defecto.mutar(doc)
    r = _puerta(doc, defecto.gravedad_real)
    it = {i["id"]: i for i in r["items"]}
    obtenido = {iid: it[iid]["estado"] for iid in defecto.atrapa}
    assert obtenido == defecto.atrapa, {iid: it[iid]["detalle"] for iid in defecto.atrapa}
    assert r["aprobado"] is False


# ------------------------------------------------------------------ el bug que destapó el testigo
def test_la_tornilleria_asentada_no_cae_en_la_gravedad_de_las_puertas():
    """La ménsula con `join_bolted` caía en la gravedad de las puertas: el casco CONVEXO del
    perno no cabe en su barreno y MuJoCo lo expulsaba (38 mm). Las puertas la tratan asentada,
    como su sujeción declarada; la simulación de siempre (`gravity_test`) no cambia."""
    from apolo.physics.stability import stability_test
    from apolo.services.delivery_inputs import exclusiones_declaradas

    d = _base("mensula_atornillada")
    args = (d.scene, d.joints, d.mates, d.fasteners, d.grounds)
    pernos = exclusiones_declaradas(d)[1]
    assert len(pernos) == 4
    crudo = stability_test(*args, seconds=0.5)
    assert {c["id"] for c in crudo["fell"]} & pernos  # el casco no cabe: lo expulsa
    assert stability_test(*args, seconds=0.5, asentadas=pernos)["fell"] == []
    api.DOC = d
    rep = TestClient(api.app).post("/api/delivery-check", json={"con_gravedad": True}).json()
    assert rep["veredicto"] == "VERDE", rep


# ------------------------------------------------------------------ el hueco de las rectas (F6)
def test_las_rectas_no_ven_la_ranura_junto_a_la_banda():
    """8D del defecto de producción de la F6 (la cuña retorno ↔ desvío de la faja de motor
    central, a 60 mm de una ranura de 36 mm junto al borde de la banda): con sólo las sondas
    RECTAS, la v4 sin cierres sale resguardada —el hueco—; con el brazo doblado (ISO 13857 tabla 6)
    fallan las cuñas de los dos tambores, y sólo por las sondas dobladas."""
    from apolo.services.calidad_seguridad import controles_seguridad

    d = _base("faja")
    sin_cierres(d)
    rectas = controles_seguridad(d, electrico=False, brazo_doblado=False)["items"][0]
    assert rectas["estado"] == OK, rectas["detalle"]
    it = controles_seguridad(d, electrico=False)["items"][0]
    assert it["estado"] == FALLA
    malos = [p for p in it["evidencia"]["peligros"] if p["estado"] == FALLA]
    assert len(malos) == 2 and all(p["id"].startswith("atrapamiento:") for p in malos)
    assert all(p["n_brazo_doblado"] == p["n_alcanzan"] > 0 for p in malos)
    f = malos[0]["fallas"][0]
    assert f["via"] == "brazo doblado" and f["distancia_mm"] <= 850 and len(f["codo"]) == 3
    assert "con el brazo doblado" in it["detalle"]
